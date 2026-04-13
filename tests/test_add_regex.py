import re


def test_add_sequential_parsing():
    def parse_quick_add(text):
        if text.startswith("/add"):
            text = text[4:].strip()

        tokens = text.split()
        if len(tokens) < 3:
            return None

        time_idx = -1
        for i, token in enumerate(tokens):
            if i >= 2 and re.match(r"^\d{1,2}:\d{2}$", token):
                time_idx = i
                break

        if time_idx == -1:
            return None

        title = " ".join(tokens[: time_idx - 1])
        date_str_raw = tokens[time_idx - 1]
        time_str = tokens[time_idx]
        remainder_tokens = tokens[time_idx + 1 :]

        return title, date_str_raw, time_str, remainder_tokens

    # Standard test
    res = parse_quick_add("/add Meeting tomorrow 15:00 1H Personal")
    assert res is not None
    assert res[0] == "Meeting"
    assert res[1] == "tomorrow"
    assert res[2] == "15:00"
    assert res[3] == ["1H", "Personal"]

    # Multiple word title
    res = parse_quick_add("/add Walk the dog 15-04 18:00")
    assert res is not None
    assert res[0] == "Walk the dog"
    assert res[1] == "15-04"
    assert res[2] == "18:00"
    assert res[3] == []

    # Short Title
    res = parse_quick_add("/add A 15-04 18:00")
    assert res is not None
    assert res[0] == "A"
    assert res[1] == "15-04"
    assert res[2] == "18:00"

    # Missing parts
    assert parse_quick_add("/add Meet 15:00") is None
    assert parse_quick_add("/add Meet 1800") is None  # invalid time format


def test_add_strict_duration_parsing():
    def parse_remainder(remainder_tokens):
        calendar_target = None
        duration_iso = "PT1H"

        if remainder_tokens:
            first_part = remainder_tokens[0].upper()

            if re.match(r"^\d+[HM]$", first_part) or re.match(
                r"^\d{1,2}:\d{2}$", first_part
            ):
                optional_arg = first_part
                if len(remainder_tokens) > 1:
                    calendar_target = " ".join(remainder_tokens[1:])

                if ":" in optional_arg:
                    pass
                elif "H" in optional_arg or "M" in optional_arg:
                    duration_iso = f"PT{optional_arg}"
            else:
                calendar_target = " ".join(remainder_tokens)

        return duration_iso, calendar_target

    dur, cal = parse_remainder(["1H", "Personal"])
    assert dur == "PT1H"
    assert cal == "Personal"

    dur, cal = parse_remainder(["30M", "Work"])
    assert dur == "PT30M"
    assert cal == "Work"

    dur, cal = parse_remainder(["Hobby"])
    assert dur == "PT1H"
    assert cal == "Hobby"

    dur, cal = parse_remainder(["Marketing", "Meeting"])
    assert dur == "PT1H"
    assert cal == "Marketing Meeting"

    dur, cal = parse_remainder(["15:30"])
    assert dur == "PT1H"
    assert cal is None
