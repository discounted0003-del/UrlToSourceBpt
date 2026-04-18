# ======================= IMPORTS =======================
import time, os, zipfile, requests, asyncio, pickle
from io import BytesIO
from datetime import datetime, timedelta, timezone 

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

import qrcode 
from telegram import (
    Update,
    InputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMemberUpdated,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

# ======================= CONFIG =======================
BOT_TOKEN = "8538798053:AAGIQT6fFNekXhB_9U7mJXghXFm3BNzLnws" # Apna Token Sahi Karein

OWNER_ID = 6068463116
OWNER_USERNAME = "Synaxchatrobot"
PUBLIC_GROUP = "@synaxLookup"

UPI_ID = "AbhishekXSynax@fam"

PREMIUM_PRICE = 49      # Normal Price
OFFER_PRICE = 39        # Flash Sale Price
SUNDAY_PRICE = 29       # Sunday Special Price
OFFER_CODE = "SAVE39"

FREE_DAILY_LIMIT = 2
PREMIUM_DAYS = 30

# ======================= PERMANENT DATABASE SYSTEM =======================
DB_FILE = "bot_data.pkl"

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "rb") as f:
                return pickle.load(f)
        except:
            pass
    return {
        "users": set(),
        "groups": set(),
        "premium": {},
        "usage": {},
        "total": {},
        "welcome": {},
        "user_names": {},
        "redeem_codes": {} 
    }

def save_data():
    data = {
        "users": ALL_USERS,
        "groups": ALL_GROUPS,
        "premium": PREMIUM_USERS,
        "usage": USER_USAGE,
        "total": TOTAL_USAGE,
        "welcome": GROUP_WELCOME,
        "user_names": ALL_USER_NAMES,
        "redeem_codes": REDEEM_CODES
    }
    try:
        with open(DB_FILE, "wb") as f:
            pickle.dump(data, f)
    except Exception as e:
        print(f"Save Error: {e}")

# --- Load Data on Start ---
db = load_data()
ALL_USERS = db.get("users", set())
ALL_GROUPS = db.get("groups", set())
PREMIUM_USERS = db.get("premium", {})
USER_USAGE = db.get("usage", {})
TOTAL_USAGE = db.get("total", {})
GROUP_WELCOME = db.get("welcome", {})
ALL_USER_NAMES = db.get("user_names", {})
REDEEM_CODES = db.get("redeem_codes", {}) 

# Temporary Memory
OFFER_TIMERS = {}
EXPIRY_NOTIFIED = set() 
BANNED_USERS = set()    
WAITING_SCREENSHOT = set()
WAITING_SUPPORT = set()
ADMIN_REPLY_TRACK = {} 
LAST_NORMAL_OFFER_TIME = 0 

# ======================= HELPERS =======================
def today():
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).date()

def is_sunday():
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%A") == "Sunday"

def is_premium(uid):
    exp = PREMIUM_USERS.get(uid)
    if not exp:
        return False
    if time.time() > exp:
        PREMIUM_USERS.pop(uid, None)
        save_data()
        return False
    return True

def can_use(uid):
    if uid == OWNER_ID or is_premium(uid):
        return True

    data = USER_USAGE.get(uid)
    if not data or data["date"] != today():
        USER_USAGE[uid] = {"date": today(), "count": 0}
        save_data()
    
    if USER_USAGE[uid]["count"] < FREE_DAILY_LIMIT:
        return True
        
    return False

def update_usage(uid):
    if uid != OWNER_ID and not is_premium(uid):
        USER_USAGE[uid]["count"] += 1
    
    if uid not in TOTAL_USAGE: TOTAL_USAGE[uid] = 0
    TOTAL_USAGE[uid] += 1
    save_data()

async def is_joined(context, uid):
    try:
        m = await context.bot.get_chat_member(PUBLIC_GROUP, uid)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

# --- ADMIN CHECKER HELPER ---
async def is_admin(update, context):
    """Check if user is Admin in the group or Owner"""
    try:
        if update.effective_user.id == OWNER_ID:
            return True
        user = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        if user.status in ['administrator', 'creator']:
            return True
    except:
        pass
    return False

# ======================= NEW FEATURES: REDEEM CODE SYSTEM =======================

async def generate_redeem_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner creates a code: /gen <code_name> <days> <max_users>"""
    if update.effective_user.id != OWNER_ID: return

    try:
        code_name = context.args[0].upper()
        days = int(context.args[1])
        max_users = int(context.args[2])

        if code_name in REDEEM_CODES:
            await update.message.reply_text(f"⚠️ Code `{code_name}` already exists!", parse_mode="Markdown")
            return

        REDEEM_CODES[code_name] = {
            "days": days,
            "max_users": max_users,
            "used_count": 0,
            "created_at": time.time()
        }
        save_data()

        msg = (
            f"✅ **Redeem Code Created!**\n\n"
            f"🏷 **Code Name:** `{code_name}`\n"
            f"⏳ **Validity:** {days} Days\n"
            f"👥 **Max Claims:** {max_users}\n\n"
            f"👉 Users can use: `/redeem {code_name}`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except (IndexError, ValueError):
        await update.message.reply_text("❌ **Error:** Format is `/gen <name> <days> <max_users>`\nExample: `/gen SALE30 30 50`")

async def redeem_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User redeems a code: /redeem <code_name>"""
    uid = update.effective_user.id
    if uid in BANNED_USERS: return

    try:
        code_name = context.args[0].upper()
        code_data = REDEEM_CODES.get(code_name)

        # 1. Check if code exists
        if not code_data:
            await update.message.reply_text("❌ **Invalid Code!**\nYeh code exist hi nahi karta.")
            return
        
        # 2. Check if code is expired or max limit reached
        if code_data["used_count"] >= code_data["max_users"]:
            await update.message.reply_text("❌ **Code Expired!**\nIs code ki limit khatam ho chuki hai.")
            return

        # 3. Grant Premium
        current_time = time.time()
        added_seconds = code_data["days"] * 86400
        
        # Logic: Extend if already premium, else new
        if uid in PREMIUM_USERS and PREMIUM_USERS[uid] > current_time:
            PREMIUM_USERS[uid] += added_seconds
        else:
            PREMIUM_USERS[uid] = current_time + added_seconds

        # 4. Update Code Usage
        REDEEM_CODES[code_name]["used_count"] += 1
        save_data()

        # 5. Success Message
        await update.message.reply_text(
            f"🎉 **Redeem Successful!**\n\n"
            f"💎 **+{code_data['days']} Days Added!**\n"
            f"🚀 Code Used: `{code_name}`\n"
            f"✅ Enjoy Premium Features.",
            parse_mode="Markdown"
        )

    except IndexError:
        await update.message.reply_text("⚠️ Usage: `/redeem <code_name>`")

