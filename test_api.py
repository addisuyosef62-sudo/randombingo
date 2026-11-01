import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from fastapi.responses import FileResponse
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
                "mini_app": "/app",
                "health": "/health",
                "docs": "/docs",
            },
        )

    def test_mini_app_route_serves_the_game_html(self):
        response = api.mini_app_page()

        self.assertIsInstance(response, FileResponse)
        self.assertTrue(response.path.endswith("index.html"))
        with open(response.path, encoding="utf-8") as game_page:
            self.assertIn('name="bingo-api-url"', game_page.read())

    @patch.dict(
        os.environ,
        {
            "PUBLIC_BASE_URL": "https://randombingo.onrender.com",
            "TELEGRAM_WEBHOOK_SECRET": "a" * 40,
            "WEB_APP_URL": "https://randombingo.onrender.com/app",
        },
    )
    def test_configures_telegram_webhook_and_menu_button(self):
        telegram_bot = SimpleNamespace(
            set_webhook=AsyncMock(),
            set_chat_menu_button=AsyncMock(),
        )

        asyncio.run(api.configure_telegram(telegram_bot))

        telegram_bot.set_webhook.assert_awaited_once_with(
            url="https://randombingo.onrender.com/telegram/webhook",
            secret_token="a" * 40,
            allowed_updates=api.Update.ALL_TYPES,
        )
        menu_button = telegram_bot.set_chat_menu_button.call_args.kwargs["menu_button"]
        self.assertEqual(menu_button.text, "Play Bingo")
        self.assertEqual(menu_button.web_app.url, "https://randombingo.onrender.com/app")

    def test_webhook_rejects_invalid_secret(self):
        request = SimpleNamespace(
            json=AsyncMock(return_value={}),
            app=SimpleNamespace(state=SimpleNamespace()),
        )
        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "a" * 40}):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(api.telegram_webhook(request, "wrong-secret"))
        self.assertEqual(error.exception.status_code, 403)

    def test_webhook_processes_authenticated_update(self):
        telegram_application = SimpleNamespace(
            bot=object(),
            update_queue=SimpleNamespace(put=AsyncMock()),
        )
        request = SimpleNamespace(
            json=AsyncMock(return_value={"update_id": 1}),
            app=SimpleNamespace(
                state=SimpleNamespace(telegram_application=telegram_application)
            ),
        )
        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "a" * 40}):
            with patch("api.Update.de_json", return_value="decoded-update"):
                result = asyncio.run(
                    api.telegram_webhook(request, "a" * 40)
                )
        self.assertEqual(result, {"ok": True})
        telegram_application.update_queue.put.assert_awaited_once_with("decoded-update")

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
