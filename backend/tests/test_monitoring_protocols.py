import asyncio
import contextlib
import ipaddress
import ssl
from datetime import datetime, timedelta, timezone
import dns.flags
import dns.message
import dns.rrset
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from app.monitoring.checks import run_check
from app.monitoring.policy import Policy, PolicyError
from app.monitoring.schemas import CheckConfig, MonitorInput


def config(**values):
    return CheckConfig(**values).model_dump()


def check(kind, c, **kw):
    return run_check(kind, c, policy=Policy("127.0.0.0/8"), **kw)


@contextlib.asynccontextmanager
async def server(handler, tls=None):
    service = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=tls)
    try:
        yield service.sockets[0].getsockname()[1]
    finally:
        service.close()
        await service.wait_closed()


async def close(writer):
    writer.close()
    with contextlib.suppress(ConnectionError, ssl.SSLError):
        await writer.wait_closed()


async def request(reader):
    head = await reader.readuntil(b"\r\n\r\n")
    size = next(
        (
            int(line.split(b":", 1)[1])
            for line in head.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        ),
        0,
    )
    return head, await reader.readexactly(size)


@pytest.mark.parametrize(
    "network,address",
    [
        ("", "127.0.0.1"),
        ("0.0.0.0/0", "169.254.169.254"),
        ("::/0", "::ffff:127.0.0.1"),
        ("0.0.0.0/0", "224.0.0.1"),
        ("0.0.0.0/0", "0.0.0.0"),
        ("0.0.0.0/0", "168.63.129.16"),
        ("::/0", "fd00:ec2::254"),
    ],
)
def test_special_addresses(network, address):
    with pytest.raises(PolicyError):
        Policy(network).validate(address)


def test_explicit_lan():
    assert Policy("10.0.0.0/8").validate("10.23.45.67") == "10.23.45.67"
    with pytest.raises(PolicyError):
        Policy("10.0.0.0/8").validate("192.168.1.1")
    with pytest.raises(PolicyError):
        Policy("invalid")


def test_mixed_dns_answer(monkeypatch):
    async def scenario():
        async def lookup(*a, **kw):
            return [
                (2, 1, 6, "", ("127.0.0.1", 80)),
                (2, 1, 6, "", ("169.254.169.254", 80)),
            ]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
        with pytest.raises(PolicyError):
            await Policy("127.0.0.0/8").resolve("monitor.invalid", 80)

    asyncio.run(scenario())


def test_tcp_http_json_and_dns_pinning(monkeypatch):
    async def scenario():
        received = []

        async def handler(reader, writer):
            try:
                head, body = await request(reader)
                received.append((head, body))
                data = b'{"service":{"ok":true}}'
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Length: "
                    + str(len(data)).encode()
                    + b"\r\n\r\n"
                    + data
                )
                await writer.drain()
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                await close(writer)

        async with server(handler) as port:
            assert (
                await check("tcp", config(host="127.0.0.1", port=port))
            ).status == "UP"
            calls = []

            async def lookup(host, *a, **kw):
                calls.append(host)
                return [
                    (
                        2,
                        1,
                        6,
                        "",
                        ("127.0.0.1" if len(calls) == 1 else "169.254.169.254", port),
                    )
                ]

            monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
            result = await check(
                "http_json",
                config(
                    url=f"http://monitor.invalid:{port}",
                    json_path=["service", "ok"],
                    expected_value=True,
                ),
                credentials={"bearer": "test-secret"},
            )
            assert result.status == "UP"
            assert calls == ["monitor.invalid"]
            assert b"Host: monitor.invalid:" in received[-1][0]
            assert b"Bearer test-secret" in received[-1][0]
            assert "test-secret" not in result.message

    asyncio.run(scenario())