async def list_redeem_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner sees all codes and stats"""
    if update.effective_user.id != OWNER_ID: return

    if not REDEEM_CODES:
        await update.message.reply_text("📭 No active redeem codes found.")
        return

    msg = "📊 **ACTIVE REDEEM CODES**\n\n"
    
    for code, data in REDEEM_CODES.items():
        remaining = data["max_users"] - data["used_count"]
        status = "✅ Active" if remaining > 0 else "❌ Full"
        msg += (
            f"🏷 **Code:** `{code}`\n"
            f"⏳ **Days:** {data['days']}\n"
            f"👥 **Usage:** {data['used_count']}/{data['max_users']}\n"
            f"📢 **Status:** {status}\n\n"
        )
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def revoke_redeem_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner deletes a code"""
    if update.effective_user.id != OWNER_ID: return
    
    try:
        code_name = context.args[0].upper()
        if code_name in REDEEM_CODES:
            del REDEEM_CODES[code_name]
            save_data()
            await update.message.reply_text(f"🗑 Code `{code_name}` deleted successfully.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Code not found.")
    except IndexError:
        await update.message.reply_text("❌ Usage: `/delcode <name>`")

async def reset_user_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/Owner can reset a user's daily limit"""
    if update.effective_user.id != OWNER_ID: return
    try:
        uid = int(context.args[0])
        if uid in USER_USAGE:
            USER_USAGE[uid]["count"] = 0
            save_data()
            await update.message.reply_text(f"✅ Reset daily limit for `{uid}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ User not in usage database.")
    except:
        await update.message.reply_text("❌ Usage: /reset <uid>")

