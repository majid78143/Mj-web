import os

# ============================================================
#  CONFIG — edit these before running
# ============================================================

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DEVELOPER_USERNAME = "@majid12390"

# Flask
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-super-secret-key-123")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# Database
DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///database.db")

# TCP / FreeFire API
EMOTE_API_BASE = "https://emote-api-ob53.vercel.app/api/send"

# Referral unlock rule
REFERRALS_REQUIRED_FOR_TCP = 1  # how many referrals a user needs to unlock TCP

# Cooldowns (seconds)
COOLDOWN_FREE    = 20
COOLDOWN_PREMIUM = 5

# Bot limits
MAX_BOTS_FREE    = 1
MAX_BOTS_PREMIUM = 10

# Flask host/port
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
