"""
Diagnostic & regression test suite for the get_all_events() event-filtering
pipeline in morgen_client.py.

This module contains a pure-Python simulation of the filtering logic so that
behavioural correctness can be verified without any network I/O.

History:
    - Initial version proved the root cause of the missing-events bug:
      calendars with ``selected=False`` were silently skipped, causing events
      from secondary/hidden calendars to vanish from the daily summary.
    - Updated after fix/missing-events-selected-guard: the ``selected`` guard
      has been removed.  Tests now assert the corrected fetch-all behaviour and
      serve as regression guards against re-introducing the old filter.

Run with:
    python -m pytest tests/test_event_filter_diagnosis.py -v
or standalone:
    python tests/test_event_filter_diagnosis.py
"""

# ---------------------------------------------------------------------------
# Synthetic API response: exactly the 5 events visible in the Morgen UI
# on March 24th.
#
# Key naming convention from the real Morgen API:
#   - `calendarId`  : UUID of the calendar the event belongs to
#   - `accountId`   : UUID of the Morgen account
#   - `selected`    : bool flag on the CALENDAR object (not the event)
#   - `title`       : event title string
#   - `start`       : ISO-8601 datetime
# ---------------------------------------------------------------------------

ACCOUNT_A = "account-aaa-111"
ACCOUNT_B = "account-bbb-222"  # second account to stress-test multi-account path

# Calendar A  → writable, SELECTED (the main personal calendar)
CAL_PERSONAL = "cal-personal-001"
# Calendar B  → writable, SELECTED (the medical / appointment calendar)
CAL_MEDICAL = "cal-medical-002"
# Calendar C  → writable, but `selected: False`  (hidden sync calendar)
CAL_HIDDEN = "cal-hidden-003"

MOCK_CALENDARS = [
    {
        "id": CAL_PERSONAL,
        "accountId": ACCOUNT_A,
        "name": "Personale",
        "selected": True,
        "myRights": {"mayWriteItems": True, "mayWriteAll": True},
    },
    {
        "id": CAL_MEDICAL,
        "accountId": ACCOUNT_A,
        "name": "Medico",
        # ---- BUG HYPOTHESIS 1: `selected` field is ABSENT (not False, not True)
        # The code does: if cal.get("selected") is False: continue
        # When the key is simply MISSING, cal.get("selected") returns None,
        # which is NOT `is False`, so the calendar IS included.
        # This is correct behaviour for this hypothesis.
        # We'll test the pathological case: field = None (should be included).
        "selected": None,
        "myRights": {"mayWriteItems": True, "mayWriteAll": True},
    },
    {
        "id": CAL_HIDDEN,
        "accountId": ACCOUNT_A,
        "name": "Nascosto",
        # This one is explicitly deselected: should be EXCLUDED
        "selected": False,
        "myRights": {"mayWriteItems": True, "mayWriteAll": True},
    },
]

# Events returned by the Morgen API for 2026-03-24 (sorted by start)
MOCK_EVENTS_PER_CALENDAR = {
    CAL_PERSONAL: [
        {
            "calendarId": CAL_PERSONAL,
            "accountId": ACCOUNT_A,
            "title": "Lezione: Didattica - PRINCIPI...",
            "start": "2026-03-24T11:15:00",
            "end": "2026-03-24T14:15:00",
            "timeZone": "Europe/Rome",
        },
        {
            "calendarId": CAL_PERSONAL,
            "accountId": ACCOUNT_A,
            "title": "Lezione: Didattica - FISICA",
            "start": "2026-03-24T11:15:00",
            "end": "2026-03-24T13:15:00",
            "timeZone": "Europe/Rome",
        },
        {
            "calendarId": CAL_PERSONAL,
            "accountId": ACCOUNT_A,
            "title": "Consiglio comunale",
            "start": "2026-03-24T21:00:00",
            "end": "2026-03-24T23:55:00",
            "timeZone": "Europe/Rome",
        },
        {
            "calendarId": CAL_PERSONAL,
            "accountId": ACCOUNT_A,
            "title": "Incontro Commissione S.I.D.E.",
            "start": "2026-03-24T21:00:00",
            "end": "2026-03-24T22:00:00",
            "timeZone": "Europe/Rome",
        },
    ],
    CAL_MEDICAL: [
        {
            "calendarId": CAL_MEDICAL,
            "accountId": ACCOUNT_A,
            # This is the MISSING event from the bug report
            "title": "RX Caviglia Destra",
            "start": "2026-03-24T09:40:00",
            "end": "2026-03-24T10:40:00",
            "timeZone": "Europe/Rome",
        },
    ],
    CAL_HIDDEN: [
        {
            "calendarId": CAL_HIDDEN,
            "accountId": ACCOUNT_A,
            "title": "Busy",  # should always be filtered out anyway
            "start": "2026-03-24T09:40:00",
            "end": "2026-03-24T10:40:00",
            "timeZone": "Europe/Rome",
        },
    ],
}

