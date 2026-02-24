import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import get_user
from morgen_client import MorgenClient, RateLimitError
from formatters import format_agenda_message
from i18n import get_text

logger = logging.getLogger(__name__)
morgen_client = MorgenClient()

async def agenda_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Displays the /agenda initial inline keyboard.
    """
    user_id = update.effective_user.id
    user_record = await get_user(user_id)
    if not user_record or not user_record.get("morgen_api_key"):
        msg = await get_text("agenda_please_link", user_id)
        await update.message.reply_text(msg)
        return

    keyboard = [
        [InlineKeyboardButton(await get_text("agenda_btn_today", user_id), callback_data="agenda_today"),
         InlineKeyboardButton(await get_text("agenda_btn_tomorrow", user_id), callback_data="agenda_tomorrow")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await get_text("agenda_prompt", user_id)
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


async def agenda_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the callback query from the /agenda keyboard.
    """
    query = update.callback_query
    await query.answer()

    action = query.data.split("_")[1]
    now = datetime.now(dt_timezone.utc)
    user_id = update.effective_user.id
    
    if action == "today":
        day = now
        day_label_key = "agenda_btn_today"
    else:
        day = now + timedelta(days=1)
        day_label_key = "agenda_btn_tomorrow"
        
    day_label = await get_text(day_label_key, user_id)

    # Define the 24-hour window for the selected day in UTC (rough estimation for generic usage)
    start_date = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=1)
    
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    user_record = await get_user(user_id)
    api_key = user_record["morgen_api_key"]

    msg = await get_text("agenda_fetching", user_id, day=day_label)
    await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)

    try:
        events = await morgen_client.get_all_events(
            api_key=api_key,
            start_datetime=start_str,
            end_datetime=end_str
        )

        msg = format_agenda_message(events, day_label, user_id=user_id, lang=user_record.get('language', 'en'))
        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
        
    except RateLimitError as e:
        import re
        match = re.search(r'wait (\d+) seconds', str(e))
        if match:
            seconds = int(match.group(1))
            minutes = seconds // 60
            secs = seconds % 60
            if minutes > 0:
                time_str = f"{minutes} minutes and {secs} seconds"
            else:
                time_str = f"{secs} seconds"
        else:
            time_str = "15 minutes"
            
        rate_limit_msg = await get_text("agenda_rate_limit", user_id, time_str=time_str)
        await query.edit_message_text(rate_limit_msg)
        
    except Exception as e:
        logger.error(f"Error fetching agenda: {e}")
        error_msg = await get_text("agenda_error", user_id)
        await query.edit_message_text(error_msg)
