"""Resolve once, validate every address, connect to the selected numeric address."""

import asyncio
import ipaddress
import socket
from .schemas import MonitorInput
from ..config import get_settings


class PolicyError(Exception):
    pass


class Policy:
    def __init__(self, networks=None):
        raw = get_settings().allowed_networks if networks is None else networks
        try:
            self.networks = [
                ipaddress.ip_network(x.strip(), strict=True)
                for x in raw.split(",")
                if x.strip()
            ]
        except ValueError:
            raise PolicyError("Nieprawidłowa lista dozwolonych podsieci.") from None

    def validate(self, address):
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise PolicyError("Nieprawidłowy adres celu.") from None
        # Never expose metadata/link-local, multicast, unspecified or mapped IPv6 routes.
        if (
            ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or getattr(ip, "ipv4_mapped", None)
            or getattr(ip, "sixtofour", None)
            or getattr(ip, "teredo", None)
        ):
            raise PolicyError("Ten adres nie może być monitorowany.")
        if str(ip) in {
            "168.63.129.16",
            "100.100.100.200",
            "192.0.0.192",
            "fd00:ec2::254",
        }:
            raise PolicyError("Adres usług metadanych jest niedozwolony.")
        if not any(ip in network for network in self.networks):
            raise PolicyError("Cel nie należy do dozwolonej podsieci.")
        return str(ip)

    async def resolve(self, host, port):
        if "%" in host:
            raise PolicyError("Adresy ze strefą interfejsu są niedozwolone.")
        try:
            return [self.validate(host)]
        except PolicyError:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise
        results = await asyncio.get_running_loop().getaddrinfo(
            host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
        addresses = list(dict.fromkeys(row[4][0] for row in results))
        if not addresses:
            raise PolicyError("DNS nie zwrócił adresu.")
        return [self.validate(address) for address in addresses]


async def validate_target(payload: MonitorInput):
    from urllib.parse import urlsplit

    if payload.kind == "heartbeat":
        return
    config = payload.config
    if payload.kind in {"http", "http_json"}:
        u = urlsplit(config.url)
        host = u.hostname
        port = u.port or (443 if u.scheme == "https" else 80)
    else:
        host, port = config.host, config.port
    async with asyncio.timeout(payload.timeout):
        await Policy().resolve(host, port)