# ======================= PREVIOUS FEATURES =======================

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saves Chat/Channel ID when bot is added or sees activity"""
    chat_id = update.effective_chat.id
    if chat_id not in ALL_GROUPS:
        ALL_GROUPS.add(chat_id)
        save_data()

async def anti_admin_protection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Punishes admin for kicking members (Group Only)"""
    result = update.chat_member
    if not result or update.effective_chat.type == "channel": return
    if result.new_chat_member.status in ["kicked", "left"]:
        actor_id = result.from_user.id
        if actor_id != OWNER_ID:
            try:
                await context.bot.promote_chat_member(chat_id=update.effective_chat.id, user_id=actor_id, can_post_messages=False, can_invite_users=False, can_delete_messages=False, can_restrict_members=False, can_promote_members=False)
                await context.bot.send_message(update.effective_chat.id, f"🚫 **Security Alert!** Admin `{actor_id}` ne member nikala, permissions hata di gayi.")
            except: pass

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner can promote user by Reply OR Username OR User ID"""
    if update.effective_user.id != OWNER_ID: return
    
    target_id = None
    
    # 1. Logic for Reply
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    
    # 2. Logic for Username or ID (e.g., /promote @Rahul or /promote 12345)
    elif context.args:
        arg = context.args[0]
        if arg.isdigit():
            target_id = int(arg)
        else:
            username_to_find = arg.replace("@", "").lower()
            # Bot searches in its database ALL_USER_NAMES
            for uid, info in ALL_USER_NAMES.items():
                if f"(@{username_to_find})" in info.lower():
                    target_id = uid
                    break
    
    if not target_id:
        await update.message.reply_text("⚠️ User ko pehchan nahi paya. Ya toh message par Reply karein ya sahi @username likhein (User ne bot ko kam se kam ek baar start kiya hona chahiye).")
        return

    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id, 
            target_id, 
            can_manage_chat=True, 
            can_post_messages=True, 
            can_delete_messages=True, 
            can_invite_users=True, 
            can_restrict_members=True, 
            can_pin_messages=True, 
            can_promote_members=True
        )
        await update.message.reply_text(f"✅ User `{target_id}` ab is chat ka Admin hai!")
    except:
        await update.message.reply_text("❌ Error: Bot ko group mein 'Add Admins' permission chahiye.")

# ======================= START =======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user
    
    # Save user details for dashboard (FIXED: Updates every time)
    u_name = f"@{user.username}" if user.username else "No Username"
    ALL_USER_NAMES[uid] = f"{user.full_name} ({u_name})"
    save_data()

    if uid in BANNED_USERS:
        await update.message.reply_text("🚫 **You are BANNED!**", parse_mode="Markdown")
        return

    # --- NEW: SEND NEW USER DATA TO OWNER ---
    if uid not in ALL_USERS:
        ALL_USERS.add(uid)
        save_data()

        try:
            log_msg = (
                f"🔔 **NEW USER ALERT!**\n\n"
                f"👤 **Name:** {user.full_name}\n"
                f"🆔 **UID:** `{uid}`\n"
                f"🔗 **Username:** {u_name}"
            )
            await context.bot.send_message(OWNER_ID, log_msg, parse_mode="Markdown")
        except:
            pass
    # ---------------------------------------

    if not await is_joined(context, uid):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Join Group", url="https://t.me/SynaxLookup")],
            [InlineKeyboardButton("✅ Check Join", callback_data="check_join")]
        ])
        await update.message.reply_text(
            "👥 *Pehle Group Join Karo*\n"
            "🔓 *Tabhi Features Unlock Honge*\n\n"
            "🌐 Without group join,\n"
            "🚫 URL extract nahi kar sakte",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    await update.message.reply_text(
        "🎉 **Welcome to URL Extractor!**\n\n"
        "🔗 **Link bhejo** → ZIP file milegi\n"
        f"🎁 **Free Plan:** {FREE_DAILY_LIMIT} files/day\n"
        "💎 **Premium:** Unlimited Access\n\n"
        "👇 **Menu:**\n"
        "/buy - Premium kharidein\n"
        "/redeem <code> - Apply Code\n"
        "/status - Apna plan dekhein\n"
        "/support - Help center",
        parse_mode="Markdown"
    )

async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if await is_joined(context, q.from_user.id):
        await q.message.reply_text(
            "✅ Group Join Successful!\n"
            "🚀 Ab aap bot use kar sakte ho\n\n"
            "🤖 Bot me URL paste karo\n"
            "🌐 Don’t worry, tension mat lo 😎\n"
            "📂 File ready mil jaegi — instantly!"
        )
    else:
        await q.message.reply_text(
            "❌ Group Join Required!\n"
            "🔒 Access Locked\n\n"
            "👉 Pehle group join karo,\n"
            "🌐 Phir URL extract kar paoge 🚀"
        )


# ======================= STATUS & CHECK (UPDATED WITH MIN/HRS/DAYS) =======================
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in BANNED_USERS: return

    if is_premium(uid):
        exp_timestamp = PREMIUM_USERS[uid]
        ist = timezone(timedelta(hours=5, minutes=30))
        dt_object = datetime.fromtimestamp(exp_timestamp, ist)
        
        # FIXED DATE FORMAT: 25 December 2025 at 09:30 AM
        exp_date_str = dt_object.strftime("%d %B %Y at %I:%M %p")
        
        remaining_seconds = exp_timestamp - time.time()
        
        # --- DAYS CALCULATION ADDED ---
        days = int(remaining_seconds // 86400)
        hours = int((remaining_seconds % 86400) // 3600)
        minutes = int((remaining_seconds % 3600) // 60)
        
        if days < 0: days, hours, minutes = 0, 0, 0
        
        count = TOTAL_USAGE.get(uid, 0)
        
        await update.message.reply_text(
            f"💎 **PREMIUM MEMBER**\n"
            f"📅 **Expiry:** {exp_date_str}\n"
            f"⏳ **Time Left:** {days} Days {hours}h {minutes}m\n"
            f"🔢 **Total Extracts:** {count}",
            parse_mode="Markdown"
        )
    else:
        used = USER_USAGE.get(uid, {}).get("count", 0)
        await update.message.reply_text(f"📊 Used: {used}/{FREE_DAILY_LIMIT}")

async def admin_check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        uid = int(context.args[0])
        
        if is_premium(uid):
            exp_timestamp = PREMIUM_USERS[uid]
            ist = timezone(timedelta(hours=5, minutes=30))
            dt_object = datetime.fromtimestamp(exp_timestamp, ist)
            exp_date_str = dt_object.strftime("%d %B %Y at %I:%M %p")
            
            remaining_seconds = exp_timestamp - time.time()
            days_left = int(remaining_seconds / (24 * 3600))
            if days_left < 0: days_left = 0
            
            msg = (
                f"👤 **User:** `{uid}`\n"
                f"💎 **Status:** PREMIUM\n"
                f"⏳ **Days Left:** {days_left}\n"
                f"📅 **Expiry:** {exp_date_str}"
            )
        else:
            used = USER_USAGE.get(uid, {}).get("count", 0)
            msg = (
                f"👤 **User:** `{uid}`\n"
                f"⚪ **Status:** FREE\n"
                f"📊 **Today Used:** {used}/{FREE_DAILY_LIMIT}"
            )
        
        await update.message.reply_text(msg, parse_mode="Markdown")
    except:
        await update.message.reply_text("⚠️ **Use:** `/check <uid>`", parse_mode="Markdown")

# ======================= BUY (FIXED WITH SMART FALLBACK) =======================
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in BANNED_USERS: return
    
    current_time = time.time()
    offer_end_time = OFFER_TIMERS.get(uid, 0)
    
    if is_sunday():
        amount = SUNDAY_PRICE
        caption_text = (
            f"🔥 **SUNDAY SPECIAL OFFER!** 🔥\n"
            f"💰 **Price: ₹{amount} ONLY** (Huge Discount)\n"
            f"🚀 **Validity:** 30 Days Premium\n"
            f"⏳ Sirf aaj ke liye valid!"
        )
    elif current_time < offer_end_time:
        amount = OFFER_PRICE
        minutes_left = int((offer_end_time - current_time) / 60)
        caption_text = (
            f"⚡ **FLASH SALE ACTIVE!** ⚡\n"
            f"💰 **Price: ₹{amount}** (Save 20%)\n"
            f"⏳ Ends in: {minutes_left} Minutes\n"
            f"🏷 Code: `{OFFER_CODE}` applied!"
        )
    else:
        amount = PREMIUM_PRICE
        caption_text = (
            f"💎 **PREMIUM PLAN**\n"
            f"💰 **Price: ₹{amount}** / Month\n"
            f"🚀 Unlimited Extracts\n"
            f"📂 Bulk Access"
        )

    # --- SMART QR LOGIC ---
    try:
        # 1. Try to Generate QR Image
        # We import constants here just to be safe
        from qrcode import constants
        qr = qrcode.QRCode(
            version=1,
            error_correction=constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        upi_link = f"upi://pay?pa={UPI_ID}&pn=URLSourceZIP&am={amount}&cu=INR"
        qr.add_data(upi_link)
        qr.make(fit=True)
        
        # CRITICAL: This requires PIL (Pillow). 
        img = qr.make_image(fill_color="black", back_color="white")
        
        # If successful, convert to BytesIO
        bio = BytesIO()
        img.save(bio, "PNG")
        bio.seek(0)
        
        # Keyboard
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📸 Send Screenshot", callback_data="send_ss")]
        ])

        # Send Photo
        await update.message.reply_photo(
            photo=bio,
            filename="upi_qr.png", 
            caption=caption_text + "\n\n👇 Scan QR or Send Screenshot:",
            parse_mode="Markdown",
            reply_markup=kb
        )
        
    except Exception as e:
        # --- FALLBACK IF QR FAILS (PIL MISSING OR OTHER ERROR) ---
        print(f"QR Image Error: {e}. Switching to Button Mode.")

        # UPI Link for button
        upi_link = f"upi://pay?pa={UPI_ID}&pn=URLSourceZIP&am={amount}&cu=INR"
        
        # Keyboard with Pay Button
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Pay Now (Open App)", url=upi_link)],
            [InlineKeyboardButton("📸 Send Screenshot", callback_data="send_ss")]
        ])

        # Send Text Message instead
        await update.message.reply_text(
            f"{caption_text}\n\n"
            f"🆔 **UPI ID:** `{UPI_ID}`\n"
            f"👇 Click 'Pay Now' button below to pay.",
            parse_mode="Markdown",
            reply_markup=kb
        )

async def ask_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    WAITING_SCREENSHOT.add(update.callback_query.from_user.id)
    await update.message.reply_text("📸 Screenshot bhejo")

# ======================= CALLBACK HANDLER (ONE-CLICK LOGIC) =======================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()

    if data == "check_join":
        if await is_joined(context, q.from_user.id):
            await q.message.reply_text(
                "✅ Group Join Successful!\n"
                "🚀 Ab aap bot use kar sakte ho\n\n"
                "🤖 Bot me URL paste karo\n"
                "🌐 Don’t worry, tension mat lo 😎\n"
                "📂 File ready mil jaegi — instantly!"
            )
        else:
            await q.message.reply_text(
                "❌ Group Join Required!\n"
                "🔒 Access Locked\n\n"
                "👉 Pehle group join karo,\n"
                "🌐 Phir URL extract kar paoge 🚀"
            )

    elif data == "send_ss":
        WAITING_SCREENSHOT.add(q.from_user.id)
        await q.message.reply_text("📸 Screenshot bhejo")


    # ONE-CLICK APPROVE (TOTAL DATE SYSTEM)
    elif data.startswith("adm_ap_"):
        uid = int(data.split("_")[2])
        current_time = time.time()
        added_seconds = PREMIUM_DAYS * 86400

        if uid in PREMIUM_USERS and PREMIUM_USERS[uid] > current_time:
            PREMIUM_USERS[uid] += added_seconds
            msg_type = "extended"
            user_msg = (
    "🎉 **Plan Extended Successfully!** ✅\n\n"
    "💎 **+30 Days Added to Your Plan**\n\n"
    "⏳ Aapke plan mein **30 days successfully add ho gaye hain**.\n"
    "Ab aap **bina kisi interruption ke saare premium features** use kar sakte ho.\n\n"
    "📊 **Please check your plan status**\n"
    "🚀 **Enjoy uninterrupted premium access!**"
)

        else:
            PREMIUM_USERS[uid] = current_time + added_seconds
            msg_type = "activated"
            user_msg = (
    "🎉 **Payment Accepted Successfully!** ✅\n\n"
    "💎 **Premium Activated — Unlimited Access**\n\n"
    "🎁 **30 Days Premium Access Activated**\n"
    "Aapko **pura unlimited access 30 days ke liye mil gaya hai**.\n"
    "Saare premium features ab **30 din tak bina kisi restriction ke use** kar sakte ho.\n\n"
    "⏳ **Validity:** 30 Days\n"
    "🚀 **Enjoy Premium Experience!**"
)

            
        save_data()
        await context.bot.send_message(uid, user_msg, parse_mode="Markdown")
        
        # Edit Owner Message
        try:
            await q.edit_message_caption(caption=f"✅ **User {uid} Approved!** ({msg_type})")
        except:
            pass

    # ONE-CLICK REJECT
    elif data.startswith("adm_rj_"):
        uid = int(data.split("_")[2])
        await context.bot.send_message(
            uid,
            "❌ Payment Verification Failed 🚫\n"
            "📌 Status: Payment Rejected ❌\n\n"
            "⚠️ Fake Payment Screenshot Detected\n\n"
            "Aapke dwara upload kiya gaya payment\n"
            "screenshot galat / fake paya gaya hai.\n\n"
            "Kripya karke dobara\n"
            "✅ REAL & SUCCESSFUL PAYMENT\n"
            "ka clear screenshot upload karein.\n\n"
            "⚠️ Fake payment screenshot accept nahi kiya jaata.\n\n"
            "🔄 Re-Upload Payment Screenshot"
        )
        await q.edit_message_caption(caption=f"❌ User {uid} Rejected!")
        
    # ONE-CLICK REPLY
    elif data.startswith("adm_rep_"):
        uid = int(data.split("_")[2])
        ADMIN_REPLY_TRACK[OWNER_ID] = uid
        await context.bot.send_message(OWNER_ID, f"✍️ Type reply for user `{uid}`:")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in WAITING_SCREENSHOT:
        return
    WAITING_SCREENSHOT.remove(uid)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"adm_ap_{uid}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"adm_rj_{uid}")]
    ])
    await context.bot.send_photo(
        OWNER_ID,
        update.message.photo[-1].file_id,
        caption=f"💳 **NEW PAYMENT**\nUser: `{uid}`\n\nSelect Action Below:",
        reply_markup=kb
    )
    await update.message.reply_text("⏳ Payment verification pending... Admin ko bheja gaya hai.")

# ======================= SUPPORT =======================
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in BANNED_USERS: return

    WAITING_SUPPORT.add(uid)
    await update.message.reply_text(
        "🆘 SUPPORT CENTER\n\n"
        "✍️ Apni problem clearly likho\n"
        "📸 Screenshot bhejo (agar ho)\n\n"
        "Team jaldi reply karegi ✅"
    )

# ======================= ADMIN COMMANDS =======================
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    uid = int(context.args[0])
    current_time = time.time()
    added_seconds = PREMIUM_DAYS * 86400

    if uid in PREMIUM_USERS and PREMIUM_USERS[uid] > current_time:
        PREMIUM_USERS[uid] += added_seconds
        msg_type = "extended"
    else:
        PREMIUM_USERS[uid] = current_time + added_seconds
        msg_type = "activated"

    OFFER_TIMERS.pop(uid, None)
    if uid in EXPIRY_NOTIFIED:
        EXPIRY_NOTIFIED.remove(uid)

    save_data()

    if msg_type == "extended":
        await context.bot.send_message(
            uid,
            "🎉 **Plan Extended Successfully!** ✅\n\n"
            "💎 **+30 Days Added to Your Plan**\n\n"
            "⏳ Aapke plan mein **30 days successfully add** ho gaye hain.\n"
            "Ab aap bina kisi interruption ke saare **premium features** use kar sakte ho.\n\n"
            "🚀 **Enjoy uninterrupted premium access!**",
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"✅ User {uid} Plan Extended.")

    else:
        await context.bot.send_message(
            uid,
            "🎉 **Payment Accepted Successfully!** ✅\n\n"
            "💎 **Premium Activated — Unlimited Access**\n\n"
            "🎁 **30 Days Premium Access Activated**\n"
            "Aapko pura unlimited access **30 din** ke liye mil gaya hai.\n"
            "Saare premium features ab **30 din tak bina kisi restriction** ke use kar sakte ho.\n\n"
            "⏳ **Validity:** 30 Days\n"
            "🚀 **Enjoy Premium Experience!**",
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"✅ User {uid} Approved.")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        uid = int(context.args[0])
        await context.bot.send_message(
    uid,
    "╔══════════════════════════════════════════╗\n"
    "║        🚫 FAKE PAYMENT NOT ALLOWED 🚫        ║\n"
    "╚══════════════════════════════════════════╝\n\n"
    "❌ Random photo, gallery image ya\n"
    "galat screenshot upload bilkul mat karein.\n\n"
    "📸 Sirf REAL PAYMENT ka CLEAR SCREENSHOT\n"
    "hi upload karein.\n\n"
    "✔️ Screenshot me payment details\n"
    "clearly dikhni chahiye.\n"
    "❌ Random photo upload karne par\n"
    "payment turant REJECT ho jaayega.\n\n"
    "⚙️ Yeh AUTOMATIC SYSTEM hai.\n"
    "Sahi payment screenshot upload karte hi\n"
    "premium automatically activate ho jaayega.\n\n"
    "🙏 Kripya time waste na karein aur\n"
    "sirf sahi payment screenshot hi upload karein.",
    parse_mode="Markdown"
)
        await update.message.reply_text(f"❌ User {uid} Rejected.")
    except:
        pass

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        uid = int(context.args[0])
        BANNED_USERS.add(uid)
        await context.bot.send_message(uid, "🚫 **You have been BANNED from using this bot.**")
        await update.message.reply_text(f"✅ User {uid} is now BANNED.")
    except:
        await update.message.reply_text("❌ Use: /ban <id>")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        uid = int(context.args[0])
        if uid in BANNED_USERS:
            BANNED_USERS.remove(uid)
            await context.bot.send_message(uid, "✅ **You have been UNBANNED.**")
            await update.message.reply_text(f"✅ User {uid} is now UNBANNED.")
        else:
            await update.message.reply_text("⚠️ User was not banned.")
    except:
        await update.message.reply_text("❌ Use: /unban <id>")

# ======================= UPDATED ALL-IN-ONE BROADCAST =======================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    msg = update.effective_message
    
    raw_text = ""
    media_type = "Text Message"
    
    if msg.text: 
        raw_text = " ".join(context.args)
    elif msg.caption: 
        raw_text = msg.caption.replace("/broadcast", "").strip()

    if msg.photo: media_type = "Photo 📸"
    elif msg.video: media_type = "Video 🎥"
    elif msg.document: media_type = "File/Document 📂"

    if not raw_text and not msg.photo and not msg.video and not msg.document:
        await update.message.reply_text("⚠️ Use: /broadcast Message | Button Name | Link")
        return

    # Button Logic Parsing
    content = raw_text
    reply_markup = None
    if "|" in raw_text:
        parts = [p.strip() for p in raw_text.split("|")]
        content = parts[0]
        if len(parts) >= 3:
            btn_name = parts[1]
            btn_url = parts[2]
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(btn_name, url=btn_url)]])

    status_report = await update.message.reply_text(f"🚀 **Broadcasting {media_type}...**")

    success, fail = 0, 0
    all_targets = set(list(ALL_USERS) + list(ALL_GROUPS))

    for target in all_targets:
        if target in BANNED_USERS: continue
        try:
            if msg.photo:
                await context.bot.send_photo(target, photo=msg.photo[-1].file_id, caption=content, reply_markup=reply_markup, parse_mode="Markdown")
            elif msg.video:
                await context.bot.send_video(target, video=msg.video.file_id, caption=content, reply_markup=reply_markup, parse_mode="Markdown")
            elif msg.document:
                await context.bot.send_document(target, document=msg.document.file_id, caption=content, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                await context.bot.send_message(target, f"📢 **ANNOUNCEMENT**\n\n{content}", reply_markup=reply_markup, parse_mode="Markdown")
            
            success += 1
            await asyncio.sleep(0.08)
        except:
            fail += 1
            
    await status_report.edit_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"📊 **Type:** {media_type}\n"
        f"🚀 **Success:** {success}\n"
        f"❌ **Failed:** {fail}"
    )

# ======================= ALL-IN-ONE POST (GHOST MODE) =======================
async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot posts Text, Photo, Video, or Any File and hides identity"""
    if update.effective_user.id != OWNER_ID: return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    
    raw_text = ""
    if msg.text: raw_text = " ".join(context.args)
    elif msg.caption: raw_text = msg.caption.replace("/post", "").strip()

    # Button Logic
    content = raw_text
    reply_markup = None
    if "|" in raw_text:
        parts = [p.strip() for p in raw_text.split("|")]
        content = parts[0]
        if len(parts) >= 3:
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(parts[1], url=parts[2])]])

    try:
        await msg.delete() # Identity Hide
        if msg.photo:
            await context.bot.send_photo(chat_id, photo=msg.photo[-1].file_id, caption=content, reply_markup=reply_markup, parse_mode="Markdown")
        elif msg.video:
            await context.bot.send_video(chat_id, video=msg.video.file_id, caption=content, reply_markup=reply_markup, parse_mode="Markdown")
        elif msg.document:
            await context.bot.send_document(chat_id, document=msg.document.file_id, caption=content, reply_markup=reply_markup, parse_mode="Markdown")
        elif content:
            await context.bot.send_message(chat_id, text=content, reply_markup=reply_markup, parse_mode="Markdown")
    except: pass