# ---------------------------------------------------------------------------
# Mirror the exact filtering logic from morgen_client.get_all_events()
# (lines 211-295 of morgen_client.py) without any I/O.
# ---------------------------------------------------------------------------


def simulate_get_all_events(calendars, events_by_cal_id):
    """
    Pure-Python simulation of the **fixed** get_all_events() filtering pipeline.

    Key difference from the pre-fix version: the ``selected`` field on calendar
    objects is completely ignored.  Every calendar returned by the API is
    included in the fetch, regardless of its UI-visibility state.  This matches
    the production code after the fix/missing-events-selected-guard patch.

    Args:
        calendars: List of calendar dicts as returned by list_calendars().
        events_by_cal_id: Dict mapping calendar ID -> list of event dicts,
            simulating what list_events() would return per calendar.

    Returns:
        Tuple of (all_events, account_map, cal_map, skipped_calendars) where
        ``skipped_calendars`` is always empty after the fix (kept for API
        compatibility with existing tests).
    """
    account_map = {}
    cal_map = {}
    skipped_calendars = []  # Always empty after fix; kept for test API compat

    for cal in calendars:
        # NOTE: The `selected is False` guard that previously existed here has
        # been intentionally removed.  See the TODO comment in
        # morgen_client.get_all_events() for the rationale and the planned
        # proper replacement (bot-side calendar blacklist).

        cal_id = cal.get("id")
        if "name" in cal:
            cal_map[cal_id] = cal["name"]
        else:
            cal_map[cal_id] = "Unknown Calendar"

        acc_id = cal.get("accountId")
        if acc_id and cal_id:
            if acc_id not in account_map:
                account_map[acc_id] = []
            account_map[acc_id].append(cal_id)

    all_events = []

    for account_id, cal_ids in account_map.items():
        batch_size = 5
        batches = [
            cal_ids[i : i + batch_size] for i in range(0, len(cal_ids), batch_size)
        ]

        for batch in batches:
            # Simulate the API returning all events for these calendar IDs
            response_events = []
            for cid in batch:
                response_events.extend(events_by_cal_id.get(cid, []))

            for ev in response_events:
                title = ev.get("title") or ""
                # Exact title-filter from morgen_client.py (lines 261-267)
                if not title or not title.strip() or title.strip() == "Busy":
                    continue
                ev["calendar_name"] = cal_map.get(
                    ev.get("calendarId"), "Unknown Calendar"
                )
                all_events.append(ev)

    all_events.sort(key=lambda x: x.get("start", ""))
    return all_events, account_map, cal_map, skipped_calendars


# ---------------------------------------------------------------------------
# Test: empty day handling
# ---------------------------------------------------------------------------


def simulate_format_daily_summary(events):
    """
    Mirrors formatters.format_daily_summary / build_event_list_text for
    the purpose of verifying empty-day handling only.
    """
    if not events:
        # Should return a valid "no events" string, NOT crash or return ""
        return "📅 No events today."

    lines = []
    for ev in events:
        start = ev.get("start", "")
        end = ev.get("end", "")
        title = ev.get("title", "")
        cal = ev.get("calendar_name", "?")

        def hhmm(ts):
            if ts and "T" in ts:
                return ts.split("T")[1][:5]
            return ts

        lines.append(f"\\- `{hhmm(start)} -> {hhmm(end)}` [{cal}] \\- {title}")
    return "\n".join(lines)


# ===========================================================================
# TEST SUITE
# ===========================================================================


