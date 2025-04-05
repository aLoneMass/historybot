import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telethon import TelegramClient
from datetime import datetime, timedelta
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
load_dotenv()

import os

API_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("TG_API_ID"))       # Telegram API ID
API_HASH = os.getenv("TG_API_HASH")        # Telegram API Hash
SESSION_NAME = "user_session"              # Для Telethon

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

scheduler = AsyncIOScheduler()

# Хранилище заданий и расписаний
user_schedules = {}

# Userbot клиент
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

class UploadStates(StatesGroup):
    waiting_for_media = State()
    waiting_for_link = State()
    waiting_for_days = State()
    waiting_for_time = State()

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

async def send_notification(user_id: int):
    data = user_schedules.get(user_id)
    if not data:
        return

    await bot.send_message(
        user_id,
        "Через 15 минут будет опубликована история. Отменить публикацию?",
        reply_markup=cancel_keyboard()
    )

    # Планируем публикацию через 15 минут
    asyncio.create_task(publish_story_delayed(user_id, delay=15*60))


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



@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Привет! Отправь фото или короткое видео и ссылку, которую хочешь размещать в историях.")

@dp.message()
async def content_handler(message: types.Message):
    user_id = message.from_user.id

    if not (message.photo or message.video):
        await message.answer("Пожалуйста, отправь фото или короткое видео.")
        return

    # Получаем ссылку (проверка в простом виде)
    if message.caption and "http" in message.caption:
        link = message.caption
    else:
        await message.answer("Пожалуйста, добавь ссылку в подписи к медиа.")
        return

    # Сохраняем контент
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    user_schedules[user_id] = {
        "file_id": file_id,
        "link": link,
        "times": [],
        "job": None
    }

    await message.answer("Как часто публиковать (в днях)? Например: 1, 3, 7")
    # Переход к следующему шагу нужно реализовать через FSM или словарь ожиданий

# Пример публикации
async def publish_story(user_id: int):
    data = user_schedules.get(user_id)
    if not data:
        return

    # Уведомление за 15 минут
    await bot.send_message(user_id, "Через 15 минут будет опубликована история. Отменить публикацию?", reply_markup=cancel_keyboard())

    # Ждем 15 минут
    await asyncio.sleep(15 * 60)

    # Проверка отмены
    if data.get("cancel_next"):
        data["cancel_next"] = False
        return

    # Публикация от имени пользователя
    async with client:
        # Здесь загрузка файла и публикация
        # Пример: await client.send_file('me', file, caption=link)
        print("Опубликовать историю от имени пользователя (реализовать через Telethon)")

def cancel_keyboard():
    buttons = [
        [types.InlineKeyboardButton(text="Отменить ближайшую", callback_data="cancel_next")],
        [types.InlineKeyboardButton(text="Остановить всё", callback_data="cancel_all")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.callback_query()
async def cancel_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == "cancel_next":
        user_schedules[user_id]["cancel_next"] = True
        await callback.message.answer("Ближайшая публикация отменена.")
    elif callback.data == "cancel_all":
        job = user_schedules[user_id].get("job")
        if job:
            job.remove()
        user_schedules.pop(user_id, None)
        await callback.message.answer("Всё расписание отменено.")

async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

async def publish_story_delayed(user_id: int, delay: int):
    await asyncio.sleep(delay)
    data = user_schedules.get(user_id)
    if not data or data.get("cancel_next"):
        data["cancel_next"] = False
        return

    async with client:
        # Здесь вместо 'me' можно указать канал, если потребуется
        await client.send_file(
            'me',
            data["file_id"],
            caption=data["link"]
        )
