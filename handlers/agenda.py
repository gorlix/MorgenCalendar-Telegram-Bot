import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import get_user
from morgen_client import MorgenClient
from formatters import format_agenda_message

logger = logging.getLogger(__name__)
morgen_client = MorgenClient()

async def agenda_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Displays the /agenda initial inline keyboard.
    """
    user_record = await get_user(update.effective_user.id)
    if not user_record or not user_record.get("morgen_api_key"):
        await update.message.reply_text("Please set your Morgen API Key using /start first.")
        return

    keyboard = [
        [InlineKeyboardButton("Today", callback_data="agenda_today"),
         InlineKeyboardButton("Tomorrow", callback_data="agenda_tomorrow")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📅 **Agenda**\n\nSelect a day to view:", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


async def agenda_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the callback query from the /agenda keyboard.
    """
    query = update.callback_query
    await query.answer()

    action = query.data.split("_")[1]
    now = datetime.now(dt_timezone.utc)
    
    if action == "today":
        day = now
        day_label = "Today"
    else:
        day = now + timedelta(days=1)
        day_label = "Tomorrow"

    # Define the 24-hour window for the selected day in UTC (rough estimation for generic usage)
    start_date = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=1)
    
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    user_id = update.effective_user.id
    user_record = await get_user(user_id)
    api_key = user_record["morgen_api_key"]

    await query.edit_message_text(f"⏳ Fetching agenda for **{day_label}**...", parse_mode=ParseMode.MARKDOWN)

    try:
        events = await morgen_client.get_all_events(
            api_key=api_key,
            start_datetime=start_str,
            end_datetime=end_str
        )

        msg = format_agenda_message(events, day_label)
        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    
    except Exception as e:
        logger.error(f"Error fetching agenda: {e}")
        await query.edit_message_text("❌ Failed to fetch agenda.")
