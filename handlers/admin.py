from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from datetime import datetime
from models.database import get_db, Client, Appointment, InactiveSlot
from config import ADMIN_IDS
from scheduler.notifier import send_reminder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from services.booking import (
    create_appointment, get_available_slots,
    get_procedures, get_procedure_by_id,
    delete_appointment,
    notify_admins_about_new_appointment,
    set_inactive_slot, remove_inactive_slot,
    get_inactive_slots
)

router = Router()

class AdminStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_phone = State()
    waiting_for_username = State()
    waiting_for_procedure = State()
    waiting_for_inactive_date = State()
    waiting_for_inactive_date_removal = State()
    waiting_for_inactive_time = State()
    waiting_for_inactive_time_removal = State()

def admin_filter(message: Message):
    return message.from_user.id in ADMIN_IDS

@router.message(Command("admin"), admin_filter)
async def cmd_admin(message: Message):
    await message.answer(
        "👨‍⚕️ Панель администратора\n\n"
        "Выберите действие:",
        reply_markup=create_admin_keyboard()
    )

@router.message(F.text == "📊 Список записей", admin_filter)
async def show_appointments(message: Message):
    db = next(get_db())
    today = datetime.now().date()
    appointments = db.query(Appointment).filter(
        Appointment.date >= today,
        Appointment.status == 'scheduled'
    ).order_by(Appointment.date).all()
    
    if not appointments:
        await message.answer("На ближайшие дни записей нет.")
        return
    
    text = "📊 Список записей:\n\n"
    for app in appointments:
        client = app.client
        text += (
            f"ID: {app.id}\n"
            f"Процедура: {app.procedure.name}\n"
            f"Длительность: {app.procedure.duration}ч\n"
            f"📅 {app.date.strftime('%d.%m.%Y %H:%M')}\n"
            f"👤 {client.name} (@{client.username})\n"
            f"📱 {client.phone or 'Телефон не указан'}\n\n"
        )
    
    await message.answer(text, reply_markup=create_appointments_list_keyboard(appointments))

@router.message(F.text == "➕ Добавить запись", admin_filter)
async def add_appointment_start(message: Message, state: FSMContext):
    await message.answer(
        "Введите имя клиента:"
    )
    await state.set_state(AdminStates.waiting_for_name)

@router.message(AdminStates.waiting_for_name, admin_filter)
async def process_client_name(message: Message, state: FSMContext):
    await state.update_data(client_name=message.text)
    
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
    await state.set_state(AdminStates.waiting_for_procedure)

@router.callback_query(AdminStates.waiting_for_procedure, F.data.startswith("proc_"))
async def process_admin_procedure_selection(callback: CallbackQuery, state: FSMContext):
    procedure_id = int(callback.data.split("_")[1])
    procedure = get_procedure_by_id(procedure_id)
    
    await state.update_data(procedure_id=procedure_id)
    
    await callback.message.edit_text(
        "Введите username клиента в Telegram (без @):"
    )
    await state.set_state(AdminStates.waiting_for_username)

@router.message(AdminStates.waiting_for_username, admin_filter)
async def process_client_username(message: Message, state: FSMContext):
    username = message.text.strip()
    db = next(get_db())
    
    # Ищем клиента по username
    client = db.query(Client).filter(Client.username == username).first()
    
    if not client:
        await message.answer(
            f"Клиент с username @{username} не найден в базе данных.\n"
            "Пожалуйста, убедитесь, что клиент уже зарегистрирован через бота."
        )
        await state.clear()
        return
    
    await state.update_data(client_id=client.id)
    
    available_dates = get_available_slots()
    if not available_dates:
        await message.answer(
            "К сожалению, на ближайшие дни все слоты заняты. "
            "Пожалуйста, попробуйте позже."
        )
        await state.clear()
        return

    await message.answer(
        "Выберите дату:",
        reply_markup=create_dates_keyboard(available_dates)
    )
    await state.set_state(AdminStates.waiting_for_date)

