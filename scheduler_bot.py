import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telethon import TelegramClient
from datetime import datetime, timedelta

import os

API_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("TG_API_ID"))       # Telegram API ID
API_HASH = os.getenv("TG_API_HASH")        # Telegram API Hash
SESSION_NAME = "user_session"              # Для Telethon

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Хранилище заданий и расписаний
user_schedules = {}

# Userbot клиент
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

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