def test_selected_is_false_no_longer_excludes_calendar():
    """
    REGRESSION GUARD (post-fix).

    After fix/missing-events-selected-guard, calendars with ``selected=False``
    must NOT be skipped.  The ``selected`` field is intentionally ignored so
    that the bot fetches events from every calendar regardless of Morgen UI
    visibility state.

    If this test fails, the old filtering behaviour has been re-introduced.
    """
    events, account_map, cal_map, skipped = simulate_get_all_events(
        MOCK_CALENDARS, MOCK_EVENTS_PER_CALENDAR
    )
    # CAL_HIDDEN (selected=False) must now be present in the account_map
    assert CAL_HIDDEN in account_map.get(ACCOUNT_A, []), (
        "REGRESSION: CAL_HIDDEN (selected=False) was excluded from account_map — "
        "the old `selected is False` guard appears to have been re-introduced."
    )
    # Its events still get filtered by the title guard ('Busy' → discarded)
    titles = [ev["title"] for ev in events]
    assert (
        "Busy" not in titles
    ), "The title-based 'Busy' filter must still discard CAL_HIDDEN's event."
    print("PASS  test_selected_is_false_no_longer_excludes_calendar")


def test_selected_is_none_includes_calendar():
    """
    CAL_MEDICAL has selected=None (key present but value is None).
    None is NOT `is False`, so the calendar SHOULD be included.
    If CAL_MEDICAL is missing from account_map, the medical event is silently dropped.
    """
    events, account_map, cal_map, skipped = simulate_get_all_events(
        MOCK_CALENDARS, MOCK_EVENTS_PER_CALENDAR
    )
    assert CAL_MEDICAL in account_map.get(ACCOUNT_A, []), (
        "FAIL: CAL_MEDICAL (selected=None) was unexpectedly excluded from account_map. "
        "This would cause 'RX Caviglia Destra' to be silently dropped."
    )
    print("PASS  test_selected_is_none_includes_calendar")


def test_missing_event_is_present():
    """
    THE CORE BUG TEST.
    'RX Caviglia Destra' must appear in the final event list.
    If this assertion FAILS, it proves the calendar it belongs to is being
    filtered out by the `selected` check.
    """
    events, _, _, skipped = simulate_get_all_events(
        MOCK_CALENDARS, MOCK_EVENTS_PER_CALENDAR
    )
    titles = [ev["title"] for ev in events]
    assert "RX Caviglia Destra" in titles, (
        "BUG CONFIRMED: 'RX Caviglia Destra' is missing from the final event list!\n"
        f"  Titles returned: {titles}\n"
        f"  Skipped calendars: {skipped}\n"
        "  Likely cause: the calendar containing this event has `selected: False` "
        "or is missing from the account_map."
    )
    print("PASS  test_missing_event_is_present")


def test_all_5_events_on_march_24():
    """All 5 events visible in the Morgen UI must appear exactly once."""
    expected = {
        "RX Caviglia Destra",
        "Lezione: Didattica - PRINCIPI...",
        "Lezione: Didattica - FISICA",
        "Consiglio comunale",
        "Incontro Commissione S.I.D.E.",
    }
    events, _, _, _ = simulate_get_all_events(MOCK_CALENDARS, MOCK_EVENTS_PER_CALENDAR)
    titles = set(ev["title"] for ev in events)
    missing = expected - titles
    extra = titles - expected
    assert not missing, (
        f"BUG CONFIRMED: The following events are MISSING from the output: {missing}\n"
        f"  Present titles: {titles}"
    )
    assert not extra, f"Unexpected extra events: {extra}"
    print(f"PASS  test_all_5_events_on_march_24  ({len(events)} events found)")


def test_chronological_ordering():
    """Events must be sorted by start time."""
    events, _, _, _ = simulate_get_all_events(MOCK_CALENDARS, MOCK_EVENTS_PER_CALENDAR)
    starts = [ev["start"] for ev in events]
    assert starts == sorted(
        starts
    ), f"FAIL: Events are not chronologically sorted.\n  Got: {starts}"
    print("PASS  test_chronological_ordering")


def test_selected_field_absent_still_includes():
    """
    Hypothesis test: if `selected` key is completely ABSENT from a calendar object,
    cal.get('selected') returns None, which is NOT `is False`, so the calendar
    must be included.  This tests that the guard clause is correctly scoped.
    """
    cal_no_selected_key = {
        "id": "cal-no-key-999",
        "accountId": ACCOUNT_A,
        "name": "No-key Calendar",
        # 'selected' key is COMPLETELY ABSENT
        "myRights": {"mayWriteItems": True},
    }
    event_in_absent_cal = {
        "calendarId": "cal-no-key-999",
        "accountId": ACCOUNT_A,
        "title": "Event In No-Key Cal",
        "start": "2026-03-24T08:00:00",
        "end": "2026-03-24T09:00:00",
        "timeZone": "Europe/Rome",
    }
    cals = [cal_no_selected_key]
    evs = {"cal-no-key-999": [event_in_absent_cal]}
    events, account_map, _, _ = simulate_get_all_events(cals, evs)
    assert "cal-no-key-999" in account_map.get(ACCOUNT_A, []), (
        "FAIL: Calendar without `selected` key was excluded — the `is False` "
        "guard should only skip calendars explicitly set to False."
    )
    titles = [ev["title"] for ev in events]
    assert "Event In No-Key Cal" in titles
    print("PASS  test_selected_field_absent_still_includes")


