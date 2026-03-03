import asyncio
import os
from typing import Optional, List, Dict, Any

import aiosqlite

DB_PATH: str = os.getenv("DB_PATH", "morgen_bot.db")


async def init_db() -> None:
    """
    Initialize the SQLite database.

    Creates the `users` table if it does not already exist. The table stores
    the user's Telegram ID, Morgen API key, timezone, and preference for the
    daily summary.
    """
    # Ensure the directory exists if the path contains directories
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_user_id INTEGER PRIMARY KEY,
                morgen_api_key TEXT,
                timezone TEXT DEFAULT 'UTC',
                daily_summary_enabled BOOLEAN DEFAULT 0,
                language TEXT DEFAULT 'en',
                agenda_enabled BOOLEAN DEFAULT 1,
                agenda_time TEXT DEFAULT '07:00'
            )
            """)
        await db.commit()

        # Add 'language' column to existing DB if missing
        try:
            await db.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
            await db.commit()
        except aiosqlite.OperationalError:
            pass  # Column already exists

        # Add Daily Settings columns if missing
        try:
            await db.execute(
                "ALTER TABLE users ADD COLUMN agenda_enabled BOOLEAN DEFAULT 1"
            )
            await db.execute(
                "ALTER TABLE users ADD COLUMN agenda_time TEXT DEFAULT '07:00'"
            )
            await db.commit()

            # Migrate the old state
            await db.execute("UPDATE users SET agenda_enabled = daily_summary_enabled")
            await db.commit()
        except aiosqlite.OperationalError:
            pass  # Columns already exist


async def get_user(telegram_user_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a user from the database by their Telegram ID.

    Args:
        telegram_user_id (int): The unique identifier of the Telegram user.

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing the user's data if
        found, else None. The dictionary keys match the column names.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?", (telegram_user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def upsert_user(
    telegram_user_id: int,
    morgen_api_key: Optional[str] = None,
    timezone: Optional[str] = None,
    daily_summary_enabled: Optional[bool] = None,
    language: Optional[str] = None,
    agenda_enabled: Optional[bool] = None,
    agenda_time: Optional[str] = None,
) -> None:
    """
    Insert a new user or update an existing user's details.

    Args:
        telegram_user_id (int): The unique identifier of the Telegram user.
        morgen_api_key (Optional[str]): The user's Morgen API key. Defaults to None.
        timezone (Optional[str]): The user's timezone (e.g., 'UTC'). Defaults to None.
        daily_summary_enabled (Optional[bool]): Legacy field. Use agenda_enabled now.
        language (Optional[str]): The user's preferred language. Defaults to None.
        agenda_enabled (Optional[bool]): Whether daily agendas are toggled on.
        agenda_time (Optional[str]): The HH:MM time string for the summary.
    """
    user = await get_user(telegram_user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        if not user:
            # Insert a new user
            await db.execute(
                """
                INSERT INTO users (telegram_user_id, morgen_api_key, timezone, daily_summary_enabled, language, agenda_enabled, agenda_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    morgen_api_key,
                    timezone or "UTC",
                    1 if daily_summary_enabled else 0,
                    language or "en",
                    1 if (agenda_enabled is not False) else 0,
                    agenda_time or "07:00",
                ),
            )
        else:
            # Update existing user, only overriding provided fields
            query = "UPDATE users SET "
            params: List[Any] = []

            if morgen_api_key is not None:
                query += "morgen_api_key = ?, "
                params.append(morgen_api_key)
            if timezone is not None:
                query += "timezone = ?, "
                params.append(timezone)
            if daily_summary_enabled is not None:
                query += "daily_summary_enabled = ?, "
                params.append(1 if daily_summary_enabled else 0)
            if language is not None:
                query += "language = ?, "
                params.append(language)
            if agenda_enabled is not None:
                query += "agenda_enabled = ?, "
                params.append(1 if agenda_enabled else 0)
            if agenda_time is not None:
                query += "agenda_time = ?, "
                params.append(agenda_time)

            # Remove trailing comma and space
            query = query.rstrip(", ")
            query += " WHERE telegram_user_id = ?"
            params.append(telegram_user_id)

            await db.execute(query, tuple(params))

        await db.commit()


async def get_users_for_daily_summary() -> List[Dict[str, Any]]:
    """
    Retrieve all users who have opted in for the daily summary.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each representing a user
        who has `daily_summary_enabled` set to true (1).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE daily_summary_enabled = 1 AND morgen_api_key IS NOT NULL"
        ) as cursor:
            rows = await cursor.fetchall()


async def get_users_with_agenda() -> List[Dict[str, Any]]:
    """
    Retrieve all users who have `agenda_enabled` = 1
    Used for initializing per-user scheduler jobs.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE agenda_enabled = 1 AND morgen_api_key IS NOT NULL"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
