#!/usr/bin/env python3
# coding: utf-8
"""
Full ready-to-run bot.py
- Replace API_TOKEN and ADMIN_ID with your values
- Uses zoneinfo (Python 3.9+) or falls back to pytz if needed
Requirements (example):
  pip install aiogram pandas openpyxl pytz
"""

import logging
import sqlite3
import pandas as pd
import os
import asyncio
from datetime import datetime, timedelta
try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
    _HAS_ZONEINFO = True
except Exception:
    import pytz
    _HAS_ZONEINFO = False

from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# --- Config (PUT YOURS HERE) ---
API_TOKEN = "8328705715:AAH1p7JxJCCLsIH6xst_ZZ8q6aAkKEsylqE"   # <- replace with your bot token
ADMIN_ID = 7776075490                  # <- replace with your numeric Telegram ID

# set Bangladesh timezone
if _HAS_ZONEINFO:
    TZ = ZoneInfo("Asia/Dhaka")
else:
    TZ = pytz.timezone("Asia/Dhaka")

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Bot init ---
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# --- Database ---
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance REAL DEFAULT 0,
    purchased INTEGER DEFAULT 0,
    last_active TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS stock(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT,
    emailpass TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS deposits(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    method TEXT,
    number TEXT,
    amount REAL,
    txid TEXT,
    status TEXT DEFAULT 'pending'
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
)""")

conn.commit()

# --- Prices ---
PRICES = {
    "Gmail (6-12 Hours)": 4.00,
    "Hotmail (6-12 Months)": 1.50,
    "Outlook (6-12 Months)": 1.50,
    "Login Gmail": 3.00
}

# --- Helpers ---
def now_utc():
    return datetime.utcnow()

def now_bangla():
    """Return current datetime in Bangladesh tz as a datetime object."""
    if _HAS_ZONEINFO:
        return datetime.now(TZ)
    else:
        return datetime.now(pytz.utc).astimezone(TZ)

def to_iso(dt: datetime):
    return dt.isoformat()

def from_iso(s: str):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        # fallback: naive parse
        try:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")
        except Exception:
            return None

def fmt_time_12(dt: datetime):
    """12-hour format with AM/PM in Bangladesh time."""
    if dt is None:
        return "-"
    # ensure dt is timezone-aware in Bangladesh
    if _HAS_ZONEINFO:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        dt = dt.astimezone(TZ)
    else:
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        dt = dt.astimezone(TZ)
    return dt.strftime("%I:%M:%S %p")  # 12-hour

def fmt_date(dt: datetime):
    if dt is None:
        return "-"
    if _HAS_ZONEINFO:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        dt = dt.astimezone(TZ)
    else:
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        dt = dt.astimezone(TZ)
    return dt.strftime("%Y-%m-%d")

def set_last_active(uid: int, username: str = None):
    uname = username or "NoUsername"
    ts = to_iso(now_utc())
    cursor.execute("INSERT OR IGNORE INTO users(user_id, username, last_active) VALUES(?,?,?)", (uid, uname, ts))
    cursor.execute("UPDATE users SET username=?, last_active=? WHERE user_id=?", (uname, ts, uid))
    conn.commit()

# async notifier
async def async_notify_all(text):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    sent = 0
    failed = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, text, disable_web_page_preview=True)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    logger.info(f"Notify finished. Sent: {sent}, Failed: {failed}")

def notify_all_users(text):
    try:
        asyncio.create_task(async_notify_all(text))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(async_notify_all(text))

# --- Menus ---
def main_menu(is_admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if is_admin:
        kb.add(KeyboardButton("⚙️Admin Panel⚙️"))
    kb.add(KeyboardButton("📧 Get Mail"), KeyboardButton("📥 Mail Inbox"))
    kb.add(KeyboardButton("💰 Balance"), KeyboardButton("💳 Deposit"))
    kb.add(KeyboardButton("🆘 Mail Bot Support"), KeyboardButton("📚 Tutorial"))
    return kb

def admin_panel_markup():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📂 Upload Stock", callback_data="admin_stock"))
    kb.add(InlineKeyboardButton("🗑 Remove Stock", callback_data="admin_removestock"))
    kb.add(InlineKeyboardButton("📂 Pending Deposits", callback_data="admin_deposits"))
    kb.add(InlineKeyboardButton("📊 Bot Statistics Dashboard", callback_data="admin_stats"))
    kb.add(InlineKeyboardButton("👥 Active Users (Realtime)", callback_data="admin_users"))
    kb.add(InlineKeyboardButton("👥 User List", callback_data="admin_userbalances"))
    kb.add(InlineKeyboardButton("⚡ Balance Control", callback_data="admin_usercontrol"))
    kb.add(InlineKeyboardButton("🆘 Set Support", callback_data="admin_support"))
    kb.add(InlineKeyboardButton("📚 Set Tutorial", callback_data="admin_tutorial"))
    kb.add(InlineKeyboardButton("📣 Broadcast", callback_data="admin_broadcast"))
    return kb

# --- Handlers ---
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    uid = message.from_user.id
    uname = message.from_user.username or "NoUsername"
    set_last_active(uid, uname)
    await message.answer("👋 স্বাগতম! আপনার কি Gmail চাই?", reply_markup=main_menu(uid == ADMIN_ID))

# Balance
@dp.message_handler(lambda m: m.text == "💰 Balance")
async def balance_cmd(message: types.Message):
    set_last_active(message.from_user.id, message.from_user.username)
    uid = message.from_user.id
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    bal = row[0] if row else 0.0
    await message.answer(f"💰 Your Balance: {bal:.2f} tk")

# Deposit
@dp.message_handler(lambda m: m.text == "💳 Deposit")
async def deposit_cmd(message: types.Message):
    set_last_active(message.from_user.id, message.from_user.username)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📲 bKash", callback_data="dep_bkash"))
    kb.add(InlineKeyboardButton("📲 Nagad", callback_data="dep_nagad"))
    await message.answer("💳 Select Payment Method:\n\n⚠️ ন্যূনতম ডিপোজিট 20 টাকা।", reply_markup=kb)

user_deposit = {}

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("dep_"))
async def dep_method(call: types.CallbackQuery):
    uid = call.from_user.id
    method = call.data.replace("dep_", "")
    user_deposit[uid] = {"method": method}
    number = "01767916048" if method == "bkash" else "01576978543"
    await call.message.answer(f"📲 Send Money to: <b>{number}</b>\n\nএখন আপনার পাঠানো নম্বর দিন (sender number):")
    await call.answer()

@dp.message_handler(lambda m: m.from_user.id in user_deposit and "number" not in user_deposit[m.from_user.id])
async def dep_number(message: types.Message):
    uid = message.from_user.id
    user_deposit[uid]["number"] = message.text.strip()
    await message.answer("💵 Enter deposit amount (সংখ্যায়):")

@dp.message_handler(lambda m: m.from_user.id in user_deposit and "amount" not in user_deposit[m.from_user.id])
async def dep_amount(message: types.Message):
    uid = message.from_user.id
    txt = message.text.strip()
    try:
        amount = float(txt)
    except:
        await message.answer("❌ সঠিক সংখ্যা লিখুন (e.g., 100)")
        return
    if amount < 20:
        await message.answer("❌ Minimum deposit is 20 tk.")
        return
    user_deposit[uid]["amount"] = amount
    await message.answer("🔑 Enter transaction ID:")

@dp.message_handler(lambda m: m.from_user.id in user_deposit and "txid" not in user_deposit[m.from_user.id])
async def dep_txid(message: types.Message):
    uid = message.from_user.id
    data = user_deposit[uid]
    txid = message.text.strip()
    data["txid"] = txid
    cursor.execute("INSERT INTO deposits(user_id, method, number, amount, txid) VALUES(?,?,?,?,?)",
                   (uid, data["method"], data["number"], data["amount"], txid))
    conn.commit()
    dep_id = cursor.lastrowid

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Approve", callback_data=f"approve_{dep_id}"),
           InlineKeyboardButton("❌ Reject", callback_data=f"reject_{dep_id}"))

    uname = message.from_user.username or "NoUsername"
    await bot.send_message(ADMIN_ID,
                           f"💳 Deposit Request\n\n👤 User: @{uname}\n🆔 ID: {uid}\n💳 Method: {data['method']}\n📞 Number: {data['number']}\n💵 Amount: {data['amount']}\n🔑 TxID: {txid}\n🆔 Deposit ID: {dep_id}",
                           reply_markup=kb)
    await message.answer("✅ Deposit request sent! Waiting for approval.")
    del user_deposit[uid]

@dp.callback_query_handler(lambda c: c.data and (c.data.startswith("approve_") or c.data.startswith("reject_")))
async def dep_admin(call: types.CallbackQuery):
    dep_id = int(call.data.split("_")[1])
    cursor.execute("SELECT user_id, amount FROM deposits WHERE id=?", (dep_id,))
    dep = cursor.fetchone()
    if not dep:
        await call.answer("❌ Deposit not found.")
        return
    uid, amount = dep
    if call.data.startswith("approve"):
        cursor.execute("UPDATE deposits SET status='approved' WHERE id=?", (dep_id,))
        cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
        conn.commit()
        try:
            await bot.send_message(uid, f"✅ আপনার deposit {amount} tk approved হয়েছে! Balance আপডেট করা হয়েছে।")
        except: pass
        await call.message.edit_text("✅ Approved and processed.")
    else:
        cursor.execute("UPDATE deposits SET status='rejected' WHERE id=?", (dep_id,))
        conn.commit()
        try:
            await bot.send_message(uid, "❌ আপনার deposit বাতিল করা হয়েছে।")
        except: pass
        await call.message.edit_text("❌ Rejected.")
    await call.answer()

# Get Mail / buy flows
@dp.message_handler(lambda m: m.text == "📧 Get Mail")
async def get_mail(message: types.Message):
    set_last_active(message.from_user.id, message.from_user.username)
    kb = InlineKeyboardMarkup()
    for service, price in PRICES.items():
        cursor.execute("SELECT COUNT(*) FROM stock WHERE service=?", (service,))
        stock = cursor.fetchone()[0]
        kb.add(InlineKeyboardButton(f"{service} | {price} tk | Stock: {stock}", callback_data=f"buy_{service}"))
    kb.add(InlineKeyboardButton("🛒 Multiple Purchase", callback_data="multi_purchase"))
    await message.answer("📧 Available Mail:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("buy_"))
async def buy_one(call: types.CallbackQuery):
    uid = call.from_user.id
    set_last_active(uid, call.from_user.username)
    service = call.data.replace("buy_", "")
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    res = cursor.fetchone()
    bal = res[0] if res else 0.0
    price = PRICES.get(service, 0)
    if bal < price:
        await call.message.answer("❌ Not enough balance!")
        await call.answer()
        return
    cursor.execute("SELECT id,emailpass FROM stock WHERE service=? ORDER BY RANDOM() LIMIT 1", (service,))
    item = cursor.fetchone()
    if not item:
        await call.message.answer("❌ Out of stock!")
        await call.answer()
        return
    stock_id, emailpass = item
    cursor.execute("DELETE FROM stock WHERE id=?", (stock_id,))
    cursor.execute("UPDATE users SET balance=balance-?, purchased=purchased+1 WHERE user_id=?", (price, uid))
    conn.commit()
    await call.message.answer(f"✅ Purchase successful!\n\n<code>{emailpass}</code>")
    await call.answer()

# Multi purchase
multi_step = {}

@dp.callback_query_handler(lambda c: c.data == "multi_purchase")
async def multi_start(call: types.CallbackQuery):
    uid = call.from_user.id
    set_last_active(uid, call.from_user.username)
    kb = InlineKeyboardMarkup()
    for s in PRICES.keys():
        kb.add(InlineKeyboardButton(s, callback_data=f"multi_{s}"))
    await call.message.answer("🛒 Select service for multiple purchase:", reply_markup=kb)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("multi_"))
async def multi_service(call: types.CallbackQuery):
    uid = call.from_user.id
    set_last_active(uid, call.from_user.username)
    service = call.data.replace("multi_", "")
    multi_step[uid] = {"service": service}
    await call.message.answer("✍️ Enter how many mails you want:")
    await call.answer()

@dp.message_handler(lambda m: m.from_user.id in multi_step and "count" not in multi_step[m.from_user.id])
async def multi_count(message: types.Message):
    uid = message.from_user.id
    set_last_active(uid, message.from_user.username)
    if not message.text.isdigit():
        await message.answer("❌ Enter a valid number.")
        return
    count = int(message.text)
    multi_step[uid]["count"] = count
    service = multi_step[uid]["service"]
    price = PRICES[service] * count
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    res = cursor.fetchone()
    bal = res[0] if res else 0.0
    cursor.execute("SELECT id,emailpass FROM stock WHERE service=? LIMIT ?", (service, count))
    items = cursor.fetchall()
    if len(items) < count:
        await message.answer("❌ Not enough stock!")
        del multi_step[uid]
        return
    if bal < price:
        await message.answer("❌ Not enough balance!")
        del multi_step[uid]
        return
    # deduct stock & update user
    mails = []
    for stock_id, emailpass in items:
        cursor.execute("DELETE FROM stock WHERE id=?", (stock_id,))
        mails.append(emailpass)
    cursor.execute("UPDATE users SET balance=balance-?, purchased=purchased+? WHERE user_id=?", (price, count, uid))
    conn.commit()
    # send file if many
    if count >= 5:
        fname = f"{uid}_mails.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write("\n".join(mails))
        await message.answer_document(open(fname, "rb"), caption=f"✅ Purchased {count} {service}")
        try:
            os.remove(fname)
        except: pass
    else:
        text = "\n".join([f"<code>{m}</code>" for m in mails])
        await message.answer(f"✅ Purchased {count} {service}\n\n{text}")
    del multi_step[uid]

# Inbox / Support / Tutorial
@dp.message_handler(lambda m: m.text == "📥 Mail Inbox")
async def inbox(message: types.Message):
    set_last_active(message.from_user.id, message.from_user.username)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📧 Gmail Inbox", callback_data="inbox_gmail"))
    kb.add(InlineKeyboardButton("📧 Hotmail Inbox", callback_data="inbox_hotmail"))
    kb.add(InlineKeyboardButton("📧 Outlook Inbox", callback_data="inbox_outlook"))
    await message.answer("📥 কোন ইনবক্স চেক করবেন?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("inbox_"))
async def inbox_links(call: types.CallbackQuery):
    if call.data == "inbox_gmail":
        await call.message.answer("➡️ Gmail কোড পাওয়ার জন্য যান: @CodeReciever71bot")
    else:
        await call.message.answer("➡️ Hotmail/Outlook কোডের জন্য যান:\nhttps://dongvanfb.net/read_mail_box/")
    await call.answer()

@dp.message_handler(lambda m: m.text == "📚 Tutorial")
async def tutorial(message: types.Message):
    set_last_active(message.from_user.id, message.from_user.username)
    cursor.execute("SELECT value FROM settings WHERE key='tutorial_link'")
    row = cursor.fetchone()
    if row:
        link = row[0]
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("📚 Mail Bot Tutorial", url=link))
        await message.answer("📚 Mail Bot Tutorial\n\nনিচের বাটনে ক্লিক করে Tutorial Video দেখুন! 🎯", reply_markup=kb)
    else:
        await message.answer("❌ Tutorial link not set. Admin দয়া করে /admin panel থেকে সেট করবেন।")

@dp.message_handler(lambda m: m.text == "🆘 Mail Bot Support")
async def support(message: types.Message):
    set_last_active(message.from_user.id, message.from_user.username)
    cursor.execute("SELECT value FROM settings WHERE key='support_username'")
    row = cursor.fetchone()
    if row:
        uname = row[0]
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("📩 Mail Bot Support", url=f"https://t.me/{uname}"))
        await message.answer("যদি কোনো সমস্যায় পড়েন, নিচের Mail Bot Support বাটনে ক্লিক করুন", reply_markup=kb)
    else:
        await message.answer("❌ Support not set by admin.")

# Admin panel entry
@dp.message_handler(lambda m: m.text == "⚙️Admin Panel⚙️" and m.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    set_last_active(message.from_user.id, message.from_user.username)
    await message.answer("⚙️ Admin Panel ⚙️", reply_markup=admin_panel_markup())

# Admin: Upload/Remove stock handlers and file upload
@dp.callback_query_handler(lambda c: c.data == "admin_stock")
async def admin_stock_prompt(call: types.CallbackQuery):
    await call.message.answer("📂 Send TXT/CSV/XLSX file\nCaption must be service name (e.g. Gmail (6-12 Hours))")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "admin_removestock")
async def admin_removestock_prompt(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup()
    for service in PRICES.keys():
        kb.add(InlineKeyboardButton(service, callback_data=f"rem_{service}"))
    await call.message.answer("🗑 Select product to clear stock:", reply_markup=kb)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("rem_"))
async def rem_stock(call: types.CallbackQuery):
    service = call.data.replace("rem_", "")
    cursor.execute("DELETE FROM stock WHERE service=?", (service,))
    conn.commit()
    await call.message.answer(f"🗑 All stock removed for {service}.")
    notify_text = f"📢 Notice: সব স্টক মুছে দেয়া হয়েছে - <b>{service}</b>।"
    notify_all_users(notify_text)
    await call.answer()

@dp.message_handler(content_types=['document'])
async def handle_file(message: types.Message):
    # Only admin should upload stock via document
    if message.from_user.id != ADMIN_ID:
        return
    if not message.caption:
        await message.answer("❌ Caption must be service name! (e.g. Gmail (6-12 Hours))")
        return
    service = message.caption.strip()
    # download file
    file = await message.document.download()
    filename = file.name
    try:
        if filename.lower().endswith(".txt"):
            with open(filename, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
        elif filename.lower().endswith(".csv"):
            df = pd.read_csv(filename, header=None, encoding='utf-8', dtype=str)
            lines = df.iloc[:, 0].dropna().astype(str).tolist()
        elif filename.lower().endswith(".xlsx") or filename.lower().endswith(".xls"):
            df = pd.read_excel(filename, header=None)
            lines = df.iloc[:, 0].dropna().astype(str).tolist()
        else:
            await message.answer("❌ Unsupported file type. Use .txt/.csv/.xlsx")
            return

        for line in lines:
            cursor.execute("INSERT INTO stock(service,emailpass) VALUES(?,?)", (service, line.strip()))
        conn.commit()

        await message.answer(f"✅ Uploaded {len(lines)} stock for {service}.\n📢 Sending notifications to users...")
        notify_text = f"📢 নতুন স্টক আপলোড হয়েছে: <b>{service}</b>\nযাচাই করতে /📧 Get Mail এ যান।"
        notify_all_users(notify_text)
    except Exception as e:
        logging.exception("Error processing file")
        await message.answer(f"❌ Error while processing file: {e}")

# Admin: deposits view
@dp.callback_query_handler(lambda c: c.data == "admin_deposits")
async def admin_deposits(call: types.CallbackQuery):
    cursor.execute("SELECT id,user_id,method,number,amount,txid,status FROM deposits ORDER BY id DESC")
    rows = cursor.fetchall()
    if not rows:
        await call.message.answer("✅ No deposits found.")
        await call.answer()
        return
    for r in rows:
        dep_id, uid, method, number, amount, txid, status = r
        kb = InlineKeyboardMarkup()
        if status == "pending":
            kb.add(InlineKeyboardButton("✅ Approve", callback_data=f"approve_{dep_id}"),
                   InlineKeyboardButton("❌ Reject", callback_data=f"reject_{dep_id}"))
        await call.message.answer(f"🆔 Deposit ID: {dep_id}\n👤 UserID: {uid}\n💳 Method: {method}\n📞 Number: {number}\n💵 Amount: {amount}\n🔑 TxID: {txid}\nStatus: {status}", reply_markup=kb)
    await call.answer()

# Admin: user balances / list
@dp.callback_query_handler(lambda c: c.data == "admin_userbalances")
async def admin_userbalances(call: types.CallbackQuery):
    cursor.execute("SELECT user_id,username,balance FROM users ORDER BY balance DESC LIMIT 50")
    rows = cursor.fetchall()
    if not rows:
        await call.message.answer("No users found.")
        await call.answer()
        return
    text = "👥 Top Users (by balance):\n\n"
    for uid, uname, bal in rows:
        text += f"@{uname} ({uid}) - {bal:.2f} tk\n"
    await call.message.answer(text)
    await call.answer()

# Admin: balance control
@dp.message_handler(commands=['addbal', 'setbal', 'delbal'])
async def bal_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("Usage: /addbal user_id amount  OR /setbal user_id amount  OR /delbal user_id amount")
            return
        cmd, uid_s, amt_s = parts
        uid = int(uid_s)
        amt = float(amt_s)
        if cmd == "/addbal":
            cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amt, uid))
        elif cmd == "/setbal":
            cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (amt, uid))
        elif cmd == "/delbal":
            cursor.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amt, uid))
        conn.commit()
        await message.answer("✅ Balance updated.")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")

# Admin: set support / tutorial
@dp.callback_query_handler(lambda c: c.data == "admin_support")
async def admin_support(call: types.CallbackQuery):
    await call.message.answer("✍️ Send new support username (without @)")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "admin_tutorial")
async def admin_tutorial(call: types.CallbackQuery):
    await call.message.answer("✍️ Send new tutorial link (http:// or https://)")
    await call.answer()

@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID and m.text and not m.text.startswith("/"))
async def admin_set_text(message: types.Message):
    # If a broadcast is pending, broadcast handler will use this text so we skip handling here
    cursor.execute("SELECT value FROM settings WHERE key='awaiting_broadcast'")
    row_flag = cursor.fetchone()
    if row_flag and row_flag[0] == '1':
        return
    text = message.text.strip()
    if text.startswith("http"):
        cursor.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('tutorial_link',?)", (text,))
        await message.answer("✅ Tutorial link updated.")
    else:
        uname = text.replace("@", "").strip()
        cursor.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('support_username',?)", (uname,))
        await message.answer("✅ Support username updated.")
    conn.commit()

# Admin: broadcast
@dp.callback_query_handler(lambda c: c.data == "admin_broadcast")
async def admin_broadcast_trigger(call: types.CallbackQuery):
    await call.message.answer("✍️ Send the message you want to broadcast to ALL users.\n\n(Tip: plain text only.)")
    cursor.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('awaiting_broadcast','1')")
    conn.commit()
    await call.answer()

@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID, content_types=['text'])
async def catch_admin_broadcast_message(message: types.Message):
    cursor.execute("SELECT value FROM settings WHERE key='awaiting_broadcast'")
    row = cursor.fetchone()
    if not (row and row[0] == '1'):
        return
    text = message.text
    cursor.execute("DELETE FROM settings WHERE key='awaiting_broadcast'")
    conn.commit()
    await message.answer("📣 Broadcast started. Sending to all users...")
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    sent = 0
    failed = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, f"📣 Broadcast from Admin:\n\n{text}", disable_web_page_preview=True)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await message.answer(f"✅ Broadcast finished. Sent: {sent}, Failed: {failed}")

# Admin: Active Users (realtime) & Bot Stats (Bangladesh time, 12-hour)
@dp.callback_query_handler(lambda c: c.data == "admin_users")
async def active_users(call: types.CallbackQuery):
    cursor.execute("SELECT last_active FROM users")
    rows = cursor.fetchall()
    total = 0
    new_today = 0
    online = 0
    active15 = 0
    active60 = 0
    now = now_utc()
    for (last,) in rows:
        if last:
            dt = from_iso(last)
            if dt:
                total += 1
                # new today using Bangladesh date
                # convert dt to Bangladesh tz and compare date
                if _HAS_ZONEINFO:
                    d_b = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
                else:
                    if dt.tzinfo is None:
                        dt = pytz.utc.localize(dt)
                    d_b = dt.astimezone(TZ)
                if d_b.date() == now_bangla().date():
                    new_today += 1
                delta = now - dt
                if delta <= timedelta(minutes=5):
                    online += 1
                if delta <= timedelta(minutes=15):
                    active15 += 1
                if delta <= timedelta(minutes=60):
                    active60 += 1
    # include users with NULL last_active
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_active IS NULL")
    null_count = cursor.fetchone()[0]
    total += null_count

    text = (f"👥 Active Users (Realtime)\n\n"
            f"Total Users: {total}\n"
            f"New Today: {new_today}\n"
            f"🟢 Online (≤5m): {online}\n"
            f"🟡 Active (≤15m): {active15}\n"
            f"🔵 Active (≤60m): {active60}")
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔄 Refresh", callback_data="admin_users"))
    kb.add(InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="back_admin"))
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "admin_stats")
async def bot_stats(call: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    # compute new today by last_active in Bangla date
    cursor.execute("SELECT last_active FROM users")
    rows = cursor.fetchall()
    new_today = 0
    for (last,) in rows:
        if last:
            dt = from_iso(last)
            if dt:
                if _HAS_ZONEINFO:
                    dt_b = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
                else:
                    if dt.tzinfo is None:
                        dt = pytz.utc.localize(dt)
                    dt_b = dt.astimezone(TZ)
                if dt_b.date() == now_bangla().date():
                    new_today += 1
    now_b = now_bangla()
    text = (f"🏹 BOT STATISTICS DASHBOARD 🏹\n"
            f"🕒 Current Time: {now_b.strftime('%I:%M:%S %p')}\n"
            f"📅 Date: {now_b.strftime('%Y-%m-%d')}\n"
            f"🔁 Last Updated: {now_b.strftime('%I:%M:%S %p')}\n"
            f"——————————————\n"
            f"👥 USER STATISTICS\n"
            f"Today (active): {new_today}\n"
            f"Total users: {total_users}\n"
            f"New Today: {new_today}")
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats"))
    kb.add(InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="back_admin"))
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except:
        await call.message.answer(text, reply_markup=kb)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "back_admin")
async def back_admin(call: types.CallbackQuery):
    try:
        await call.message.edit_text("⚙️ Admin Panel ⚙️", reply_markup=admin_panel_markup())
    except:
        await call.message.answer("⚙️ Admin Panel ⚙️", reply_markup=admin_panel_markup())
    await call.answer()

# simple admin convenience
@dp.message_handler(commands=['users'])
async def cmd_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    await message.answer(f"Total users: {total}")

# Run
if __name__ == "__main__":
    try:
        logger.info("Starting bot...")
        executor.start_polling(dp, skip_updates=True)
    finally:
        conn.close()