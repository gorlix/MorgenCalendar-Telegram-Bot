from utils.inline_calendar import (
    build_calendar_keyboard,
    get_month_name,
    process_calendar_callback,
)


def test_get_month_name():
    assert get_month_name(1, "en") == "January"
    assert get_month_name(1, "it") == "Gennaio"
    assert get_month_name(12, "en") == "December"
    assert get_month_name(13, "en") == ""


def test_build_calendar_days():
    markup = build_calendar_keyboard(2026, 3, "en", view="days")
    assert markup is not None
    # Row 1 has Month Name and Year
    assert markup.inline_keyboard[0][0].text == "March"
    assert markup.inline_keyboard[0][1].text == "2026"

    # Weekdays
    assert markup.inline_keyboard[1][0].text == "Mo"

    # Navigation Buttons (bottom row)
    nav_row = markup.inline_keyboard[-1]
    assert len(nav_row) == 2
    assert nav_row[0].callback_data == "cal:nav:2026:02"
    assert nav_row[1].callback_data == "cal:nav:2026:04"


def test_build_calendar_months():
    markup = build_calendar_keyboard(2026, 3, "it", view="months")
    assert markup is not None
    # Grid is 4 rows of 3 buttons
    assert len(markup.inline_keyboard) == 4
    assert markup.inline_keyboard[0][0].text == "Gennaio"
    assert markup.inline_keyboard[3][2].text == "Dicembre"
    assert markup.inline_keyboard[0][0].callback_data == "cal:nav:2026:01"


def test_build_calendar_years():
    markup = build_calendar_keyboard(2026, 3, "en", view="years")
    assert markup is not None
    # Start year is 2026 - 4 = 2022
    assert len(markup.inline_keyboard) == 3
    assert markup.inline_keyboard[0][0].text == "2022"
    assert markup.inline_keyboard[2][2].text == "2030"
    assert markup.inline_keyboard[0][0].callback_data == "cal:view_months:2022:03"


def test_process_calendar_callback():
    assert process_calendar_callback("cal:ignore") == ("IGNORE", None, None, None)
    assert process_calendar_callback("cal:nav:2026:04") == ("NAV", 2026, 4, None)
    assert process_calendar_callback("cal:day:2026:03:15") == ("DAY", 2026, 3, 15)
    assert process_calendar_callback("cal:view_months:2026:03") == (
        "VIEW_MONTHS",
        2026,
        3,
        None,
    )
    assert process_calendar_callback("cal:view_years:2026:03") == (
        "VIEW_YEARS",
        2026,
        3,
        None,
    )
    assert process_calendar_callback("invalid_data") == ("IGNORE", None, None, None)
