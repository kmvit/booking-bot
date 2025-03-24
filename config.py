import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot settings
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Очищаем строку от комментариев и пробелов
admin_ids_str = os.getenv('ADMIN_IDS', '').split('#')[0].strip()
ADMIN_IDS = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip()]

# Database settings
DATABASE_URL = os.getenv('DATABASE_URL')

# Time settings
TIMEZONE = os.getenv('TIMEZONE', 'Europe/Moscow')

# Reminder settings
REMINDER_BEFORE_DAY = os.getenv('REMINDER_BEFORE_DAY', '10:00')
REMINDER_DAY_OF = os.getenv('REMINDER_DAY_OF', '08:00')

# Working hours
WORK_START = os.getenv('WORK_START', '09:00')
WORK_END = os.getenv('WORK_END', '20:00')
SLOT_DURATION = int(os.getenv('SLOT_DURATION', '60')) 