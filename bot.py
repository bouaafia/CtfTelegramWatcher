import os
import time
import json
import html
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException

                           
               
                           
DATA_FILE ="data.json"
BOT_TOKEN = "" # Your telegram bot token

if not BOT_TOKEN:
    raise SystemExit("Please set BOT_TOKEN  variable.")

                                                 
DEFAULT_DATA = {
    "channels": [],                                                                        
    "admins": [],                                         
    "settings": {
        "interval_sec": 300,                                       
        "horizon_days": 14,                                          
        "min_weight": 0,                                            
        "disable_web_preview": False
    },
    "state": {
        "running": False,
        "last_run": None,                          
                                                                                                                    
        "events": {}
    }
}

data_lock = threading.RLock()
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True)

scheduler_thread: Optional[threading.Thread] = None
scheduler_stop_flag = threading.Event()


                           
                     
                           
def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return json.loads(json.dumps(DEFAULT_DATA))
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return json.loads(json.dumps(DEFAULT_DATA))


def save_data(d: Dict[str, Any]) -> None:
    tmp_path = DATA_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, DATA_FILE)


def with_data(fn):
    def wrapper(*args, **kwargs):
        with data_lock:
            d = load_data()
            result = fn(d, *args, **kwargs)
            save_data(d)
            return result
    return wrapper


                           
           
                           
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(dt_str: str) -> datetime:
                                                                   
    if dt_str.endswith("Z"):
        dt_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(dt_str).astimezone(timezone.utc)


def fmt_dt(dt: datetime) -> str:
                             
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def google_calendar_link(title: str, start: datetime, end: datetime, details: str, url: str) -> str:
                               
    def gcal_fmt(d: datetime) -> str:
        d = d.astimezone(timezone.utc)
        return d.strftime("%Y%m%dT%H%M%SZ")
    from urllib.parse import quote_plus
    base = "https://www.google.com/calendar/render?action=TEMPLATE"
    params = [
        ("text", title),
        ("dates", f"{gcal_fmt(start)}/{gcal_fmt(end)}"),
        ("details", f"{details}\n{url}".strip()),
        ("ctz", "UTC")
    ]
    return base + "&" + "&".join(f"{k}={quote_plus(v)}" for k, v in params)


def is_admin(user_id: int, d: Dict[str, Any]) -> bool:
    return user_id in d.get("admins", [])


def ensure_admin(user_id: int):
    def decorator(fn):
        def wrapper(message: types.Message, *args, **kwargs):
            with data_lock:
                d = load_data()
                if not is_admin(user_id=message.from_user.id, d=d):
                    bot.reply_to(message, "Only admins can use this command.")
                    return
            return fn(message, *args, **kwargs)
        return wrapper
    return decorator


def sanitize_channel_id(s: str) -> str:
    s = s.strip()
                                                                                                 
    return s


def build_event_status(start: datetime, end: datetime, now: Optional[datetime] = None) -> str:
    n = now or now_utc()
    if n < start:
        return "upcoming"
    elif start <= n < end:
        return "running"
    else:
        return "ended"


def safe_get(d: Dict[str, Any], key: str, default=None):
    v = d.get(key, default)
    return v if v is not None else default


                           
             
                           
