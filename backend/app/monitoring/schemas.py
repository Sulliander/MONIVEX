import re
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

Kind = Literal["icmp", "tcp", "http", "dns", "tls", "smtp", "http_json", "heartbeat"]


class CheckConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = Field(default="", max_length=253)
    port: int = Field(default=443, ge=1, le=65535)
    url: str = Field(default="", max_length=2048)
    method: Literal["GET", "HEAD", "POST"] = "GET"
    expected_codes: list[int] = Field(
        default_factory=lambda: [200], min_length=1, max_length=30
    )
    follow_redirects: bool = False
    contains: str = Field(default="", max_length=1024)
    warning_ms: int = Field(default=0, ge=0, le=120000)
    domain: str = Field(default="", max_length=253)
    record_type: Literal["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SOA", "SRV"] = "A"
    expected_answer: str = Field(default="", max_length=512)
    expiry_warning_days: int = Field(default=30, ge=0, le=365)
    starttls: bool = False
    json_path: list[str | int] = Field(default_factory=list, max_length=20)
    expected_value: str | int | float | bool | None = None
    grace_seconds: int = Field(default=30, ge=0, le=86400)


class CheckSecrets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: SecretStr = SecretStr("")
    password: SecretStr = SecretStr("")
    bearer: SecretStr = SecretStr("")
    headers: dict[str, SecretStr] = Field(default_factory=dict, max_length=20)
    body: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def validate_secrets(self):
        for name, value in self.headers.items():
            if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", name) or name.lower() in {
                "host",
                "content-length",
                "connection",
                "transfer-encoding",
                "authorization",
                "cookie",
                "proxy-authorization",
                "accept-encoding",
            }:
                raise ValueError("Niedozwolony nagłówek.")
            if len(value.get_secret_value()) > 4096 or any(
                c in value.get_secret_value() for c in "\r\n"
            ):
                raise ValueError("Nieprawidłowa wartość nagłówka.")
        if len(self.body.get_secret_value()) > 65536:
            raise ValueError("Treść żądania jest zbyt długa.")
        for value in [self.username, self.password, self.bearer]:
            if len(value.get_secret_value()) > 4096 or any(
                c in value.get_secret_value() for c in "\r\n"
            ):
                raise ValueError("Nieprawidłowe dane uwierzytelniające.")
        if self.bearer.get_secret_value() and (
            self.username.get_secret_value() or self.password.get_secret_value()
        ):
            raise ValueError("Wybierz jeden sposób uwierzytelniania.")
        return self

    def reveal(self):
        return {
            "username": self.username.get_secret_value(),
            "password": self.password.get_secret_value(),
            "bearer": self.bearer.get_secret_value(),
            "body": self.body.get_secret_value(),
            "headers": {k: v.get_secret_value() for k, v in self.headers.items()},
        }


class MonitorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    kind: Kind
    interval: int = Field(default=60, ge=10, le=86400)
    timeout: float = Field(default=5, ge=0.1, le=30)
    failure_threshold: int = Field(default=3, ge=1, le=20)
    recovery_threshold: int = Field(default=2, ge=1, le=20)
    config: CheckConfig = Field(default_factory=CheckConfig)
    secrets: CheckSecrets = Field(default_factory=CheckSecrets)

    @model_validator(mode="after")
    def validate_config(self):
        c = self.config
        if self.timeout >= self.interval:
            raise ValueError("Timeout musi być krótszy niż interwał.")
        if self.kind in {"http", "http_json"}:
            u = urlsplit(c.url)
            if (
                u.scheme not in {"http", "https"}
                or not u.hostname
                or u.username
                or u.password
                or u.fragment
            ):
                raise ValueError("Wymagany URL HTTP/HTTPS bez loginu i fragmentu.")
            if any(ord(x) < 33 for x in c.url) or "\\" in c.url:
                raise ValueError("Nieprawidłowy URL.")
            _ = u.port
            if any(code < 100 or code > 599 for code in c.expected_codes):
                raise ValueError("Nieprawidłowy kod HTTP.")
            if any(
                isinstance(x, int) and (isinstance(x, bool) or x < 0 or x > 10000)
                for x in c.json_path
            ):
                raise ValueError("Nieprawidłowa ścieżka JSON.")
        elif self.kind != "heartbeat":
            if not re.fullmatch(r"[A-Za-z0-9.:_-]{1,253}", c.host):
                raise ValueError("Nieprawidłowy host.")
            if self.kind == "dns" and not re.fullmatch(
                r"[A-Za-z0-9._-]{1,253}", c.domain
            ):
                raise ValueError("Nieprawidłowa domena DNS.")
        if self.kind not in {"http", "http_json"} and any(
            self.secrets.reveal().values()
        ):
            raise ValueError("Ten typ nie obsługuje sekretów.")
        return self
