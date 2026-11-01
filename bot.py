import os
import re
import secrets
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    ConversationHandler, filters, ContextTypes
)
from telegram.helpers import escape_markdown
from auth_utils import hash_password
from supabase_client import SupabaseError, supabase_request

BOT_TOKEN = '9267476327:AAFl8y4cHGgQ6il5hJz7IFUDb0UYj7DsDcU'
WEB_APP_URL = "https://randombingo.onrender.com"
ADMIN_ID = '7902432584'

# Conversation states for Deposit
WAITING_FOR_DEP_AMOUNT, WAITING_FOR_DEP_PROOF, CONFIRM_DEPOSIT = range(3)

users_db = {}


def load_user_profile(user_id: int):
    rows = supabase_request(
        "GET",
        "user_profiles"
        f"?select=user_id,full_name,phone_number,balance,winnings_balance,phone_verified_at"
        f"&user_id=eq.tg_{user_id}&limit=1",
    )
    if not rows:
        return None

    profile = rows[0]
    users_db[user_id] = {
        "name": profile.get("full_name") or "User",
        "phone": profile.get("phone_number") or "",
        "play_balance": float(profile.get("balance") or 0),
        "main_balance": float(profile.get("winnings_balance") or 0),
    }
    return profile


def get_keyboard(is_registered: bool = False):
    if is_registered:
        top_button = KeyboardButton("🎮 ጌም ይጫወቱ (PLAY)")
    else:
        top_button = KeyboardButton("📱 ለመመዝገብ ስልክ ቁጥር ያጋሩ", request_contact=True)

    keyboard_layout = [
        [top_button],
        [KeyboardButton("👤 ፕሮፋይል"), KeyboardButton("💰 ሂሳብ")],
        [KeyboardButton("📩 ገቢ (Deposit)"), KeyboardButton("📤 ወጪ (Withdraw)")],
        [KeyboardButton("🔗 ጋብዝ & አግኝ"), KeyboardButton("🗣 ድርጅቱን አስተዋውቅ")],
        [KeyboardButton("🎫 ፕሮሞ ኮድ"), KeyboardButton("🌐 ቋንቋ (Language)")],
        [KeyboardButton("📖 መመሪያ"), KeyboardButton("🆘 እርዳታ"), KeyboardButton("📜 ደንቦች")]
    ]
    return ReplyKeyboardMarkup(keyboard_layout, resize_keyboard=True)

def get_back_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("🔙 ወደ ኋላ ተመልስ")]], resize_keyboard=True)


def load_app_setting(key: str):
    rows = supabase_request(
        "GET",
        f"app_settings?select=value&key=eq.{key}&limit=1",
    )
    return rows[0].get("value") if rows else None


async def set_payment_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if user.id != ADMIN_ID or update.effective_chat.type != "private":
        await message.reply_text("This command is only available to the administrator in a private chat.")
        return

    if len(context.args) < 3:
        await message.reply_text(
            "Usage: /setpayment <telebirr|cbe> <account_number> <account_name>\n"
            "Example: /setpayment telebirr 0912345678 Your Name"
        )
        return

    method = context.args[0].lower()
    setting_key = {
        "telebirr": "payment_telebirr",
        "cbe": "payment_cbe",
        "cbebirr": "payment_cbe",
    }.get(method)
    account_number = context.args[1].strip()
    account_name = " ".join(context.args[2:]).strip()
    if not setting_key or not re.fullmatch(r"[+0-9][0-9 -]{5,23}", account_number):
        await message.reply_text("Invalid method or account number. Use telebirr or cbe and enter a valid number.")
        return
    if not account_name or len(account_name) > 100:
        await message.reply_text("Account name must contain 1 to 100 characters.")
        return

    try:
        supabase_request(
            "POST",
            "app_settings?on_conflict=key",
            {
                "key": setting_key,
                "value": {
                    "account_name": account_name,
                    "account_number": account_number,
                },
                "updated_by": user.id,
            },
            prefer="resolution=merge-duplicates,return=minimal",
        )
    except SupabaseError as exc:
        print(f"Could not save payment details: {exc}")
        await message.reply_text("Could not save payment details. Please try again.")
        return

    display_method = "TeleBirr" if setting_key == "payment_telebirr" else "CBE Birr"
    await message.reply_text(f"{display_method} deposit details have been updated.")


