import os
import logging
from telegram import Update
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import get_user, upsert_user
from morgen_client import MorgenClient
from i18n import get_text

logger = logging.getLogger(__name__)
morgen_client = MorgenClient()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for the /start command.

    Welcomes the user and asks for their Morgen API key if not already set.
    """
    user_id = update.effective_user.id
    user_record = await get_user(user_id)

    welcome_msg = await get_text("start_welcome", user_id)

    if user_record and user_record.get("morgen_api_key"):
        msg = await get_text("start_dashboard", user_id)
        keyboard = [
            [
                InlineKeyboardButton(
                    await get_text("start_btn_guided", user_id),
                    callback_data="dashboard_guided",
                ),
                InlineKeyboardButton(
                    await get_text("start_btn_quick", user_id),
                    callback_data="dashboard_quick",
                ),
            ],
            [
                InlineKeyboardButton(
                    await get_text("start_btn_agenda", user_id),
                    callback_data="dashboard_agenda",
                ),
                InlineKeyboardButton(
                    await get_text("start_btn_settings", user_id),
                    callback_data="dashboard_settings",
                ),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
        )
    else:
        welcome_msg += await get_text("start_link_prompt", user_id)
        await update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN)


async def quick_event_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Sends instructional text for creating a quick event.
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    msg = await get_text("quick_event_guide", user_id)

    # We send a new message instead of replacing the dashboard so the user can see both
    await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


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
                await upsert_user(
                    user_id, morgen_api_key=text, daily_summary_enabled=True
                )
                await update.message.reply_text(
                    await get_text("api_key_valid", user_id)
                )
            else:
                await update.message.reply_text(
                    await get_text("api_key_valid_no_calendars", user_id)
                )
        except Exception as e:
            logger.error(f"Failed to validate API key for user {user_id}: {e}")
            await update.message.reply_text(await get_text("api_key_invalid", user_id))
    else:
        # Ignore messages if they already have an API key or if it's not a key
        user_record = await get_user(user_id)
        if not user_record or not user_record.get("morgen_api_key"):
            await update.message.reply_text(await get_text("api_key_prompt", user_id))


async def version_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for the /version command.
    Reads the APP_VERSION environment variable and replies with the current version.
    """
    app_version = os.environ.get("APP_VERSION", "dev")
    msg = await get_text("version", update.effective_user.id, version=app_version)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