def test_redirect_policy_and_cross_origin_credentials():
    async def scenario():
        received = []

        async def dest(reader, writer):
            received.append(await request(reader))
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            await writer.drain()
            await close(writer)

        async with server(dest) as other:

            async def redirect(reader, writer):
                await request(reader)
                writer.write(
                    f"HTTP/1.1 307 Temporary Redirect\r\nLocation: http://127.0.0.1:{other}/\r\nContent-Length: 0\r\n\r\n".encode()
                )
                await writer.drain()
                await close(writer)

            async with server(redirect) as port:
                result = await check(
                    "http",
                    config(
                        url=f"http://127.0.0.1:{port}",
                        method="POST",
                        follow_redirects=True,
                    ),
                    credentials={
                        "bearer": "secret",
                        "headers": {"X-Private": "secret"},
                        "body": "secret",
                    },
                )
                assert result.status == "UP"
                assert b"secret" not in received[0][0] + received[0][1]

        async def unsafe(reader, writer):
            await request(reader)
            writer.write(
                b"HTTP/1.1 302 Found\r\nLocation: http://169.254.169.254/\r\nContent-Length: 0\r\n\r\n"
            )
            await writer.drain()
            await close(writer)

        async with server(unsafe) as port:
            assert (
                await check(
                    "http",
                    config(url=f"http://127.0.0.1:{port}", follow_redirects=True),
                )
            ).status == "UNKNOWN"

    asyncio.run(scenario())


def test_timeout_conditions_and_body_bound():
    async def scenario():
        async def handler(reader, writer):
            try:
                head, _ = await request(reader)
                if b"/slow " in head:
                    await asyncio.sleep(0.2)
                data = b"x" * (1024 * 1024 + 1) if b"/big " in head else b"plain"
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Length: "
                    + str(len(data)).encode()
                    + b"\r\n\r\n"
                    + data
                )
                await writer.drain()
            except ConnectionError:
                pass
            finally:
                await close(writer)

        async with server(handler) as port:
            url = f"http://127.0.0.1:{port}"
            for path, options in [
                ("/", {"contains": "missing"}),
                ("/big", {"contains": "x"}),
                ("/", {"expected_codes": [201]}),
            ]:
                assert (
                    await check("http", config(url=url + path, **options))
                ).status == "DOWN"
            assert (
                await check("http", config(url=url + "/slow"), timeout=0.03)
            ).status == "DOWN"
            assert (
                await check("http", config(url=url + "/slow", warning_ms=1))
            ).status == "DEGRADED"
            assert (await check("http_json", config(url=url))).status == "DOWN"

    asyncio.run(scenario())