async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    
    total = len(ALL_USERS)
    prem = len(PREMIUM_USERS)
    free = total - prem
    codes_count = len(REDEEM_CODES) 
    
    msg = (
        f"📊 **ADMIN DASHBOARD**\n\n"
        f"👥 **Total Users:** `{total}`\n"
        f"💎 **Premium Users:** `{prem}`\n"
        f"⚪ **Free Users:** `{free}`\n"
        f"🎟 **Active Codes:** `{codes_count}`\n\n"
        f"👇 **User List (Live Tracking):**"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    
    for uid in ALL_USERS:
        joined = await is_joined(context, uid)
        u_info = ALL_USER_NAMES.get(uid, "Unknown User (Click /start to update)")
        status_txt = "Joined Success ✅" if joined else "Not Joined ❌"
        plan_icon = "💎" if is_premium(uid) else "⚪"
        
        text = f"{plan_icon} **Name:** {u_info}\n🆔 **UID:** `{uid}`\n📢 **Status:** {status_txt}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Send Message", callback_data=f"adm_rep_{uid}")]])
        
        try:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
            await asyncio.sleep(0.08)
        except:
            continue

async def admin_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        uid = int(context.args[0])
        msg = " ".join(context.args[1:])
        await context.bot.send_message(uid, f"📩 **Admin:** {msg}")
        await update.message.reply_text("✅ Sent.")
    except:
        await update.message.reply_text("❌ Fail.")

