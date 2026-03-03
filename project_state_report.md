# Project State Report

## Directory Structure
```
.dockerignore
.github/workflows/deploy.yml
.gitignore
Dockerfile
README.md
database.py
docker-compose.yml
formatters.py
handlers/agenda.py
handlers/basic.py
handlers/events.py
main.py
morgen_client.py
project_state_report.md
requirements.txt
tasks/scheduler.py
test_and_build.sh
```

## Git Status
```
On branch Development
Your branch is ahead of 'origin/Development' by 8 commits.
  (use "git push" to publish your local commits)

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
        modified:   formatters.py
        modified:   handlers/agenda.py
        modified:   morgen_client.py
        modified:   tasks/scheduler.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
        project_state_report.md

no changes added to commit (use "git add" and/or "git commit -a")
```

### Recent Commits
```
e015f04 (HEAD -> Development) docs: add warning about Morgen API rate limits
fba023e fix(api): implement smart batching to resolve 400 and 429 errors
e281098 docs: align documentation with modular architecture
5b0e56d chore(docker): update entrypoint and container configuration
7ac2d9a docs: align documentation with modular architecture
```

## Core API Client
### morgen_client.py
```python
import logging
import httpx
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class RateLimitError(Exception):
    pass

class MorgenClient:
    """
    An asynchronous client for interacting with the Morgen API.

    Handles authentication, calendar listing, and event operations (creating,
    listing). Relies on `httpx.AsyncClient` for non-blocking network requests.
    """
    
    BASE_URL = "https://api.morgen.so/v3"

    def __init__(self) -> None:
        """
        Initialize the MorgenClient.
        """
        self.client: httpx.AsyncClient = httpx.AsyncClient(timeout=10.0)

    def _auth_headers(self, api_key: str) -> Dict[str, str]:
        """
        Generate the required authorization headers.

        Args:
            api_key (str): The user's Morgen API key.

        Returns:
            Dict[str, str]: Headers including 'accept' and 'Authorization'.
        """
        return {
            "accept": "application/json",
            "Authorization": f"ApiKey {api_key}"
        }

    async def list_calendars(self, api_key: str) -> List[Dict[str, Any]]:
        """
        Fetch all calendars associated with the user's Morgen account.

        Args:
            api_key (str): The user's Morgen API key.

        Returns:
            List[Dict[str, Any]]: A list of calendar dictionary objects.
            Raises httpx.HTTPError on failed requests.
        """
        url = f"{self.BASE_URL}/calendars/list"
        response = await self.client.get(url, headers=self._auth_headers(api_key))
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("calendars", [])

    async def get_primary_calendar(self, api_key: str) -> Optional[Dict[str, Any]]:
        """
        Identify the first writable calendar to use as the default/primary calendar.

        Args:
            api_key (str): The user's Morgen API key.

        Returns:
            Optional[Dict[str, Any]]: The primary calendar object if found, else None.
        """
        try:
            calendars = await self.list_calendars(api_key)
            # Find a calendar where we can create items
            for cal in calendars:
                my_rights = cal.get("myRights", {})
                if my_rights.get("mayWriteItems", True) or my_rights.get("mayWriteAll", True):
                    return cal
            return calendars[0] if calendars else None
        except Exception as e:
            logger.error(f"Error fetching primary calendar: {e}")
            return None

    async def create_event(
        self,
        api_key: str,
        account_id: str,
        calendar_id: str,
        title: str,
        start_datetime_iso: str,
        duration_iso: str,
        timezone: str = "UTC"
    ) -> Dict[str, Any]:
        """
        Create a new calendar event.

        Args:
            api_key (str): The user's Morgen API key.
            account_id (str): The Morgen account ID where the calendar lives.
            calendar_id (str): The specific calendar ID.
            title (str): The title of the event.
            start_datetime_iso (str): Event start time, e.g. "2023-03-01T10:15:00".
            duration_iso (str): Duration in ISO format, e.g. "PT30M" for 30 mins.
            timezone (str): the associated timezone. Defaults to "UTC".

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        url = f"{self.BASE_URL}/events/create"
        payload = {
            "accountId": account_id,
            "calendarId": calendar_id,
            "title": title,
            "start": start_datetime_iso,
            "duration": duration_iso,
            "timeZone": timezone,
            "showWithoutTime": False
        }
        response = await self.client.post(
            url,
            headers=self._auth_headers(api_key),
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def list_events(
        self,
        api_key: str,
        account_id: str,
        calendar_ids: List[str],
        start_datetime: str,
        end_datetime: str
    ) -> httpx.Response:
        """
        Retrieve events for a specified time window from multiple calendars.

        Args:
            api_key (str): The user's Morgen API key.
            account_id (str): The Morgen account ID.
            calendar_ids (List[str]): List of calendar IDs to fetch events from.
            start_datetime (str): Datetime string with timezone (e.g. "2023-03-01T00:00:00Z").
            end_datetime (str): Datetime string with timezone (e.g. "2023-03-02T00:00:00Z").

        Returns:
            httpx.Response: The raw httpx response object so caller can read headers.
        """
        url = f"{self.BASE_URL}/events/list"
        
        # Use a list of tuples to pass multiple identical parameters to httpx correctly
        params = [
            ("accountId", account_id),
            ("start", start_datetime),
            ("end", end_datetime)
        ]
        for cid in calendar_ids:
            params.append(("calendarIds", cid))

        response = await self.client.get(
            url,
            headers=self._auth_headers(api_key),
            params=params
        )
        response.raise_for_status()
        return response

    async def get_all_events(self, api_key: str, start_datetime: str, end_datetime: str) -> List[Dict[str, Any]]:
        """
        Fetch events in batches from all available user calendars to avoid rate limits
        and URL length constraints.

        Args:
            api_key (str): The user's Morgen API key.
            start_datetime (str): Datetime string with timezone (e.g. "2023-03-01T00:00:00Z").
            end_datetime (str): Datetime string with timezone (e.g. "2023-03-02T00:00:00Z").

        Returns:
            List[Dict[str, Any]]: A flattened, sorted list of all events from all accessible calendars.
        """
        try:
            calendars = await self.list_calendars(api_key)
            if not calendars:
                return []

            # Group calendars by accountId, though typically it's just one account
            account_map = {}
            cal_map = {}
            for cal in calendars:
                if cal.get("selected") is False:
                    continue
                    
                cal_id = cal.get("id")
                if "name" in cal:
                    cal_map[cal_id] = cal["name"]
                else:
                    cal_map[cal_id] = "Unknown Calendar"
                    
                acc_id = cal.get("accountId")
                if acc_id and cal_id:
                    if acc_id not in account_map:
                        account_map[acc_id] = []
                    account_map[acc_id].append(cal_id)

            all_events = []

            # Process batches for each account
            for account_id, cal_ids in account_map.items():
                # Define batch size
                batch_size = 5
                batches = [cal_ids[i:i + batch_size] for i in range(0, len(cal_ids), batch_size)]

                for batch in batches:
                    try:
                        response = await self.list_events(
                            api_key=api_key,
                            account_id=account_id,
                            calendar_ids=batch,
                            start_datetime=start_datetime,
                            end_datetime=end_datetime
                        )
                        
                        # Log rate limits
                        rem = response.headers.get("RateLimit-Remaining")
                        if rem:
                            logger.info(f"Morgen API Points Remaining: {rem}")
                            
                        data = response.json()
                        response_events = data.get("data", {}).get("events", [])
                        
                        for ev in response_events:
                            title = ev.get("title", "")
                            if not title or not title.strip() or title.strip() == "Busy":
                                continue
                            ev["calendar_name"] = cal_map.get(ev.get("calendarId"), "Unknown Calendar")
                            all_events.append(ev)
                            
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429:
                            reset = e.response.headers.get("RateLimit-Reset") or e.response.headers.get("Retry-After")
                            try:
                                reset_seconds = int(reset)
                            except (TypeError, ValueError):
                                reset_seconds = 900
                            raise RateLimitError(f"API Limit Reached. Please wait {reset_seconds} seconds.")
                        else:
                            logger.warning(f"Error fetching batch {batch}: {e}")
                    except Exception as e:
                        logger.warning(f"Error fetching batch {batch}: {e}")
                        
                    # Sleep to respect rate limits between chunks
                    await asyncio.sleep(0.5)

            # Sort chronologically by start
            all_events.sort(key=lambda x: x.get("start", ""))
            return all_events
            
        except RateLimitError:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                reset = e.response.headers.get("RateLimit-Reset") or e.response.headers.get("Retry-After")
                try:
                    reset_seconds = int(reset)
                except (TypeError, ValueError):
                    reset_seconds = 900
                raise RateLimitError(f"API Limit Reached. Please wait {reset_seconds} seconds.")
            logger.error(f"HTTP error in get_all_events: {e}")
            return []
        except Exception as e:
            logger.error(f"Error in get_all_events: {e}")
            return []

    async def close(self) -> None:
        """
        Close the underlying httpx client.
        """
        await self.client.aclose()
```