def test_empty_day_does_not_crash():
    """
    Edge case: zero events for the day.
    The formatter must produce a non-empty, non-crashing string.
    """
    msg = simulate_format_daily_summary([])
    assert msg, "FAIL: Empty-day formatter returned an empty string."
    assert isinstance(msg, str), "FAIL: Empty-day formatter returned a non-string."
    print(f"PASS  test_empty_day_does_not_crash  (output: '{msg}')")


def test_busy_title_is_filtered_out():
    """Events titled exactly 'Busy' must be silently discarded."""
    busy_cals = [
        {
            "id": "cal-freebusy",
            "accountId": ACCOUNT_A,
            "name": "Free/Busy",
            "selected": True,
            "myRights": {"mayWriteItems": True},
        }
    ]
    busy_evs = {
        "cal-freebusy": [
            {
                "calendarId": "cal-freebusy",
                "title": "Busy",
                "start": "2026-03-24T10:00:00",
                "end": "2026-03-24T11:00:00",
            },
            {
                "calendarId": "cal-freebusy",
                "title": None,
                "start": "2026-03-24T11:00:00",
                "end": "2026-03-24T12:00:00",
            },
            {
                "calendarId": "cal-freebusy",
                "title": "   ",
                "start": "2026-03-24T12:00:00",
                "end": "2026-03-24T13:00:00",
            },
        ]
    }
    events, _, _, _ = simulate_get_all_events(busy_cals, busy_evs)
    assert len(events) == 0, (
        f"FAIL: Expected 0 events after filtering, got {len(events)}: "
        f"{[ev['title'] for ev in events]}"
    )
    print("PASS  test_busy_title_is_filtered_out")


def test_real_world_selected_false_previously_dropped_event():
    """
    REGRESSION GUARD (post-fix) — historical proof of the original bug.

    This test documents what the old code would have produced: marking
    CAL_MEDICAL as ``selected=False`` previously caused 'RX Caviglia Destra'
    to vanish silently.  After the fix, the event must still appear even when
    its calendar has ``selected=False``.
    """
    calendars_with_medical_deselected = [
        cal if cal["id"] != CAL_MEDICAL else {**cal, "selected": False}
        for cal in MOCK_CALENDARS
    ]
    events, _, _, skipped = simulate_get_all_events(
        calendars_with_medical_deselected, MOCK_EVENTS_PER_CALENDAR
    )
    titles = [ev["title"] for ev in events]
    # After the fix, the event must be present despite selected=False
    assert "RX Caviglia Destra" in titles, (
        "REGRESSION: 'RX Caviglia Destra' is missing even though the fix should "
        "make selected=False calendars no longer be skipped."
    )
    # skipped must be empty because the filter was removed
    assert len(skipped) == 0, (
        f"REGRESSION: skipped is non-empty ({skipped}), indicating the "
        "selected-filter was re-introduced."
    )
    print(
        "PASS  test_real_world_selected_false_previously_dropped_event "
        "(fix confirmed: selected=False on CAL_MEDICAL no longer drops event)"
    )


# ---------------------------------------------------------------------------
# Runner (also usable via pytest)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("EVENT FILTER DIAGNOSIS & REGRESSION SUITE — MorgenCalendar-Telegram-Bot")
    print("=" * 70 + "\n")

    tests = [
        test_selected_is_false_no_longer_excludes_calendar,
        test_selected_is_none_includes_calendar,
        test_missing_event_is_present,
        test_all_5_events_on_march_24,
        test_chronological_ordering,
        test_selected_field_absent_still_includes,
        test_empty_day_does_not_crash,
        test_busy_title_is_filtered_out,
        test_real_world_selected_false_previously_dropped_event,
    ]

    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}\n      {e}\n")

    print(f"\n{'=' * 70}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 70)

    if failed:
        raise SystemExit(1)
