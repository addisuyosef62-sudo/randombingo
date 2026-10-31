import os
import random
import string
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    ConversationHandler, filters, ContextTypes
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://your-mini-app-url.com")
ADMIN_ID = 7902432584

# Conversation states for Deposit
WAITING_FOR_DEP_AMOUNT, CONFIRM_DEPOSIT = range(2)

# Conversation states for Withdrawal
WAITING_FOR_WTH_ACC, WAITING_FOR_WTH_AMOUNT, CONFIRM_WITHDRAW = range(2, 5)

users_db = {}

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_registered = user_id in users_db
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

    random_password = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

    users_db[user_id] = {
        "name": first_name,
        "phone": contact.phone_number,
        "password": random_password,
        "play_balance": 15.00,
        "main_balance": 0.00
    }

    response_text = (
        f"🟢 ቢንጎ ⚪️ ሀበሻ\n\n"
        f"🎉 እንኳን ደስ አለዎት {first_name}! ምዝገባው ተጠናቋል::\n\n"
        f"👤 **የእርስዎን ፕሮፋይል**\n\n"
        f"🔹 **ስም:** {first_name}\n"
        f"🔹 **ስልክ:** {contact.phone_number}\n"
        f"🔑 **የይለፍ ቃል:** {random_password}\n\n"
        f"💰 **መጨወቻ ሂሳብ:** 15.00 ETB\n"
        f"💰 **ዋና ሂሳብ:** 0.00 ETB\n\n"
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
            InlineKeyboardButton("🏦 CBEBirr", callback_data="dep_cbebirr")
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

    bank_name = "TeleBirr" if query.data == "dep_telebirr" else "CBEBirr"
    context.user_data["selected_bank"] = bank_name

    payment_info_text = (
        f"🏦 **ባንክ:** {bank_name}\n\n"
        f"⚠️ **ማሳሰቢያ:** እባክዎ ከ {bank_name} ወደ {bank_name} ብቻ ያስገቡ!\n\n"
        f"እባክዎ ብሩን ወደዚህ አካውንት ያስገቡ:\n"
        f"👤 **ስም:** አብይ ዘለቀ\n"
        f"👉 **ቁጥር:** 0937584000\n\n"
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

    if not text.isdigit():
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ ቁጥር ብቻ ያስገቡ (ምሳሌ: 100):")
        return WAITING_FOR_DEP_AMOUNT

    amount = float(text)
    context.user_data["deposit_amount"] = amount
    bank_name = context.user_data.get("selected_bank", "Bank")

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
    user_info = users_db.get(user.id, {})
    phone = user_info.get("phone", "N/A")

    admin_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"admin_app_dep_{user.id}_{amount}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_rej_dep_{user.id}_{amount}")
        ]
    ])

    admin_msg = (
        f"📩 **አዲስ የገቢ (Deposit) ጥያቄ!**\n\n"
        f"👤 **ስም:** {user.first_name}\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"📱 **ስልክ:** {phone}\n"
        f"🏦 **ባንክ:** {bank_name}\n"
        f"💵 **መጠን:** {amount:.2f} ETB"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=admin_markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Error notifying admin: {e}")

    success_text = (
        f"✅ **የገቢ ጥያቄዎ ለአድሚን ተልኳል!**\n\n"
        f"🏦 **ባንክ:** {bank_name}\n"
        f"💵 **መጠን:** {amount:.2f} ETB\n\n"
        f"አድሚኑ ሲያረጋግጥልዎት ሂሳብዎ ላይ ገቢ ይደረጋል::"
    )

    is_registered = user.id in users_db
    await query.message.reply_text(success_text, reply_markup=get_keyboard(is_registered), parse_mode="Markdown")
    return ConversationHandler.END

# --- WITHDRAWAL FLOW ---

async def start_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = users_db.get(user_id)

    if not user_info:
        await update.message.reply_text("⚠️ እባክዎን አስቀድመው ይመዝገቡ!")
        return ConversationHandler.END

    withdraw_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📱 TeleBirr", callback_data="wth_telebirr"),
            InlineKeyboardButton("🏦 CBEBirr", callback_data="wth_cbebirr")
        ]
    ])
    await update.message.reply_text(
        "📤 **ወጪ (Withdraw)**\n\n"
        "የሚቀበሉበትን የባንክ አማራጭ ይምረጡ:",
        reply_markup=withdraw_keyboard
    )
    return WAITING_FOR_WTH_ACC

