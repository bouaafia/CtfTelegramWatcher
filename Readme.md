# 🚩 CTFtime Telegram Bot (TeleBot)

A clean, fast Telegram bot that posts upcoming CTFs from [CTFtime](https://ctftime.org) to your channels — with pretty HTML, buttons, and zero duplicates. It auto-edits posts when events start or end, and keeps everything in a simple JSON file.

✨ Highlights
- 🧠 Smart: Tracks sent posts per channel; never double-posts
- ⏱️ Auto: Scheduler posts and updates (Upcoming → Running → Ended)
- 🖼️ Polished: HTML formatting, inline buttons, Google Calendar link
- 💾 Durable: JSON persistence for channels, settings, messages
- 🔐 Safe: Admin-only controls; first /start user becomes admin

---

## 🚀 Quick Start

1) Install
```bash
pip install -r requirements.txt
```

2) Configure
```bash
# from @BotFather Create your bot and get Token and put it in the code
```

3) Run
```bash
python main.py
```

4) In Telegram
- DM your bot: `/start` (you become admin)
- Add the bot as Admin in your channel(s)
- `/addchannel @your_channel` (or `/addchannel -1001234567890`)
- `/run` to start posting

---

## 🧩 What You Get

- 🟡🟢🔴 Status badges (Upcoming / Running / Ended)
- 🔗 Buttons: CTFtime • Website • Add to Google Calendar
- 🔁 Auto-update messages when status changes
- 🧾 Clean JSON state: channels, settings, message IDs
- 🛡️ Robust error handling, rate-limit retries, safe HTML fallbacks

---

## 🕹️ Commands (Admin)

- `/control` – Open control panel
- `/run` • `/stop` – Start/stop scheduler
- `/status` – Quick status and stats
- `/addchannel <id_or_@username>` – Add a channel to post into
- `/removechannel <id_or_@username>` – Remove a channel
- `/listchannels` – Show configured channels
- `/setinterval <seconds>` – Fetch interval (default 300)
- `/sethorizon <days>` – Lookahead window (default 14)
- `/setminweight <weight>` – Minimum CTFtime weight to post

Tip: Make sure the bot is an Admin in every target channel.

---

## 🎛️ Control Panel

- ▶️/⏸ Run/Stop scheduler
- 🔁 Cycle Now (fetch once instantly)
- 📡 Channels list
- ⚙️ Settings preview

---

## 🧠 Tips

- Time is shown in UTC for consistency
- Deleted/non-editable posts are handled gracefully
- Need richer copy? Swap message builder for your own style

---

## 📦 Requirements

- Python 3.9+
- `pyTelegramBotAPI` • `requests`

---
