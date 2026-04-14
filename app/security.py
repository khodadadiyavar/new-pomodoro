import base64
import hashlib
import hmac
import os
import time
from typing import Optional


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, password_hash: str) -> bool:
    salt_b64, digest_b64 = password_hash.split("$", 1)
    salt = base64.b64decode(salt_b64.encode())
    expected = base64.b64decode(digest_b64.encode())
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return hmac.compare_digest(actual, expected)


def sign_session(user_id: int, secret_key: str) -> str:
    issued_at = str(int(time.time()))
    payload = f"{user_id}:{issued_at}"
    signature = hmac.new(
        secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{payload}:{signature}"


def read_session(cookie_value: str, secret_key: str) -> Optional[int]:
    try:
        user_id, issued_at, signature = cookie_value.split(":")
        payload = f"{user_id}:{issued_at}"
    except ValueError:
        return None

    expected = hmac.new(
        secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return int(user_id)
