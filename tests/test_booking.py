import pytest
from datetime import datetime, timedelta, date
from .conftest import db_session, test_procedure, test_client
from sqlalchemy.orm import Session
from services.booking import (
    get_available_slots,
    create_appointment,
    get_procedures,
    get_procedure_by_id,
    get_procedure_duration,
    cancel_appointment,
    complete_appointment,
    delete_appointment,
    notify_admins_about_new_appointment,
    set_inactive_slot,
    remove_inactive_slot,
    get_inactive_slots,
    init_inactive_dates
)
from models.database import Appointment, Procedure, Client, InactiveSlot
from aiogram import Bot


def test_get_available_slots(db_session):
    """Тест получения доступных слотов"""
    # Тест без указания даты
    dates = get_available_slots()
    assert isinstance(dates, list)
    assert len(dates) > 0
    
    # Тест с указанием даты
    test_date = datetime.now().date()
    slots = get_available_slots(test_date)
    assert isinstance(slots, list)
    assert all(isinstance(slot, str) for slot in slots)

def test_create_appointment(db_session, test_client, test_procedure):
    """Тест создания записи"""
    test_date = datetime.now() + timedelta(days=1)
    appointment = create_appointment(
        db_session,
        test_client.id,
        test_procedure.id,
        test_date
    )
    
    assert isinstance(appointment, Appointment)
    assert appointment.client_id == test_client.id
    assert appointment.procedure_id == test_procedure.id
    assert appointment.date == test_date
    assert appointment.status == 'scheduled'

def test_get_procedures(db_session, test_procedure):
    """Тест получения списка процедур"""
    # Используем тестовую сессию базы данных
    procedures = get_procedures(db=db_session)
    
    # Проверяем, что возвращается список
    assert isinstance(procedures, list)
    
    # Проверяем, что список не пустой
    assert len(procedures) > 0
    
    # Проверяем, что в списке есть тестовая процедура, которую мы создали через фикстуру test_procedure
    assert any(p.id == test_procedure.id for p in procedures)
    
    # Проверяем, что все процедуры в списке уникальны
    procedure_ids = [p.id for p in procedures]
    assert len(procedure_ids) == len(set(procedure_ids)), "В списке есть дубликаты процедур"

def test_get_procedure_by_id(db_session, test_procedure):
    """Тест получения процедуры по ID"""
    procedure = get_procedure_by_id(test_procedure.id)
    assert procedure is not None
    assert procedure.id == test_procedure.id

def test_get_procedure_duration(db_session, test_procedure):
    """Тест получения длительности процедуры"""
    # Получаем длительность процедуры по её ID, передавая тестовую сессию
    duration = get_procedure_duration(test_procedure.id, db=db_session)
    
    # Проверяем, что длительность совпадает с ожидаемой
    assert duration == test_procedure.duration, f"Ожидалась длительность {test_procedure.duration}, получено {duration}"

def test_cancel_appointment(db_session, test_client, test_procedure):
    """Тест отмены записи"""
    test_date = datetime.now() + timedelta(days=1)
    appointment = create_appointment(
        db_session,
        test_client.id,
        test_procedure.id,
        test_date
    )
    
    result = cancel_appointment(db_session, appointment.id)
    assert result is True
    
    updated_appointment = db_session.query(Appointment).get(appointment.id)
    assert updated_appointment.status == 'cancelled'

def test_complete_appointment(db_session, test_client, test_procedure):
    """Тест завершения записи"""
    test_date = datetime.now() + timedelta(days=1)
    appointment = create_appointment(
        db_session,
        test_client.id,
        test_procedure.id,
        test_date
    )
    
    result = complete_appointment(db_session, appointment.id)
    assert result is True
    
    updated_appointment = db_session.query(Appointment).get(appointment.id)
    assert updated_appointment.status == 'completed'

