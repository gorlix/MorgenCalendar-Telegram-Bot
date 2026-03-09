import os
import httpx
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from database import get_user, upsert_user
from morgen_client import MorgenClient
from i18n import get_text
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)
morgen_client = MorgenClient()

# States
WAITING_FOR_KEY = 1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handler for the /start command.
    """
    user_id = update.effective_user.id
    user_record = await get_user(user_id)

    if user_record and user_record.get("morgen_api_key"):
        await send_authenticated_dashboard(update, context)
        return ConversationHandler.END
    else:
        welcome_msg = await get_text("start_welcome", user_id)
        welcome_msg += await get_text("start_link_prompt", user_id)
        await update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN)
        return WAITING_FOR_KEY


async def send_authenticated_dashboard(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Renders the main dashboard for authenticated users.
    """
    user_id = update.effective_user.id
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

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
        )


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


async def handle_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Processes the API key and auto-starts the authenticated experience.
    """
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # Cleanup in case the user pastes the full header or has extra whitespace
    api_key = text.replace("ApiKey ", "").strip()

    # Validate by attempting to fetch calendars
    try:
        calendars = await morgen_client.list_calendars(api_key)
        if calendars:
            await upsert_user(user_id, morgen_api_key=api_key, agenda_enabled=True)
            await update.message.reply_text(await get_text("api_key_valid", user_id))

            # Programmatically trigger the welcome dashboard
            await send_authenticated_dashboard(update, context)
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                await get_text("api_key_valid_no_calendars", user_id)
            )
            return WAITING_FOR_KEY
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            await update.message.reply_text(
                await get_text("api_key_rate_limit", user_id)
            )
        else:
            logger.error(
                f"Morgen API Error (Status {e.response.status_code}): {e.response.text}"
            )
            await update.message.reply_text(await get_text("api_key_invalid", user_id))
        return WAITING_FOR_KEY
    except Exception as e:
        logger.error(
            f"Failed to validate API key for user {user_id}: {type(e).__name__}: {e}"
        )
        await update.message.reply_text(await get_text("api_key_invalid", user_id))
        return WAITING_FOR_KEY


async def cancel_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the onboarding process."""
    await update.message.reply_text(
        await get_text("settings_cancelled", update.effective_user.id)
    )
    return ConversationHandler.END


onboarding_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        WAITING_FOR_KEY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_api_key)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_onboarding)],
)


async def version_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for the /version command.
    Reads the APP_VERSION environment variable and replies with the current version.
    """
    app_version = os.environ.get("APP_VERSION", "dev")
    msg = await get_text("version", update.effective_user.id, version=app_version)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