async def handle_withdraw_bank_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    bank_name = "TeleBirr" if query.data == "wth_telebirr" else "CBEBirr"
    context.user_data["wth_bank"] = bank_name

    await query.message.reply_text(
        f"🏦 **ባንክ:** {bank_name}\n\n"
        f"እባክዎ ገንዘቡ የሚላክበትን የ{bank_name} ስልክ/አካውንት ቁጥር ያስገቡ:",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    return WAITING_FOR_WTH_ACC

async def receive_withdraw_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🔙 ወደ ኋላ ተመልስ":
        return await cancel_transaction(update, context)

    context.user_data["wth_acc"] = text
    user_info = users_db.get(user_id, {})
    main_bal = user_info.get("main_balance", 0.0)

    await update.message.reply_text(
        f"🟡 **የእርስዎ ዋና ሂሳብ:** {main_bal:.2f} ETB\n\n"
        f"እባክዎ ወጪ ማድረግ የሚፈልጉትን የብር መጠን ያስገቡ:",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    return WAITING_FOR_WTH_AMOUNT

async def receive_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🔙 ወደ ኋላ ተመልስ":
        return await cancel_transaction(update, context)

    if not text.isdigit():
        await update.message.reply_text("⚠️ እባክዎን ትክክለኛ ቁጥር ብቻ ያስገቡ:")
        return WAITING_FOR_WTH_AMOUNT

    amount = float(text)
    user_info = users_db.get(user_id, {})
    main_bal = user_info.get("main_balance", 0.0)

    if amount > main_bal:
        await update.message.reply_text(
            f"❌ **የቦዘነ ሂሳብ!**\n\nያስገቡት መጠን ከተጫዋች ሂሳብዎ ({main_bal:.2f} ETB) በላይ ነው:: እባክዎ ድጋሚ ያስገቡ:",
            parse_mode="Markdown"
        )
        return WAITING_FOR_WTH_AMOUNT

    context.user_data["withdraw_amount"] = amount
    bank_name = context.user_data.get("wth_bank", "Bank")
    account_num = context.user_data.get("wth_acc", "N/A")

    confirm_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ወጪ አድርግ (Confirm)", callback_data="confirm_withdraw")]
    ])

    summary_text = (
        f"📌 **የወጪ ጥያቄ ማጠቃለያ:**\n\n"
        f"🏦 **ባንክ:** {bank_name}\n"
        f"💳 **አካውንት ቁጥር:** `{account_num}`\n"
        f"💵 **የወጪ መጠን:** {amount:.2f} ETB\n\n"
        f"ለማረጋገጥ ከታች ያለውን **'✅ ወጪ አድርግ (Confirm)'** የሚለውን ይጫኑ:"
    )

    await update.message.reply_text(
        summary_text,
        reply_markup=confirm_keyboard,
        parse_mode="Markdown"
    )
    return CONFIRM_WITHDRAW