def tls_context(tmp_path, monkeypatch, wrong=False, expired=False):
    now = datetime.now(timezone.utc)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    leaf = ec.generate_private_key(ec.SECP256R1())
    san = (
        [x509.DNSName("wrong.invalid")]
        if wrong
        else [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(name)
        .public_key(leaf.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(
            now - timedelta(hours=1) if expired else now + timedelta(days=2)
        )
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )
    ca_path = tmp_path / "ca.pem"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    monkeypatch.setenv("SSL_CERT_FILE", str(ca_path))
    cert_path = tmp_path / "cert.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path = tmp_path / "key.pem"
    key_path.write_bytes(
        leaf.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    return context


@pytest.mark.parametrize(
    "wrong,expired,expected",
    [(False, False, "DEGRADED"), (True, False, "DOWN"), (False, True, "DOWN")],
)
def test_tls_validity_name_expiry(tmp_path, monkeypatch, wrong, expired, expected):
    tls = tls_context(tmp_path, monkeypatch, wrong, expired)

    async def scenario():
        async def handler(reader, writer):
            await close(writer)

        async with server(handler, tls) as port:
            assert (
                await check("tls", config(host="127.0.0.1", port=port))
            ).status == expected

    asyncio.run(scenario())


def test_https_smtp_starttls(tmp_path, monkeypatch):
    tls = tls_context(tmp_path, monkeypatch)

    seen = []
    tls.set_servername_callback(lambda sslobj, name, context: seen.append(name))

    async def scenario():
        async def lookup(host, *args, **kwargs):
            return [(2, 1, 6, "", ("127.0.0.1", args[0]))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)

        async def http(reader, writer):
            await request(reader)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            await writer.drain()
            await close(writer)

        async with server(http, tls) as port:
            assert (
                await check("http", config(url=f"https://localhost:{port}/"))
            ).status == "UP"
        assert "localhost" in seen
        commands = []

        async def smtp(reader, writer):
            writer.write(b"220 test SMTP\r\n")
            await writer.drain()
            while line := await reader.readline():
                commands.append(line)
                if line.startswith(b"EHLO"):
                    writer.write(b"250-test\r\n250 STARTTLS\r\n")
                elif line.startswith(b"STARTTLS"):
                    writer.write(b"220 Ready\r\n")
                    await writer.drain()
                    await writer.start_tls(tls)
                    continue
                elif line.startswith(b"QUIT"):
                    break
                else:
                    raise AssertionError("Unexpected command")
                await writer.drain()
            await close(writer)

        async with server(smtp) as port:
            for starttls in [False, True]:
                assert (
                    await check(
                        "smtp", config(host="127.0.0.1", port=port, starttls=starttls)
                    )
                ).status == "UP"
        assert any(x.startswith(b"STARTTLS") for x in commands)
        assert not any(x.startswith((b"MAIL", b"RCPT", b"DATA")) for x in commands)

    asyncio.run(scenario())


def test_dns_udp_tcp_fallback():
    async def scenario():
        def answer(data):
            response = dns.message.make_response(dns.message.from_wire(data))
            response.answer.append(
                dns.rrset.from_text("service.invalid.", 60, "IN", "A", "198.51.100.7")
            )
            return response.to_wire()

        async def tcp(reader, writer):
            size = int.from_bytes(await reader.readexactly(2), "big")
            data = answer(await reader.readexactly(size))
            writer.write(len(data).to_bytes(2, "big") + data)
            await writer.drain()
            await close(writer)

        async with server(tcp) as port:

            class DNS(asyncio.DatagramProtocol):
                truncated = False

                def connection_made(self, t):
                    self.transport = t

                def datagram_received(self, data, address):
                    if self.truncated:
                        r = dns.message.make_response(dns.message.from_wire(data))
                        r.flags |= dns.flags.TC
                        data = r.to_wire()
                    else:
                        data = answer(data)
                    self.transport.sendto(data, address)

            proto = DNS()
            transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
                lambda: proto, local_addr=("127.0.0.1", port)
            )
            try:
                c = config(
                    host="127.0.0.1",
                    port=port,
                    domain="service.invalid",
                    expected_answer="198.51.100.7",
                )
                assert (await check("dns", c)).status == "UP"
                proto.truncated = True
                assert (await check("dns", c)).status == "UP"
                c["expected_answer"] = "198.51.100.8"
                assert (await check("dns", c)).status == "DOWN"
            finally:
                transport.close()

    asyncio.run(scenario())


def test_icmp_loopback():
    result = asyncio.run(check("icmp", config(host="127.0.0.1"), timeout=2))
    if result.status == "UNKNOWN" and "uprawnień" in result.message:
        pytest.skip("Runtime nie udostępnia unprivileged ICMP")
    assert result.status == "UP"


@pytest.mark.parametrize(
    "values",
    [
        {"kind": "http", "config": {"url": "file:///etc/passwd"}},
        {"kind": "http", "config": {"url": "http://user:pass@example.org"}},
        {"kind": "tcp", "config": {"host": "host;command"}},
        {
            "kind": "http",
            "config": {"url": "http://example.org"},
            "secrets": {"headers": {"Host": "bad"}},
        },
        {
            "kind": "http",
            "config": {"url": "http://example.org"},
            "secrets": {"bearer": "a\r\nb"},
        },
    ],
)
def test_injection_validation(values):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MonitorInput(name="test", **values)
