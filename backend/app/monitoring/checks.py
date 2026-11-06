"""Bounded protocol checks; response bodies and raw exceptions are never persisted."""

import asyncio
import base64
import contextlib
import json
import os
import socket
import ssl
import struct
import time
from dataclasses import dataclass
from urllib.parse import urljoin
import httpcore
import httpx
import dns.asyncquery
import dns.flags
import dns.message
from .policy import Policy, PolicyError
from .vault import VaultError

MAX_BODY = 1024 * 1024


@dataclass(frozen=True)
class Outcome:
    status: str
    duration_ms: float
    message: str


class CheckFailure(Exception):
    pass


class Stream(httpcore.AsyncNetworkStream):
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer

    async def read(self, max_bytes, timeout=None):
        return await asyncio.wait_for(self.reader.read(max_bytes), timeout)

    async def write(self, buffer, timeout=None):
        self.writer.write(buffer)
        await asyncio.wait_for(self.writer.drain(), timeout)

    async def aclose(self):
        self.writer.close()
        with contextlib.suppress(OSError, TimeoutError, ssl.SSLError):
            await asyncio.wait_for(self.writer.wait_closed(), 1)

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        await self.writer.start_tls(
            ssl_context, server_hostname=server_hostname, ssl_handshake_timeout=timeout
        )
        return self

    def get_extra_info(self, info):
        return self.writer.get_extra_info(info)


class PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, policy):
        self.policy = policy

    async def connect_tcp(
        self, host, port, timeout=None, local_address=None, socket_options=None
    ):
        addresses = await self.policy.resolve(host, port)
        last_error = None
        for address in addresses:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(address, port, limit=16384), timeout
                )
                return Stream(reader, writer)
            except OSError as exc:
                last_error = exc
        raise last_error or OSError("connection failed")

    async def connect_unix_socket(self, *args, **kwargs):
        raise PolicyError("Gniazda lokalne są niedozwolone.")

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


async def http_check(config, credentials, policy, kind):
    url = httpx.URL(config["url"])
    original_origin = (url.scheme, url.host, url.port)
    method, body, auth_allowed = (
        config["method"],
        credentials.get("body", "").encode(),
        True,
    )
    async with httpcore.AsyncConnectionPool(
        network_backend=PinnedBackend(policy),
        ssl_context=ssl.create_default_context(),
        max_connections=1,
        max_keepalive_connections=0,
    ) as pool:
        for hop in range(6):
            headers = {"User-Agent": "MONIVEX/0.2", "Accept-Encoding": "identity"}
            if auth_allowed:
                headers.update(credentials.get("headers", {}))
                if credentials.get("bearer"):
                    headers["Authorization"] = "Bearer " + credentials["bearer"]
                elif credentials.get("username") or credentials.get("password"):
                    value = (
                        credentials.get("username", "")
                        + ":"
                        + credentials.get("password", "")
                    ).encode()
                    headers["Authorization"] = (
                        "Basic " + base64.b64encode(value).decode()
                    )
            request = httpx.Request(
                method, url, headers=headers, content=body if auth_allowed else b""
            )
            async with pool.stream(
                request.method,
                str(url),
                headers=request.headers.raw,
                content=request.content,
            ) as response:
                if (
                    response.status in {301, 302, 303, 307, 308}
                    and config["follow_redirects"]
                ):
                    location = next(
                        (
                            v.decode("latin1")
                            for k, v in response.headers
                            if k.lower() == b"location"
                        ),
                        None,
                    )
                    if not location or hop == 5:
                        raise CheckFailure(
                            "Nieprawidłowe przekierowanie lub przekroczony limit."
                        )
                    destination = httpx.URL(urljoin(str(url), location))
                    if (
                        destination.scheme not in {"http", "https"}
                        or destination.userinfo
                        or destination.fragment
                    ):
                        raise PolicyError("Niedozwolone przekierowanie.")
                    if url.scheme == "https" and destination.scheme != "https":
                        raise PolicyError("Przekierowanie obniża bezpieczeństwo TLS.")
                    auth_allowed = (
                        auth_allowed
                        and (destination.scheme, destination.host, destination.port)
                        == original_origin
                    )
                    if response.status == 303 or (
                        response.status in {301, 302} and method == "POST"
                    ):
                        method, body = "GET", b""
                    url = destination
                    continue
                if response.status not in config["expected_codes"]:
                    raise CheckFailure("Nieoczekiwany kod odpowiedzi HTTP.")
                if not config["contains"] and kind != "http_json":
                    return "UP", "Odpowiedź HTTP jest prawidłowa."
                data = bytearray()
                async for chunk in response.aiter_stream():
                    if len(data) + len(chunk) > MAX_BODY:
                        raise CheckFailure("Odpowiedź przekracza limit 1 MiB.")
                    data.extend(chunk)
                if config["contains"] and config["contains"] not in data.decode(
                    "utf-8", errors="replace"
                ):
                    raise CheckFailure("Brak oczekiwanego fragmentu treści.")
                if kind == "http_json":
                    try:
                        value = json.loads(data)
                        for key in config["json_path"]:
                            if isinstance(key, int) and isinstance(value, list):
                                value = value[key]
                            elif isinstance(key, str) and isinstance(value, dict):
                                value = value[key]
                            else:
                                raise KeyError()
                        expected = config["expected_value"]
                        if type(value) is not type(expected) or value != expected:
                            raise KeyError()
                    except (
                        ValueError,
                        KeyError,
                        IndexError,
                        TypeError,
                        RecursionError,
                    ):
                        raise CheckFailure(
                            "Wartość pola JSON nie spełnia warunku."
                        ) from None
                return "UP", "Warunki odpowiedzi HTTP są spełnione."
    raise CheckFailure("Przekroczony limit przekierowań.")


