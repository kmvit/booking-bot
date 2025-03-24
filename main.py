import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from config import BOT_TOKEN
from handlers import client, admin
from models.database import Base, engine
from services.booking import init_inactive_dates
from scheduler.notifier import setup_scheduler
from models.database import InactiveSlot
from datetime import datetime, timedelta
from models.database import get_db

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем порт из переменных окружения для Heroku
PORT = int(os.environ.get('PORT', 5000))
# Получаем URL для вебхука из переменных окружения
WEBHOOK_HOST = os.environ.get('WEBHOOK_HOST', '')
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Определяем режим запуска - webhook или polling
WEBHOOK_MODE = os.environ.get('WEBHOOK_MODE', 'False').lower() == 'true'

async def init_inactive_dates():
    """
    Инициализация неактивных дат на выходные дни
    """
    db = next(get_db())
    today = datetime.now().date()
    
    # Добавляем выходные на ближайшие 30 дней
    for i in range(30):
        date = today + timedelta(days=i)
        if date.weekday() >= 5:  # 5 - суббота, 6 - воскресенье
            # Проверяем, не существует ли уже такая дата
            existing = db.query(InactiveSlot).filter(InactiveSlot.date == date).first()
            if not existing:
                inactive_slot = InactiveSlot(date=date, is_weekend=True)
                db.add(inactive_slot)
    
    db.commit()

async def start_webhook(bot, dp):
    """Запуск бота в режиме webhook для Heroku"""
    try:
        # Создаем приложение aiohttp
        app = web.Application()
        
        # Настройка вебхука
        await bot.set_webhook(url=WEBHOOK_URL)
        
        # Настройка обработчика
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
        
        # Настройка веб-сервера
        setup_application(app, dp, bot=bot)
        
        # Запускаем веб-сервер
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host='0.0.0.0', port=PORT)
        await site.start()
        
        logger.info(f"Bot started in webhook mode on port {PORT}")
        
        # Блокируем выполнение, чтобы сервер продолжал работать
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Ошибка при запуске webhook: {e}")
        raise

async def start_polling(bot, dp):
    """Запуск бота в режиме long polling для локальной разработки"""
    try:
        logger.info("Bot started in polling mode")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске polling: {e}")
        raise

async def main():
    try:
        # Создаем таблицы в базе данных
        Base.metadata.create_all(engine)
        
        # Инициализируем неактивные слоты
        await init_inactive_dates()
        
        # Инициализируем бота и диспетчер
        bot = Bot(token=BOT_TOKEN)
        dp = Dispatcher()
        
        # Регистрируем роутеры
        dp.include_router(client.router)
        dp.include_router(admin.router)

        # Настройка планировщика для напоминаний
        scheduler = setup_scheduler(bot)
        scheduler.start()

        # Запуск бота в зависимости от режима
        if WEBHOOK_MODE:
            await start_webhook(bot, dp)
        else:
            await start_polling(bot, dp)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise
    finally:
        if 'scheduler' in locals():
            scheduler.shutdown()
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main()) 