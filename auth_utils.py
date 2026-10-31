import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import parse_qsl


PASSWORD_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${password_hash.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected_hex = encoded_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def verify_telegram_init_data(init_data: str, bot_token: str, max_age: int = 86_400):
    pairs = parse_qsl(init_data, keep_blank_values=True)
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Invalid Telegram Web App data.")
    received_hash = fields.pop("hash", None)
    if not received_hash or not fields:
        raise ValueError("Missing Telegram Web App signature.")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Invalid Telegram Web App signature.")

    try:
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Invalid Telegram Web App identity.") from exc

    now = int(time.time())
    if auth_date > now + 60 or now - auth_date > max_age:
        raise ValueError("Telegram Web App login has expired.")
    if not isinstance(user, dict) or not user.get("id"):
        raise ValueError("Telegram Web App identity is incomplete.")

    return user
