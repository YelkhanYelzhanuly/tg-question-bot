import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher, F
from aiogram import BaseMiddleware
from aiogram.types import Message
from cachetools import TTLCache

from database import init_db, save_message


BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("Критическая ошибка: BOT_TOKEN не обнаружен!")
    sys.exit(1)

MIN_TEXT_LENGTH = 20
THROTTLING_RATE_SEC = 5.0
DB_STARTUP_RETRIES = 10
DB_STARTUP_DELAY = 2.0

MESSAGES = {
    "start": (
        "Привет! Отправь текстовый вопрос (можно с эмодзи).\n"
        "⚠️ Длина должна быть более 20 символов. Ссылки, гифки и стикеры запрещены!"
    ),
    "err_not_text": "❌ Ошибка: Можно отправлять только текст.",
    "err_too_short": "❌ Ошибка: Слишком коротко ({length}/{min}+ симв.).",
    "err_links": "❌ Ошибка: Ссылки запрещены.",
    "err_flood": "⏱️ Не спеши! Можно отправлять вопросы только раз в {rate} секунд.",
    "success": "✅ Сообщение сохранено в БД!",
    "db_error": "⚠️ Ошибка при записи в базу данных.",
}

user_cooldowns: TTLCache = TTLCache(maxsize=10_000, ttl=THROTTLING_RATE_SEC)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        user_id = event.from_user.id if event.from_user else "unknown"
        text_preview = (event.text or "")[:50]
        logging.info(f"[user={user_id}] Входящее сообщение: {text_preview!r}")
        return await handler(event, data)


class AntiFloodMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        if not event.from_user:
            return await handler(event, data)

        if event.text and event.text.startswith("/start"):
            return await handler(event, data)

        user_id = event.from_user.id

        if user_id in user_cooldowns:
            await event.answer(
                MESSAGES["err_flood"].format(rate=int(THROTTLING_RATE_SEC))
            )
            return

        user_cooldowns[user_id] = True
        return await handler(event, data)


dp.message.middleware(LoggingMiddleware())
dp.message.middleware(AntiFloodMiddleware())


def validate_message(message: Message) -> str | None:
    if not message.text:
        return MESSAGES["err_not_text"]

    if len(message.text) <= MIN_TEXT_LENGTH:
        return MESSAGES["err_too_short"].format(
            length=len(message.text),
            min=MIN_TEXT_LENGTH + 1,
        )

    if message.entities and any(
        e.type in ("url", "text_link") for e in message.entities
    ):
        return MESSAGES["err_links"]

    return None


@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer(MESSAGES["start"])


@dp.message()
async def handle_message(message: Message):
    error = validate_message(message)
    if error:
        await message.answer(error)
        return

    tg_id = message.from_user.id if message.from_user else message.chat.id

    try:
        await save_message(
            message_id=message.message_id,
            tg_id=tg_id,
            text=message.text,
        )
        await message.answer(MESSAGES["success"])
    except Exception as e:
        logging.error(f"Ошибка сохранения: {e}")
        await message.answer(MESSAGES["db_error"])


async def wait_for_db():
    for attempt in range(1, DB_STARTUP_RETRIES + 1):
        try:
            await init_db()
            logging.info("✅ База данных подключена.")
            return
        except Exception as e:
            logging.warning(
                f"Попытка {attempt}/{DB_STARTUP_RETRIES}: БД недоступна — {e}"
            )
            await asyncio.sleep(DB_STARTUP_DELAY)

    logging.critical("❌ Не удалось подключиться к БД. Завершение работы.")
    sys.exit(1)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    await wait_for_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