async def smtp_reply(stream, expected):
    for _ in range(50):
        line = await stream.reader.readline()
        if not line or len(line) > 4096 or line[:3] != str(expected).encode():
            raise CheckFailure("Nieprawidłowa odpowiedź SMTP.")
        if line[3:4] == b" ":
            return
        if line[3:4] != b"-":
            break
    raise CheckFailure("Nieprawidłowa wielowierszowa odpowiedź SMTP.")


async def smtp_check(stream, config):
    await smtp_reply(stream, 220)
    await stream.write(b"EHLO monivex.invalid\r\n")
    await smtp_reply(stream, 250)
    if config["starttls"]:
        await stream.write(b"STARTTLS\r\n")
        await smtp_reply(stream, 220)
        await stream.start_tls(ssl.create_default_context(), config["host"])
        await stream.write(b"EHLO monivex.invalid\r\n")
        await smtp_reply(stream, 250)
    await stream.write(b"QUIT\r\n")
    return "UP", "Banner i EHLO SMTP są prawidłowe."


async def dns_check(config, policy, timeout):
    addresses = await policy.resolve(config["host"], config["port"])
    query = dns.message.make_query(config["domain"], config["record_type"])
    response = await dns.asyncquery.udp(
        query, addresses[0], port=config["port"], timeout=timeout
    )
    if response.flags & dns.flags.TC:
        response = await dns.asyncquery.tcp(
            query, addresses[0], port=config["port"], timeout=timeout
        )
    if response.rcode() != 0:
        raise CheckFailure("Serwer DNS zwrócił błąd.")
    answers = [
        item.to_text()
        for rrset in response.answer
        if rrset.rdtype == query.question[0].rdtype
        for item in rrset
    ]
    if not answers or (
        config["expected_answer"] and config["expected_answer"] not in answers
    ):
        raise CheckFailure("Brak oczekiwanej odpowiedzi DNS.")
    return "UP", "Odpowiedź DNS jest prawidłowa."


