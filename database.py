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
        await db.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                telegram_user_id INTEGER PRIMARY KEY,
                morgen_api_key TEXT,
                timezone TEXT DEFAULT 'UTC',
                daily_summary_enabled BOOLEAN DEFAULT 0
            )
            '''
        )
        await db.commit()


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
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def upsert_user(
    telegram_user_id: int,
    morgen_api_key: Optional[str] = None,
    timezone: Optional[str] = None,
    daily_summary_enabled: Optional[bool] = None
) -> None:
    """
    Insert a new user or update an existing user's details.

    Args:
        telegram_user_id (int): The unique identifier of the Telegram user.
        morgen_api_key (Optional[str]): The user's Morgen API key. Defaults to None.
        timezone (Optional[str]): The user's timezone (e.g., 'UTC'). Defaults to None.
        daily_summary_enabled (Optional[bool]): Whether the user wants daily summaries. Defaults to None.
    """
    user = await get_user(telegram_user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        if not user:
            # Insert a new user
            await db.execute(
                '''
                INSERT INTO users (telegram_user_id, morgen_api_key, timezone, daily_summary_enabled)
                VALUES (?, ?, ?, ?)
                ''',
                (
                    telegram_user_id,
                    morgen_api_key,
                    timezone or 'UTC',
                    1 if daily_summary_enabled else 0
                )
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
            
            # Remove trailing comma and space
            query = query.rstrip(', ')
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
            return [dict(row) for row in rows]
