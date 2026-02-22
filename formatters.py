import re
from typing import List, Dict, Any

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
    e_title = event.get("title", "Untitled Event")
    e_start_raw = event.get("start", "")
    
    if "T" in e_start_raw:
        time_part = e_start_raw.split("T")[1][:5]
    else:
        time_part = "All-day"
        
    escaped_title = escape_markdown_v2(e_title)
    escaped_time = escape_markdown_v2(time_part)
    
    return f"\\- `{escaped_time}` \\- {escaped_title}"

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
        
    # Sort events by start time
    events.sort(key=lambda x: x.get("start", ""))
    
    for ev in events:
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
        
    # Sort events by start time
    events.sort(key=lambda x: x.get("start", ""))
    
    for ev in events:
        msg += format_single_event(ev) + "\n"
        
    return msg
