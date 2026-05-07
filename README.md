# FreeFire SaaS System

A fully-featured SaaS system for FreeFire: Telegram Bot, TCP Client, Flask Web Panel, Admin Panel, Referral System, Premium System, Multi-Account Bot Manager, and Emotes System.

---

## Project Structure

```
project/
├── main.py          — Telegram Bot (Emotes, Bots, Referral, Premium, Admin)
├── tcp_client.py    — Guest Login TCP system + session manager
├── bot_manager.py   — Multi-account thread manager
├── app.py           — Flask web backend (API + Web Panel)
├── models.py        — SQLAlchemy database models
├── config.py        — All configuration & secrets
├── requirements.txt — Python dependencies
├── database.db      — SQLite database (auto-created on first run)
├── token.json       — TCP login session storage (auto-created)
│
├── templates/
│   ├── login.html       — Register / Login page
│   ├── dashboard.html   — User dashboard
│   └── admin.html       — Admin panel
│
└── static/
    ├── css/style.css
    └── js/main.js
```

---

## Installation

### 1. Requirements

- Python 3.10+
- pip

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Open `config.py` and set:

```python
BOT_TOKEN  = "your_telegram_bot_token_here"
SECRET_KEY = "your_random_secret_key_here"
```

Optionally set via environment variables:
```bash
export BOT_TOKEN="your_token"
export SECRET_KEY="random_secret"
```

---

## Running

### Start the Web Panel (Flask)

```bash
python app.py
```

The panel will be available at: `http://localhost:5000`

**Default Admin Account:**
- Email: `admin@localhost`
- Password: `Admin@123`

> Change the admin password immediately after first login!

### Start the Telegram Bot

In a **separate terminal**:

```bash
python main.py
```

---

## Setup Guide

### Database

The SQLite database is auto-created on first run of `app.py`.  
To use PostgreSQL instead, set `DATABASE_URI` in `config.py`:

```python
DATABASE_URI = "postgresql://user:pass@localhost/ffdb"
```

### Telegram Bot Setup

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Copy the token into `config.py` → `BOT_TOKEN`
3. Run `python main.py`

### TCP Client

The TCP client connects to FreeFire login servers.  
To test manually:

```bash
python tcp_client.py <uid> <region> <password>
```

Supported regions: `IND, BR, SG, VN, TH, US, ID, PK, BD, ME`

### Linking Telegram to Web Account

1. Register on the web panel
2. Open the bot → Settings → your Telegram ID is shown
3. Enter your Telegram ID in the web panel profile settings

---

## Features

| Feature             | Description                                              |
|---------------------|----------------------------------------------------------|
| Auth                | Register/Login with bcrypt hashed passwords + JWT cookies |
| Referral System     | Unique codes, reward credits, unlock TCP on referral     |
| Premium System      | Admin assigns premium, auto-expiry, higher limits        |
| Emotes System       | 250+ emotes with pagination, cooldown, inline buttons    |
| TCP Client          | Real SSL TCP login to FreeFire servers, token saved      |
| Multi-Account Bots  | Per-account threads, start/stop/restart, status tracking |
| Admin Panel         | Manage users, admins, permissions, applications, logs    |
| Broadcast System    | Send to all / premium / selected users (text + image)    |
| Log System          | Login, TCP, bot, admin, broadcast logs with filters      |
| Apply Admin         | Users apply via bot or web, admin approve/reject         |

---

## Security Notes

- Change `SECRET_KEY` in `config.py` before deploying
- Change the default admin password immediately
- Use HTTPS in production (e.g. with Nginx + Certbot)
- Never commit `config.py` with real tokens to git

---

## Running on VPS (Production)

Use `screen` or `systemd` to run both services in background:

```bash
# Screen method
screen -S webapp
python app.py
# Ctrl+A, D to detach

screen -S telebot
python main.py
# Ctrl+A, D to detach
```

Or use `systemd` services for auto-restart on reboot.

---

## Developer

Telegram: [@majid12390](https://t.me/majid12390)
