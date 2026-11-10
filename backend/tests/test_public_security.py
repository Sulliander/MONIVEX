import pytest
from starlette.requests import Request
from app.config import get_settings
from app.security import client_ip, validate_public_settings


def request(peer, headers):
    return Request(
        {
            "type": "http",
            "client": (peer, 1234),
            "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        }
    )


def test_proxy_address_cannot_be_spoofed(monkeypatch):
    monkeypatch.setenv("MONIVEX_TRUSTED_PROXIES", "172.30.44.3/32")
    get_settings.cache_clear()
    headers = {
        "x-monivex-client-ip": "198.51.100.24",
        "x-forwarded-for": "192.0.2.1",
        "forwarded": "for=192.0.2.2",
        "x-real-ip": "192.0.2.3",
    }
    assert client_ip(request("203.0.113.5", headers)) == "203.0.113.5"
    assert client_ip(request("172.30.44.3", headers)) == "198.51.100.24"
    assert (
        client_ip(
            request("172.30.44.3", {"x-monivex-client-ip": "192.0.2.1, 192.0.2.2"})
        )
        == "172.30.44.3"
    )
    assert (
        client_ip(request("172.30.44.3", {"x-forwarded-for": "192.0.2.1"}))
        == "172.30.44.3"
    )
    assert client_ip(request("::1", headers)) == "::1"


@pytest.mark.parametrize(
    "name,value",
    [
        ("MONIVEX_PUBLIC_ORIGIN", "http://monitoring.example.com"),
        ("MONIVEX_PUBLIC_ORIGIN", "https://monitoring.example.com/path"),
        ("MONIVEX_COOKIE_SECURE", "false"),
        ("MONIVEX_ENCRYPTION_KEY", ""),
        ("MONIVEX_TRUSTED_PROXIES", ""),
        ("MONIVEX_TRUSTED_PROXIES", "0.0.0.0/0"),
        ("MONIVEX_TRUSTED_PROXIES", "invalid"),
    ],
)
def test_public_profile_rejects_unsafe_settings(name, value, monkeypatch):
    monkeypatch.setenv("MONIVEX_PUBLIC_PROFILE", "true")
    monkeypatch.setenv("MONIVEX_PUBLIC_ORIGIN", "https://monitoring.example.com")
    monkeypatch.setenv("MONIVEX_COOKIE_SECURE", "true")
    monkeypatch.setenv("MONIVEX_ENCRYPTION_KEY", "present")
    monkeypatch.setenv("MONIVEX_TRUSTED_PROXIES", "172.30.44.3/32")
    monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        validate_public_settings()


def test_public_profile_validates_and_local_profile_still_works(monkeypatch):
    monkeypatch.setenv("MONIVEX_PUBLIC_PROFILE", "true")
    monkeypatch.setenv("MONIVEX_PUBLIC_ORIGIN", "https://monitoring.example.com")
    monkeypatch.setenv("MONIVEX_COOKIE_SECURE", "true")
    monkeypatch.setenv("MONIVEX_ENCRYPTION_KEY", "present")
    monkeypatch.setenv("MONIVEX_TRUSTED_PROXIES", "172.30.44.3/32")
    get_settings.cache_clear()
    validate_public_settings()
    monkeypatch.setenv("MONIVEX_PUBLIC_PROFILE", "false")
    monkeypatch.setenv("MONIVEX_PUBLIC_ORIGIN", "http://localhost:8080")
    monkeypatch.setenv("MONIVEX_COOKIE_SECURE", "false")
    monkeypatch.setenv("MONIVEX_ENCRYPTION_KEY", "")
    monkeypatch.setenv("MONIVEX_TRUSTED_PROXIES", "")
    get_settings.cache_clear()
    validate_public_settings()
