from typing import Any


def match_calendar(
    calendars: list[dict[str, Any]], target: str
) -> dict[str, Any] | None:
    """
    Finds a target calendar based on a user-provided string.

    Supports:
    - 1-indexed integers
    - Case-insensitive substring matching

    Args:
        calendars (List[Dict[str, Any]]): The list of available calendars.
        target (str): The search target.

    Returns:
        Optional[Dict[str, Any]]: The matching calendar, or None if no match is found.
    """
    target = target.strip()
    if not target:
        return None

    # Try matching as 1-indexed integer
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(calendars):
            return calendars[idx]
        return None

    # Fallback to keyword matching
    target_lower = target.lower()
    for cal in calendars:
        morgen_metadata = cal.get("morgen.so:metadata", {})
        display_name = morgen_metadata.get("overrideName") or cal.get(
            "name", "Unknown Calendar"
        )
        if target_lower in display_name.lower():
            return cal

    return None
