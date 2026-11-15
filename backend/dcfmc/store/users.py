"""User accounts and signed session tokens (standard library only)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time

from sqlalchemy import func, select

from .db import Store, User

USERNAME_RX = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
SESSION_DAYS = 30


class AuthError(ValueError):
    pass


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt_b64, h_b64 = stored.split("$")
        salt, h = base64.b64decode(salt_b64), base64.b64decode(h_b64)
    except ValueError:
        return False
    return hmac.compare_digest(hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32), h)


def create_user(store: Store, username: str, password: str) -> dict:
    u = username.strip().lower()
    if not USERNAME_RX.match(u):
        raise AuthError("Username: 3-32 characters, letters, digits, dot, dash or underscore.")
    if len(password) < 8:
        raise AuthError("Password: at least 8 characters.")
    with store.Session.begin() as s:
        if s.scalar(select(User).where(User.username == u)):
            raise AuthError("That username is taken.")
        user = User(username=u, password_hash=hash_password(password))
        s.add(user)
        s.flush()
        return {"id": user.id, "username": user.username}


def authenticate(store: Store, username: str, password: str) -> dict:
    with store.Session() as s:
        user = s.scalar(select(User).where(User.username == username.strip().lower()))
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Wrong username or password.")
        return {"id": user.id, "username": user.username}


def get_user(store: Store, uid: int) -> dict | None:
    with store.Session() as s:
        user = s.get(User, uid)
        return {"id": user.id, "username": user.username} if user else None


def count_users(store: Store) -> int:
    with store.Session() as s:
        return s.scalar(select(func.count()).select_from(User)) or 0


def make_token(secret: str, uid: int, days: int = SESSION_DAYS) -> str:
    exp = int(time.time()) + days * 86400
    msg = f"{uid}.{exp}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}.{sig}"


def read_token(secret: str, token: str | None) -> int | None:
    if not token:
        return None
    try:
        uid, exp, sig = token.split(".")
    except ValueError:
        return None
    good = hmac.new(secret.encode(), f"{uid}.{exp}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, sig) or int(exp) < time.time():
        return None
    return int(uid)
