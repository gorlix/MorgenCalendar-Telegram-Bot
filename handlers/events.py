import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from database import get_user
from i18n import get_text
from morgen_client import MorgenClient
from utils.calendar_matcher import match_calendar
from utils.date_parser import parse_date
from utils.inline_calendar import build_calendar_keyboard, process_calendar_callback

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
    Handle the /add quick-insert command.

    Parses the command using the format
    ``/add <Title> <Date_or_Day> <HH:MM> [duration_or_end] [calendar_target]``, resolves the target
    calendar, and creates the event via the Morgen API.
    """
    user_id = update.effective_user.id
    user_record = await get_user(user_id)

    if not user_record or not user_record.get("morgen_api_key"):
        msg = await get_text("new_please_link", user_id)
        await update.message.reply_text(msg)
        return

    api_key = user_record["morgen_api_key"]

    text = update.message.text.strip()
    # /add <Title> <Date> <Time> [Remainder]
    match = re.match(
        r"^/add\s+(.+?)\s+([a-zA-Z0-9-]+)\s+(\d{1,2}:\d{2})(?:\s+(.+))?$",
        text,
    )

    if not match:
        msg = await get_text("add_invalid_format", user_id)
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        return

    title = match.group(1).strip()
    date_str_raw = match.group(2).strip()
    time_str = match.group(3).strip()
    remainder = match.group(4)

    duration_iso = "PT1H"  # default
    calendar_target = None

    if remainder:
        remainder = remainder.strip()
        parts = remainder.split(maxsplit=1)
        first_part = parts[0].upper()

        # Strict regex for duration or end time (e.g. '1H', '30M', '15:30')
        if re.match(r"^\d+[HM]$", first_part) or re.match(
            r"^\d{1,2}:\d{2}$", first_part
        ):
            optional_arg = first_part
            if len(parts) > 1:
                calendar_target = parts[1].strip()

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
                    if h > 0:
                        dur_parts.append(f"{h}H")
                    if m > 0:
                        dur_parts.append(f"{m}M")

                    if len(dur_parts) > 1:
                        duration_iso = "".join(dur_parts)
                except ValueError:
                    pass
            elif "H" in optional_arg or "M" in optional_arg:
                duration_iso = f"PT{optional_arg}"
        else:
            # First part is not a duration, so the entire remainder is the calendar target
            calendar_target = remainder

    logger.debug(
        f"Regex matched: title='{title}', date='{date_str_raw}', "
        f"time='{time_str}', duration='{duration_iso}', target='{calendar_target}'"
    )

    lang = user_record.get("language", "en") if user_record else "en"

    try:
        date_str = parse_date(date_str_raw, lang=lang)
    except ValueError as e:
        logger.error(f"Error parsing date: {e}")
        msg = await get_text("add_invalid_datetime", user_id)
        await update.message.reply_text(msg)
        return

    try:
        start_naive_iso = get_naive_iso_string(date_str, time_str)
        logger.debug(f"Constructed start datetime ISO: {start_naive_iso}")
    except ValueError:
        msg = await get_text("add_invalid_datetime", user_id)
        await update.message.reply_text(msg)
        return

    try:
        calendars = await morgen_client.list_calendars(api_key)
        writable_cals = [
            cal
            for cal in calendars
            if cal.get("selected") is not False
            and (
                cal.get("myRights", {}).get("mayWriteItems")
                or cal.get("myRights", {}).get("mayWriteAll")
            )
        ]
    except Exception as e:
        logger.error(f"Error fetching calendars: {e}")
        msg = await get_text("new_error_fetching_cals", user_id)
        await update.message.reply_text(msg)
        return

    if not writable_cals:
        msg = await get_text("new_no_writable_cals", user_id)
        await update.message.reply_text(msg)
        return

    target_cal = None
    if calendar_target:
        target_cal = match_calendar(writable_cals, calendar_target)

    if not target_cal:
        preferred_cal_id = user_record.get("default_calendar_id")
        selected_cal = None
        if preferred_cal_id:
            for cal in writable_cals:
                if cal.get("id") == preferred_cal_id:
                    selected_cal = cal
                    break
        if not selected_cal:
            selected_cal = writable_cals[0]
        target_cal = selected_cal

    account_id = target_cal["accountId"]
    calendar_id = target_cal["id"]

    logger.debug(
        f"Target calendar selected: id={calendar_id}, account={account_id}, name={target_cal.get('name')}"
    )

    try:
        await morgen_client.create_event(
            api_key=api_key,
            account_id=account_id,
            calendar_id=calendar_id,
            title=title,
            start_datetime_iso=start_naive_iso,
            duration_iso=duration_iso,
            timezone="Europe/Rome",
        )
        msg = await get_text("add_success", user_id, title=title)
        if calendar_target:
            msg += f"\n🗓 Calendar: {target_cal.get('name')}"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        msg = await get_text("add_failed", user_id)
        await update.message.reply_text(msg)


async def list_calendars_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Lists all available writable calendars numbered starting from 1.
    """
    user_id = update.effective_user.id
    user_record = await get_user(user_id)

    if not user_record or not user_record.get("morgen_api_key"):
        msg = await get_text("new_please_link", user_id)
        await update.message.reply_text(msg)
        return

    api_key = user_record["morgen_api_key"]
    try:
        calendars = await morgen_client.list_calendars(api_key)
        writable_cals = [
            cal
            for cal in calendars
            if cal.get("selected") is not False
            and (
                cal.get("myRights", {}).get("mayWriteItems")
                or cal.get("myRights", {}).get("mayWriteAll")
            )
        ]
    except Exception as e:
        logger.error(f"Error fetching calendars: {e}")
        msg = await get_text("new_error_fetching_cals", user_id)
        await update.message.reply_text(msg)
        return

    if not writable_cals:
        msg = await get_text("new_no_writable_cals", user_id)
        await update.message.reply_text(msg)
        return

    response = "🗓 *Available Calendars:*\n\n"
    for i, cal in enumerate(writable_cals, start=1):
        name = cal.get("name", "Unknown")
        response += f"*{i}.* {name}\n"

    response += "\n_Use the number or name in the /add command!_"
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)


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

    # NOTE: We intentionally do NOT store the decrypted API key in
    # context.user_data to minimize the in-memory exposure window.
    # Each step that needs it will call get_user() fresh.
    title_msg = await get_text("new_ask_title", user_id)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            title_msg, parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(title_msg, parse_mode=ParseMode.MARKDOWN)

    logger.info("Transitioning to ASK_TITLE")
    return ASK_TITLE


