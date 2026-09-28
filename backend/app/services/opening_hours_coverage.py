from __future__ import annotations

import re

OPEN_TIME_COVERAGE_UNKNOWN = "unknown"
OPEN_TIME_COVERAGE_COVERS_SCHEDULED_WINDOW = "covers_scheduled_window"
OPEN_TIME_COVERAGE_DOES_NOT_COVER_SCHEDULED_WINDOW = "does_not_cover_scheduled_window"

_DAILY_WINDOW_PATTERN = re.compile(
    r"^\s*(?P<open>\d{1,2}:\d{2})\s*[-–]\s*(?P<close>\d{1,2}:\d{2})\s*$"
)
_CLOCK_PATTERN = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::\d{2})?$")


def assess_regular_daily_open_time_coverage(
    *,
    open_time: str | None,
    scheduled_start_time: str | None,
    scheduled_end_time: str | None,
) -> str:
    """Compare only an unambiguous single daily provider window to a scheduled clock window.

    Provider strings with weekday rules, split hours, holidays, or overnight windows are
    deliberately left unknown. This is a deterministic clock comparison, not a claim
    about a particular date, booking, temporary closure, or admission eligibility.
    """
    if not open_time or not scheduled_start_time or not scheduled_end_time:
        return OPEN_TIME_COVERAGE_UNKNOWN

    opening_match = _DAILY_WINDOW_PATTERN.fullmatch(open_time)
    if opening_match is None:
        return OPEN_TIME_COVERAGE_UNKNOWN

    opening_start = clock_minutes(opening_match.group("open"))
    opening_end = clock_minutes(opening_match.group("close"))
    scheduled_start = clock_minutes(scheduled_start_time)
    scheduled_end = clock_minutes(scheduled_end_time)
    if None in {opening_start, opening_end, scheduled_start, scheduled_end}:
        return OPEN_TIME_COVERAGE_UNKNOWN

    if opening_end <= opening_start or scheduled_end <= scheduled_start:
        return OPEN_TIME_COVERAGE_UNKNOWN
    if opening_start <= scheduled_start and scheduled_end <= opening_end:
        return OPEN_TIME_COVERAGE_COVERS_SCHEDULED_WINDOW
    return OPEN_TIME_COVERAGE_DOES_NOT_COVER_SCHEDULED_WINDOW


def clock_minutes(value: str) -> int | None:
    match = _CLOCK_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute
