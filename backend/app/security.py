from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from .config import settings

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def issue_token(user_id: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": user_id, "exp": expires}, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> str:
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    subject = claims.get("sub")
    if not isinstance(subject, str):
        raise jwt.InvalidTokenError("missing subject")
    return subject
