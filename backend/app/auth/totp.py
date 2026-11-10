"""RFC 4226/6238: SHA-1, six digits, 30 seconds; secrets encrypted at rest."""

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from ..monitoring.vault import cipher, VaultError


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode()


def seal(secret):
    try:
        return cipher().encrypt(secret.encode()).decode()
    except VaultError:
        raise HTTPException(
            503, "2FA wymaga poprawnego klucza szyfrowania instalacji."
        ) from None


def unseal(value):
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError, VaultError):
        raise HTTPException(
            503,
            "Nie można odczytać konfiguracji 2FA. Skontaktuj się z właścicielem instalacji.",
        ) from None


def hotp(secret, counter, digits=6):
    mac = hmac.new(
        base64.b32decode(secret), struct.pack(">Q", counter), hashlib.sha1
    ).digest()
    offset = mac[-1] & 15
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def matching_step(secret, code, last_step=-1, now=None):
    if not re.fullmatch(r"\d{6}", code, flags=re.ASCII):
        return None
    step = int(time.time() if now is None else now) // 30
    # Accept +/- one interval for clock skew, but never replay an accepted interval.
    for candidate in [step, step - 1, step + 1]:
        if candidate > last_step and hmac.compare_digest(hotp(secret, candidate), code):
            return candidate
    return None
