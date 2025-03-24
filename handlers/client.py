from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models.database import get_db, Client, Appointment
from services.booking import (
    get_available_slots, create_appointment, cancel_appointment,
    get_procedures, get_procedure_by_id,
    notify_admins_about_new_appointment
)

router = Router()

class BookingStates(StatesGroup):
    selecting_procedure = State()
    selecting_date = State()
    selecting_time = State()
    confirming = State()

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Добро пожаловать в бот для записи на процедуры!\n\n"
        "Выберите действие:",
        reply_markup=create_client_keyboard()
    )

@router.message(F.text == "📝 Записаться")
async def start_booking(message: Message, state: FSMContext):
    procedures = get_procedures()
    keyboard = []
    for procedure in procedures:
        keyboard.append([
            InlineKeyboardButton(
                text=f"{procedure.name} ({procedure.duration}ч)",
                callback_data=f"proc_{procedure.id}"
            )
        ])
    
    await message.answer(
        "Выберите процедуру:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await state.set_state(BookingStates.selecting_procedure)

@router.callback_query(BookingStates.selecting_procedure, F.data.startswith("proc_"))
async def process_procedure_selection(callback: CallbackQuery, state: FSMContext):
    procedure_id = int(callback.data.split("_")[1])
    procedure = get_procedure_by_id(procedure_id)
    
    await state.update_data(procedure_id=procedure_id)
    
    available_dates = get_available_slots()
    if not available_dates:
        await callback.message.edit_text(
            "К сожалению, на ближайшие дни все слоты заняты. "
            "Пожалуйста, попробуйте позже."
        )
        await state.clear()
        return

    await callback.message.edit_text(
        f"Выбрана процедура: {procedure.name}\n"
        f"Длительность: {procedure.duration}ч\n\n"
        "Выберите дату:",
        reply_markup=create_dates_keyboard(available_dates)
    )
    await state.set_state(BookingStates.selecting_date)

@router.callback_query(BookingStates.selecting_date, F.data.startswith("date_"))
async def process_date_selection(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split("_")[1]
    date = datetime.strptime(date_str, "%Y-%m-%d").date()
    await state.update_data(appointment_date=date)
    
    # Получаем доступные слоты
    available_slots = get_available_slots(date)
    
    if not available_slots:
        await callback.message.edit_text(
            f"На {date.strftime('%d.%m.%Y')} нет доступных слотов."
        )
        return
    
    # Создаем клавиатуру с доступными слотами
    keyboard = []
    for slot in available_slots:
        keyboard.append([
            InlineKeyboardButton(
                text=slot,
                callback_data=f"time_{slot}"
            )
        ])
    
    await callback.message.edit_text(
        f"Выберите время на {date.strftime('%d.%m.%Y')}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await state.set_state(BookingStates.selecting_time)

@router.callback_query(BookingStates.selecting_time, F.data.startswith("time_"))
async def process_time_selection(callback: CallbackQuery, state: FSMContext):
    selected_time = callback.data.split("_")[1]
    data = await state.get_data()
    selected_date = data['appointment_date']
    procedure_id = data['procedure_id']
    procedure = get_procedure_by_id(procedure_id)
    
    # Создаем полную дату и время
    appointment_datetime = datetime.combine(
        selected_date,
        datetime.strptime(selected_time, "%H:%M").time()
    )
    
    await state.update_data(appointment_datetime=appointment_datetime)
    
    await callback.message.edit_text(
        f"Подтвердите запись:\n\n"
        f"Процедура: {procedure.name}\n"
        f"Длительность: {procedure.duration}ч\n"
        f"Дата: {selected_date.strftime('%d.%m.%Y')}\n"
        f"Время: {selected_time}",
        reply_markup=create_confirmation_keyboard()
    )
    await state.set_state(BookingStates.confirming)

@router.callback_query(BookingStates.confirming, F.data == "confirm")
async def process_confirmation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    appointment_datetime = data['appointment_datetime']
    procedure_id = data['procedure_id']
    
    # Получаем или создаем клиента
    db = next(get_db())
    client = db.query(Client).filter(Client.telegram_id == callback.from_user.id).first()
    
    if not client:
        client = Client(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            name=callback.from_user.full_name
        )
        db.add(client)
        db.commit()
    
    try:
        appointment = create_appointment(db, client.id, procedure_id, appointment_datetime)
        await callback.message.edit_text(
            f"✅ Запись успешно создана!\n\n"
            f"Процедура: {appointment.procedure.name}\n"
            f"Длительность: {appointment.procedure.duration}ч\n"
            f"Дата: {appointment.date.strftime('%d.%m.%Y')}\n"
            f"Время: {appointment.date.strftime('%H:%M')}"
        )
        
        # Отправляем уведомление администраторам
        bot = callback.bot
        await notify_admins_about_new_appointment(bot, appointment)
        
    except ValueError as e:
        await callback.message.edit_text(
            f"❌ Ошибка при создании записи: {str(e)}\n"
            "Пожалуйста, попробуйте выбрать другое время."
        )
    
    await state.clear()

@router.message(F.text == "📋 Мои записи")
async def show_my_appointments(message: Message):
    db = next(get_db())
    client = db.query(Client).filter(Client.telegram_id == message.from_user.id).first()
    
    if not client:
        await message.answer("У вас пока нет записей.")
        return
    
    appointments = db.query(Appointment).filter(
        Appointment.client_id == client.id,
        Appointment.status == 'scheduled'
    ).order_by(Appointment.date).all()
    
    if not appointments:
        await message.answer("У вас пока нет записей.")
        return
    
    text = "📋 Ваши записи:\n\n"
    for app in appointments:
        text += (
            f"ID: {app.id}\n"
            f"Процедура: {app.procedure.name}\n"
            f"Длительность: {app.procedure.duration}ч\n"
            f"📅 {app.date.strftime('%d.%m.%Y %H:%M')}\n\n"
        )
    
    await message.answer(text, reply_markup=create_appointments_keyboard(appointments))

@router.callback_query(F.data.startswith("cancel_"))
async def process_cancel_selection(callback: CallbackQuery):
    appointment_id = int(callback.data.split("_")[1])
    db = next(get_db())
    
    # Сначала получаем клиента
    client = db.query(Client).filter(Client.telegram_id == callback.from_user.id).first()
    if not client:
        await callback.answer("Клиент не найден", show_alert=True)
        return
    
    # Затем проверяем, принадлежит ли запись этому клиенту
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.client_id == client.id
    ).first()
    
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    try:
        if cancel_appointment(db, appointment_id):
            await callback.answer("Запись успешно отменена!")
            await callback.message.edit_text(
                f"✅ Запись на {appointment.date.strftime('%d.%m.%Y %H:%M')} отменена."
            )
        else:
            await callback.answer("Не удалось отменить запись", show_alert=True)
    except Exception as e:
        await callback.answer(f"Ошибка при отмене записи: {str(e)}", show_alert=True)

def create_client_keyboard():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Записаться")],
            [KeyboardButton(text="📋 Мои записи")]
        ],
        resize_keyboard=True
    )

def create_dates_keyboard(dates):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = []
    for date in dates:
        keyboard.append([
            InlineKeyboardButton(
                text=date.strftime("%d.%m.%Y"),
                callback_data=f"date_{date.strftime('%Y-%m-%d')}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def create_times_keyboard(times):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = []
    for time in times:
        keyboard.append([
            InlineKeyboardButton(
                text=time,
                callback_data=f"time_{time}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def create_confirmation_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")
            ]
        ]
    )

def create_appointments_keyboard(appointments):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = []
    for app in appointments:
        keyboard.append([
            InlineKeyboardButton(
                text=f"❌ Отменить запись {app.id}",
                callback_data=f"cancel_{app.id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_status_emoji(status):
    status_emojis = {
        'scheduled': '✅',
        'completed': '✅',
        'cancelled': '❌'
    }
    return status_emojis.get(status, '❓') 