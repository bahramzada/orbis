from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import os
import secrets

from app.schemas import UserRole


PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 210_000
SESSION_TOKEN_BYTES = 32


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    email: str
    role: UserRole
    source: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return (
        f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = password_hash.split("$", 3)
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False

    if algorithm != PASSWORD_ALGORITHM:
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def create_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expires_at(hours: int) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)
