import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


def fake_update(user_id=123):
    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(type="private"),
        effective_message=message,
    )
    return update, message


class AdminSettingsTests(unittest.TestCase):
    def test_payment_command_saves_cbe_details_for_admin(self):
        update, message = fake_update(user_id=456)
        context = SimpleNamespace(args=["cbe", "0912345678", "CBE", "Account"])
        with patch.object(bot, "ADMIN_ID", 456), patch.object(bot, "supabase_request") as request:
            asyncio.run(bot.set_payment_details(update, context))

        self.assertEqual(request.call_args.args[1], "app_settings?on_conflict=key")
        self.assertEqual(request.call_args.args[2]["key"], "payment_cbe")
        self.assertEqual(
            request.call_args.args[2]["value"],
            {"account_name": "CBE Account", "account_number": "0912345678"},
        )
        self.assertIn("updated", message.replies[0])

    def test_payment_command_rejects_non_admin(self):
        update, message = fake_update(user_id=123)
        context = SimpleNamespace(args=["telebirr", "0912345678", "Account"])
        with patch.object(bot, "ADMIN_ID", 456), patch.object(bot, "supabase_request") as request:
            asyncio.run(bot.set_payment_details(update, context))

        request.assert_not_called()
        self.assertIn("only available", message.replies[0])

    def test_coupon_command_sets_fixed_demo_reward(self):
        update, message = fake_update(user_id=456)
        context = SimpleNamespace(args=["WELCOME40"])
        with patch.object(bot, "ADMIN_ID", 456), patch.object(bot, "supabase_request") as request:
            asyncio.run(bot.set_active_coupon(update, context))

        self.assertEqual(request.call_args.args[2]["key"], "active_coupon")
        self.assertEqual(
            request.call_args.args[2]["value"],
            {"code": "WELCOME40", "reward_amount": 40.00},
        )
        self.assertIn("40 ETB", message.replies[0])

    def test_coupon_command_deactivates_with_non_null_json_value(self):
        update, message = fake_update(user_id=456)
        context = SimpleNamespace(args=["off"])
        with patch.object(bot, "ADMIN_ID", 456), patch.object(bot, "supabase_request") as request:
            asyncio.run(bot.set_active_coupon(update, context))

        self.assertEqual(request.call_args.args[2]["value"], {"code": None})
        self.assertIn("deactivated", message.replies[0])


if __name__ == "__main__":
    unittest.main()
