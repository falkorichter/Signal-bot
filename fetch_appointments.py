#!/usr/bin/env python3
"""fetch_appointments.py — Fetch and format upcoming appointment data.

This script outputs human-readable appointment information that is injected
into the LLM prompt as context.

Usage::

    python fetch_appointments.py

**Customisation**: Replace the body of :func:`fetch_appointments` with calls
to your actual data source — a calendar API (e.g. Google Calendar, CalDAV),
a database query, or a local file — and adjust the field names accordingly.
"""

import logging
import sys
from datetime import datetime, timedelta
from typing import List

logger = logging.getLogger(__name__)


def fetch_appointments() -> List[dict]:
    """Return a list of upcoming appointment dicts.

    Each dict should contain at minimum:
    - ``date``      (str, ``YYYY-MM-DD``)
    - ``time``      (str, ``HH:MM``)
    - ``title``     (str)
    - ``location``  (str, optional)
    - ``available`` (bool, optional — ``False`` marks a fully-booked slot)

    Replace the stub below with your real data source.
    """
    today = datetime.now()
    appointments = [
        {
            "date": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
            "time": "09:00",
            "title": "General Consultation",
            "location": "Main Office",
            "available": True,
        },
        {
            "date": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
            "time": "14:00",
            "title": "Follow-up Meeting",
            "location": "Room B",
            "available": True,
        },
        {
            "date": (today + timedelta(days=5)).strftime("%Y-%m-%d"),
            "time": "10:30",
            "title": "Open Office Hours",
            "location": "Community Centre",
            "available": True,
        },
    ]
    logger.debug("Fetched %d appointments", len(appointments))
    return appointments


def format_appointments(appointments: List[dict]) -> str:
    """Format a list of appointment dicts into a human-readable string."""
    if not appointments:
        return "No upcoming appointments are currently scheduled."

    lines = ["Upcoming appointments:"]
    for appt in appointments:
        line = (
            f"- {appt.get('date', '?')} at {appt.get('time', '?')}: "
            f"{appt.get('title', 'Untitled')}"
        )
        location = appt.get("location")
        if location:
            line += f" ({location})"
        if not appt.get("available", True):
            line += " [FULLY BOOKED]"
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        appointments = fetch_appointments()
        print(format_appointments(appointments))
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to fetch appointments: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