@router.callback_query(AdminStates.waiting_for_date, admin_filter)
async def process_admin_date_selection(callback: CallbackQuery, state: FSMContext):
    selected_date = datetime.strptime(callback.data.split("_")[1], "%Y-%m-%d")
    data = await state.get_data()
    procedure_id = data['procedure_id']
    procedure = get_procedure_by_id(procedure_id)
    
    await state.update_data(selected_date=selected_date)
    
    available_times = get_available_slots(selected_date)
    if not available_times:
        await callback.message.edit_text(
            "К сожалению, на этот день все слоты заняты. "
            "Пожалуйста, выберите другую дату."
        )
        return

    await callback.message.edit_text(
        f"Выбрана процедура: {procedure.name}\n"
        f"Длительность: {procedure.duration}ч\n"
        f"Дата: {selected_date.strftime('%d.%m.%Y')}\n\n"
        "Выберите время:",
        reply_markup=create_times_keyboard(available_times)
    )
    await state.set_state(AdminStates.waiting_for_time)

@router.callback_query(AdminStates.waiting_for_time, admin_filter)
async def process_admin_time_selection(callback: CallbackQuery, state: FSMContext):
    selected_time = callback.data.split("_")[1]
    data = await state.get_data()
    selected_date = data['selected_date']
    procedure_id = data['procedure_id']
    procedure = get_procedure_by_id(procedure_id)
    
    # Создаем полную дату и время
    appointment_datetime = datetime.combine(
        selected_date.date(),
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
    await state.set_state(AdminStates.waiting_for_phone)

@router.callback_query(AdminStates.waiting_for_phone, F.data == "confirm", admin_filter)
async def process_admin_confirmation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    appointment_datetime = data['appointment_datetime']
    client_id = data['client_id']
    procedure_id = data['procedure_id']
    
    # Создаем запись в базе данных
    db = next(get_db())
    client = db.query(Client).filter(Client.id == client_id).first()
    
    if not client:
        await callback.answer("Ошибка: клиент не найден", show_alert=True)
        await state.clear()
        return
    
    appointment = create_appointment(db, client.id, procedure_id, appointment_datetime)
    
    await callback.message.edit_text(
        f"✅ Запись успешно создана!\n\n"
        f"👤 Клиент: {client.name} (@{client.username})\n"
        f"Процедура: {appointment.procedure.name}\n"
        f"Длительность: {appointment.procedure.duration}ч\n"
        f"📅 Дата: {appointment_datetime.strftime('%d.%m.%Y')}\n"
        f"🕒 Время: {appointment_datetime.strftime('%H:%M')}"
    )
    
    # Отправляем уведомление администраторам
    await notify_admins_about_new_appointment(callback.bot, appointment)
    
    await state.clear()

@router.message(F.text == "📨 Отправить напоминание", admin_filter)
async def send_reminder_start(message: Message):
    db = next(get_db())
    today = datetime.now().date()
    appointments = db.query(Appointment).filter(
        Appointment.date >= today,
        Appointment.status == 'scheduled'
    ).all()
    
    if not appointments:
        await message.answer("Нет активных записей для отправки напоминания.")
        return
    
    text = "Выберите запись для отправки напоминания:\n\n"
    for app in appointments:
        client = app.client
        text += (
            f"ID: {app.id}\n"
            f"📅 {app.date.strftime('%d.%m.%Y %H:%M')}\n"
            f"👤 {client.name}\n\n"
        )
    
    await message.answer(text, reply_markup=create_appointments_keyboard(appointments))

@router.callback_query(F.data.startswith("remind_"))
async def process_reminder_selection(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав для выполнения этого действия", show_alert=True)
        return

    appointment_id = int(callback.data.split("_")[1])
    db = next(get_db())
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    
    if not appointment:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    
    if not appointment.client.telegram_id:
        await callback.answer(
            "Не удалось отправить напоминание: у клиента не указан Telegram ID", 
            show_alert=True
        )
        return
    
    try:
        await send_reminder(callback.bot, appointment.client.telegram_id, appointment)
        await callback.answer("Напоминание успешно отправлено!")
        await callback.message.edit_text(
            f"✅ Напоминание отправлено клиенту {appointment.client.name}\n"
            f"📅 Дата: {appointment.date.strftime('%d.%m.%Y %H:%M')}"
        )
    except Exception as e:
        await callback.answer(f"Ошибка при отправке напоминания: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("delete_"))
async def process_appointment_deletion(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав для выполнения этого действия", show_alert=True)
        return

    appointment_id = int(callback.data.split("_")[1])
    db = next(get_db())
    
    try:
        if delete_appointment(db, appointment_id):
            await callback.answer("Запись успешно удалена!")
            # Обновляем сообщение с обновленным списком записей
            today = datetime.now().date()
            appointments = db.query(Appointment).filter(
                Appointment.date >= today,
                Appointment.status == 'scheduled'
            ).order_by(Appointment.date).all()
            
            if not appointments:
                await callback.message.edit_text("На ближайшие дни записей нет.")
            else:
                text = "📊 Список записей:\n\n"
                for app in appointments:
                    client = app.client
                    text += (
                        f"ID: {app.id}\n"
                        f"Процедура: {app.procedure.name}\n"
                        f"Длительность: {app.procedure.duration}ч\n"
                        f"📅 {app.date.strftime('%d.%m.%Y %H:%M')}\n"
                        f"👤 {client.name} (@{client.username})\n"
                        f"📱 {client.phone or 'Телефон не указан'}\n\n"
                    )
                await callback.message.edit_text(text, reply_markup=create_appointments_list_keyboard(appointments))
        else:
            await callback.answer("Запись не найдена", show_alert=True)
    except Exception as e:
        await callback.answer(f"Ошибка при удалении записи: {str(e)}", show_alert=True)

@router.message(F.text == "📅 Управление датами", admin_filter)
async def manage_dates(message: Message):
    db = next(get_db())
    today = datetime.now().date()
    
    # Получаем неактивные слоты на ближайшие 14 дней
    inactive_slots = db.query(InactiveSlot).filter(
        InactiveSlot.date >= today
    ).order_by(InactiveSlot.date, InactiveSlot.time).all()
    
    if not inactive_slots:
        await message.answer(
            "Сейчас нет неактивных слотов.\n"
            "Выберите действие:",
            reply_markup=create_dates_management_keyboard()
        )
        return
    
    # Группируем слоты по датам
    slots_by_date = {}
    for slot in inactive_slots:
        date_str = slot.date.strftime("%d.%m.%Y")
        if date_str not in slots_by_date:
            slots_by_date[date_str] = []
        slots_by_date[date_str].append(slot.time)
    
    # Формируем текст сообщения
    text = "📅 Неактивные слоты:\n\n"
    for date_str, times in slots_by_date.items():
        text += f"📅 {date_str}:\n"
        for time in sorted(times):
            text += f"• {time}\n"
        text += "\n"
    
    await message.answer(
        text + "Выберите действие:",
        reply_markup=create_dates_management_keyboard()
    )

@router.callback_query(F.data == "add_inactive_slot", admin_filter)
async def add_inactive_slot_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите дату в формате ДД.ММ.ГГГГ:"
    )
    await state.set_state(AdminStates.waiting_for_inactive_date)

@router.callback_query(F.data == "remove_inactive_slot", admin_filter)
async def remove_inactive_slot_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите дату в формате ДД.ММ.ГГГГ:"
    )
    await state.set_state(AdminStates.waiting_for_inactive_date_removal)

@router.message(AdminStates.waiting_for_inactive_date, admin_filter)
async def process_inactive_date(message: Message, state: FSMContext):
    try:
        date = datetime.strptime(message.text, "%d.%m.%Y").date()
        await state.update_data(inactive_date=date)
        
        # Показываем доступные временные слоты
        available_slots = get_available_slots(date)
        if not available_slots:
            await message.answer(
                f"На дату {date.strftime('%d.%m.%Y')} нет доступных слотов."
            )
            await state.clear()
            return
        
        keyboard = []
        for slot in available_slots:
            keyboard.append([
                InlineKeyboardButton(
                    text=slot,
                    callback_data=f"inactive_time_{slot}"
                )
            ])
        
        await message.answer(
            f"Выберите время для добавления в неактивные слоты на {date.strftime('%d.%m.%Y')}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await state.set_state(AdminStates.waiting_for_inactive_time)
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты. Используйте формат ДД.ММ.ГГГГ"
        )

@router.callback_query(AdminStates.waiting_for_inactive_time, F.data.startswith("inactive_time_"))
async def process_inactive_time(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    date = data['inactive_date']
    time = callback.data.split("_")[2]
    db = next(get_db())
    
    print(f"Попытка добавить неактивный слот: дата={date}, время={time}")
    
    if set_inactive_slot(db, date, time):
        # Проверяем, что слот действительно добавлен
        inactive_slots = get_inactive_slots(db, date)
        print(f"Неактивные слоты после добавления: {[slot.time for slot in inactive_slots]}")
        
        await callback.answer(f"✅ Слот {time} на {date.strftime('%d.%m.%Y')} добавлен в неактивные.")
    else:
        await callback.answer(f"❌ Ошибка при добавлении слота {time} на {date.strftime('%d.%m.%Y')}.")
    
    await state.clear()
    await manage_dates(callback.message)

@router.message(AdminStates.waiting_for_inactive_date_removal, admin_filter)
async def process_inactive_date_removal(message: Message, state: FSMContext):
    try:
        date = datetime.strptime(message.text, "%d.%m.%Y").date()
        db = next(get_db())
        inactive_slots = get_inactive_slots(db, date)
        
        if not inactive_slots:
            await message.answer(
                f"На дату {date.strftime('%d.%m.%Y')} нет неактивных слотов."
            )
            await state.clear()
            return
        
        keyboard = []
        for slot in inactive_slots:
            if not slot.is_weekend:  # Показываем только не выходные слоты
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"{slot.time}",
                        callback_data=f"remove_inactive_{date.strftime('%Y-%m-%d')}_{slot.time}"
                    )
                ])
        
        if not keyboard:
            await message.answer(
                f"На дату {date.strftime('%d.%m.%Y')} нет неактивных слотов (кроме выходных)."
            )
            await state.clear()
            return
        
        await message.answer(
            f"Выберите время для удаления из неактивных слотов на {date.strftime('%d.%m.%Y')}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await state.set_state(AdminStates.waiting_for_inactive_time_removal)
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты. Используйте формат ДД.ММ.ГГГГ"
        )