## Formatters
### formatters.py
```python
import re
from typing import List, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

def escape_markdown_v2(text: str) -> str:
    """
    Escapes special characters for Telegram's MarkdownV2 format.

    Args:
        text (str): The raw string to be escaped.

    Returns:
        str: The safely escaped string ready for MarkdownV2 parsing.
    """
    # Characters that must be escaped in MarkdownV2
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

def format_single_event(event: Dict[str, Any]) -> str:
    """
    Formats a single Morgen event dictionary into a MarkdownV2 list item.

    Args:
        event (Dict[str, Any]): The event payload from Morgen API.

    Returns:
        str: A formatted string for a single event.
    """
    e_title = event.get("title", "")
        
    e_start_raw = event.get("start", "")
    e_end_raw = event.get("end", "")
    cal_name = event.get("calendar_name", "Unknown Calendar")
    
    def parse_time(raw_str: str) -> str:
        if not raw_str or "T" not in raw_str:
            return ""
        try:
            # Force +00:00 UTC offset for naive ISO strings from Morgen
            if not raw_str.endswith("Z") and "+" not in raw_str:
                raw_str += "+00:00"
            raw_fixed = raw_str.replace("Z", "+00:00")
            dt_utc = datetime.fromisoformat(raw_fixed)
            dt_rome = dt_utc.astimezone(ZoneInfo("Europe/Rome"))
            return dt_rome.strftime("%H:%M")
        except Exception:
            return raw_str.split("T")[1][:5]
            
    time_part = parse_time(e_start_raw)
    end_part = parse_time(e_end_raw)
    
    if not time_part:
        time_display = "All-day"
    elif time_part and end_part:
        time_display = f"{time_part} -> {end_part}"
    else:
        time_display = time_part
        
    escaped_title = escape_markdown_v2(e_title)
    escaped_time = escape_markdown_v2(time_display)
    escaped_cal = escape_markdown_v2(f"[{cal_name}]")
    
    return f"\\- `{escaped_time}` {escaped_cal} \\- {escaped_title}"

def format_agenda_message(events: List[Dict[str, Any]], day_label: str) -> str:
    """
    Formats a list of events into a Telegram MarkdownV2 agenda message.

    Args:
        events (List[Dict[str, Any]]): The list of events.
        day_label (str): The label for the day (e.g., 'Today' or 'Tomorrow').

    Returns:
        str: The full MarkdownV2 formatted message block.
    """
    escaped_day = escape_markdown_v2(day_label)
    msg = f"📅 *Agenda for {escaped_day}*\n\n"
    
    if not events:
        msg += escape_markdown_v2("Relax! No events scheduled.")
        return msg
        
    all_day_events = [ev for ev in events if "T" not in ev.get("start", "")]
    timed_events = [ev for ev in events if "T" in ev.get("start", "")]
    
    all_day_events.sort(key=lambda x: x.get("start", ""))
    timed_events.sort(key=lambda x: x.get("start", ""))
    
    if all_day_events:
        msg += "*All day events:*\n"
        for ev in all_day_events:
            title = escape_markdown_v2(ev.get("title", ""))
            cal = escape_markdown_v2(f"[{ev.get('calendar_name', 'Unknown Calendar')}]")
            msg += f"\\- {cal} {title}\n"
            
        if timed_events:
            msg += "\n"
            
    for ev in timed_events:
        msg += format_single_event(ev) + "\n"
        
    return msg

def format_daily_summary(events: List[Dict[str, Any]]) -> str:
    """
    Formats a list of events into a Telegram MarkdownV2 daily summary message.

    Args:
        events (List[Dict[str, Any]]): The list of events for the day.

    Returns:
        str: The fully formatted daily summary string.
    """
    msg = f"🌅 *Good Morning\\! Here is your agenda for today:*\n\n"
    
    if not events:
        msg += escape_markdown_v2("No events scheduled. Enjoy your day!")
        return msg
        
    all_day_events = [ev for ev in events if "T" not in ev.get("start", "")]
    timed_events = [ev for ev in events if "T" in ev.get("start", "")]
    
    all_day_events.sort(key=lambda x: x.get("start", ""))
    timed_events.sort(key=lambda x: x.get("start", ""))
    
    if all_day_events:
        msg += "*All day events:*\n"
        for ev in all_day_events:
            title = escape_markdown_v2(ev.get("title", ""))
            cal = escape_markdown_v2(f"[{ev.get('calendar_name', 'Unknown Calendar')}]")
            msg += f"\\- {cal} {title}\n"
            
        if timed_events:
            msg += "\n"
            
    for ev in timed_events:
        msg += format_single_event(ev) + "\n"
        
    return msg
```