async def set_active_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if user.id != ADMIN_ID or update.effective_chat.type != "private":
        await message.reply_text("This command is only available to the administrator in a private chat.")
        return

    if len(context.args) != 1:
        await message.reply_text("Usage: /setcoupon <CODE> (or /setcoupon off to deactivate it)")
        return

    code = context.args[0].upper()
    if code == "OFF":
        value = {"code": None}
    else:
        if not re.fullmatch(r"[A-Z0-9_-]{4,32}", code):
            await message.reply_text("Coupon codes must be 4 to 32 letters, numbers, underscores, or hyphens.")
            return
        value = {"code": code, "reward_amount": 40.00}

    try:
        supabase_request(
            "POST",
            "app_settings?on_conflict=key",
            {"key": "active_coupon", "value": value, "updated_by": user.id},
            prefer="resolution=merge-duplicates,return=minimal",
        )
    except SupabaseError as exc:
        print(f"Could not update active promo code: {exc}")
        await message.reply_text("Could not update the promo code. Please try again.")
        return

    if code != "OFF":
        await message.reply_text(
            f"Promo code {code} is active. It awards 40 ETB to each user's demo balance once."
        )
    else:
        await message.reply_text("The active promo code has been deactivated.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        profile = load_user_profile(user_id)
    except SupabaseError as exc:
        print(f"Could not load Telegram user profile: {exc}")
        await update.message.reply_text("⚠️ መረጃዎን ማረጋገጥ አልተቻለም። እባክዎ ቆይተው እንደገና ይሞክሩ።")
        return ConversationHandler.END
    is_registered = bool(profile and profile.get("phone_verified_at"))
    keyboard = get_keyboard(is_registered)
    welcome_text = (
        "🟢 ቢንጎ ⚪️ ሀበሻ\n\n"
        "👏 እንኳን ወደ BINGO HABESHA መጡ!\n\n"
        "ጌሙን ለመጀመር ከታች ያለውን '📱 ለመመዝገብ ስልክ ቁጥር ያጋሩ' ይጫኑ::"
    )
    await update.message.reply_text(welcome_text, reply_markup=keyboard)
    return ConversationHandler.END

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name

    if contact.user_id != user_id:
        await update.message.reply_text("⚠️ እባክዎ የራስዎን ስልክ ቁጥር በአዝራሩ በኩል ያጋሩ።")
        return

    try:
        existing_profile = load_user_profile(user_id)
        if existing_profile and existing_profile.get("phone_verified_at"):
            await update.message.reply_text("የእርስዎ መለያ አስቀድሞ ተመዝግቧል። /start ይጫኑ።", reply_markup=get_keyboard(True))
            return
    except SupabaseError as exc:
        print(f"Could not check Telegram user registration: {exc}")
        await update.message.reply_text("⚠️ ምዝገባውን ማረጋገጥ አልተቻለም። እባክዎ ቆይተው እንደገና ይሞክሩ።")
        return

    random_password = ''.join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(12))
    phone_verified_at = update.message.date.isoformat()
    try:
        profile_fields = {
            "full_name": first_name,
            "phone_number": contact.phone_number,
            "password_hash": hash_password(random_password),
            "phone_verified_at": phone_verified_at,
            "updated_at": phone_verified_at,
        }
        if existing_profile:
            supabase_request(
                "PATCH",
                f"user_profiles?user_id=eq.tg_{user_id}",
                profile_fields,
                prefer="return=minimal",
            )
        else:
            supabase_request(
                "POST",
                "user_profiles",
                {
                    **profile_fields,
                    "user_id": f"tg_{user_id}",
                    "balance": 5.00,
                    "winnings_balance": 0.00,
                },
                prefer="return=minimal",
            )
    except SupabaseError as exc:
        print(f"Could not save Telegram registration: {exc}")
        await update.message.reply_text("⚠️ ምዝገባው አልተሳካም። እባክዎ ቆይተው እንደገና ይሞክሩ።")
        return

    users_db[user_id] = {
        "name": first_name,
        "phone": contact.phone_number,
        "play_balance": float((existing_profile or {}).get("balance") or 5.00),
        "main_balance": float((existing_profile or {}).get("winnings_balance") or 0.00)
    }

    response_text = (
        f"🟢 ቢንጎ ⚪️ ሀበሻ\n\n"
        f"🎉 እንኳን ደስ አለዎት {first_name}! ምዝገባው ተጠናቋል::\n\n"
        f"👤 **የእርስዎን ፕሮፋይል**\n\n"
        f"🔹 **ስም:** {first_name}\n"
        f"🔹 **ስልክ:** {contact.phone_number}\n"
        f"🔑 **የይለፍ ቃል:** {random_password}\n\n"
        f"💰 **መጨወቻ ሂሳብ:** {users_db[user_id]['play_balance']:.2f} ETB\n"
        f"💰 **ዋና ሂሳብ:** {users_db[user_id]['main_balance']:.2f} ETB\n\n"
        f"👇 ጌሙን ለመጀመር ከታች **'🎮 ጌም ይጫወቱ (PLAY)'** የሚለውን ይጫኑ::"
    )

    await update.message.reply_text(
        response_text, 
        reply_markup=get_keyboard(is_registered=True),
        parse_mode="Markdown"
    )

