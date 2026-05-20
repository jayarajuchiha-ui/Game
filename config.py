import os
from os import getenv
from dotenv import load_dotenv

load_dotenv()

# Safely cast to int with a fallback "0" to prevent empty string crashes
API_ID = int(getenv("API_ID", "0"))
API_HASH = getenv("API_HASH", "")
BOT_TOKEN = getenv("BOT_TOKEN", "8793834902:AAEUH8NxVY2J00vepALQw5WSivD4Pmi6IB8"))
OWNER_ID = int(getenv("OWNER_ID", "8425183548"))
MONGO_URL = getenv("MONGO_URL", None)