# ======================= NEW FEATURES ADDED =======================

# 1. GROUP REPLY COMMAND (Only Owner)
async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message: return 

    try:
        reply_text = " ".join(context.args)
        if not reply_text: return

        # Send message as bot
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=reply_text,
            reply_to_message_id=update.message.reply_to_message.message_id
        )
        # Delete owner's command
        try:
            await update.message.delete()
        except:
            pass 
    except:
        pass

# 2. SET WELCOME COMMAND
async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only Admin or Owner can set welcome message
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Sirf Admin ye command use kar sakta hai!")
        return

    text = " ".join(context.args)
    if not text:
        await update.message.reply_text(
            "⚠️ **Format:**\n`/setwelcome Message | Button Name | Link`\n\n"
            "Example:\n`/setwelcome Hello Dosto! | Join Now | https://t.me/example`",
            parse_mode="Markdown"
        )
        return

    chat_id = update.effective_chat.id
    
    # Check for buttons (separated by |)
    parts = [p.strip() for p in text.split('|')]
    
    welcome_data = {'text': parts[0]}
    
    if len(parts) >= 3:
        welcome_data['btn_text'] = parts[1]
        welcome_data['btn_url'] = parts[2]
        await update.message.reply_text(f"✅ **Welcome Message & Button Set!**\n\nMsg: {parts[0]}\nBtn: {parts[1]}")
    else:
        await update.message.reply_text(f"✅ **Welcome Message Set!** (No Button)\n\nMsg: {parts[0]}")
    
    GROUP_WELCOME[chat_id] = welcome_data
    save_data() # Save Welcome

