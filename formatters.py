import re
from typing import List, Dict, Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import html
from i18n import get_text_sync


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


def format_single_event(event: Dict[str, Any], lang: str = "en") -> str:
    """
    Formats a single Morgen event dictionary into a MarkdownV2 list item.

    Args:
        event (Dict[str, Any]): The event payload from Morgen API.

    Returns:
        str: A formatted string for a single event.
    """
    e_title = html.unescape(event.get("title") or "")

    e_start_raw = event.get("start", "")
    e_end_raw = event.get("end", "")
    e_duration = event.get("duration", "")
    e_timezone = event.get("timeZone", "Europe/Rome")
    cal_name = event.get("calendar_name", "Unknown Calendar")

    def parse_time(
        raw_str: str, duration_str: str = "", tz_str: str = "Europe/Rome"
    ) -> str:
        if not raw_str or "T" not in raw_str or len(raw_str) <= 10:
            return ""
        try:
            tz = ZoneInfo(tz_str)
            if raw_str.endswith("Z") or "+" in raw_str:
                raw_fixed = raw_str.replace("Z", "+00:00")
                dt_obj = datetime.fromisoformat(raw_fixed)
                # If we need to calculate end time from start + duration
                if duration_str and duration_str.startswith("PT"):
                    h_match = re.search(r"(\d+)H", duration_str)
                    m_match = re.search(r"(\d+)M", duration_str)
                    hours = int(h_match.group(1)) if h_match else 0
                    minutes = int(m_match.group(1)) if m_match else 0
                    dt_obj += timedelta(hours=hours, minutes=minutes)

                dt_local = dt_obj.astimezone(ZoneInfo("Europe/Rome"))
                return dt_local.strftime("%H:%M")
            else:
                # Naive datetime
                dt_obj = datetime.fromisoformat(raw_str)
                # Attach the given timezone
                dt_obj = dt_obj.replace(tzinfo=tz)

                if duration_str and duration_str.startswith("PT"):
                    h_match = re.search(r"(\d+)H", duration_str)
                    m_match = re.search(r"(\d+)M", duration_str)
                    hours = int(h_match.group(1)) if h_match else 0
                    minutes = int(m_match.group(1)) if m_match else 0
                    dt_obj += timedelta(hours=hours, minutes=minutes)

                dt_local = dt_obj.astimezone(ZoneInfo("Europe/Rome"))
                return dt_local.strftime("%H:%M")
        except Exception:
            if "T" in raw_str:
                return raw_str.split("T")[1][:5]
            return ""

    time_part = parse_time(str(e_start_raw), tz_str=e_timezone) if e_start_raw else ""
    end_part = ""
    if e_end_raw:
        end_part = parse_time(str(e_end_raw), tz_str=e_timezone)
    elif e_duration and time_part:
        end_part = parse_time(str(e_start_raw), str(e_duration), tz_str=e_timezone)

    if time_part and end_part:
        time_display = f"{time_part} -> {end_part}"
    elif time_part:
        time_display = time_part
    else:
        # Currently "All-day" but we can translate this if needed, skipping for now
        # since UI doesn't explicitly display it unless it's timed
        time_display = "All-day"

    escaped_title = escape_markdown_v2(e_title)
    escaped_time = escape_markdown_v2(time_display)
    escaped_cal = escape_markdown_v2(f"[{cal_name}]")

    return f"\\- `{escaped_time}` {escaped_cal} \\- {escaped_title}"


def build_event_list_text(events: List[Dict[str, Any]], lang: str = "en") -> str:
    if not events:
        return ""

    all_day_events = [
        ev
        for ev in events
        if "T" not in str(ev.get("start", "")) or len(str(ev.get("start", ""))) <= 10
    ]
    timed_events = [
        ev
        for ev in events
        if "T" in str(ev.get("start", "")) and len(str(ev.get("start", ""))) > 10
    ]

    all_day_events.sort(key=lambda x: str(x.get("start", "")))
    timed_events.sort(key=lambda x: str(x.get("start", "")))

    msg = ""
    if all_day_events:
        header = get_text_sync("agenda_all_day_header", lang=lang)
        msg += header
        for ev in all_day_events:
            title = escape_markdown_v2(html.unescape(ev.get("title", "")))
            cal = escape_markdown_v2(f"[{ev.get('calendar_name', 'Unknown Calendar')}]")
            msg += f"\\- {cal} {title}\n"

        if timed_events:
            msg += "\n"

    for ev in timed_events:
        msg += format_single_event(ev, lang=lang) + "\n"

    return msg


def format_agenda_message(
    events: List[Dict[str, Any]], day_label: str, user_id: int, lang: str = "en"
) -> str:
    """
    Formats a list of events into a Telegram MarkdownV2 agenda message.

    Args:
        events (List[Dict[str, Any]]): The list of events.
        day_label (str): The label for the day (e.g., 'Today' or 'Tomorrow').

    Returns:
        str: The full MarkdownV2 formatted message block.
    """
    escaped_day = escape_markdown_v2(day_label)
    msg = get_text_sync("agenda_header", lang=lang, day=escaped_day)

    if not events:
        empty_text = get_text_sync("agenda_empty", lang=lang)
        msg += escape_markdown_v2(empty_text)
        return msg

    msg += build_event_list_text(events, lang=lang)
    return msg


def format_daily_summary(events: List[Dict[str, Any]], lang: str = "en") -> str:
    """
    Formats a list of events into a Telegram MarkdownV2 daily summary message.

    Args:
        events (List[Dict[str, Any]]): The list of events for the day.

    Returns:
        str: The fully formatted daily summary string.
    """
    msg = get_text_sync("daily_summary_header", lang=lang)

    if not events:
        empty_text = get_text_sync("daily_summary_empty", lang=lang)
        msg += escape_markdown_v2(empty_text)
        return msg

    msg += build_event_list_text(events, lang=lang)
    return msg
