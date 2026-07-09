import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env.telegram from project root
_env_path = Path(__file__).parent.parent / ".env.telegram"
load_dotenv(_env_path)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_raw_ids = os.environ.get("TELEGRAM_ALLOWED_IDS", "")
ALLOWED_USER_IDS: list[int] = [
    int(uid.strip()) for uid in _raw_ids.split(",") if uid.strip().isdigit()
]
PROJECT_ROOT = Path(__file__).parent.parent