# 3. NEW MEMBER HANDLER (Sends Welcome)
async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = GROUP_WELCOME.get(chat_id)
    
    if data:
        text = data['text']
        reply_markup = None
        
        # Add button if exists
        if 'btn_text' in data and 'btn_url' in data:
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(data['btn_text'], url=data['btn_url'])]
            ])
            
        await context.bot.send_message(chat_id, text, reply_markup=reply_markup)

# ======================= AUTO JOBS =======================
async def send_auto_offers(context: ContextTypes.DEFAULT_TYPE):
    global LAST_NORMAL_OFFER_TIME
    current_time = time.time()
    sunday_mode = is_sunday() 
    
    should_run_normal = False
    if not sunday_mode:
        if current_time - LAST_NORMAL_OFFER_TIME > 43200: 
            should_run_normal = True
            LAST_NORMAL_OFFER_TIME = current_time
        else:
            return 

    for uid in ALL_USERS:
        if uid in BANNED_USERS: continue 
        if is_premium(uid) or uid == OWNER_ID: continue

        if sunday_mode:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="🔥 **SUNDAY SPECIAL OFFER!** 🔥\n\n"
                         f"Sirf aaj Premium lein **₹{SUNDAY_PRICE}** mein!\n"
                         "✅ Unlimited Access.\n"
                         "✅ Koi Daily Limit Nahi.\n\n"
                         "👉 Abhi `/buy` dabayein!",
                    parse_mode="Markdown"
                )
                await asyncio.sleep(0.05) 
            except:
                pass
                
        elif should_run_normal:
            OFFER_TIMERS[uid] = current_time + (30 * 60)
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="⚡ **LIMITED TIME DEAL!** ⚡\n\n"
                         f"Premium sirf Rs {OFFER_PRICE} mein!\n"
                         "👉 Jaldi `/buy` dabayein!",
                    parse_mode="Markdown"
                )
                await asyncio.sleep(0.1)
            except:
                pass

