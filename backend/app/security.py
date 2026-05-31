from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import os
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.schemas import UserRole


ARGON2_HASH_PREFIX = "$argon2"
PBKDF2_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 210_000
SESSION_TOKEN_BYTES = 32
CSRF_TOKEN_BYTES = 32

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)
_SENSITIVE_PATTERNS = (
    re.compile(r"(postgresql(?:\+asyncpg)?://[^:\s]+:)[^@\s]+(@)", re.IGNORECASE),
    re.compile(r"(sk-or-v1-)[a-zA-Z0-9_-]+()", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[a-zA-Z0-9._~+/=-]+()", re.IGNORECASE),
)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    email: str
    role: UserRole
    source: str
    session_token_hash: str = ""
    csrf_hash: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith(ARGON2_HASH_PREFIX):
        try:
            return _password_hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False
    return verify_pbkdf2_password(password, password_hash)


def password_needs_rehash(password_hash: str) -> bool:
    if not password_hash.startswith(ARGON2_HASH_PREFIX):
        return True
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def hash_pbkdf2_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return (
        f"{PBKDF2_HASH_ALGORITHM}${PASSWORD_ITERATIONS}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_pbkdf2_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = password_hash.split("$", 3)
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False

    if algorithm != PBKDF2_HASH_ALGORITHM:
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


def create_csrf_token() -> str:
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_csrf_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_csrf_token(token: str, csrf_hash: str) -> bool:
    return bool(token) and hmac.compare_digest(hash_csrf_token(token), csrf_hash)


def session_expires_at(hours: int) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)


def redact_sensitive_text(value: str) -> str:
    redacted = value
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"\1[redacted]\2", redacted)
    return redacted