@router.callback_query(AdminStates.waiting_for_inactive_time_removal, F.data.startswith("remove_inactive_"))
async def process_inactive_time_removal(callback: CallbackQuery, state: FSMContext):
    _, date_str, time = callback.data.split("_")
    date = datetime.strptime(date_str, "%Y-%m-%d").date()
    db = next(get_db())
    
    if remove_inactive_slot(db, date, time):
        await callback.answer(f"✅ Слот {time} на {date.strftime('%d.%m.%Y')} удален из неактивных.")
    else:
        await callback.answer(f"❌ Ошибка при удалении слота {time} на {date.strftime('%d.%m.%Y')}.")
    
    await state.clear()
    await manage_dates(callback.message)

def create_admin_keyboard():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Список записей")],
            [KeyboardButton(text="➕ Добавить запись")],
            [KeyboardButton(text="📨 Отправить напоминание")],
            [KeyboardButton(text="📅 Управление датами")]
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
                text=f"📨 Отправить напоминание для записи {app.id}",
                callback_data=f"remind_{app.id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def create_appointments_list_keyboard(appointments):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = []
    for app in appointments:
        keyboard.append([
            InlineKeyboardButton(
                text=f"❌ Удалить запись {app.id}",
                callback_data=f"delete_{app.id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def create_dates_management_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить неактивный слот", callback_data="add_inactive_slot"),
                InlineKeyboardButton(text="➖ Удалить неактивный слот", callback_data="remove_inactive_slot")
            ]
        ]
    ) 