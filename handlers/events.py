import re
import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters,
)
from telegram.constants import ParseMode

from database import get_user
from morgen_client import MorgenClient

logger = logging.getLogger(__name__)
morgen_client = MorgenClient()

# Conversation states for /new command
WAITING_TITLE = 1
WAITING_DATE = 2
WAITING_TIME = 3
WAITING_DURATION = 4
WAITING_CUSTOM_DATE = 5
WAITING_CUSTOM_TIME = 6

async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for the /add command (Structured text creation).

    Expected format: /add <YYYY-MM-DD> <HH:MM> <Duration_in_minutes> <Title>
    """
    user_id = update.effective_user.id
    user_record = await get_user(user_id)

    if not user_record or not user_record.get("morgen_api_key"):
        await update.message.reply_text("Please set your Morgen API Key using /start first.")
        return

    api_key = user_record["morgen_api_key"]
    args = context.args

    if len(args) < 4:
        await update.message.reply_text(
            "❌ Invalid format.\n\n"
            "Usage: `/add <YYYY-MM-DD> <HH:MM> <Duration_in_minutes> <Title>`\n"
            "Example: `/add 2026-03-01 10:00 30 Team Meeting`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    date_str, time_str, duration_str = args[0], args[1], args[2]
    title = " ".join(args[3:])

    # Basic validations
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        await update.message.reply_text("❌ Invalid date. Use YYYY-MM-DD.")
        return
    if not re.match(r"^\d{2}:\d{2}$", time_str):
        await update.message.reply_text("❌ Invalid time. Use HH:MM.")
        return
    if not duration_str.isdigit():
        await update.message.reply_text("❌ Duration must be a number of minutes.")
        return

    # Construct datetime string
    start_datetime_iso = f"{date_str}T{time_str}:00"
    duration_iso = f"PT{duration_str}M"

    await _process_event_creation(update.message, api_key, title, start_datetime_iso, duration_iso)


async def _process_event_creation(
    message, api_key: str, title: str, start_datetime_iso: str, duration_iso: str
) -> None:
    """
    Helper function to process the event creation logic via Morgen API.
    """
    primary_cal = await morgen_client.get_primary_calendar(api_key)
    if not primary_cal:
        await message.reply_text("❌ Could not find a primary writable calendar on your Morgen account.")
        return

    account_id = primary_cal["accountId"]
    calendar_id = primary_cal["id"]

    try:
        await morgen_client.create_event(
            api_key=api_key,
            account_id=account_id,
            calendar_id=calendar_id,
            title=title,
            start_datetime_iso=start_datetime_iso,
            duration_iso=duration_iso
        )
        await message.reply_text(f"✅ Successfully created event: **{title}**", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        await message.reply_text("❌ Failed to create event. Please check the logs.")


# --- Conversation Handler stuff for /new ---

async def new_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_record = await get_user(user_id)

    if not user_record or not user_record.get("morgen_api_key"):
        await update.message.reply_text("Please set your Morgen API Key using /start first.")
        return ConversationHandler.END

    await update.message.reply_text("Let's create a new event. What is the **Title**? (Type it below)", parse_mode=ParseMode.MARKDOWN)
    return WAITING_TITLE


async def new_event_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['title'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Today", callback_data="date_today"),
         InlineKeyboardButton("Tomorrow", callback_data="date_tomorrow")],
        [InlineKeyboardButton("Custom Date", callback_data="date_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Great. Which **Date**?", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return WAITING_DATE


async def new_event_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "date_today":
        context.user_data['date'] = datetime.now().strftime("%Y-%m-%d")
    elif query.data == "date_tomorrow":
        context.user_data['date'] = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    elif query.data == "date_custom":
        await query.edit_message_text("Please reply with the date in `YYYY-MM-DD` format:", parse_mode=ParseMode.MARKDOWN)
        return WAITING_CUSTOM_DATE

    return await ask_time(query, context)


async def new_event_custom_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        await update.message.reply_text("Invalid format. Please use `YYYY-MM-DD`:", parse_mode=ParseMode.MARKDOWN)
        return WAITING_CUSTOM_DATE
    context.user_data['date'] = text
    # we need to simulate a query behavior or just send a message
    return await ask_time(update, context, is_message=True)


async def ask_time(update_obj, context: ContextTypes.DEFAULT_TYPE, is_message: bool = False) -> int:
    keyboard = [
        [InlineKeyboardButton("Morning (09:00)", callback_data="time_09:00"),
         InlineKeyboardButton("Afternoon (14:00)", callback_data="time_14:00")],
        [InlineKeyboardButton("Evening (18:00)", callback_data="time_18:00"),
         InlineKeyboardButton("Custom Time", callback_data="time_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"Date set to {context.user_data['date']}. What **Time**?"
    
    if is_message:
        await update_obj.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update_obj.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    return WAITING_TIME


async def new_event_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data.startswith("time_") and query.data != "time_custom":
        context.user_data['time'] = query.data.split("_")[1]
    elif query.data == "time_custom":
        await query.edit_message_text("Please reply with the time in `HH:MM` format (24h):", parse_mode=ParseMode.MARKDOWN)
        return WAITING_CUSTOM_TIME

    return await ask_duration(query, context)


async def new_event_custom_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not re.match(r"^\d{2}:\d{2}$", text):
        await update.message.reply_text("Invalid format. Please use `HH:MM`:", parse_mode=ParseMode.MARKDOWN)
        return WAITING_CUSTOM_TIME
    context.user_data['time'] = text
    return await ask_duration(update, context, is_message=True)


async def ask_duration(update_obj, context: ContextTypes.DEFAULT_TYPE, is_message: bool = False) -> int:
    keyboard = [
        [InlineKeyboardButton("15m", callback_data="dur_15"),
         InlineKeyboardButton("30m", callback_data="dur_30")],
        [InlineKeyboardButton("1h", callback_data="dur_60")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"Time set to {context.user_data['time']}. What is the **Duration**?"

    if is_message:
        await update_obj.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update_obj.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    return WAITING_DURATION


async def new_event_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    duration_mins = query.data.split("_")[1]
    
    # We have all info, compile and execute
    title = context.user_data['title']
    date_str = context.user_data['date']
    time_str = context.user_data['time']
    
    start_datetime_iso = f"{date_str}T{time_str}:00"
    duration_iso = f"PT{duration_mins}M"

    user_id = update.effective_user.id
    user_record = await get_user(user_id)
    api_key = user_record["morgen_api_key"]

    await query.edit_message_text(f"⏳ Creating event **{title}**...", parse_mode=ParseMode.MARKDOWN)

    # Note: query.message is roughly equivalent to a message object for this helper function
    await _process_event_creation(query.message, api_key, title, start_datetime_iso, duration_iso)
    
    # Cleanup
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Event creation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

# Export the ConversationHandler for /new
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("new", new_event_start)],
    states={
        WAITING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_event_title)],
        WAITING_DATE: [CallbackQueryHandler(new_event_date_callback, pattern="^date_")],
        WAITING_CUSTOM_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_event_custom_date)],
        WAITING_TIME: [CallbackQueryHandler(new_event_time_callback, pattern="^time_")],
        WAITING_CUSTOM_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_event_custom_time)],
        WAITING_DURATION: [CallbackQueryHandler(new_event_duration_callback, pattern="^dur_")]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
