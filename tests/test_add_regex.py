import re


def test_add_regex_strict_duration():
    # The regex extracted from events.py
    pattern = r"^/add\s+(.+?)\s+([a-zA-Z0-9-]+)\s+(\d{1,2}:\d{2})(?:\s+(.+))?$"

    text = "/add Meeting tomorrow 15:00 1H Personal"
    match = re.match(pattern, text)
    assert match is not None
    assert match.group(1) == "Meeting"
    assert match.group(2) == "tomorrow"
    assert match.group(3) == "15:00"
    assert match.group(4) == "1H Personal"

    text_no_duration = "/add Meeting tomorrow 15:00 Personal"
    match = re.match(pattern, text_no_duration)
    assert match is not None
    assert match.group(1) == "Meeting"
    assert match.group(2) == "tomorrow"
    assert match.group(3) == "15:00"
    assert match.group(4) == "Personal"


def test_add_strict_duration_parsing():
    # Emulate the strict regex validation from events.py remainder splitting logic

    def parse_remainder(remainder):
        calendar_target = None
        duration_iso = "PT1H"

        if remainder:
            remainder = remainder.strip()
            parts = remainder.split(maxsplit=1)
            first_part = parts[0].upper()

            # Strict regex for duration or end time (e.g. '1H', '30M', '15:30')
            if re.match(r"^\d+[HM]$", first_part) or re.match(
                r"^\d{1,2}:\d{2}$", first_part
            ):
                optional_arg = first_part
                if len(parts) > 1:
                    calendar_target = parts[1].strip()

                if ":" in optional_arg:
                    pass  # We do not mock datetime handling here
                elif "H" in optional_arg or "M" in optional_arg:
                    duration_iso = f"PT{optional_arg}"
            else:
                # First part is not a duration, so the entire remainder is the calendar target
                calendar_target = remainder

        return duration_iso, calendar_target

    dur, cal = parse_remainder("1H Personal")
    assert dur == "PT1H"
    assert cal == "Personal"

    dur, cal = parse_remainder("30M Work")
    assert dur == "PT30M"
    assert cal == "Work"

    # Testing the user edge case
    dur, cal = parse_remainder("Hobby")
    assert dur == "PT1H"  # defaulted
    assert cal == "Hobby"  # not parsed as H duration

    dur, cal = parse_remainder("Marketing")
    assert dur == "PT1H"  # defaulted
    assert cal == "Marketing"  # not parsed as M duration

    dur, cal = parse_remainder("15:30")
    assert (
        dur == "PT1H"
    )  # handled outside in real implementation, but cal should be None
    assert cal is None
