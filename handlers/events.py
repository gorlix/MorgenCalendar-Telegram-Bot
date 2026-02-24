import re
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
from i18n import get_text

logger = logging.getLogger(__name__)
morgen_client = MorgenClient()

# Conversation states for /new command
ASK_TITLE, ASK_DATE, ASK_TIME, ASK_CALENDAR = range(4)

def get_naive_iso_string(date_str: str, time_str: str) -> str:
    """
    Takes 'YYYY-MM-DD' and 'HH:MM', and constructs a naive ISO8601 string
    (e.g. 2026-02-28T15:00:00) without timezone offsets for Morgen API.
    """
    dt_str = f"{date_str} {time_str}"
    dt_obj_naive = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    return dt_obj_naive.strftime("%Y-%m-%dT%H:%M:00")

async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Quick Insert Command (/add)
    Expected format: /add <Title> <DD-MM> <HH:MM>
    """
    user_id = update.effective_user.id
    user_record = await get_user(user_id)

    if not user_record or not user_record.get("morgen_api_key"):
        msg = await get_text("new_please_link", user_id)
        await update.message.reply_text(msg)
        return

    api_key = user_record["morgen_api_key"]
    
    # We use update.message.text to parse with regex since context.args splits by space 
    # and the title may contain spaces.
    text = update.message.text.strip()
    match = re.match(r'^/add\s+(.+?)\s+(\d{1,2}-\d{1,2})\s+(\d{1,2}:\d{2})(?:\s+([a-zA-Z0-9:]+))?$', text)
    
    if not match:
        msg = await get_text("add_invalid_format", user_id)
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        return

    title = match.group(1).strip()
    date_dd_mm = match.group(2)
    time_str = match.group(3)
    optional_arg = match.group(4)
    
    duration_iso = "PT1H"  # default
    
    if optional_arg:
        optional_arg = optional_arg.upper()
        if ":" in optional_arg:
            try:
                start_dt = datetime.strptime(time_str, "%H:%M")
                end_dt = datetime.strptime(optional_arg, "%H:%M")
                if end_dt < start_dt:
                    end_dt += timedelta(days=1)
                
                diff_sec = int((end_dt - start_dt).total_seconds())
                h = diff_sec // 3600
                m = (diff_sec % 3600) // 60
                
                dur_parts = ["PT"]
                if h > 0: dur_parts.append(f"{h}H")
                if m > 0: dur_parts.append(f"{m}M")
                
                if len(dur_parts) > 1:
                    duration_iso = "".join(dur_parts)
            except ValueError:
                pass
        elif "H" in optional_arg or "M" in optional_arg:
            duration_iso = f"PT{optional_arg}"
            
    logger.info(f"Regex matched! Title: '{title}', Date: '{date_dd_mm}', Time: '{time_str}', Duration ISO: '{duration_iso}'")
    
    # Reformat date to YYYY-MM-DD
    current_year = datetime.now().year
    day, month = date_dd_mm.split("-")
    date_str = f"{current_year}-{month.zfill(2)}-{day.zfill(2)}"
    
    # Basic time validation
    try:
        start_naive_iso = get_naive_iso_string(date_str, time_str)
        logger.info(f"Constructed start datetime ISO: {start_naive_iso}")
    except ValueError:
        msg = await get_text("add_invalid_datetime", user_id)
        await update.message.reply_text(msg)
        return

    primary_cal = await morgen_client.get_primary_calendar(api_key)
    if not primary_cal:
        msg = await get_text("add_no_primary_cal", user_id)
        await update.message.reply_text(msg)
        return

    account_id = primary_cal["accountId"]
    calendar_id = primary_cal["id"]
    
    logger.info(f"Primary Calendar selected -> ID: {calendar_id}, Account: {account_id}")

    try:
        await morgen_client.create_event(
            api_key=api_key,
            account_id=account_id,
            calendar_id=calendar_id,
            title=title,
            start_datetime_iso=start_naive_iso,
            duration_iso=duration_iso,
            timezone="Europe/Rome"
        )
        msg = await get_text("add_success", user_id, title=title)
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        msg = await get_text("add_failed", user_id)
        await update.message.reply_text(msg)


# --- Interactive Wizard (/new) ---

async def new_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Step 1: Ask for title"""
    logger.info("new_event_start triggered")
    user_id = update.effective_user.id
    user_record = await get_user(user_id)

    if not user_record or not user_record.get("morgen_api_key"):
        logger.warning(f"User {user_id} lacks morgen_api_key")
        msg = await get_text("new_please_link", user_id)
        await update.message.reply_text(msg)
        return ConversationHandler.END

    context.user_data['api_key'] = user_record["morgen_api_key"]
    title_msg = await get_text("new_ask_title", user_id)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(title_msg, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(title_msg, parse_mode=ParseMode.MARKDOWN)
        
    logger.info("Transitioning to ASK_TITLE")
    return ASK_TITLE

async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Step 2: Save title and ask for date"""
    title_text = update.message.text.strip()
    logger.info(f"ask_date triggered. Title received: '{title_text}'")
    context.user_data['title'] = title_text
    
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton(await get_text("new_btn_today", user_id), callback_data="date_today"),
         InlineKeyboardButton(await get_text("new_btn_tomorrow", user_id), callback_data="date_tomorrow"),
         InlineKeyboardButton(await get_text("new_btn_in2days", user_id), callback_data="date_in2days")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await get_text("new_ask_date", user_id)
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    logger.info("Transitioning to ASK_DATE")
    return ASK_DATE

async def process_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process date input (either callback or text)"""
    now = datetime.now(ZoneInfo("Europe/Rome"))
    logger.info("process_date triggered")
    
    user_id = update.effective_user.id
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        data = query.data
        logger.info(f"Callback data received: {data}")
        if data == "date_today":
            date_str = now.strftime("%Y-%m-%d")
        elif data == "date_tomorrow":
            date_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        elif data == "date_in2days":
            date_str = (now + timedelta(days=2)).strftime("%Y-%m-%d")
        context.user_data['date'] = date_str
        reply_func = query.edit_message_text
    else:
        text = update.message.text.strip()
        logger.info(f"Text data received: {text}")
        match = re.match(r"^(\d{1,2})-(\d{1,2})$", text)
        if not match:
            logger.warning("Invalid date format entered.")
            msg = await get_text("new_invalid_date", user_id)
            await update.message.reply_text(msg)
            return ASK_DATE
        day, month = match.group(1), match.group(2)
        context.user_data['date'] = f"{now.year}-{month.zfill(2)}-{day.zfill(2)}"
        reply_func = update.message.reply_text

    logger.info(f"Date set to: {context.user_data['date']}")
    
    keyboard = [
        [InlineKeyboardButton(f"{h:02d}:00", callback_data=f"{h:02d}:00"),
         InlineKeyboardButton(f"{h:02d}:30", callback_data=f"{h:02d}:30")]
        for h in range(7, 24)
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await get_text("new_ask_time", user_id, date=context.user_data['date'])
    await reply_func(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    logger.info("Transitioning to ASK_TIME")
    return ASK_TIME

async def process_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process time input and ask for Calendar"""
    logger.info("process_time triggered")
    user_id = update.effective_user.id
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        time_str = query.data
        logger.info(f"Callback time received: {time_str}")
        reply_func = query.edit_message_text
    else:
        text = update.message.text.strip()
        logger.info(f"Text time received: {text}")
        if not re.match(r"^\d{1,2}:\d{2}$", text):
            logger.warning("Invalid time format entered.")
            msg = await get_text("new_invalid_time", user_id)
            await update.message.reply_text(msg)
            return ASK_TIME
        time_str = text.zfill(5)
        reply_func = update.message.reply_text

    context.user_data['time'] = time_str
    
    api_key = context.user_data['api_key']
    try:
        logger.info("Fetching calendars...")
        calendars = await morgen_client.list_calendars(api_key)
        logger.info(f"Fetched {len(calendars)} calendars")
    except Exception as e:
        logger.error(f"Error fetching calendars: {e}")
        msg = await get_text("new_error_fetching_cals", user_id)
        await reply_func(msg)
        return ConversationHandler.END

    keyboard = []
    for cal in calendars:
        rights = cal.get("myRights", {})
        if cal.get("selected") is not False and (rights.get("mayWriteItems") or rights.get("mayWriteAll")):
            cal_id = cal.get("id")
            acc_id = cal.get("accountId")
            name = cal.get("name", "Unknown")
            
            if 'calendars' not in context.user_data:
                context.user_data['calendars'] = []
            
            idx = len(context.user_data['calendars'])
            context.user_data['calendars'].append({
                "id": cal_id,
                "accountId": acc_id,
                "name": name
            })
            keyboard.append([InlineKeyboardButton(name, callback_data=f"cal_{idx}")])

    if not keyboard:
        logger.warning("No writable calendars found")
        msg = await get_text("new_no_writable_cals", user_id)
        await reply_func(msg)
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await get_text("new_ask_calendar", user_id, time=time_str)
    await reply_func(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    logger.info("Transitioning to ASK_CALENDAR")
    return ASK_CALENDAR

async def process_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Final step: Create the event"""
    logger.info("process_calendar triggered")
    user_id = update.effective_user.id
    
    query = update.callback_query
    await query.answer()
    
    idx = int(query.data.split("_")[1])
    selected_cal = context.user_data['calendars'][idx]
    
    title = context.user_data['title']
    date_str = context.user_data['date']
    time_str = context.user_data['time']
    api_key = context.user_data['api_key']
    
    logger.info(f"Selected calendar index {idx}: {selected_cal.get('name')}")
    
    try:
        start_naive_iso = get_naive_iso_string(date_str, time_str)
        logger.info(f"Parsed naive iso string: {start_naive_iso}")
    except Exception as e:
        logger.error(f"Datetime parse error: {e}")
        msg = await get_text("new_error_datetime", user_id)
        await query.edit_message_text(msg)
        return ConversationHandler.END

    progress_msg = await get_text("new_creating_event", user_id, title=title)
    await query.edit_message_text(progress_msg, parse_mode=ParseMode.MARKDOWN)

    try:
        logger.info(f"Sending create_event payload for '{title}' to Morgen API...")
        await morgen_client.create_event(
            api_key=api_key,
            account_id=selected_cal["accountId"],
            calendar_id=selected_cal["id"],
            title=title,
            start_datetime_iso=start_naive_iso,
            duration_iso="PT1H",
            timezone="Europe/Rome"
        )
        logger.info("create_event payload succeeded")
        success_msg = await get_text("new_success", user_id, title=title, date=date_str, time=time_str, calendar=selected_cal['name'])
        await query.edit_message_text(success_msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        failure_msg = await get_text("new_failed", user_id)
        await query.edit_message_text(failure_msg)
    
    context.user_data.clear()
    logger.info("Ending ConversationHandler naturally.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Conversation cancelled via /cancel block.")
    user_id = update.effective_user.id
    msg = await get_text("cancel_msg", user_id)
    await update.message.reply_text(msg)
    context.user_data.clear()
    return ConversationHandler.END

# Explicit dictionary routing map
conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("new", new_event_start),
        CallbackQueryHandler(new_event_start, pattern="^dashboard_guided$")
    ],
    states={
        ASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_date)],
        ASK_DATE: [
            CallbackQueryHandler(process_date, pattern="^date_"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_date)
        ],
        ASK_TIME: [
            CallbackQueryHandler(process_time, pattern=r"^\d{2}:\d{2}$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_time)
        ],
        ASK_CALENDAR: [
            CallbackQueryHandler(process_calendar, pattern="^cal_")
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
