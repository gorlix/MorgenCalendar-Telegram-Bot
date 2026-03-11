import re
from datetime import datetime, timedelta
from typing import Optional

from i18n import get_text_sync


def parse_date(
    date_str: str, current_date: Optional[datetime] = None, lang: str = "en"
) -> str:
    """
    Parses a natural language date string into a 'YYYY-MM-DD' format.

    Supports:
    - 'today'
    - 'tomorrow'
    - Weekdays (e.g., 'monday', 'sunday') resolving to the *next* occurrence.
    - 'DD-MM' resolving to the current year.

    Args:
        date_str (str): The date string to parse.
        current_date (Optional[datetime]): The reference date. Defaults to datetime.now().
        lang (str): The user's language code from their profile setting.

    Returns:
        str: The resolved date in 'YYYY-MM-DD' format.

    Raises:
        ValueError: If the date_str format is invalid.
    """
    if current_date is None:
        current_date = datetime.now()

    date_str_lower = date_str.strip().lower()

    if date_str_lower == get_text_sync("date_today", lang).lower():
        return current_date.strftime("%Y-%m-%d")

    if date_str_lower == get_text_sync("date_tomorrow", lang).lower():
        return (current_date + timedelta(days=1)).strftime("%Y-%m-%d")

    weekdays_keys = [
        "date_monday",
        "date_tuesday",
        "date_wednesday",
        "date_thursday",
        "date_friday",
        "date_saturday",
        "date_sunday",
    ]

    weekdays = {
        get_text_sync(key, lang).lower(): i for i, key in enumerate(weekdays_keys)
    }

    if date_str_lower in weekdays:
        target_weekday = weekdays[date_str_lower]
        current_weekday = current_date.weekday()
        days_ahead = (target_weekday - current_weekday) % 7
        if days_ahead == 0:
            days_ahead = 7
        target_date = current_date + timedelta(days=days_ahead)
        return target_date.strftime("%Y-%m-%d")

    # Fallback to DD-MM
    match = re.match(r"^(\d{1,2})-(\d{1,2})$", date_str)
    if match:
        day = match.group(1).zfill(2)
        month = match.group(2).zfill(2)
        return f"{current_date.year}-{month}-{day}"

    raise ValueError(f"Invalid date format: {date_str}")
