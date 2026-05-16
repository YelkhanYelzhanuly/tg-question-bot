import logging
import os

import asyncpg


DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_HOST = os.getenv("DB_HOST", "db")

_pool: asyncpg.Pool | None = None


async def init_db():
    global _pool
    _pool = await asyncpg.create_pool(
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        host=DB_HOST,
        min_size=2,
        max_size=10,
    )
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_messages (
                id SERIAL PRIMARY KEY,           -- Наш автоинкремент (1, 2, 3...)
                message_id BIGINT NOT NULL,      -- ID сообщения из Telegram (5, 7...)
                tg_id BIGINT NOT NULL,           -- ID пользователя
                message_text TEXT NOT NULL,      -- Текст
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    logging.info("База данных успешно инициализирована.")


async def save_message(message_id: int, tg_id: int, text: str):
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_messages (message_id, tg_id, message_text)
            VALUES ($1, $2, $3);
            """,
            message_id,
            tg_id,
            text,
        )