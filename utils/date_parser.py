import re
from datetime import datetime, timedelta

from i18n import get_text_sync


def parse_date(
    date_str: str, current_date: datetime | None = None, lang: str = "en"
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

    # Check "today" explicitly using hardcoded lists alongside dynamic translation fallback
    today_variants = {"today", "oggi", get_text_sync("date_today", lang).lower()}
    if date_str_lower in today_variants:
        return current_date.strftime("%Y-%m-%d")

    # Check "tomorrow" explicitly using hardcoded lists alongside dynamic translation fallback
    tomorrow_variants = {
        "tomorrow",
        "domani",
        get_text_sync("date_tomorrow", lang).lower(),
    }
    if date_str_lower in tomorrow_variants:
        return (current_date + timedelta(days=1)).strftime("%Y-%m-%d")

    # Map weekdays natively without relying on get_text_sync translations.
    # This allows users of any language profile to freely use English names,
    # Italian names, and unaccented variants (e.g. venerdi vs venerdì).
    # Values represent Python's datetime.weekday() standard (0 = Monday, 6 = Sunday).
    WEEKDAYS_MAP = {
        "monday": 0,
        "mo": 0,
        "lunedì": 0,
        "lunedi": 0,
        "lu": 0,
        "tuesday": 1,
        "tu": 1,
        "martedì": 1,
        "martedi": 1,
        "ma": 1,
        "wednesday": 2,
        "we": 2,
        "mercoledì": 2,
        "mercoledi": 2,
        "me": 2,
        "thursday": 3,
        "th": 3,
        "giovedì": 3,
        "giovedi": 3,
        "gi": 3,
        "friday": 4,
        "fr": 4,
        "venerdì": 4,
        "venerdi": 4,
        "ve": 4,
        "saturday": 5,
        "sa": 5,
        "sabato": 5,
        "sunday": 6,
        "su": 6,
        "domenica": 6,
    }

    if date_str_lower in WEEKDAYS_MAP:
        target_weekday = WEEKDAYS_MAP[date_str_lower]
        current_weekday = current_date.weekday()

        # Calculate the number of days until the next desired weekday.
        # Modulo 7 yields the distance forward.
        days_ahead = (target_weekday - current_weekday) % 7

        # If the target is the same as the current day (0 days ahead),
        # strictly push the date to next week (+7 days).
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
