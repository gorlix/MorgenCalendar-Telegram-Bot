import logging
import os
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import init_db, get_user, upsert_user, get_users_for_daily_summary
from morgen_client import MorgenClient

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Conversation states for /new command
WAITING_TITLE = 1
WAITING_DATE = 2
WAITING_TIME = 3
WAITING_DURATION = 4
WAITING_CUSTOM_DATE = 5
WAITING_CUSTOM_TIME = 6

# Instantiate global Morgen API client
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


# --- Agenda Handlers ---

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
        # Fetch all calendars to get their IDs
        calendars = await morgen_client.list_calendars(api_key)
        if not calendars:
            await query.edit_message_text("No calendars found on your account.")
            return

        calendar_ids = [cal["id"] for cal in calendars]
        account_id = calendars[0]["accountId"]  # Assuming the first account ID applies generally

        events = await morgen_client.list_events(
            api_key=api_key,
            account_id=account_id,
            calendar_ids=calendar_ids,
            start_datetime=start_str,
            end_datetime=end_str
        )

        if not events:
            msg = f"📅 **Agenda for {day_label}**\n\nRelax! No events scheduled."
        else:
            msg = f"📅 **Agenda for {day_label}**\n\n"
            # Sort events by start time. Need to parse the ISO format slightly.
            # Format given in docs: '2023-03-01T10:15:00' (no Z for local)
            events.sort(key=lambda x: x.get("start", ""))
            
            for ev in events:
                e_title = ev.get("title", "Untitled Event")
                e_start_raw = ev.get("start", "")
                
                # Format start time to something readable, e.g. "10:15"
                if "T" in e_start_raw:
                    time_part = e_start_raw.split("T")[1][:5]
                else:
                    time_part = "All-day"
                
                msg += f"• `{time_part}` - {e_title}\n"
        
        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
    
    except Exception as e:
        logger.error(f"Error fetching agenda: {e}")
        await query.edit_message_text("❌ Failed to fetch agenda.")


# --- Daily Summary Task ---

async def send_daily_summaries(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Background task to send daily summaries to opted-in users at 07:00 AM.
    This fetches today's agenda and pushes it to their chat.
    """
    logger.info("Executing daily summary job...")
    users = await get_users_for_daily_summary()
    
    now = datetime.now(dt_timezone.utc)
    start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=1)
    
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    for u in users:
        api_key = u["morgen_api_key"]
        uid = u["telegram_user_id"]
        
        try:
            calendars = await morgen_client.list_calendars(api_key)
            if not calendars:
                continue

            calendar_ids = [cal["id"] for cal in calendars]
            account_id = calendars[0]["accountId"]

            events = await morgen_client.list_events(
                api_key=api_key,
                account_id=account_id,
                calendar_ids=calendar_ids,
                start_datetime=start_str,
                end_datetime=end_str
            )

            msg = "🌅 **Good Morning! Here is your agenda for today:**\n\n"
            if not events:
                msg += "No events scheduled. Enjoy your day!"
            else:
                events.sort(key=lambda x: x.get("start", ""))
                for ev in events:
                    e_title = ev.get("title", "Untitled Event")
                    e_start_raw = ev.get("start", "")
                    if "T" in e_start_raw:
                        time_part = e_start_raw.split("T")[1][:5]
                    else:
                        time_part = "All-day"
                    msg += f"• `{time_part}` - {e_title}\n"
            
            await context.bot.send_message(chat_id=uid, text=msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Failed to send summary to {uid}: {e}")


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


def main() -> None:
    """
    Initializes the bot, attaches handlers, and starts the polling loop.
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN environment variable not set.")
        return

    # Ensure DB is created before starting
    # We run this synchronously in the main thread just to initialize
    import asyncio
    asyncio.run(init_db())

    # Build the application
    application = ApplicationBuilder().token(token).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_event))
    application.add_handler(CommandHandler("agenda", agenda_cmd))
    application.add_handler(CommandHandler("version", version_cmd))

    # Conversation handler for /new
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
    application.add_handler(conv_handler)

    # Agenda callback handler
    application.add_handler(CallbackQueryHandler(agenda_callback, pattern="^agenda_"))

    # Handler for capturing API key (generic text messages outside conversations)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_api_key))

    # Setup Daily Summary Job at 07:00 AM
    job_queue = application.job_queue
    if job_queue:
        # Note: scheduling using server time as per requirements
        import datetime as dt
        t = dt.time(hour=7, minute=0, second=0)
        job_queue.run_daily(send_daily_summaries, time=t)
        logger.info("Daily summary scheduled for 07:00 AM server time.")
    else:
        logger.warning("JobQueue is not initialized.")

    # Run the bot
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
