from utils.calendar_matcher import match_calendar

mock_cals = [
    {"id": "cal_1", "name": "Personal"},
    {"id": "cal_2", "name": "Work"},
    {"id": "cal_3", "name": "Varie ed Eventuali"},
]


def test_match_calendar_exact_index():
    result = match_calendar(mock_cals, "1")
    assert result is not None
    assert result["name"] == "Personal"


def test_match_calendar_exact_index_out_of_bounds():
    result = match_calendar(mock_cals, "4")
    assert result is None

    result = match_calendar(mock_cals, "0")
    assert result is None


def test_match_calendar_keyword_exact():
    result = match_calendar(mock_cals, "Work")
    assert result is not None
    assert result["name"] == "Work"


def test_match_calendar_keyword_partial_insensitive():
    result = match_calendar(mock_cals, "varie")
    assert result is not None
    assert result["name"] == "Varie ed Eventuali"


def test_match_calendar_keyword_not_found():
    result = match_calendar(mock_cals, "Hobbies")
    assert result is None