def checksum(data):
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack("!" + "H" * (len(data) // 2), data))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return (~total) & 0xFFFF


async def icmp_check(config, policy):
    address = (await policy.resolve(config["host"], 0))[0]
    version6 = ":" in address
    protocol = socket.IPPROTO_ICMPV6 if version6 else socket.IPPROTO_ICMP
    payload = os.urandom(24)
    header = struct.pack("!BBHHH", 128 if version6 else 8, 0, 0, 0, 1)
    packet = header + payload
    if not version6:
        packet = struct.pack("!BBHHH", 8, 0, checksum(packet), 0, 1) + payload
    with socket.socket(
        socket.AF_INET6 if version6 else socket.AF_INET, socket.SOCK_DGRAM, protocol
    ) as sock:
        sock.setblocking(False)
        loop = asyncio.get_running_loop()
        await loop.sock_connect(sock, (address, 0))
        await loop.sock_sendall(sock, packet)
        while True:
            reply = await loop.sock_recv(sock, 4096)
            if (
                len(reply) >= 32
                and reply[0] == (129 if version6 else 0)
                and reply[8:] == payload
            ):
                return "UP", "Otrzymano odpowiedź ICMP."


async def run_check(
    kind,
    config,
    credentials=None,
    *,
    timeout=5,
    policy=None,
    heartbeat_at=None,
    created_at=None,
    interval=60,
):
    start = time.monotonic()
    try:
        async with asyncio.timeout(timeout):
            policy = policy or Policy()
            if kind == "heartbeat":
                last = heartbeat_at if heartbeat_at is not None else created_at
                if (
                    last is None
                    or time.time() - last > interval + config["grace_seconds"]
                ):
                    raise CheckFailure("Nie otrzymano heartbeat w wymaganym czasie.")
                status, message = (
                    ("UP", "Heartbeat jest aktualny.")
                    if heartbeat_at
                    else ("UNKNOWN", "Oczekiwanie na pierwszy heartbeat.")
                )
            elif kind in {"http", "http_json"}:
                status, message = await http_check(
                    config, credentials or {}, policy, kind
                )
            elif kind == "dns":
                status, message = await dns_check(config, policy, timeout)
            elif kind == "icmp":
                status, message = await icmp_check(config, policy)
            else:
                stream = await PinnedBackend(policy).connect_tcp(
                    config["host"], config["port"], timeout
                )
                try:
                    if kind == "tcp":
                        status, message = "UP", "Połączenie TCP jest dostępne."
                    elif kind == "smtp":
                        status, message = await smtp_check(stream, config)
                    elif kind == "tls":
                        await stream.start_tls(
                            ssl.create_default_context(), config["host"], timeout
                        )
                        certificate = stream.get_extra_info("ssl_object").getpeercert()
                        remaining = (
                            ssl.cert_time_to_seconds(certificate["notAfter"])
                            - time.time()
                        )
                        status = (
                            "DEGRADED"
                            if remaining <= config["expiry_warning_days"] * 86400
                            else "UP"
                        )
                        message = (
                            "Certyfikat wkrótce wygaśnie."
                            if status == "DEGRADED"
                            else "Certyfikat TLS jest prawidłowy."
                        )
                    else:
                        raise CheckFailure("Nieobsługiwany typ kontroli.")
                finally:
                    await stream.aclose()
            elapsed = (time.monotonic() - start) * 1000
            if (
                status == "UP"
                and config["warning_ms"]
                and elapsed > config["warning_ms"]
            ):
                status, message = "DEGRADED", "Przekroczony próg czasu odpowiedzi."
            return Outcome(status, round(elapsed, 2), message)
    except (PolicyError, VaultError) as exc:
        status, message = "UNKNOWN", str(exc)
    except PermissionError:
        status, message = "UNKNOWN", "Brak uprawnień systemowych do wykonania kontroli."
    except TimeoutError:
        status, message = "DOWN", "Przekroczono czas kontroli."
    except CheckFailure as exc:
        status, message = "DOWN", str(exc)
    except (ssl.SSLError, httpcore.ConnectError):
        status, message = "DOWN", "Błąd połączenia lub weryfikacji TLS."
    except (
        OSError,
        httpcore.NetworkError,
        httpcore.ProtocolError,
        dns.exception.DNSException,
    ):
        status, message = "DOWN", "Brak prawidłowej odpowiedzi usługi."
    except (ValueError, TypeError, KeyError):
        status, message = "UNKNOWN", "Nieprawidłowa konfiguracja kontroli."
    return Outcome(status, round((time.monotonic() - start) * 1000, 2), message)
