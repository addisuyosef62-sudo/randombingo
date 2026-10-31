import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode

from auth_utils import hash_password, verify_password, verify_telegram_init_data


BOT_TOKEN = "test-token"


def signed_init_data(auth_date=None):
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "user": json.dumps({"id": 12345, "first_name": "Test"}, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


class AuthUtilsTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifies(self):
        first_hash = hash_password("correct horse battery")
        second_hash = hash_password("correct horse battery")

        self.assertNotEqual(first_hash, second_hash)
        self.assertTrue(verify_password("correct horse battery", first_hash))
        self.assertFalse(verify_password("wrong password", first_hash))

    def test_telegram_init_data_verifies(self):
        user = verify_telegram_init_data(signed_init_data(), BOT_TOKEN)

        self.assertEqual(user["id"], 12345)

    def test_telegram_init_data_rejects_tampering(self):
        init_data = signed_init_data().replace("Test", "Attacker")

        with self.assertRaises(ValueError):
            verify_telegram_init_data(init_data, BOT_TOKEN)

    def test_telegram_init_data_rejects_expired_auth(self):
        init_data = signed_init_data(auth_date=int(time.time()) - 86_401)

        with self.assertRaises(ValueError):
            verify_telegram_init_data(init_data, BOT_TOKEN)


if __name__ == "__main__":
    unittest.main()
