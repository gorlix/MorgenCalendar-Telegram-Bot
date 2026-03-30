from datetime import datetime

import pytest

from utils.date_parser import parse_date


def test_parse_date_today():
    mock_now = datetime(2026, 3, 11, 14, 0, 0)
    result = parse_date("today", current_date=mock_now, lang="en")
    assert result == "2026-03-11"

    result_it = parse_date("oggi", current_date=mock_now, lang="it")
    assert result_it == "2026-03-11"


def test_parse_date_tomorrow():
    mock_now = datetime(2026, 3, 11, 14, 0, 0)
    result = parse_date("tomorrow", current_date=mock_now, lang="en")
    assert result == "2026-03-12"

    result_it = parse_date("domani", current_date=mock_now, lang="it")
    assert result_it == "2026-03-12"


def test_parse_date_next_weekday_same_day():
    # March 11 2026 is a Wednesday (2)
    mock_now = datetime(2026, 3, 11, 14, 0, 0)
    # If today is Wednesday and user says Wednesday, it should be next Wednesday (+7 days)
    result = parse_date("wednesday", current_date=mock_now, lang="en")
    assert result == "2026-03-18"

    result_it = parse_date("mercoledì", current_date=mock_now, lang="it")
    assert result_it == "2026-03-18"


def test_parse_date_next_weekday_future():
    # March 11 2026 is a Wednesday (2)
    mock_now = datetime(2026, 3, 11, 14, 0, 0)
    # Next Friday is +2 days
    result = parse_date("friday", current_date=mock_now, lang="en")
    assert result == "2026-03-13"

    result_it = parse_date("venerdì", current_date=mock_now, lang="it")
    assert result_it == "2026-03-13"


def test_parse_date_next_weekday_past():
    # March 11 2026 is a Wednesday (2)
    mock_now = datetime(2026, 3, 11, 14, 0, 0)
    # Next Monday is +5 days
    result = parse_date("monday", current_date=mock_now, lang="en")
    assert result == "2026-03-16"

    result_it = parse_date("lunedì", current_date=mock_now, lang="it")
    assert result_it == "2026-03-16"


def test_parse_date_dd_mm():
    mock_now = datetime(2026, 3, 11, 14, 0, 0)
    result = parse_date("15-08", current_date=mock_now, lang="en")
    assert result == "2026-08-15"

    result_it = parse_date("15-08", current_date=mock_now, lang="it")
    assert result_it == "2026-08-15"


def test_parse_date_invalid():
    with pytest.raises(ValueError):
        parse_date("not-a-date", lang="en")