async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Step 2: Save title and ask for date"""
    title_text = update.message.text.strip()
    logger.info(f"ask_date triggered. Title received: '{title_text}'")
    context.user_data["title"] = title_text

    user_id = update.effective_user.id
    user_record = await get_user(user_id)
    lang = user_record.get("language", "en") if user_record else "en"

    now = datetime.now(ZoneInfo("Europe/Rome"))
    reply_markup = build_calendar_keyboard(now.year, now.month, lang)

    msg = await get_text("new_ask_date", user_id)
    await update.message.reply_text(
        msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
    )
    logger.info("Transitioning to ASK_DATE")
    return ASK_DATE


async def process_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process date input (interactive calendar callback or NLP text fallback)"""
    logger.info("process_date triggered")

    user_id = update.effective_user.id
    user_record = await get_user(user_id)
    lang = user_record.get("language", "en") if user_record else "en"

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        data = query.data
        logger.info(f"Callback data received: {data}")

        action, year, month, day = process_calendar_callback(data)

        if action == "IGNORE":
            return ASK_DATE

        if action in ["NAV", "VIEW_MONTHS", "VIEW_YEARS"]:
            view_mapping = {
                "NAV": "days",
                "VIEW_MONTHS": "months",
                "VIEW_YEARS": "years",
            }
            view = view_mapping[action]
            reply_markup = build_calendar_keyboard(year, month, lang, view=view)
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            return ASK_DATE

        if action == "DAY":
            date_str = f"{year}-{month:02d}-{day:02d}"
            context.user_data["date"] = date_str
            reply_func = query.edit_message_text

    else:
        text = update.message.text.strip()
        logger.info(f"Text data received: {text}")
        try:
            date_str = parse_date(text, lang=lang)
            context.user_data["date"] = date_str
            reply_func = update.message.reply_text
        except ValueError:
            logger.warning("Invalid date format entered.")
            msg = await get_text("new_invalid_date", user_id)
            await update.message.reply_text(msg)
            return ASK_DATE

    logger.info(f"Date set to: {context.user_data['date']}")

    keyboard = [
        [
            InlineKeyboardButton(f"{h:02d}:00", callback_data=f"{h:02d}:00"),
            InlineKeyboardButton(f"{h:02d}:30", callback_data=f"{h:02d}:30"),
        ]
        for h in range(7, 24)
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await get_text("new_ask_time", user_id, date=context.user_data["date"])
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

    context.user_data["time"] = time_str

    # Fetch decrypted API key fresh — minimizes in-memory exposure
    user_record = await get_user(user_id)
    api_key = user_record.get("morgen_api_key") if user_record else None
    if not api_key:
        msg = await get_text("new_please_link", user_id)
        await reply_func(msg)
        return ConversationHandler.END

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
        if cal.get("selected") is not False and (
            rights.get("mayWriteItems") or rights.get("mayWriteAll")
        ):
            cal_id = cal.get("id")
            acc_id = cal.get("accountId")
            name = cal.get("name", "Unknown")

            if "calendars" not in context.user_data:
                context.user_data["calendars"] = []

            idx = len(context.user_data["calendars"])
            context.user_data["calendars"].append(
                {"id": cal_id, "accountId": acc_id, "name": name}
            )
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
    selected_cal = context.user_data["calendars"][idx]

    title = context.user_data["title"]
    date_str = context.user_data["date"]
    time_str = context.user_data["time"]

    # Fetch decrypted API key fresh — minimizes in-memory exposure
    user_record = await get_user(user_id)
    api_key = user_record.get("morgen_api_key") if user_record else None
    if not api_key:
        msg = await get_text("new_please_link", user_id)
        await query.edit_message_text(msg)
        return ConversationHandler.END

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
            timezone="Europe/Rome",
        )
        logger.info("create_event payload succeeded")
        success_msg = await get_text(
            "new_success",
            user_id,
            title=title,
            date=date_str,
            time=time_str,
            calendar=selected_cal["name"],
        )
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
        CallbackQueryHandler(new_event_start, pattern="^dashboard_guided$"),
    ],
    states={
        ASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_date)],
        ASK_DATE: [
            CallbackQueryHandler(process_date, pattern="^cal:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_date),
        ],
        ASK_TIME: [
            CallbackQueryHandler(process_time, pattern=r"^\d{2}:\d{2}$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_time),
        ],
        ASK_CALENDAR: [CallbackQueryHandler(process_calendar, pattern="^cal_")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
