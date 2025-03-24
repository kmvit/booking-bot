import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
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

        # Запуск бота в режиме polling
        logger.info("Бот запущен в режиме polling")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise
    finally:
        if 'scheduler' in locals():
            scheduler.shutdown()
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main()) 