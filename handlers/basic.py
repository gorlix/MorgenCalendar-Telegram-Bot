import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import get_user, upsert_user
from morgen_client import MorgenClient

logger = logging.getLogger(__name__)
morgen_client = MorgenClient()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for the /start command.

    Welcomes the user and asks for their Morgen API key if not already set.
    """
    user_id = update.effective_user.id
    user_record = await get_user(user_id)

    welcome_msg = (
        "👋 Welcome to the **Morgen Calendar Bot**!\n\n"
        "I can help you manage your calendar events directly from Telegram.\n\n"
    )

    if user_record and user_record.get("morgen_api_key"):
        welcome_msg += "✅ Your Morgen API Key is already linked.\nYou can use /add, /new, or /agenda."
    else:
        welcome_msg += (
            "⚠️ To get started, I need your Morgen API Key.\n\n"
            "1. Go to https://platform.morgen.so/developers-api\n"
            "2. Copy your API Key\n"
            "3. **Reply to this message with your API Key** to securely link your account."
        )

    await update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN)


async def handle_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for receiving the Morgen API key as a text message.

    This function intercepts plain text messages and, if it looks long enough to
    be an API key, saves it in the DB.
    """
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # Extremely basic heuristic: if it's longer than 20 chars and looks like a key
    if len(text) > 20 and " " not in text:
        # Validate by attempting to fetch calendars
        try:
            calendars = await morgen_client.list_calendars(text)
            if calendars:
                await upsert_user(user_id, morgen_api_key=text, daily_summary_enabled=True)
                await update.message.reply_text(
                    "✅ Your Morgen API Key has been successfully linked and validated!\n\n"
                    "I have also enabled **Daily Summaries** for you. You will receive an agenda every day at 07:00 AM server time.\n\n"
                    "Try using /agenda to see your schedule today."
                )
            else:
                await update.message.reply_text("Your API key seems valid, but no writable calendars were found.")
        except Exception as e:
            logger.error(f"Failed to validate API key for user {user_id}: {e}")
            await update.message.reply_text(
                "❌ I could not validate your Morgen API key. Please ensure it is correct and try again."
            )
    else:
        # Ignore messages if they already have an API key or if it's not a key
        user_record = await get_user(user_id)
        if not user_record or not user_record.get("morgen_api_key"):
            await update.message.reply_text("Are you trying to set an API key? Please paste it directly here.")


async def version_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for the /version command.
    Reads the APP_VERSION environment variable and replies with the current version.
    """
    app_version = os.environ.get("APP_VERSION", "dev")
    await update.message.reply_text(
        f"🤖 **Morgen Calendar Bot**\n\n🏷 **Version:** `{app_version}`",
        parse_mode=ParseMode.MARKDOWN
    )
