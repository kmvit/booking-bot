from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from models.database import get_db, Appointment
from config import REMINDER_BEFORE_DAY, REMINDER_DAY_OF

async def send_reminder(bot, chat_id: int, appointment: Appointment):
    """
    Отправка напоминания клиенту
    """
    message = (
        f"🔔  Здравствуйте!🤍\n\n"
        f"Вы записаны на процедуру:\n"
        f"{appointment.procedure.name}\n"
        f"📅 Дата: {appointment.date.strftime('%d.%m.%Y')}\n"
        f"🕒 Время: {appointment.date.strftime('%H:%M')}\n\n"
        f"Адрес: улица Пушкинская 31, корпус 3\n"
        f"Чтобы вам было легче меня найти, прикрепляю точные координаты студии, вы можете ввести их в картах:\n"
        f"44.0520270, 43.0663848\n"
        f"Ваш косметолог ~ Полина💜"
    )
    
    try:
        await bot.send_message(chat_id=chat_id, text=message)
    except Exception as e:
        print(f"Ошибка отправки напоминания: {e}")

async def check_and_send_reminders(bot):
    """
    Проверка и отправка напоминаний
    """
    db = next(get_db())
    now = datetime.now()
    
    # Проверяем записи на завтра
    tomorrow = now.date() + timedelta(days=1)
    tomorrow_appointments = db.query(Appointment).filter(
        Appointment.date >= tomorrow,
        Appointment.date < tomorrow + timedelta(days=1),
        Appointment.status == 'scheduled',
        Appointment.reminder_sent == False
    ).all()
    
    for appointment in tomorrow_appointments:
        await send_reminder(bot, appointment.client.telegram_id, appointment)
        appointment.reminder_sent = True
    
    # Проверяем записи на сегодня
    today_appointments = db.query(Appointment).filter(
        Appointment.date >= now.date(),
        Appointment.date < now.date() + timedelta(days=1),
        Appointment.status == 'scheduled',
        Appointment.reminder_sent == False
    ).all()
    
    for appointment in today_appointments:
        await send_reminder(bot, appointment.client.telegram_id, appointment)
        appointment.reminder_sent = True
    
    db.commit()

def setup_scheduler(bot):
    """
    Настройка планировщика для отправки напоминаний
    """
    scheduler = AsyncIOScheduler()
    
    # Добавляем задачи для проверки и отправки напоминаний
    scheduler.add_job(
        check_and_send_reminders,
        CronTrigger(hour=13, minute=32),  # В 8:00
        args=[bot],
        id='morning_reminders'
    )
    
    scheduler.add_job(
        check_and_send_reminders,
        CronTrigger(hour=13, minute=41),  # В 10:00
        args=[bot],
        id='evening_reminders'
    )
    
    return scheduler 