def fetch_ctftime_events(start: datetime, finish: datetime, limit: int = 100) -> List[Dict[str, Any]]:
    url = "https://ctftime.org/api/v1/events/"
    params = {
        "limit": limit,
        "start": int(start.timestamp()),
        "finish": int(finish.timestamp())
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        events = r.json()
        if not isinstance(events, list):
            return []
        return events
    except Exception as e:
        print(f"[ERROR] CTFtime fetch failed: {e}")
        return []


                           
           
                           
def build_event_text(event: Dict[str, Any], status: str) -> str:
    title = html.escape(safe_get(event, "title", "Untitled"))
    ctftime_url = safe_get(event, "ctftime_url", "")
    url = safe_get(event, "url", ctftime_url) or ctftime_url
    weight = safe_get(event, "weight", 0)
    format_ = "Onsite" if safe_get(event, "onsite", False) else "Online"
    start = parse_iso(event["start"])
    finish = parse_iso(event["finish"])
    duration = finish - start
    orgs = []
    if isinstance(event.get("organizers"), list):
        for org in event["organizers"]:
            name = org.get("name")
            if name:
                orgs.append(name)
    organizers = ", ".join(orgs) if orgs else "N/A"

                  
    if status == "upcoming":
        badge = "🟡 <b>Upcoming</b>"
    elif status == "running":
        badge = "🟢 <b>Running</b>"
    else:
        badge = "🔴 <b>Ended</b>"

                       
    days = duration.days
    hours = duration.seconds // 3600
    mins = (duration.seconds % 3600) // 60
    dur_parts = []
    if days: dur_parts.append(f"{days}d")
    if hours: dur_parts.append(f"{hours}h")
    if mins and not days and not hours: dur_parts.append(f"{mins}m")
    dur_str = " ".join(dur_parts) if dur_parts else f"{duration}"

                          
    lines = [
        f"{badge}",
        f"<b>{title}</b>",
        f"Format: <i>{format_}</i>",
        f"Starts: <b>{fmt_dt(start)}</b>",
        f"Ends: <b>{fmt_dt(finish)}</b>",
        f"Duration: <i>{dur_str}</i>",
        f"Weight: <b>{weight}</b>",
        f"Organizers: <i>{html.escape(organizers)}</i>",
        "",
        f'<a href="{html.escape(ctftime_url)}">View on CTFtime</a>' + (f' • <a href="{html.escape(url)}">Website</a>' if url and url != ctftime_url else "")
    ]

    n = now_utc()
    if status == "upcoming":
        delta = start - n
        h = int(delta.total_seconds() // 3600)
        m = int((delta.total_seconds() % 3600) // 60)
        if delta.total_seconds() > 0:
            lines.append(f"⏳ Starts in ~ {h}h {m}m")
    elif status == "running":
        delta = finish - n
        h = int(delta.total_seconds() // 3600)
        m = int((delta.total_seconds() % 3600) // 60)
        if delta.total_seconds() > 0:
            lines.append(f"⏱ Ends in ~ {h}h {m}m")

    return "\n".join(lines).strip()


def build_event_markup(event: Dict[str, Any]) -> Optional[types.InlineKeyboardMarkup]:
    ctftime_url = safe_get(event, "ctftime_url", "")
    url = safe_get(event, "url", ctftime_url) or ctftime_url
    start = parse_iso(event["start"])
    finish = parse_iso(event["finish"])
    title = safe_get(event, "title", "CTF")
    gcal = google_calendar_link(title=title, start=start, end=finish, details="CTFtime event", url=ctftime_url or url)

    kb = types.InlineKeyboardMarkup()
    btns = []
    if ctftime_url:
        btns.append(types.InlineKeyboardButton("CTFtime", url=ctftime_url))
    if url and url != ctftime_url:
        btns.append(types.InlineKeyboardButton("Website", url=url))
    btns.append(types.InlineKeyboardButton("Add to Google Calendar", url=gcal))
    kb.row(*btns)
    return kb



@with_data
def ensure_user_is_admin(d: Dict[str, Any], user: types.User) -> None:
    if not d["admins"]:
        d["admins"].append(user.id)


@with_data
def add_channel(d: Dict[str, Any], channel: str) -> bool:
    channel = sanitize_channel_id(channel)
    if channel and channel not in d["channels"]:
        d["channels"].append(channel)
        return True
    return False


@with_data
def remove_channel(d: Dict[str, Any], channel: str) -> bool:
    channel = sanitize_channel_id(channel)
    if channel in d["channels"]:
        d["channels"].remove(channel)
                                                    
        for ev in d["state"]["events"].values():
            msgs = ev.get("messages", {})
            if channel in msgs:
                msgs.pop(channel, None)
        return True
    return False


def post_event_to_channels(d: Dict[str, Any], event: Dict[str, Any], status: str) -> None:
    text = build_event_text(event, status)
    markup = build_event_markup(event)
    disable_preview = d["settings"].get("disable_web_preview", False)

    event_id = str(event["id"])
    ev_state = d["state"]["events"].setdefault(event_id, {
        "status": status,
        "starts_at": event["start"],
        "ends_at": event["finish"],
        "messages": {}
    })

    for channel in d["channels"]:
                                                
        if str(channel) in ev_state["messages"]:
            continue
        try:
            msg = bot.send_message(
                chat_id=channel,
                text=text,
                reply_markup=markup,
                disable_web_page_preview=disable_preview
            )
            ev_state["messages"][str(channel)] = msg.message_id
            ev_state["status"] = status
            ev_state["starts_at"] = event["start"]
            ev_state["ends_at"] = event["finish"]
            print(f"[INFO] Posted event {event_id} to {channel} (msg {msg.message_id})")
        except ApiTelegramException as te:
            print(f"[WARN] Failed to send to {channel}: {te}")
        except Exception as e:
            print(f"[WARN] Unexpected send error to {channel}: {e}")


def edit_event_messages(d: Dict[str, Any], event: Dict[str, Any], new_status: str) -> None:
    event_id = str(event["id"])
    if event_id not in d["state"]["events"]:
        return
    text = build_event_text(event, new_status)
    markup = build_event_markup(event)
    disable_preview = d["settings"].get("disable_web_preview", False)

    ev_state = d["state"]["events"][event_id]
    channels_to_forget = []
    for channel, message_id in ev_state.get("messages", {}).items():
        try:
            bot.edit_message_text(
                chat_id=channel,
                message_id=message_id,
                text=text,
                reply_markup=markup,
                disable_web_page_preview=disable_preview,
                parse_mode="HTML"
            )
            print(f"[INFO] Edited event {event_id} in {channel} -> {new_status}")
        except ApiTelegramException as te:
                                                                               
            print(f"[WARN] Edit failed for {channel}:{message_id} - {te}")
                                                                                  
            if "message to edit not found" in str(te).lower():
                channels_to_forget.append(channel)
        except Exception as e:
            print(f"[WARN] Unexpected edit error for {channel}:{message_id} - {e}")

    for ch in channels_to_forget:
        ev_state["messages"].pop(ch, None)

    ev_state["status"] = new_status
    ev_state["starts_at"] = event["start"]
    ev_state["ends_at"] = event["finish"]


@with_data
def run_cycle(d: Dict[str, Any]) -> None:
    start = now_utc()
    finish = start + timedelta(days=int(d["settings"].get("horizon_days", 14)))
    min_weight = int(d["settings"].get("min_weight", 0))

    events = fetch_ctftime_events(start, finish, limit=100)
                                      
    for ev in events:
                                                                
        if "start" not in ev and "starts" in ev:
            ev["start"] = ev["starts"]
        if "finish" not in ev and "finishes" in ev:
            ev["finish"] = ev["finishes"]

                      
    filtered = [ev for ev in events if float(safe_get(ev, "weight", 0) or 0) >= min_weight]

    for ev in filtered:
        try:
            ev_id = str(ev["id"])
            ev_start = parse_iso(ev["start"])
            ev_end = parse_iso(ev["finish"])
            status_now = build_event_status(ev_start, ev_end, now=start)

                                                
            known = d["state"]["events"].get(ev_id)
            if not known:
                                                                             
                if status_now in ("upcoming", "running"):
                    post_event_to_channels(d, ev, status_now)
                continue

                                                            
            prev_status = known.get("status", "upcoming")
            if status_now != prev_status:
                                                 
                if known.get("messages"):
                    edit_event_messages(d, ev, status_now)
                else:
                                                                                                       
                    if status_now in ("upcoming", "running"):
                        post_event_to_channels(d, ev, status_now)

                                                                                                              
            if status_now in ("upcoming", "running"):
                post_event_to_channels(d, ev, status_now)

        except Exception as e:
            print(f"[WARN] Error processing event: {e}")

    d["state"]["last_run"] = to_utc_iso(now_utc())


def scheduler_loop():
    while not scheduler_stop_flag.is_set():
        try:
            with data_lock:
                d = load_data()
                running = d["state"].get("running", False)
                interval = int(d["settings"].get("interval_sec", 300))
            if running:
                run_cycle()                                
            time.sleep(max(5, interval))
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[ERROR] Scheduler loop exception: {e}")
            time.sleep(10)


def ensure_scheduler_running():
    global scheduler_thread
    if scheduler_thread and scheduler_thread.is_alive():
        return
    scheduler_stop_flag.clear()
    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()


@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    ensure_user_is_admin(message.from_user)
    bot.reply_to(message, (
        "Welcome to CTFtime Bot!\n\n"
        "Commands:\n"
        "/help - Show help\n"
        "/control - Open control panel\n"
        "/run - Start scheduler\n"
        "/stop - Stop scheduler\n"
        "/status - Show status\n"
        "/addchannel id_or_@username - Add a channel\n"
        "/removechannel id_or_@username - Remove a channel\n"
        "/listchannels - List channels\n"
        "/setinterval seconds - Set fetch interval\n"
        "/sethorizon days - Set upcoming horizon\n"
        "/setminweight weight - Set minimum CTFtime weight\n"
    ))


@bot.message_handler(commands=["help"])
def cmd_help(message: types.Message):
    bot.reply_to(message, (
        "<b>CTFtime Telegram Bot</b>\n"
        "• Adds upcoming CTFs from CTFtime to your channels.\n"
        "• Edits messages when events start (Running) and end (Ended).\n"
        "• HTML-rich formatting with buttons and calendar links.\n\n"
        "<b>Admin-only Controls</b>\n"
        "/control • /run • /stop • /status • /addchannel • /removechannel • /listchannels • /setinterval • /sethorizon • /setminweight\n\n"
        "Make sure the bot is an admin in target channels to post and edit messages."
    ))


@bot.message_handler(commands=["run"])
@ensure_admin(user_id=0) 
def cmd_run(message: types.Message):
    @with_data
    def _run(d: Dict[str, Any]):
        d["state"]["running"] = True
    _run()
    ensure_scheduler_running()
    bot.reply_to(message, "Scheduler started. I will post/refresh events periodically.")


@bot.message_handler(commands=["stop"])
@ensure_admin(user_id=0)
def cmd_stop(message: types.Message):
    @with_data
    def _stop(d: Dict[str, Any]):
        d["state"]["running"] = False
    _stop()
    bot.reply_to(message, "Scheduler stopped.")


@bot.message_handler(commands=["status"])
@ensure_admin(user_id=0)
def cmd_status(message: types.Message):
    with data_lock:
        d = load_data()
    running = d["state"].get("running", False)
    last_run = d["state"].get("last_run") or "never"
    interval = d["settings"].get("interval_sec", 300)
    horizon = d["settings"].get("horizon_days", 14)
    minw = d["settings"].get("min_weight", 0)
    channels = d["channels"]
    events_count = len(d["state"].get("events", {}))
    bot.reply_to(message, (
        f"<b>Status</b>\n"
        f"Running: <b>{running}</b>\n"
        f"Last run: <i>{html.escape(str(last_run))}</i>\n"
        f"Interval: <b>{interval}s</b>\n"
        f"Horizon: <b>{horizon} days</b>\n"
        f"Min weight: <b>{minw}</b>\n"
        f"Channels: <b>{len(channels)}</b>\n"
        f"Tracked events: <b>{events_count}</b>"
    ))

def is_bot_admin_in_channel(channel_id: str) -> bool:
    try:
        member = bot.get_chat_member(chat_id=channel_id, user_id=bot.get_me().id)
        return member.status in ['administrator', 'creator', 'owner', 'admin' , 'moderator']
    except ApiTelegramException:
        return False
@bot.message_handler(commands=["addchannel"])
@ensure_admin(user_id=0)
def cmd_add_channel(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /addchannel <id_or_@username>")
        return
    ch = parts[1].strip()
    if ch.startswith("@") is False and ch.lstrip("-").isdigit() is False:
        ch = "@" + ch
    chat_id = bot.get_chat(ch).id
    if not is_bot_admin_in_channel(chat_id):
        bot.reply_to(message, f"Bot is not an admin in the channel: <code>{html.escape(ch)}</code>. Please add the bot as an admin first.")
        return
    ok = add_channel(str(chat_id))
    if ok:
        bot.reply_to(message, f"Added channel: <code>{html.escape(ch)}</code>.")
    else:
        bot.reply_to(message, f"Channel already present or invalid: <code>{html.escape(ch)}</code>")


@bot.message_handler(commands=["removechannel"])
@ensure_admin(user_id=0)
def cmd_remove_channel(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /removechannel <id_or_@username>")
        return
    ch = parts[1].strip()
    ok = remove_channel(ch)
    if ok:
        bot.reply_to(message, f"Removed channel: <code>{html.escape(ch)}</code>")
    else:
        bot.reply_to(message, f"Channel not found: <code>{html.escape(ch)}</code>")


@bot.message_handler(commands=["listchannels"])
@ensure_admin(user_id=0)
def cmd_list_channels(message: types.Message):
    with data_lock:
        d = load_data()
        channels = d["channels"]
    if not channels:
        bot.reply_to(message, "No channels configured. Use /addchannel to add one.")
        return
    lines = ["<b>Channels</b>"]
    for ch in channels:
        lines.append(f"• <code>{html.escape(str(ch))}</code>")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=["setinterval"])
@ensure_admin(user_id=0)
def cmd_set_interval(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        bot.reply_to(message, "Usage: /setinterval <seconds>")
        return
    seconds = max(30, int(parts[1].strip()))
    @with_data
    def _set(d: Dict[str, Any]):
        d["settings"]["interval_sec"] = seconds
    _set()
    bot.reply_to(message, f"Interval set to <b>{seconds} seconds</b>.")


@bot.message_handler(commands=["sethorizon"])
@ensure_admin(user_id=0)
def cmd_set_horizon(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        bot.reply_to(message, "Usage: /sethorizon <days>")
        return
    days = max(1, int(parts[1].strip()))
    @with_data
    def _set(d: Dict[str, Any]):
        d["settings"]["horizon_days"] = days
    _set()
    bot.reply_to(message, f"Horizon set to <b>{days} days</b>.")


@bot.message_handler(commands=["setminweight"])
@ensure_admin(user_id=0)
def cmd_set_min_weight(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /setminweight <weight>")
        return
    try:
        weight = float(parts[1].strip())
    except ValueError:
        bot.reply_to(message, "Please provide a numeric weight (e.g., 0, 10, 69.5).")
        return
    @with_data
    def _set(d: Dict[str, Any]):
        d["settings"]["min_weight"] = weight
    _set()
    bot.reply_to(message, f"Minimum weight set to <b>{weight}</b>.")



def control_panel_markup(d: Dict[str, Any]) -> types.InlineKeyboardMarkup:
    running = d["state"].get("running", False)
    kb = types.InlineKeyboardMarkup()
    row1 = [
        types.InlineKeyboardButton("▶️ Run" if not running else "⏸ Stop", callback_data="cp:toggle_run"),
        types.InlineKeyboardButton("🔁 Cycle Now", callback_data="cp:cycle")
    ]
    row2 = [
        types.InlineKeyboardButton("📡 Channels", callback_data="cp:list_channels"),
        types.InlineKeyboardButton("⚙️ Settings", callback_data="cp:settings")
    ]
    kb.row(*row1)
    kb.row(*row2)
    return kb


@bot.message_handler(commands=["control"])
@ensure_admin(user_id=0)
def cmd_control(message: types.Message):
    with data_lock:
        d = load_data()
    bot.reply_to(message, "Control Panel:", reply_markup=control_panel_markup(d))


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("cp:"))
def on_control_action(call: types.CallbackQuery):
    action = call.data.split(":", 1)[1]
    user_id = call.from_user.id
    with data_lock:
        d = load_data()
        if not is_admin(user_id, d):
            bot.answer_callback_query(call.id, "Admins only.")
            return

        if action == "toggle_run":
            d["state"]["running"] = not d["state"].get("running", False)
            save_data(d)
            ensure_scheduler_running()
            bot.answer_callback_query(call.id, "Scheduler toggled.")
            try:
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=control_panel_markup(d))
            except Exception:
                pass
        elif action == "cycle":
            bot.answer_callback_query(call.id, "Running one cycle...")
                                            
            run_cycle()
        elif action == "list_channels":
            channels = d.get("channels", [])
            text = "No channels configured." if not channels else "Channels:\n" + "\n".join(f"• {ch}" for ch in channels)
            bot.answer_callback_query(call.id, "OK")
            bot.send_message(call.message.chat.id, html.escape(text))
        elif action == "settings":
            s = d.get("settings", {})
            text = (
                f"Interval: {s.get('interval_sec', 300)}s\n"
                f"Horizon: {s.get('horizon_days', 14)} days\n"
                f"Min weight: {s.get('min_weight', 0)}\n"
                f"Disable web preview: {s.get('disable_web_preview', False)}\n"
            )
            bot.answer_callback_query(call.id, "OK")
            bot.send_message(call.message.chat.id, f"<b>Settings</b>\n<pre>{html.escape(text)}</pre>")
                
def main():
    print("[INFO] Bot starting. Press Ctrl+C to stop.")
    ensure_scheduler_running()
                      
    bot.infinity_polling(timeout=60, long_polling_timeout=60)


if __name__ == "__main__":
    main()
