import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

import api


class DepositApiTests(unittest.TestCase):
    def setUp(self):
        self.payload = api.DepositRequest(
            amount=50,
            payment_method="TeleBirr",
            payment_proof="confirmed bank transfer",
        )

    def test_root_returns_api_status_and_discovery_links(self):
        self.assertEqual(
            api.root(),
            {
                "status": "ok",
                "service": "Bingo Habesha API",
                "health": "/health",
                "docs": "/docs",
            },
        )

    def test_deposit_requires_telegram_auth(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"}):
            with self.assertRaises(HTTPException) as error:
                api.create_deposit(self.payload, None)

        self.assertEqual(error.exception.status_code, 401)

    def test_deposit_rejects_out_of_range_amount(self):
        with self.assertRaises(ValidationError):
            api.DepositRequest(
                amount=49,
                payment_method="TeleBirr",
                payment_proof="confirmed bank transfer",
            )

    @patch(
        "api.supabase_request",
        return_value=[
            {
                "key": "payment_telebirr",
                "value": {"account_name": "Test Account", "account_number": "0912345678"},
            }
        ],
    )
    def test_payment_methods_return_admin_configured_details(self, supabase_request):
        result = api.list_payment_methods()

        self.assertEqual(
            result["TeleBirr"],
            {
                "configured": True,
                "account_name": "Test Account",
                "account_number": "0912345678",
            },
        )
        self.assertFalse(result["CBE Birr"]["configured"])
        supabase_request.assert_called_once()

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"})
    @patch("api.verify_telegram_init_data", return_value={"id": 12345})
    @patch(
        "api.supabase_request",
        return_value=[
            {
                "full_name": "DARK",
                "phone_number": "0950218819",
                "winnings_balance": "0.00",
            }
        ],
    )
    def test_profile_returns_private_wallet_contact_and_main_balance(
        self, supabase_request, verify_init_data
    ):
        result = api.get_profile("signed-init-data")

        self.assertEqual(
            result,
            {
                "full_name": "DARK",
                "phone_number": "0950218819",
                "main_balance": 0.00,
            },
        )
        self.assertEqual(supabase_request.call_args.args[1], "user_profiles?select=full_name,phone_number,winnings_balance&user_id=eq.tg_12345&limit=1")
        verify_init_data.assert_called_once_with("signed-init-data", "test-token")

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"})
    @patch("api.verify_telegram_init_data", return_value={"id": 12345, "first_name": "Test"})
    @patch("api.supabase_request", return_value=[{"id": "request-123"}])
    @patch("api.send_admin_message")
    def test_deposit_saves_request_and_notifies_admin(
        self, send_admin_message, supabase_request, verify_init_data
    ):
        result = api.create_deposit(self.payload, "signed-init-data")

        self.assertEqual(result, {"id": "request-123", "status": "pending_review"})
        self.assertEqual(supabase_request.call_args.args[0], "POST")
        self.assertEqual(
            supabase_request.call_args.args[1],
            "wallet_deposit_requests",
        )
        send_admin_message.assert_called_once()
        verify_init_data.assert_called_once_with("signed-init-data", "test-token")

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"})
    @patch("api.verify_telegram_init_data", return_value={"id": 12345})
    @patch(
        "api.supabase_request",
        side_effect=[
            [{"value": {"code": "WELCOME40"}}],
            None,
        ],
    )
    def test_coupon_redemption_is_recorded_once(self, supabase_request, verify_init_data):
        result = api.redeem_coupon(
            api.CouponRedemption(code=" welcome40 "),
            "signed-init-data",
        )

        self.assertEqual(result["status"], "redeemed")
        self.assertEqual(result["reward_amount"], 40.00)
        self.assertIn("not withdrawable", result["balance_note"])
        self.assertEqual(supabase_request.call_count, 2)
        self.assertEqual(
            supabase_request.call_args_list[1].args[1],
            "wallet_coupon_redemptions",
        )
        verify_init_data.assert_called_once_with("signed-init-data", "test-token")

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token"})
    @patch("api.verify_telegram_init_data", return_value={"id": 12345})
    @patch("api.supabase_request", return_value=[])
    def test_coupon_redemption_rejects_inactive_code(self, supabase_request, verify_init_data):
        with self.assertRaises(HTTPException) as error:
            api.redeem_coupon(api.CouponRedemption(code="WELCOME40"), "signed-init-data")

        self.assertEqual(error.exception.status_code, 400)
        supabase_request.assert_called_once()
        verify_init_data.assert_called_once()


if __name__ == "__main__":
    unittest.main()