async def confirm_withdraw_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    bank_name = context.user_data.get("wth_bank", "Bank")
    account_num = context.user_data.get("wth_acc", "N/A")
    amount = context.user_data.get("withdraw_amount", 0.0)
    user_info = users_db.get(user.id, {})
    phone = user_info.get("phone", "N/A")

    admin_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"admin_app_wth_{user.id}_{amount}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_rej_wth_{user.id}_{amount}")
        ]
    ])

    admin_msg = (
        f"📤 **አዲስ የወጪ (Withdraw) ጥያቄ!**\n\n"
        f"👤 **ስም:** {user.first_name}\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"📱 **ስልክ:** {phone}\n"
        f"🏦 **ባንክ:** {bank_name}\n"
        f"💳 **የተጠቃሚው አካውንት:** `{account_num}`\n"
        f"💵 **መጠን:** {amount:.2f} ETB"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=admin_markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Error notifying admin: {e}")

    is_registered = user.id in users_db
    await query.message.reply_text(
        f"✅ **የወጪ ጥያቄዎ ለአድሚን ተልኳል!**\n\n"
        f"🏦 **ባንክ:** {bank_name}\n"
        f"💳 **አካውንት:** {account_num}\n"
        f"💵 **መጠን:** {amount:.2f} ETB\n\n"
        f"አድሚኑ ክፍያውን ፈጽሞ ሲያረጋግጥልዎት ይላክልዎታል::",
        reply_markup=get_keyboard(is_registered),
        parse_mode="Markdown"
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

# --- ADMIN ACTIONS HANDLER ---

async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    action = data[1]       # app or rej
    txn_type = data[2]     # dep or wth
    target_user_id = int(data[3])
    amount = float(data[4])

    user_info = users_db.get(target_user_id)

    if action == "app":
        if txn_type == "dep":
            if user_info:
                user_info["play_balance"] += amount
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 **ገቢዎ ጸድቋል!**\n\n💰 **+{amount:.2f} ETB** በመጨወቻ ሂሳብዎ ላይ ተጨምሯል::",
                parse_mode="Markdown"
            )
            await query.edit_message_text(f"{query.message.text}\n\n✅ **APPROVED (+{amount:.2f} ETB Deposited)**")

        elif txn_type == "wth":
            if user_info and user_info["main_balance"] >= amount:
                user_info["main_balance"] -= amount
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"✅ **የወጪ ጥያቄዎ ጸድቋል!**\n\n💵 **{amount:.2f} ETB** ተልኮልዎታል::",
                    parse_mode="Markdown"
                )
                await query.edit_message_text(f"{query.message.text}\n\n✅ **APPROVED (-{amount:.2f} ETB Withdrawn)**")
            else:
                await query.edit_message_text(f"{query.message.text}\n\n❌ **FAILED: User has insufficient balance!**")

    elif action == "rej":
        txn_name = "የገቢ" if txn_type == "dep" else "የወጪ"
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"❌ **የ{txn_name} ጥያቄዎ ውድቅ ተደርጓል!**\n\nለበለጠ መረጃ አድሚኑን ያናግሩ::",
            parse_mode="Markdown"
        )
        await query.edit_message_text(f"{query.message.text}\n\n❌ **REJECTED**")

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
            CONFIRM_DEPOSIT: [
                CallbackQueryHandler(confirm_deposit_action, pattern=r"^confirm_deposit$")
            ]
        },
        fallbacks=[MessageHandler(filters.Regex(r"^🔙 ወደ ኋላ ተመልስ$"), cancel_transaction)],
        per_chat=True,
        per_user=True,
        per_message=False
    )

    withdraw_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📤 ወጪ \(Withdraw\)$"), start_withdraw)],
        states={
            WAITING_FOR_WTH_ACC: [
                CallbackQueryHandler(handle_withdraw_bank_selection, pattern=r"^wth_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_withdraw_account),
            ],
            WAITING_FOR_WTH_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_withdraw_amount)
            ],
            CONFIRM_WITHDRAW: [
                CallbackQueryHandler(confirm_withdraw_action, pattern=r"^confirm_withdraw$")
            ]
        },
        fallbacks=[MessageHandler(filters.Regex(r"^🔙 ወደ ኋላ ተመልስ$"), cancel_transaction)],
        per_chat=True,
        per_user=True,
        per_message=False
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(deposit_handler)
    application.add_handler(withdraw_handler)
    application.add_handler(CallbackQueryHandler(handle_admin_actions, pattern=r"^admin_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    application.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=5)

if __name__ == '__main__':
    main()
