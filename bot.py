import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)

# Configuration
BOT_TOKEN = "8679067966:AAF0pjyWGl2LdImXwv39akiC1xKT1BiZ1sc"
QUOTEX_REF_LINK = "https://broker-qx.pro/sign-up/?lid=356370"

# Set your Telegram User ID here
ADMIN_ID = 1146290731

# Database Storage
users_db = {} 
user_state = {}  # Tracks user state for capital input

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Risk Matrices (Calculations ke liye internal memory)
STANDARD_RISK = [0.01, 0.03, 0.07, 0.15]   # 1%, 3%, 7%, 15%
HIGH_TIER_RISK = [0.01, 0.02, 0.05, 0.10]  # 1%, 2%, 5%, 10% (After 7 wins)

# --- HELPER FUNCTIONS ---
def parse_capital_input(text):
    text = text.strip().lower()
    
    currency = "₹"
    if "$" in text or "usd" in text or "dollar" in text:
        currency = "$"
    elif "₹" in text or "rs" in text or "inr" in text or "rupee" in text or "rupees" in text:
        currency = "₹"

    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    if numbers:
        amount = float(numbers[0])
        return amount, currency
    return None, None

def get_trade_amount(user_id):
    user = users_db[user_id]
    cap = user['capital']
    step = user['step']
    is_high_tier = user['high_tier']
    
    risk_matrix = HIGH_TIER_RISK if is_high_tier else STANDARD_RISK
    pct = risk_matrix[step]
    amount = cap * pct
    return round(amount, 2), int(pct * 100)

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user already exists and is active
    if user_id in users_db and users_db[user_id]['expiry'] > datetime.now():
        if users_db[user_id]['capital'] > 0:
            await send_trade_signal(update, context, user_id)
            return
            
        user_state[user_id] = "AWAITING_CAPITAL"
        await update.message.reply_text(
            "💎 FREE ACCESS ACTIVE 💎\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💵 Apna Trading Capital / Balance enter karein:\n\n"
            "📌 *Examples:* 100$ ya 1000₹\n\n"
            "💡 *(Agar aapko capital change karna ho toh /capital command use karein)*", 
            parse_mode='Markdown'
        )
        return

    text = (
        "🚀 WELCOME TO QUOTEX RISK MANAGEMENT BOT 🚀\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Sahi Money Management se trading mein continuous loss se bachein aur daily profit target achieve karein.\n\n"
        "🎁 FREE ACCESS GET KARNE KE STEPS:\n"
        "1️⃣ Niche diye gaye link se Quotex Account create karein.\n"
        "2️⃣ Apni Quotex Trader ID is chat mein send karein.\n"
        "3️⃣ Admin approval ke baad aapko 7 Days Free Access mil jayega.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = [
        [InlineKeyboardButton("🌐 Register on Quotex", url=QUOTEX_REF_LINK)],
        [InlineKeyboardButton("📩 Send Trader ID Below", callback_data="guide_send_id")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def set_capital_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in users_db and users_db[user_id]['expiry'] > datetime.now():
        user_state[user_id] = "AWAITING_CAPITAL"
        await update.message.reply_text(
            "🔄 **CHANGE CAPITAL**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💵 Apna naya Trading Capital / Balance enter karein:\n\n"
            "📌 *Examples:* 200$ ya 5000₹",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Pehle apni Quotex ID verify karwayein ya /start dabayein.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Case 1: Waiting for Capital Input
    if user_state.get(user_id) == "AWAITING_CAPITAL" or (user_id in users_db and users_db[user_id]['capital'] == 0):
        capital_val, currency_sym = parse_capital_input(text)
        
        if capital_val is not None and capital_val > 0:
            users_db[user_id]['capital'] = capital_val
            users_db[user_id]['currency'] = currency_sym
            users_db[user_id]['step'] = 0
            users_db[user_id]['win_streak'] = 0
            users_db[user_id]['high_tier'] = False
            user_state[user_id] = None

            await update.message.reply_text(
                f"✅ Capital Updated Successfully!\n"
                f"💰 New Capital: {capital_val} {currency_sym}\n\n"
                f"💡 *(Jab chahein /capital command se ise phir se badal sakte hain)*", 
                parse_mode='Markdown'
            )
            await send_trade_signal(update, context, user_id)
            return
        else:
            await update.message.reply_text("⚠️ Please enter a valid capital amount (e.g. 100$ or 1000₹).", parse_mode='Markdown')
            return

    # Case 2: Quotex Trader ID Submission
    if text.isdigit() and len(text) >= 5:
        if user_id in users_db and users_db[user_id]['expiry'] > datetime.now():
            await update.message.reply_text("✅ Aapka account pehle se Approved hai!")
            if users_db[user_id]['capital'] == 0:
                user_state[user_id] = "AWAITING_CAPITAL"
                await update.message.reply_text("💵 Apna Capital Amount likhkar bhejein (e.g. 100$ ya 1000₹):")
            else:
                await send_trade_signal(update, context, user_id)
            return

        # Send request to Admin
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve (7 Days)", callback_data=f"approve_{user_id}_{text}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📥 NEW VERIFICATION REQUEST\n"
                 f"━━━━━━━━━━━━━━━━━━━\n"
                 f"👤 User: @{update.effective_user.username}\n"
                 f"🆔 Telegram ID: {user_id}\n"
                 f"🔢 Quotex ID: {text}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        await update.message.reply_text(
            "⏳ Verification Pending!\n"
            "Aapki Quotex Trader ID check ho rahi hai. Admin approval milte hi bot start ho jayega.",
            parse_mode='Markdown'
        )

async def admin_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    action = data[0]
    
    if action == "guide":
        await query.message.reply_text("👉 Simply Apni Quotex Trader ID (Numbers) yahan type karke message send karein!")
        return

    target_user_id = int(data[1])

    if action == "approve":
        qx_id = data[2]
        expiry_date = datetime.now() + timedelta(days=7)
        
        users_db[target_user_id] = {
            'qx_id': qx_id,
            'expiry': expiry_date,
            'capital': 0,
            'currency': '$',
            'step': 0,
            'win_streak': 0,
            'high_tier': False
        }
        
        user_state[target_user_id] = "AWAITING_CAPITAL"
        
        await query.edit_message_text(text=f"✅ Approved User {target_user_id} for 7 Days.")
        
        await context.bot.send_message(
            chat_id=target_user_id,
            text="🎉 CONGRATULATIONS! ACCESS GRANTED 🎉\n"
                 "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                 "✅ Aapki Quotex ID approve ho gayi hai.\n"
                 "🎁 Free Access: 7 Days Active\n\n"
                 "💵 Apna Trading Capital/Balance likhkar send karein:\n"
                 "*(Examples: 100$ ya 1000₹)*",
            parse_mode='Markdown'
        )
    elif action == "reject":
        await query.edit_message_text(text=f"❌ Rejected User {target_user_id}.")
        await context.bot.send_message(
            chat_id=target_user_id,
            text="❌ Verification Failed!\n"
                 "Aapki Quotex Trader ID verified nahi hui. Sahi ID bhejien ya naya account register karein.",
            parse_mode='Markdown'
        )

async def send_trade_signal(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    amount, pct = get_trade_amount(user_id)
    curr = users_db[user_id]['currency']
    streak = users_db[user_id]['win_streak']

    text = (
        f"📊 TRADE MANAGEMENT SIGNAL\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Total Capital: {users_db[user_id]['capital']} {curr}\n"
        f"🔥 Continuous Wins: {streak}\n\n"
        f"👉 NEXT TRADE AMOUNT ({pct}%): {amount} {curr}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *(Capital change karne ke liye /capital type karein)*\n"
        f"Select trade result after completion:"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ WIN", callback_data="trade_win"),
            InlineKeyboardButton("❌ LOSS", callback_data="trade_loss")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode='Markdown')

async def trade_result_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in users_db:
        await query.edit_message_text("❌ Session Expired. Type /start to restart.")
        return

    result = query.data
    user = users_db[user_id]

    if result == "trade_win":
        user['win_streak'] += 1
        user['step'] = 0

        if user['win_streak'] >= 7 and not user['high_tier']:
            user['high_tier'] = True
            await query.edit_message_text(
                "🎉 7 CONTINUOUS WINS ACHIEVED! 🎉\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🔥 Money Management Strategy Upgraded!",
                parse_mode='Markdown'
            )
            await send_trade_signal(update, context, user_id)
            return
        else:
            await query.edit_message_text("✅ WIN! Profit secured. Resetting back to 1% Base Trade.")

    elif result == "trade_loss":
        user['win_streak'] = 0
        user['step'] += 1

        if user['step'] >= 4:
            user['step'] = 0
            user['high_tier'] = False
            await query.edit_message_text(
                "🛑 STOP LOSS (SL) HIT! 🛑\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "❌ 4 Back-to-Back Losses ho chuke hain.\n"
                "⚠️ Risk mitigation active: Step reset to 1% Base Amount.",
                parse_mode='Markdown'
            )
            await send_trade_signal(update, context, user_id)
            return
        else:
            await query.edit_message_text("❌ LOSS! Moving to next recovery step.")

    await send_trade_signal(update, context, user_id)

# --- MAIN RUNNER ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("capital", set_capital_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(admin_button_callback, pattern="^(approve|reject|guide)_"))
    app.add_handler(CallbackQueryHandler(trade_result_callback, pattern="^trade_"))

    print("Quotex Management Bot starts successfully...")
    app.run_polling()
