from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models.database import Appointment, Procedure, Client, get_db, InactiveSlot
from config import WORK_START, WORK_END, SLOT_DURATION, ADMIN_IDS
from aiogram import Bot

def get_available_slots(date=None):
    """Получение доступных слотов с учетом длительности процедур"""
    db = next(get_db())
    today = datetime.now().date()
    
    if date is None:
        # Получаем даты на ближайшие 14 дней
        dates = []
        for i in range(14):
            current_date = today + timedelta(days=i)
            # Проверяем, является ли дата выходным днем
            inactive_slot = db.query(InactiveSlot).filter(
                InactiveSlot.date == current_date,
                InactiveSlot.is_weekend == True
            ).first()
            if not inactive_slot:
                dates.append(current_date)
        return dates
    
    # Получаем все записи на выбранную дату
    appointments = db.query(Appointment).filter(
        Appointment.date >= date,
        Appointment.date < date + timedelta(days=1),
        Appointment.status == 'scheduled'
    ).all()
    
    # Базовые временные слоты
    base_slots = [
        "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00"
    ]
    
    # Получаем неактивные слоты на эту дату
    inactive_slots = db.query(InactiveSlot).filter(
        InactiveSlot.date == date
    ).all()
    inactive_times = [slot.time for slot in inactive_slots]
    
    # Создаем список занятых временных слотов
    occupied_slots = []
    for appointment in appointments:
        start_time = appointment.date.time()
        duration = appointment.procedure.duration
        end_time = (datetime.combine(date, start_time) + timedelta(hours=duration)).time()
        
        # Добавляем все слоты, которые перекрываются с этой записью
        current_time = start_time
        while current_time < end_time:
            occupied_slots.append(current_time.strftime("%H:%M"))
            current_time = (datetime.combine(date, current_time) + timedelta(hours=1)).time()
    
    # Фильтруем доступные слоты, исключая занятые и неактивные
    available_slots = []
    for slot in base_slots:
        if slot not in occupied_slots and slot not in inactive_times:
            available_slots.append(slot)
    
    return available_slots

def create_appointment(db: Session, client_id: int, procedure_id: int, date: datetime) -> Appointment:
    """Создание новой записи"""
    appointment = Appointment(
        client_id=client_id,
        procedure_id=procedure_id,
        date=date,
        status='scheduled'
    )
    db.add(appointment)
    db.commit()
    return appointment

def get_procedures(db: Session = None):
    """Получение списка всех процедур"""
    if db is None:
        db = next(get_db())
    return db.query(Procedure).all()

def get_procedure_by_id(procedure_id: int, db: Session = None):
    """Получение процедуры по ID"""
    if db is None:
        db = next(get_db())
    return db.query(Procedure).filter(Procedure.id == procedure_id).first()

def get_procedure_duration(procedure_id: int, db: Session = None) -> float:
    """Получение длительности процедуры в часах"""
    procedure = get_procedure_by_id(procedure_id, db)
    return procedure.duration if procedure else 0.0

def cancel_appointment(db: Session, appointment_id: int) -> bool:
    """
    Отмена записи
    """
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.status == 'scheduled'
    ).first()
    
    if not appointment:
        return False
    
    appointment.status = 'cancelled'
    db.commit()
    return True

def complete_appointment(db: Session, appointment_id: int) -> bool:
    """
    Завершение записи
    """
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.status == 'scheduled'
    ).first()
    
    if not appointment:
        return False
    
    appointment.status = 'completed'
    db.commit()
    return True

def delete_appointment(db: Session, appointment_id: int) -> bool:
    """
    Удаление записи по ID
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return False
    
    db.delete(appointment)
    db.commit()
    return True

async def notify_admins_about_new_appointment(bot: Bot, appointment: Appointment):
    """
    Отправка уведомления администраторам о новой записи
    """
    message = (
        f"🆕 Новая запись!\n\n"
        f"ID: {appointment.id}\n"
        f"Процедура: {appointment.procedure.name}\n"
        f"Длительность: {appointment.procedure.duration}ч\n"
        f"Дата: {appointment.date.strftime('%d.%m.%Y')}\n"
        f"Время: {appointment.date.strftime('%H:%M')}\n"
        f"Клиент: {appointment.client.name}\n"
        f"Username: @{appointment.client.username}\n"
        f"Телефон: {appointment.client.phone or 'Не указан'}"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message)
        except Exception as e:
            print(f"Ошибка при отправке уведомления администратору {admin_id}: {str(e)}")

def set_inactive_slot(db: Session, date: datetime.date, time: str, is_weekend: bool = False) -> bool:
    """
    Установка временного слота как неактивного
    """
    try:
        # Проверяем, существует ли уже такой слот
        existing_slot = db.query(InactiveSlot).filter(
            InactiveSlot.date == date,
            InactiveSlot.time == time
        ).first()
        
        if existing_slot:
            return True
            
        inactive_slot = InactiveSlot(date=date, time=time, is_weekend=is_weekend)
        
        db.add(inactive_slot)
        db.commit()
        
        # Проверяем, что слот действительно добавлен
        added_slot = db.query(InactiveSlot).filter(
            InactiveSlot.date == date,
            InactiveSlot.time == time
        ).first()
        
        if not added_slot:
            return False
            
        return True
    except Exception as e:
        db.rollback()
        return False

def remove_inactive_slot(db: Session, date: datetime.date, time: str) -> bool:
    """
    Удаление временного слота из неактивных
    """
    try:
        inactive_slot = db.query(InactiveSlot).filter(
            InactiveSlot.date == date,
            InactiveSlot.time == time
        ).first()
        if inactive_slot:
            db.delete(inactive_slot)
            db.commit()
            return True
        return False
    except Exception:
        db.rollback()
        return False

def get_inactive_slots(db: Session, date: datetime.date = None) -> list:
    """
    Получение списка неактивных слотов
    """
    query = db.query(InactiveSlot)
    if date:
        query = query.filter(InactiveSlot.date == date)
    return query.order_by(InactiveSlot.date, InactiveSlot.time).all()

async def init_inactive_dates(db: Session = None):
    """
    Инициализация неактивных слотов на выходные дни
    """
    if db is None:
        db = next(get_db())
    
    today = datetime.now().date()
    
    # Базовые временные слоты
    base_slots = [
        "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", 
        "15:00", "16:00", "17:00", "18:00", "19:00", "20:00"
    ]
    
    # Добавляем выходные на ближайшие 30 дней
    for i in range(30):
        date = today + timedelta(days=i)
        if date.weekday() >= 5:  # 5 - суббота, 6 - воскресенье
            # Добавляем все временные слоты для выходного дня
            for time in base_slots:
                # Проверяем, не существует ли уже такой слот
                existing = db.query(InactiveSlot).filter(
                    InactiveSlot.date == date,
                    InactiveSlot.time == time
                ).first()
                if not existing:
                    inactive_slot = InactiveSlot(date=date, time=time, is_weekend=True)
                    db.add(inactive_slot)
    
    db.commit() 