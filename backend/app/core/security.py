from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
import jwt
from app.core.config import settings

_BCRYPT_ROUNDS = 12
_BCRYPT_MAX_BYTES = 72  # bcrypt silently truncates at 72 bytes


def _encode_password(password: str) -> bytes:
    """UTF-8 encode a password, truncated to bcrypt's 72-byte limit."""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if *plain_password* matches the stored bcrypt hash."""
    return bcrypt.checkpw(_encode_password(plain_password), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """Return a bcrypt hash of *password* (cost factor 12)."""
    return bcrypt.hashpw(_encode_password(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
