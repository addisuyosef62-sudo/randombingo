import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
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


class DepositReviewTests(unittest.TestCase):
    def test_confirm_saves_request_and_notifies_admin_with_review_buttons(self):
        class FakeBot:
            def __init__(self):
                self.sent_messages = []

            async def send_message(self, **kwargs):
                self.sent_messages.append(kwargs)

        message = FakeMessage()
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=123, first_name="Test", last_name="User"),
            message=message,
            answer=unittest.mock.AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        telegram_bot = FakeBot()
        context = SimpleNamespace(
            user_data={
                "selected_bank": "TeleBirr",
                "deposit_amount": 100.0,
                "deposit_proof": "confirmed transfer receipt",
            },
            bot=telegram_bot,
        )

        with patch.object(bot, "ADMIN_ID", 456), patch.object(
            bot, "supabase_request", return_value=[{"id": "request-123"}]
        ) as request:
            state = asyncio.run(bot.confirm_deposit_action(update, context))

        self.assertEqual(state, bot.ConversationHandler.END)
        self.assertEqual(request.call_args.args[0], "POST")
        self.assertEqual(request.call_args.args[1], "wallet_deposit_requests")
        self.assertEqual(request.call_args.args[2]["status"], "pending_review")
        self.assertEqual(request.call_args.args[2]["payment_proof"], "confirmed transfer receipt")
        self.assertEqual(request.call_args.kwargs["prefer"], "return=representation")

        admin_message = telegram_bot.sent_messages[0]
        self.assertEqual(admin_message["chat_id"], 456)
        self.assertIn("confirmed transfer receipt", admin_message["text"])
        approve_button, reject_button = admin_message["reply_markup"].inline_keyboard[0]
        self.assertEqual(approve_button.callback_data, "webdep_request-123_approve")
        self.assertEqual(reject_button.callback_data, "webdep_request-123_reject")
        self.assertIn("pending", message.replies[-1])

    def test_only_admin_can_review_deposit(self):
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=123),
            data="webdep_request-123_approve",
            answer=unittest.mock.AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace()

        with patch.object(bot, "ADMIN_ID", 456), patch.object(bot, "supabase_request") as request:
            asyncio.run(bot.handle_web_deposit_review(update, context))

        query.answer.assert_awaited_once_with(
            "You are not authorized to review deposits.", show_alert=True
        )
        request.assert_not_called()

    def test_admin_review_updates_request_and_notifies_user(self):
        class FakeBot:
            def __init__(self):
                self.sent_messages = []

            async def send_message(self, **kwargs):
                self.sent_messages.append(kwargs)

        message = SimpleNamespace(
            text="Deposit request",
        )
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=456),
            data="webdep_request-123_approve",
            message=message,
            answer=unittest.mock.AsyncMock(),
            edit_message_text=unittest.mock.AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        telegram_bot = FakeBot()
        context = SimpleNamespace(bot=telegram_bot)

        with patch.object(bot, "ADMIN_ID", 456), patch.object(
            bot,
            "supabase_request",
            side_effect=[True, [{"telegram_user_id": 123}]],
        ) as request:
            asyncio.run(bot.handle_web_deposit_review(update, context))

        self.assertEqual(request.call_args_list[0].args[1], "rpc/review_wallet_deposit")
        self.assertEqual(
            request.call_args_list[0].args[2],
            {
                "request_id": "request-123",
                "new_status": "approved",
                "reviewer_id": 456,
            },
        )
        self.assertEqual(telegram_bot.sent_messages[0]["chat_id"], 123)
        self.assertIn("does not credit", telegram_bot.sent_messages[0]["text"])
        query.edit_message_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
