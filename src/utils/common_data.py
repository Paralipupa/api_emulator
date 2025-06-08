
from datetime import datetime
from src.settings import settings

def get_webhook_url():
    return settings.WEBHOOK_URL

def get_current_timestamp():
    return str(datetime.utcnow().timestamp()).split(".")[0]
