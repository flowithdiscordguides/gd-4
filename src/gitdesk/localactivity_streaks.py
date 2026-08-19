"""Pure consecutive-day streak calculations for factual project activity."""

from __future__ import annotations

# Calendar arithmetic keeps streak boundaries independent from timestamps and timezones.
from datetime import date, timedelta
from typing import Any


# Calculates current and longest consecutive-day work streaks from actual activity dates.
def streak_summary(active_dates: set[date], today: date) -> dict[str, Any]:
    """Return current, longest, and most recent factual project-work streak metadata."""

    current_streak = 0
    cursor = today
    while cursor in active_dates:
        current_streak += 1
        cursor -= timedelta(days=1)

    longest_streak = 0
    running_streak = 0
    previous_day = None
    for active_day in sorted(active_dates):
        running_streak = running_streak + 1 if previous_day == active_day - timedelta(days=1) else 1
        longest_streak = max(longest_streak, running_streak)
        previous_day = active_day
    return {
        "current": current_streak,
        "longest": longest_streak,
        "last_active": max(active_dates).isoformat() if active_dates else "",
    }