# --- DEPOSIT FLOW ---

async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    deposit_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📱 TeleBirr", callback_data="dep_telebirr"),
            InlineKeyboardButton("🏦 CBE Birr", callback_data="dep_cbebirr")
        ]
    ])
    await update.message.reply_text(
        "🏦 የትኛውን የባንክ አማራጭ መጠቀም ይፈልጋሉ?",
        reply_markup=deposit_keyboard
    )
    return WAITING_FOR_DEP_AMOUNT

async def handle_bank_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    bank_name = "TeleBirr" if query.data == "dep_telebirr" else "CBE Birr"
    setting_key = "payment_telebirr" if bank_name == "TeleBirr" else "payment_cbe"
    context.user_data["selected_bank"] = bank_name

    try:
        payment_details = load_app_setting(setting_key)
    except SupabaseError as exc:
        print(f"Could not load {bank_name} payment details: {exc}")
        await query.message.reply_text("Payment details are temporarily unavailable. Please try again later.")
        return ConversationHandler.END

    if not isinstance(payment_details, dict) or not payment_details.get("account_number"):
        await query.message.reply_text(
            f"{bank_name} deposit details have not been set up yet. Please contact the administrator."
        )
        return ConversationHandler.END

    payment_info_text = (
        f"🏦 **ባንክ:** {bank_name}\n\n"
        f"⚠️ **ማሳሰቢያ:** እባክዎ ከ {bank_name} ወደ {bank_name} ብቻ ያስገቡ!\n\n"
        f"እባክዎ ብሩን ወደዚህ አካውንት ያስገቡ:\n"
        f"👤 **ስም:** {escape_markdown(str(payment_details.get('account_name', '')))}\n"
        f"👉 **ቁጥር:** {escape_markdown(str(payment_details['account_number']))}\n\n"
        f"ከዚያም ያስገቡትን የብር መጠን ብቻ እዚህ ይጻፉልኝ (ምሳሌ: 100):"
    )

    await query.message.reply_text(
        payment_info_text,
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    return WAITING_FOR_DEP_AMOUNT

async def receive_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🔙 ወደ ኋላ ተመልስ":
        return await cancel_transaction(update, context)

    if not text.isdigit() or not 50 <= int(text) <= 100_000:
        await update.message.reply_text("⚠️ Enter a whole amount between 50 and 100,000 ETB.")
        return WAITING_FOR_DEP_AMOUNT

    amount = float(text)
    context.user_data["deposit_amount"] = amount
    await update.message.reply_text(
        "Paste the complete payment receipt SMS for the administrator to verify:"
    )
    return WAITING_FOR_DEP_PROOF


async def receive_deposit_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proof = update.message.text.strip()
    if proof == "🔙 ወደ ኋላ ተመልስ":
        return await cancel_transaction(update, context)
    if not 8 <= len(proof) <= 3000:
        await update.message.reply_text("Receipt SMS must contain 8 to 3,000 characters.")
        return WAITING_FOR_DEP_PROOF

    context.user_data["deposit_proof"] = proof
    bank_name = context.user_data.get("selected_bank", "Bank")
    amount = context.user_data["deposit_amount"]

    confirm_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ አረጋግጥ (Confirm)", callback_data="confirm_deposit")]
    ])

    summary_text = (
        f"📌 **የገቢ ጥያቄ ማጠቃለያ:**\n\n"
        f"🏦 **ባንክ:** {bank_name}\n"
        f"💵 **የብር መጠን:** {amount:.2f} ETB\n\n"
        f"ለማረጋገጥ ከታች ያለውን **'✅ አረጋግጥ (Confirm)'** የሚለውን ይጫኑ:"
    )

    await update.message.reply_text(
        summary_text,
        reply_markup=confirm_keyboard,
        parse_mode="Markdown"
    )
    return CONFIRM_DEPOSIT