def test_delete_appointment(db_session, test_client, test_procedure):
    """Тест удаления записи"""
    test_date = datetime.now() + timedelta(days=1)
    appointment = create_appointment(
        db_session,
        test_client.id,
        test_procedure.id,
        test_date
    )
    
    result = delete_appointment(db_session, appointment.id)
    assert result is True
    
    deleted_appointment = db_session.query(Appointment).get(appointment.id)
    assert deleted_appointment is None

@pytest.mark.asyncio
async def test_notify_admins_about_new_appointment(db_session, test_client, test_procedure, mocker):
    """Тест отправки уведомления администраторам"""
    # Создаем тестовую запись
    test_date = datetime.now() + timedelta(days=1)
    appointment = create_appointment(
        db_session,
        test_client.id,
        test_procedure.id,
        test_date
    )
    
    # Мокаем объект Bot и его метод send_message
    mock_bot = mocker.Mock()
    mock_bot.send_message = mocker.AsyncMock()
    
    # Мокаем конфигурацию ADMIN_IDS
    mocker.patch('config.ADMIN_IDS', [123456789])
    
    # Вызываем тестируемую функцию
    await notify_admins_about_new_appointment(mock_bot, appointment)
    
    # Проверяем, что метод send_message был вызван
    mock_bot.send_message.assert_called()

def test_set_inactive_slot(db_session):
    """Тест установки неактивного слота"""
    test_date = datetime.now().date()
    test_time = "10:00"
    
    result = set_inactive_slot(db_session, test_date, test_time)
    assert result is True
    
    # Проверяем, что слот действительно добавлен
    inactive_slot = db_session.query(InactiveSlot).filter(
        InactiveSlot.date == test_date,
        InactiveSlot.time == test_time
    ).first()
    assert inactive_slot is not None

def test_remove_inactive_slot(db_session):
    """Тест удаления неактивного слота"""
    test_date = datetime.now().date()
    test_time = "10:00"
    
    # Сначала создаем неактивный слот
    set_inactive_slot(db_session, test_date, test_time)
    
    # Затем удаляем его
    result = remove_inactive_slot(db_session, test_date, test_time)
    assert result is True
    
    # Проверяем, что слот действительно удален
    inactive_slot = db_session.query(InactiveSlot).filter(
        InactiveSlot.date == test_date,
        InactiveSlot.time == test_time
    ).first()
    assert inactive_slot is None

def test_get_inactive_slots(db_session):
    """Тест получения списка неактивных слотов"""
    test_date = datetime.now().date()
    test_time = "10:00"
    
    # Создаем тестовый неактивный слот
    set_inactive_slot(db_session, test_date, test_time)
    
    # Получаем все неактивные слоты
    all_slots = get_inactive_slots(db_session)
    assert isinstance(all_slots, list)
    
    # Получаем неактивные слоты для конкретной даты
    date_slots = get_inactive_slots(db_session, test_date)
    assert isinstance(date_slots, list)
    assert len(date_slots) > 0

@pytest.mark.asyncio
async def test_init_inactive_dates(db_session):
    """Тест инициализации неактивных дат"""
    # Очищаем все существующие неактивные слоты
    db_session.query(InactiveSlot).delete()
    db_session.commit()
    
    # Выполняем инициализацию, передавая тестовую сессию
    await init_inactive_dates(db=db_session)
    
    # Проверяем, что выходные дни добавлены
    today = datetime.now().date()
    weekend_slots_found = False
    
    # Проверяем только ближайшие 7 дней, чтобы тест был более стабильным
    for i in range(7):
        test_date = today + timedelta(days=i)
        if test_date.weekday() >= 5:  # 5 - суббота, 6 - воскресенье
            inactive_slots = db_session.query(InactiveSlot).filter(
                InactiveSlot.date == test_date,
                InactiveSlot.is_weekend == True
            ).all()
            
            if inactive_slots:
                weekend_slots_found = True
                # Проверяем, что добавлены все базовые слоты
                base_slots = [
                    "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", 
                    "15:00", "16:00", "17:00", "18:00", "19:00", "20:00"
                ]
                assert len(inactive_slots) == len(base_slots)
                break
    
    assert weekend_slots_found, "Не найдены неактивные слоты для выходных дней" 