## Main & Handlers
### main.py
```python
import os
import logging
import asyncio

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from database import init_db
from handlers.basic import start, handle_api_key, version_cmd
from handlers.events import add_event, conv_handler
from handlers.agenda import agenda_cmd, agenda_callback
from tasks.scheduler import send_daily_summaries

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

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
    asyncio.run(init_db())

    # Build the application
    application = ApplicationBuilder().token(token).build()

    # Basic handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("version", version_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_api_key))

    # Event handlers
    application.add_handler(CommandHandler("add", add_event))
    application.add_handler(conv_handler)
    
    # Agenda handlers
    application.add_handler(CommandHandler("agenda", agenda_cmd))
    application.add_handler(CallbackQueryHandler(agenda_callback, pattern="^agenda_"))

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
```

### handlers/agenda.py
```python
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import get_user
from morgen_client import MorgenClient, RateLimitError
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
        await query.edit_message_text(f"⚠️ Morgen API Rate Limit exceeded. Your points will reset in {time_str}. Please try again then.")
        
    except Exception as e:
        logger.error(f"Error fetching agenda: {e}")
        await query.edit_message_text("❌ Failed to fetch agenda.")
```

## Infrastructure
### Dockerfile
```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install procps for HEALTHCHECK
RUN apt-get update && apt-get install -y procps && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY . .

# Build arguments and environment variables
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Create data directory for SQLite DB
RUN mkdir -p /app/data
ENV DB_PATH=/app/data/morgen_bot.db

# Healthcheck to verify the bot process is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ps -ef | grep "[p]ython main.py" || exit 1

# Run the application
CMD ["python", "main.py"]
```

### requirements.txt
```text
python-telegram-bot[job-queue]>=20.0
httpx>=0.24.0
aiosqlite>=0.19.0
APScheduler>=3.10.1
uvicorn>=0.23.0
```