async def check_expiry_alerts(context: ContextTypes.DEFAULT_TYPE):
    current_time = time.time()
    alert_window = 5 * 24 * 60 * 60
    
    for uid, exp_time in list(PREMIUM_USERS.items()):
        if uid in BANNED_USERS: continue
        time_left = exp_time - current_time
        if 0 < time_left <= alert_window:
            if uid not in EXPIRY_NOTIFIED:
                days_left = int(time_left / (24 * 3600)) + 1
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"⚠️ **EXPIRY ALERT**\nPlan ends in {days_left} days. Renew now!",
                        parse_mode="Markdown"
                    )
                    EXPIRY_NOTIFIED.add(uid)
                except:
                    pass

# ======================= EXTRACT (FIXED) =======================
async def extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message.text:
        url = update.message.text.strip()
    else:
        return
    
    if uid in BANNED_USERS:
        await update.message.reply_text("🚫 **You are BANNED!**", parse_mode="Markdown")
        return

    # Check Join
    if not await is_joined(context, uid):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Join Group", url="https://t.me/SynaxLookup")],
            [InlineKeyboardButton("✅ Check Join", callback_data="check_join")]
        ])
        await update.message.reply_text(
            "👥 *Pehle Group Join Karo*\n"
            "🔓 *Tabhi Features Unlock Honge*\n\n"
            "🌐 Without group join,\n"
            "🚫 URL extract nahi kar sakte",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    # Check Limit
    if not can_use(uid):
        await update.message.reply_text(
            "❌ Daily Limit Reached!\n"
            "Aapne aaj ki 2 Free Files extract kar li hain.\n"
            "Unlimited access ke liye Premium Plan upgrade karein.\n\n"
            "👇 Abhi kharidein:\n"
            "/buy"
        )
        return

    status_msg = await update.message.reply_text("🌐 **Connecting to website...**\n⏳ Please wait...")

    try:
        # FAKE HEADERS (Fix for blocking)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()

        # ==================== USAGE UPDATE ====================
        update_usage(uid)
        # =======================================================

        soup = BeautifulSoup(r.text, "html.parser")

        zip_buf = BytesIO()
        file_count = 1

        await status_msg.edit_text("⚙️ **Creating ZIP file...**")

        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("index.html", r.text)

            for tag in soup.find_all(["script", "link", "img"]):
                src = tag.get("src") or tag.get("href")
                if not src: continue
                
                full = urljoin(url, src)
                try:
                    res = requests.get(full, headers=headers, timeout=5)
                    if res.status_code == 200:
                        name = os.path.basename(urlparse(full).path)
                        if not name: name = f"file_{file_count}.assets"
                        z.writestr(f"assets/{file_count}_{name}", res.content)
                        file_count += 1
                except: 
                    pass

        zip_buf.seek(0)
        size_kb = len(zip_buf.getvalue()) / 1024
        
        # FILE NAME FIX
        zip_buf.name = "website_source.zip"
        
        await status_msg.delete()
        
        # DIRECT SEND (InputFile Removed)
        await update.message.reply_document(
            document=zip_buf,
            filename="website_source.zip",
            caption=(
                f"👑 Owner: @{OWNER_USERNAME}\n"
                f"✅ extract Success!**\n"
                f"📦 Files Fetched: {file_count}\n"
                f"🔍 Size: {size_kb:.1f} KB"
            )
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ **Error:** {str(e)}\n\nWebsite secure ho sakti hai ya link galat hai.")

# ======================= ROUTER (WITH ANTI-SPAM) =======================
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in BANNED_USERS: return

    # --- TRACK CHANNEL/GROUP ON ACTIVITY ---
    if update.effective_chat.id not in ALL_GROUPS:
        ALL_GROUPS.add(update.effective_chat.id)
        save_data()

    text = update.message.text.strip() if update.message.text else ""

    # --- 1. ADMIN DIRECT REPLY (NEW) ---
    if uid == OWNER_ID and uid in ADMIN_REPLY_TRACK:
        target = ADMIN_REPLY_TRACK.pop(uid)
        try:
            await context.bot.send_message(target, f"📩 **Admin Message:**\n\n{text}")
            await update.message.reply_text(f"✅ Sent to `{target}`")
        except:
            await update.message.reply_text("❌ Failed.")
        return

    # --- 2. ANTI-SPAM (GROUP ONLY) ---
    if update.effective_chat.type in ["group", "supergroup"]:
        # Check if user is Admin/Owner/Bot
        is_user_admin = await is_admin(update, context)
        
        # Agar Admin NAHI hai, to check karo
        if not is_user_admin:
            # Check for Link OR Username (@)
            if any(word.startswith("@") for word in text.split()) or \
               any(x in text for x in ["http", "https", "www.", ".com", ".me", ".xyz"]):
                try:
                    await update.message.delete()
                except:
                    pass
                return # Delete karke return (Bot aage reply nahi karega)

    # --- 3. SUPPORT LOGIC (DM Only) ---
    if uid in WAITING_SUPPORT:
        WAITING_SUPPORT.remove(uid)
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Reply", callback_data=f"adm_rep_{uid}")]])
        await context.bot.send_message(OWNER_ID, f"🆘 **SUPPORT:** `{uid}`\nMsg: {text}", reply_markup=kb)
        
        await update.message.reply_text(
            "🎉 **Message Successfully Submitted!** ✅\n"
            "Aapka message admin tak pahunch gaya hai\n"
            "Admin online aate hi reply zarur karega\n"
            "⏳ Tab tak wait karo"
        )
        return

    # --- 4. URL EXTRACTOR (Starts with http) ---
    if text.startswith("http"):
        await extract(update, context)



# ======================= MEDIA COMMAND ROUTER (FIXED) =======================
async def media_command_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catch /post or /broadcast in media captions (GROUP + DM safe)"""
    msg = update.effective_message
    if not msg:
        return

    text = (msg.caption or msg.text or "").strip()

    if text.startswith("/post") or text.startswith("/post@"):
        await post_command(update, context)
    elif text.startswith("/broadcast") or text.startswith("/broadcast@"):
        await broadcast(update, context)


# ======================= MAIN =======================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_dashboard))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("support", support))
    app.add_handler(CommandHandler("check", admin_check_user))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("msg", admin_msg))
    
    # NEW COMMANDS ADDED HERE
    app.add_handler(CommandHandler("promote", promote_user))
    app.add_handler(CommandHandler("reply", admin_reply))
    app.add_handler(CommandHandler("setwelcome", set_welcome))
    app.add_handler(CommandHandler("post", post_command))
    
    # --- ADVANCED REDEEM SYSTEM HANDLERS ---
    app.add_handler(CommandHandler("gen", generate_redeem_code))       # Owner: Create Code
    app.add_handler(CommandHandler("redeem", redeem_code))             # User: Use Code
    app.add_handler(CommandHandler("codes", list_redeem_codes))        # Owner: List Codes
    app.add_handler(CommandHandler("delcode", revoke_redeem_code))     # Owner: Delete Code
    app.add_handler(CommandHandler("reset", reset_user_usage))         # Owner: Reset Daily Limit
    
    # HANDLERS
    app.add_handler(ChatMemberHandler(anti_admin_protection, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.CHAT_CREATED, track_chats))
    
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(
        (filters.PHOTO | filters.VIDEO | filters.Document.ALL) & filters.CaptionRegex(r'^/(post|broadcast)'),
        media_command_router
    ))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    # --- FIXED JOBQUEUE SECTION ---
    if app.job_queue:
        job_queue = app.job_queue
        job_queue.run_repeating(send_auto_offers, interval=600, first=10)
        job_queue.run_repeating(check_expiry_alerts, interval=86400, first=60)
        print("✅ JobQueue Active: Auto-offers enabled.")
    else:
        print("⚠️ WARNING: JobQueue is NOT initialized. Auto-offers and expiry alerts are disabled.")
        print("💡 FIX: Add 'python-telegram-bot[job-queue]' to requirements.txt")
    # ------------------------------

    print("🔥 BOT RUNNING – NEW MESSAGE UPDATE")
    app.run_polling()

if __name__ == "__main__":
    main()
