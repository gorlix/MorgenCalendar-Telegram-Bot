import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import get_users_for_daily_summary
from morgen_client import MorgenClient, RateLimitError
from formatters import format_daily_summary
from i18n import get_text

logger = logging.getLogger(__name__)
morgen_client = MorgenClient()

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
            events = await morgen_client.get_all_events(
                api_key=api_key,
                start_datetime=start_str,
                end_datetime=end_str
            )

            msg = format_daily_summary(events, lang=u.get('language', 'en'))
            await context.bot.send_message(chat_id=uid, text=msg, parse_mode=ParseMode.MARKDOWN_V2)
            
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
                
            delay_msg = await get_text("daily_summary_delayed", uid, time_str=time_str)
            await context.bot.send_message(chat_id=uid, text=delay_msg)
            
        except Exception as e:
            logger.error(f"Failed to send summary to {uid}: {e}")
