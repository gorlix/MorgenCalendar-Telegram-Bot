import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import datetime as dt

from database import get_user
from morgen_client import MorgenClient, RateLimitError
from formatters import format_daily_summary
from i18n import get_text

logger = logging.getLogger(__name__)
morgen_client = MorgenClient()


async def send_daily_summaries(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Background task to send daily summaries to a specific opted-in user at their chosen time.
    """
    job = context.job
    if not job or not job.data:
        logger.error("Job or job.data missing.")
        return

    uid = job.data.get("user_id")
    if not uid:
        logger.error("user_id missing from job data.")
        return

    logger.info(f"Executing daily summary job for user {uid}...")
    user_record = await get_user(uid)

    if not user_record or not user_record.get("morgen_api_key"):
        logger.warning(f"User {uid} missing API key. Aborting agenda run.")
        return

    api_key = user_record["morgen_api_key"]

    now = datetime.now(dt_timezone.utc)
    start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=1)

    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        events = await morgen_client.get_all_events(
            api_key=api_key, start_datetime=start_str, end_datetime=end_str
        )

        msg = format_daily_summary(events, lang=user_record.get("language", "en"))
        await context.bot.send_message(
            chat_id=uid, text=msg, parse_mode=ParseMode.MARKDOWN_V2
        )

    except RateLimitError as e:
        import re

        match = re.search(r"wait (\d+) seconds", str(e))
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

        delay_msg = await get_text("daily_summary_delayed", uid, time_str=time_str)
        await context.bot.send_message(chat_id=uid, text=delay_msg)

    except Exception as e:
        logger.error(f"Failed to send summary to {uid}: {e}")


def update_user_agenda_job(
    job_queue, user_id: int, is_enabled: bool, time_str: str
) -> None:
    """
    Adds, updates, or removes a daily summary scheduled job for a specific user.
    """
    job_name = f"agenda_{user_id}"

    # Remove existing jobs with this name
    current_jobs = job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    if not is_enabled:
        logger.info(f"Removed agenda job for user {user_id}")
        return

    try:
        from zoneinfo import ZoneInfo
        hour, minute = map(int, time_str.split(":"))
        t = dt.time(hour=hour, minute=minute, second=0, tzinfo=ZoneInfo("Europe/Rome"))
    except Exception as e:
        logger.error(
            f"Failed to parse time string '{time_str}' for user {user_id}: {e}"
        )
        return

    # Schedule the new job
    job_queue.run_daily(
        send_daily_summaries, time=t, name=job_name, data={"user_id": user_id}
    )
    logger.info(f"Scheduled agenda job for user {user_id} at {time_str} server time.")
