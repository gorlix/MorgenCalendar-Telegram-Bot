import calendar

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from i18n import get_text_sync


def get_month_name(month_int: int, lang: str) -> str:
    """Returns the localized name of the month."""
    months = [
        "cal_jan",
        "cal_feb",
        "cal_mar",
        "cal_apr",
        "cal_may",
        "cal_jun",
        "cal_jul",
        "cal_aug",
        "cal_sep",
        "cal_oct",
        "cal_nov",
        "cal_dec",
    ]
    if 1 <= month_int <= 12:
        return get_text_sync(months[month_int - 1], lang)
    return ""


def build_calendar_keyboard(
    year: int, month: int, lang: str, view: str = "days"
) -> InlineKeyboardMarkup:
    """
    Builds the interactive inline calendar keyboard.

    Views:
    - 'days': Shows the standard month grid.
    - 'months': Shows a grid of all 12 months for the selected year.
    - 'years': Shows a 3x3 grid of surrounding years to quickly jump.
    """
    keyboard = []

    if view == "days":
        # Row 1 (Header): Month Name | Year
        month_name = get_month_name(month, lang)
        keyboard.append(
            [
                InlineKeyboardButton(
                    month_name, callback_data=f"cal:view_months:{year}:{month:02d}"
                ),
                InlineKeyboardButton(
                    str(year), callback_data=f"cal:view_years:{year}:{month:02d}"
                ),
            ]
        )

        # Row 2 (Weekdays)
        weekdays_keys = [
            "cal_mo",
            "cal_tu",
            "cal_we",
            "cal_th",
            "cal_fr",
            "cal_sa",
            "cal_su",
        ]
        row = []
        for key in weekdays_keys:
            row.append(
                InlineKeyboardButton(
                    get_text_sync(key, lang), callback_data="cal:ignore"
                )
            )
        keyboard.append(row)

        # Rows 3+ (Days Grid)
        # Using calendar.monthcalendar which returns lists of weeks (list of lists of ints)
        month_calendar = calendar.monthcalendar(year, month)
        for week in month_calendar:
            row = []
            for day in week:
                if day == 0:
                    row.append(InlineKeyboardButton(" ", callback_data="cal:ignore"))
                else:
                    row.append(
                        InlineKeyboardButton(
                            str(day),
                            callback_data=f"cal:day:{year}:{month:02d}:{day:02d}",
                        )
                    )
            keyboard.append(row)

        # Bottom Row (Navigation)
        prev_month = month - 1
        prev_year = year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1

        next_month = month + 1
        next_year = year
        if next_month == 13:
            next_month = 1
            next_year += 1

        prev_text = get_text_sync("cal_prev_month", lang) or "⬅️"
        next_text = get_text_sync("cal_next_month", lang) or "➡️"

        keyboard.append(
            [
                InlineKeyboardButton(
                    prev_text, callback_data=f"cal:nav:{prev_year}:{prev_month:02d}"
                ),
                InlineKeyboardButton(
                    next_text, callback_data=f"cal:nav:{next_year}:{next_month:02d}"
                ),
            ]
        )

    elif view == "months":
        # A grid of 12 buttons for the months
        months = [
            "cal_jan",
            "cal_feb",
            "cal_mar",
            "cal_apr",
            "cal_may",
            "cal_jun",
            "cal_jul",
            "cal_aug",
            "cal_sep",
            "cal_oct",
            "cal_nov",
            "cal_dec",
        ]
        row = []
        for i, m_key in enumerate(months, start=1):
            row.append(
                InlineKeyboardButton(
                    get_text_sync(m_key, lang), callback_data=f"cal:nav:{year}:{i:02d}"
                )
            )
            if len(row) == 3:
                keyboard.append(row)
                row = []

    elif view == "years":
        # A grid of 9 years centered around the currently selected year (3x3 grid)
        start_year = year - 4
        row = []
        for i in range(9):
            y = start_year + i
            row.append(
                InlineKeyboardButton(
                    str(y), callback_data=f"cal:view_months:{y}:{month:02d}"
                )
            )
            if len(row) == 3:
                keyboard.append(row)
                row = []

    return InlineKeyboardMarkup(keyboard)


def process_calendar_callback(
    callback_data: str,
) -> tuple[str, int | None, int | None, int | None]:
    """
    Parses the inline calendar callback data.

    Returns a tuple: (action, year, month, day)
    Actions can be: 'IGNORE', 'NAV', 'DAY', 'VIEW_MONTHS', 'VIEW_YEARS'
    """
    parts = callback_data.split(":")
    if len(parts) < 2 or parts[0] != "cal":
        return "IGNORE", None, None, None

    action = parts[1]

    if action == "ignore":
        return "IGNORE", None, None, None

    if action == "nav" and len(parts) == 4:
        # cal:nav:YYYY:MM
        return "NAV", int(parts[2]), int(parts[3]), None

    if action == "day" and len(parts) == 5:
        # cal:day:YYYY:MM:DD
        return "DAY", int(parts[2]), int(parts[3]), int(parts[4])

    if action == "view_months" and len(parts) == 4:
        # cal:view_months:YYYY:MM
        return "VIEW_MONTHS", int(parts[2]), int(parts[3]), None

    if action == "view_years" and len(parts) == 4:
        # cal:view_years:YYYY:MM
        return "VIEW_YEARS", int(parts[2]), int(parts[3]), None

    return "IGNORE", None, None, None
