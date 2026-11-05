import json
from cryptography.fernet import Fernet, InvalidToken
from ..config import get_settings


class VaultError(Exception):
    pass


def cipher():
    try:
        return Fernet(get_settings().encryption_key.encode())
    except (ValueError, TypeError):
        raise VaultError("Brak poprawnego klucza szyfrowania instalacji.") from None


def encrypt(data):
    if not any(data.values()):
        return None
    return cipher().encrypt(json.dumps(data).encode()).decode()


def decrypt(value):
    if not value:
        return {}
    try:
        return json.loads(cipher().decrypt(value.encode()))
    except (InvalidToken, ValueError):
        raise VaultError("Nie można odczytać sekretów monitora.") from None
