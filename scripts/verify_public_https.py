"""Local HTTPS verification of the real public profile; no ACME/VPS deployment."""

import base64
import json
from pathlib import Path
import secrets
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import http.cookiejar

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "monivex-https-test"


def main():
    with tempfile.TemporaryDirectory(prefix="monivex-https-") as temporary:
        directory = Path(temporary)
        # Rootless Docker must traverse the directory to mount the public Caddyfile.
        # The environment file remains mode 0600; the directory cannot be listed.
        directory.chmod(0o711)
        env_file = directory / "test.env"
        setup_token = secrets.token_urlsafe(48)
        env_file.write_text(
            "MONIVEX_DOMAIN=localhost:18443\nMONIVEX_ACME_EMAIL=test@example.com\nMONIVEX_SETUP_TOKEN="
            + setup_token
            + "\nMONIVEX_ENCRYPTION_KEY="
            + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
            + "\n"
        )
        env_file.chmod(0o600)
        caddyfile = directory / "Caddyfile"
        # Only the certificate issuer is changed for localhost testing.
        caddyfile.write_text(
            (ROOT / "deploy/Caddyfile")
            .read_text()
            .replace("{$MONIVEX_DOMAIN} {", "https://localhost {\n    tls internal")
        )
        caddyfile.chmod(0o644)
        override = directory / "override.yaml"
        override.write_text(
            'services:\n  caddy:\n    ports: !override ["127.0.0.1:18081:80", "127.0.0.1:18443:443"]\n    volumes:\n      - '
            + str(caddyfile)
            + ":/etc/caddy/Caddyfile:ro\n"
        )
        compose = [
            "docker",
            "compose",
            "-p",
            PROJECT,
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "compose.public.yaml"),
            "-f",
            str(override),
        ]

        def run(*args):
            result = subprocess.run(
                [*compose, *args], cwd=ROOT, capture_output=True, text=True, timeout=210
            )
            if result.returncode:
                message = (result.stderr or result.stdout)[-4000:]
                for line in env_file.read_text().splitlines():
                    name, value = line.split("=", 1)
                    if value and ("TOKEN" in name or "KEY" in name):
                        message = message.replace(value, "[REDACTED]")
                raise RuntimeError(
                    "Operacja testowego profilu HTTPS nie powiodła się: "
                    + args[0]
                    + "\n"
                    + message
                )
            return result.stdout

        try:
            run("config", "--quiet")
            run("up", "--no-build", "-d", "--wait", "--wait-timeout", "150")
            ca = directory / "ca.crt"
            for _ in range(30):
                result = subprocess.run(
                    [
                        *compose,
                        "cp",
                        "caddy:/data/caddy/pki/authorities/local/root.crt",
                        str(ca),
                    ],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Testowe CA Caddy nie jest gotowe.")
            context = ssl.create_default_context(cafile=str(ca))
            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=context),
                urllib.request.HTTPCookieProcessor(jar),
            )
            csrf = ""
            origin = "https://localhost:18443"

            def request(path, method="GET", data=None, extra=None):
                headers = {
                    "Origin": origin,
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrf,
                    **(extra or {}),
                }
                req = urllib.request.Request(
                    origin + path,
                    method=method,
                    headers=headers,
                    data=json.dumps(data).encode() if data is not None else None,
                )
                try:
                    response = opener.open(req, timeout=10)
                except urllib.error.HTTPError as error:
                    response = error
                body = response.read()
                return (
                    response.code,
                    response.headers,
                    json.loads(body)
                    if body.startswith(b"{") or body.startswith(b"[")
                    else None,
                )

            last_error = "brak odpowiedzi"
            for _ in range(30):
                try:
                    status, headers, _ = request("/")
                    last_error = "HTTP " + str(status)
                    if status == 200:
                        break
                except (OSError, urllib.error.URLError) as error:
                    last_error = str(error)
                time.sleep(1)
            else:
                raise RuntimeError(
                    "HTTPS nie odpowiada z poprawnie zweryfikowanym certyfikatem: "
                    + last_error
                )

            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            redirect_client = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), NoRedirect()
            )
            try:
                redirect_client.open("http://localhost:18081/", timeout=5)
            except urllib.error.HTTPError as error:
                assert error.code == 308 and error.headers["Location"].startswith(
                    "https://localhost"
                )
            else:
                raise AssertionError("Brak przekierowania HTTP do HTTPS.")
            assert headers.get("Strict-Transport-Security") == "max-age=31536000"
            assert "frame-ancestors 'none'" in headers.get(
                "Content-Security-Policy", ""
            )
            for path in [
                "/api/auth/me",
                "/api/auth/security",
                "/api/auth/sessions",
                "/api/auth/events",
                "/api/dashboard",
                "/api/monitors",
                "/api/resources",
            ]:
                assert request(path)[0] == 401, "Brak ochrony endpointu: " + path
            assert request("/api/auth/register", "POST", {})[0] == 404
            assert request("/api/health/ready")[0] == 404
            assert request("/openapi.json")[0] == 404
            password = secrets.token_urlsafe(32)
            account = {
                "username": "owner",
                "password": password,
                "installation_name": "MONIVEX HTTPS test",
                "timezone": "Europe/Warsaw",
            }
            assert (
                request("/api/setup", "POST", account, {"X-Setup-Token": setup_token})[
                    0
                ]
                == 201
            )
            spoofed = {
                "X-Forwarded-For": "198.51.100.1",
                "Forwarded": "for=198.51.100.2",
                "X-Real-IP": "198.51.100.3",
                "X-Monivex-Client-IP": "198.51.100.4",
            }
            status, headers, data = request("/api/auth/login", "POST", account, spoofed)
            assert status == 200
            cookie = headers.get("Set-Cookie", "")
            assert all(
                v in cookie
                for v in ["Secure", "HttpOnly", "SameSite=strict", "Path=/api"]
            )
            csrf = data["csrf_token"]
            status, _, sessions = request("/api/auth/sessions")
            assert status == 200 and len(sessions) == 1
            assert sessions[0]["client_ip"] and sessions[0]["client_ip"] not in {
                "198.51.100." + str(i) for i in range(1, 5)
            }
            assert sessions[0]["client_ip"] != "172.30.44.3", (
                "API nie odczytało adresu klienta z zaufanego proxy."
            )
            assert (
                request(
                    "/api/auth/logout", "POST", {}, {"Origin": "https://evil.invalid"}
                )[0]
                == 403
            )
            assert (
                request("/api/auth/logout", "POST", {}, {"X-CSRF-Token": "bad"})[0]
                == 403
            )
            # Varying every attacker-controlled forwarding header cannot evade the IP limit.
            for i in range(9):
                assert (
                    request(
                        "/api/auth/login",
                        "POST",
                        {"username": "owner", "password": "wrong"},
                        {
                            "X-Forwarded-For": f"192.0.2.{i}",
                            "X-Monivex-Client-IP": f"192.0.2.{i}",
                        },
                    )[0]
                    == 401
                )
            status, headers, _ = request(
                "/api/auth/login", "POST", account, {"X-Forwarded-For": "203.0.113.99"}
            )
            assert status == 429 and headers.get("Retry-After")
            # Verify the running profile has no other published ports.
            containers = [
                json.loads(line)
                for line in run("ps", "--format", "json").splitlines()
                if line.strip()
            ]
            for container in containers:
                if container["Service"] != "caddy":
                    assert not any(
                        p.get("PublishedPort", 0)
                        for p in container.get("Publishers") or []
                    ), "Nieoczekiwany publiczny port usługi."
            run("restart", "api", "web")
            for _ in range(30):
                try:
                    if request("/api/auth/me")[0] == 200:
                        break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Sesja nie przetrwała restartu stacku HTTPS.")
            print(
                "HTTPS: certyfikat, Secure cookies, HSTS/CSP, uwierzytelnianie API, Origin/CSRF, proxy, brute force, porty i restart — OK."
            )
        finally:
            run("down", "-v")


if __name__ == "__main__":
    main()
