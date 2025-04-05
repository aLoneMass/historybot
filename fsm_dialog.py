from aiogram import F
from datetime import time as dtime

@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await message.answer("Привет! Отправь фото или короткое видео для сторис.")
    await state.set_state(UploadStates.waiting_for_media)

@dp.message(UploadStates.waiting_for_media, F.content_type.in_({'photo', 'video'}))
async def handle_media(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    await state.update_data(file_id=file_id)
    await message.answer("Теперь отправь ссылку, которую нужно прикрепить к истории.")
    await state.set_state(UploadStates.waiting_for_link)

@dp.message(UploadStates.waiting_for_link)
async def handle_link(message: types.Message, state: FSMContext):
    if "http" not in message.text:
        await message.answer("Пожалуйста, отправь корректную ссылку (начинается с http/https).")
        return
    await state.update_data(link=message.text)
    await message.answer("Сколько дней между публикациями? (например: 1, 3, 7)")
    await state.set_state(UploadStates.waiting_for_days)

@dp.message(UploadStates.waiting_for_days)
async def handle_days(message: types.Message, state: FSMContext):
    try:
        interval = int(message.text.strip())
        if interval <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("Введите число больше нуля, например: 2")
        return
    await state.update_data(interval_days=interval)
    await message.answer("Во сколько публиковать? (формат HH:MM, например 14:30)")
    await state.set_state(UploadStates.waiting_for_time)

@dp.message(UploadStates.waiting_for_time)
async def handle_time(message: types.Message, state: FSMContext):
    try:
        h, m = map(int, message.text.strip().split(":"))
        pub_time = dtime(hour=h, minute=m)
    except:
        await message.answer("Формат времени должен быть HH:MM, например 09:00 или 23:45.")
        return

    data = await state.get_data()
    user_id = message.from_user.id

    # Запоминаем всё в user_schedules
    user_schedules[user_id] = {
        "file_id": data["file_id"],
        "link": data["link"],
        "interval_days": data["interval_days"],
        "time": pub_time,
        "cancel_next": False
    }

    # Запускаем задачу в расписании
    start_datetime = datetime.combine(datetime.now().date(), pub_time) + timedelta(minutes=-15)
    scheduler.add_job(
        send_notification,  # функция напоминания
        trigger='interval',
        days=data["interval_days"],
        next_run_time=start_datetime,
        args=[user_id],
        id=str(user_id),
        replace_existing=True
    )

    await message.answer("Публикация запланирована! Я пришлю напоминание за 15 минут до каждого поста.")
    await state.clear()