async def confirm_deposit_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    bank_name = context.user_data.get("selected_bank", "Bank")
    amount = context.user_data.get("deposit_amount", 0.0)
    proof = context.user_data.get("deposit_proof", "")
    user_info = users_db.get(user.id, {})
    phone = user_info.get("phone", "N/A")

    request_row = {
        "user_id": f"tg_{user.id}",
        "telegram_user_id": user.id,
        "user_name": " ".join(
            part for part in (user.first_name, getattr(user, "last_name", None)) if part
        )[:120],
        "amount": amount,
        "payment_method": bank_name,
        "payment_proof": proof,
        "status": "pending_review",
    }

    try:
        inserted = supabase_request(
            "POST",
            "wallet_deposit_requests",
            request_row,
            prefer="return=representation",
        )
    except SupabaseError as exc:
        if exc.status_code == 409:
            await query.message.reply_text(
                "You already have a deposit request awaiting admin review."
            )
        else:
            print(f"Could not save Telegram deposit request: {exc}")
            await query.message.reply_text("Could not save your deposit request. Please try again.")
        return ConversationHandler.END

    if not inserted:
        await query.message.reply_text(
            "The database did not confirm your request. Please contact the administrator."
        )
        return ConversationHandler.END

    request_id = inserted[0]["id"]
    admin_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"webdep_{request_id}_approve"),
        InlineKeyboardButton("❌ Reject", callback_data=f"webdep_{request_id}_reject"),
    ]])
    admin_msg = (
        "New Telegram deposit request\n"
        f"Request: {request_id}\n"
        f"User: {request_row['user_name'] or user.id} (tg_{user.id})\n"
        f"Phone: {phone}\n"
        f"Amount: {amount:.2f} ETB\n"
        f"Method: {bank_name}\n"
        f"Receipt SMS:\n{proof}"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_msg,
            reply_markup=admin_markup,
        )
    except TelegramError as exc:
        print(f"Could not notify admin about deposit request {request_id}: {exc}")
        await query.message.reply_text(
            f"Request {request_id} was saved, but Telegram could not notify the administrator. "
            "Please contact support."
        )
        return ConversationHandler.END

    success_text = (
        f"✅ **የገቢ ጥያቄዎ ለአድሚን ተልኳል!**\n\n"
        f"🏦 **ባንክ:** {bank_name}\n"
        f"💵 **መጠን:** {amount:.2f} ETB\n\n"
        "Your request is pending the administrator's review."
    )

    is_registered = user.id in users_db
    await query.message.reply_text(success_text, reply_markup=get_keyboard(is_registered), parse_mode="Markdown")
    return ConversationHandler.END

# --- WITHDRAWAL FLOW ---

async def start_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📤 Withdrawals are being prepared and will open after the wagering rules and server-side balance checks are implemented."
    )
    return ConversationHandler.END

async def cancel_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_registered = user_id in users_db
    await update.message.reply_text(
        "ወደ ዋናው ማውጫ ተመልሰዋል::",
        reply_markup=get_keyboard(is_registered)
    )
    return ConversationHandler.END

async def handle_web_deposit_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("You are not authorized to review deposits.", show_alert=True)
        return

    _, request_id, decision = query.data.split("_", 2)
    status = {"approve": "approved", "reject": "rejected"}.get(decision)
    if not status:
        await query.answer("Invalid deposit decision.", show_alert=True)
        return

    try:
        reviewed = supabase_request(
            "POST",
            "rpc/review_wallet_deposit",
            {
                "request_id": request_id,
                "new_status": status,
                "reviewer_id": query.from_user.id,
            },
        )
        rows = supabase_request(
            "GET",
            "wallet_deposit_requests"
            f"?select=telegram_user_id&id=eq.{request_id}&limit=1",
        )
    except SupabaseError as exc:
        print(f"Could not review web deposit request: {exc}")
        await query.answer("Could not save the review. Please try again.", show_alert=True)
        return

    if not reviewed or not rows:
        await query.answer("This request has already been reviewed or no longer exists.", show_alert=True)
        return

    await context.bot.send_message(
        chat_id=rows[0]["telegram_user_id"],
        text=(
            f"Your deposit request {status}. "
            "This review does not credit the browser demo balance."
        ),
    )
    await query.answer("Review saved.")
    await query.edit_message_text(f"{query.message.text}\n\n{status.upper()} (request status only)")


