import asyncio
import os
from datetime import datetime, timedelta, time as dtime

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, time, timedelta, timezone
from telethon import TelegramClient



local_offset = timedelta(hours=3)
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
load_dotenv()

# === Настройки и инициализация ===
API_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION_NAME = "user_session"

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
scheduler = AsyncIOScheduler(timezone=timezone.utc)
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

user_schedules = {}

# === Состояния FSM ===
class UploadStates(StatesGroup):
    waiting_for_media = State()
    waiting_for_link = State()
    waiting_for_days = State()
    waiting_for_time = State()

# === Функция публикации истории с задержкой ===
async def publish_story_delayed(user_id: int, delay: int):
    await asyncio.sleep(delay)
    data = user_schedules.get(user_id)
    print(f"[DEBUG] func publish_story_delayed Напоминание для user_id: {user_id}")
    if not data or data.get("cancel_next"):
        data["cancel_next"] = False
        return

    file_id = data["file_id"]
    link = data["link"]

    # Вместо NamedTemporaryFile (использует ssl), сохраняем вручную
    file = await bot.get_file(file_id)
    file_path = file.file_path
    downloaded_file = await bot.download_file(file_path)

    temp_file_path = f"temp_{user_id}.bin"
    with open(temp_file_path, "wb") as f:
        f.write(downloaded_file.read())

    async with client:
        await client.send_file(
            'me',
            temp_file_path,
            caption=link
        )

    os.remove(temp_file_path)

# === Функция отправки напоминания ===
async def send_notification(user_id: int):
    data = user_schedules.get(user_id)
    print(f"[NOTIFY] функция send_notification вызвана. Время: {datetime.now()}")
    print(f"[NOTIFY] Напоминание для user_id={user_id} в {datetime.now(timezone.utc)}")
    if not data:
        return

    await bot.send_message(
        user_id,
        f"! Сейчас {now}. Через 2 минуты будет опубликована история. Отменить публикацию?",
        reply_markup=cancel_keyboard()
    )
    asyncio.create_task(publish_story_delayed(user_id, delay=2 * 60))

# === Кнопки отмены ===
def cancel_keyboard():
    buttons = [
        [types.InlineKeyboardButton(text="❌ Отменить ближайшую", callback_data="cancel_next")],
        [types.InlineKeyboardButton(text="⏹ Остановить всё", callback_data="cancel_all")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

# === FSM: диалог настройки публикации ===
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
        await message.answer("Пожалуйста, отправь корректную ссылку (http/https).")
        return
    await state.update_data(link=message.text)
    await message.answer("Сколько дней между публикациями? (1, 2, 7)")
    await state.set_state(UploadStates.waiting_for_days)

@dp.message(UploadStates.waiting_for_days)
async def handle_days(message: types.Message, state: FSMContext):
    try:
        interval = int(message.text.strip())
        if interval <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("Введите целое число больше 0, например: 2")
        return
    await state.update_data(interval_days=interval)
    await message.answer("Во сколько публиковать? (HH:MM)")
    await state.set_state(UploadStates.waiting_for_time)

@dp.message(UploadStates.waiting_for_time, F.text)
async def handle_time(message: types.Message, state: FSMContext):
    print(f"[HANDLE_TIME] Получено сообщение: {message.text!r}")
    if not message.text or ":" not in message.text:
        await message.answer("Неверный формат. Пиши HH:MM, например 13:30")
        return

    try:
        h, m = map(int, message.text.strip().split(":"))
        pub_time = dtime(hour=h, minute=m)
    except Exception as e:
        await message.answer(f"Неверный формат ({e}). Пиши HH:MM, например 14:30")
        return

    data = await state.get_data()
    user_id = message.from_user.id

    user_schedules[user_id] = {
        "file_id": data["file_id"],
        "link": data["link"],
        "interval_days": data["interval_days"],
        "time": pub_time,
        "cancel_next": False
    }

    now = datetime.now(timezone.utc)
    start_datetime = datetime.combine(datetime.now().date(), pub_time) - timedelta(minutes=2)
    start_datetime = start_datetime - local_offset
    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
    
    if start_datetime < now:
        start_datetime += timedelta(days=1)
        print(f"[SCHEDULE] Задача будет запущена в {start_datetime}")
    print(f"[SCHEDULE] Задача будет запущена в {start_datetime}")
    print(f"[SCHEDULE] Публикация для user_id={user_id} в {pub_time}, запуск уведомления в {start_datetime}")
    scheduler.add_job(
        # send_notification,
        # trigger='interval',
        # days=data["interval_days"],
        # next_run_time=start_datetime,
        # args=[user_id],
        # id=str(user_id),
        # replace_existing=True
        func=send_notification,
        trigger=DateTrigger(run_date=start_datetime),
        args=[user_id],
        id=f"notify_{user_id}_{start_datetime}",
        replace_existing=True
    )

    print("[DEBUG] Текущие задачи:")
    for job in scheduler.get_jobs():
        print(job)

    await message.answer("📅 Публикация запланирована! Буду напоминать за 2 минуты до каждой.")
    await state.clear()

# === Кнопки отмены ===
@dp.callback_query()
async def cancel_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "cancel_next":
        user_schedules[user_id]["cancel_next"] = True
        await callback.message.answer("❌ Ближайшая публикация отменена.")
    elif callback.data == "cancel_all":
        job = scheduler.get_job(str(user_id))
        if job:
            job.remove()
        user_schedules.pop(user_id, None)
        await callback.message.answer("⏹ Все задачи отменены.")

# === Точка входа ===
async def on_startup(dispatcher: Dispatcher, bot: Bot):
    print("[INIT] Запускаю планировщик...")
    scheduler.start()

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)
    # print(f"[MAIN] Старт бота. Сейчас: {now}.")
    # print("[DEBUG] Запланированные задачи:")
    # print(scheduler.get_jobs())
    # print("[SCHEDULER] Планировщик запущен")

if __name__ == "__main__":
    asyncio.run(main())