# --- GENERAL MENU HANDLERS ---

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🎮 ጌም ይጫወቱ (PLAY)":
        play_text = "በቢንጎ ሀበሻ ቤት ይጫወቱ ይዝናኑ በሺዎች ያሸንፉ መልካም እድል ይሁንሎት"
        inline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 ጌም ይጫወቱ (PLAY)", web_app=WebAppInfo(url=WEB_APP_URL))]
        ])
        await update.message.reply_text(play_text, reply_markup=inline_keyboard)

    elif text == "💰 ሂሳብ":
        user_info = users_db.get(user_id, {"play_balance": 0.00, "main_balance": 0.00})
        balance_text = (
            "💰 **የሂሳብ ማረጋገጫ:**\n\n"
            f"🟢 **መጨወቻ ሂሳብ (Play):** {user_info['play_balance']:.2f} ETB\n"
            f"🟡 **ዋና ሂሳብ (Main):** {user_info['main_balance']:.2f} ETB"
        )
        await update.message.reply_text(balance_text, parse_mode="Markdown")

    elif text == "👤 ፕሮፋይል":
        user_info = users_db.get(user_id)
        if user_info:
            profile_text = (
                f"👤 **የእርስዎን ፕሮፋይል**\n\n"
                f"🔹 **ስም:** {user_info['name']}\n"
                f"🔹 **ስልክ:** {user_info['phone']}\n\n"
                f"💰 **መጨወቻ ሂሳብ:** {user_info['play_balance']:.2f} ETB\n"
                f"💰 **ዋና ሂሳብ:** {user_info['main_balance']:.2f} ETB\n\n"
                f"👇 ጌሙን ለመጀመር ከታች **'🎮 ጌም ይጫወቱ (PLAY)'** የሚለውን ይጫኑ::"
            )
        else:
            profile_text = "⚠️ እባክዎን አስቀድመው ይመዝገቡ!"
        await update.message.reply_text(profile_text, parse_mode="Markdown")

    elif text == "🆘 እርዳታ":
        help_text = (
            "💬 ማንኛውም ጥያቄ ወይም አስተያየት ካለዎት አድሚኑን በቴሌግራም ቀጥታ በ @bingohabesha ያናግሩ::\n\n"
            "📞 በተጨማሪም በቀጥታ በስልክ መስመራችን: 0953839231 ይደውሉልን::"
        )
        await update.message.reply_text(help_text)

    elif text == "📜 ደንቦች":
        rules_text = (
            "📜 **የጨዋታው ደንቦች:**\n\n"
            "1️⃣ **የሂሳብ ደንቦች:**\n"
            "🟢 **መጨወቻ ሂሳብ:** ካርድ ገዝቶ ለመጫወት ብቻ የሚያገለግል ሲሆን በstrictly ወጪ (Withdraw) ማድረግ አይቻልም።\n"
            "🟡 **ዋና ሂሳብ:** ተጨዋተው ሲያሸንፉ የሚገቡበት ሲሆን በምንም ሰዓት ወጪ ማድረግ ይችላሉ።\n\n"
            "2️⃣ **የገቢ ደንብ:**\n"
            "👉 ከ ቴሌብር ወደ ቴሌብር\n"
            "👉 ከ ሲቢኤ ብር ወደ ሲቢኤ ብር ብቻ ያስገቡ።\n\n"
            "3️⃣ **ማረጋገጫ:** ገቢ ሲያደርጉ የደረሰዎትን ትክክለኛ የባንክ (SMS/TxRef) በትክክል ያስገቡ።\n\n"
            "4️⃣ **እድሜ:** ተጫዋቾች ከ 21 ዓመት በላይ መሆን አለባቸው::"
        )
        await update.message.reply_text(rules_text, parse_mode="Markdown")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Set the TELEGRAM_BOT_TOKEN environment variable before starting the bot.")

    if not BOT_TOKEN:
        raise RuntimeError("Set the TELEGRAM_BOT_TOKEN environment variable before starting the bot.")
    if ADMIN_ID <= 0:
        raise RuntimeError("Set TELEGRAM_ADMIN_ID to the numeric Telegram ID authorized to review requests.")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .get_updates_read_timeout(30)
        .build()
    )

    deposit_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📩 ገቢ \(Deposit\)$"), start_deposit)],
        states={
            WAITING_FOR_DEP_AMOUNT: [
                CallbackQueryHandler(handle_bank_selection, pattern=r"^dep_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_deposit_amount),
            ],
            WAITING_FOR_DEP_PROOF: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_deposit_proof),
            ],
            CONFIRM_DEPOSIT: [
                CallbackQueryHandler(confirm_deposit_action, pattern=r"^confirm_deposit$")
            ]
        },
        fallbacks=[MessageHandler(filters.Regex(r"^🔙 ወደ ኋላ ተመልስ$"), cancel_transaction)],
        per_chat=True,
        per_user=True,
        per_message=False
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setpayment", set_payment_details))
    application.add_handler(CommandHandler("setcoupon", set_active_coupon))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(deposit_handler)
    application.add_handler(
        MessageHandler(filters.Regex(r"^📤 ወጪ \(Withdraw\)$"), start_withdraw)
    )
    application.add_handler(CallbackQueryHandler(handle_web_deposit_review, pattern=r"^webdep_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    application.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=5)

if __name__ == '__main__':
    main()
