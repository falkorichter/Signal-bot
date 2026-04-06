"""Tests for fetch_appointments.py — appointment fetching and formatting."""

from datetime import datetime, timedelta

import pytest

from fetch_appointments import fetch_appointments, format_appointments


# ---------------------------------------------------------------------------
# fetch_appointments
# ---------------------------------------------------------------------------

class TestFetchAppointments:
    def test_returns_list(self):
        result = fetch_appointments()
        assert isinstance(result, list)

    def test_list_is_not_empty(self):
        result = fetch_appointments()
        assert len(result) > 0

    def test_required_fields_present(self):
        for appt in fetch_appointments():
            assert "date" in appt, "Missing 'date' field"
            assert "time" in appt, "Missing 'time' field"
            assert "title" in appt, "Missing 'title' field"

    def test_date_format_is_iso(self):
        for appt in fetch_appointments():
            # Should parse as YYYY-MM-DD without raising
            datetime.strptime(appt["date"], "%Y-%m-%d")

    def test_time_format_is_hhmm(self):
        for appt in fetch_appointments():
            parts = appt["time"].split(":")
            assert len(parts) == 2
            assert parts[0].isdigit() and parts[1].isdigit()

    def test_available_field_is_bool_when_present(self):
        for appt in fetch_appointments():
            if "available" in appt:
                assert isinstance(appt["available"], bool)

    def test_dates_are_in_the_future(self):
        today = datetime.now().strftime("%Y-%m-%d")
        for appt in fetch_appointments():
            assert appt["date"] >= today


# ---------------------------------------------------------------------------
# format_appointments
# ---------------------------------------------------------------------------

class TestFormatAppointments:
    def test_empty_list_returns_no_appointments_message(self):
        result = format_appointments([])
        assert "No upcoming" in result

    def test_single_appointment_contains_title(self):
        appts = [{"date": "2099-01-01", "time": "09:00", "title": "Test Visit"}]
        assert "Test Visit" in format_appointments(appts)

    def test_contains_date_and_time(self):
        appts = [{"date": "2099-06-15", "time": "14:30", "title": "Check-up"}]
        result = format_appointments(appts)
        assert "2099-06-15" in result
        assert "14:30" in result

    def test_location_included_when_present(self):
        appts = [
            {"date": "2099-01-01", "time": "10:00", "title": "Visit",
             "location": "Room 42"}
        ]
        assert "Room 42" in format_appointments(appts)

    def test_fully_booked_slot_marked(self):
        appts = [
            {"date": "2099-01-01", "time": "10:00", "title": "Visit",
             "available": False}
        ]
        assert "FULLY BOOKED" in format_appointments(appts)

    def test_available_slot_not_marked_booked(self):
        appts = [
            {"date": "2099-01-01", "time": "10:00", "title": "Visit",
             "available": True}
        ]
        assert "FULLY BOOKED" not in format_appointments(appts)

    def test_multiple_appointments_all_listed(self):
        appts = [
            {"date": "2099-01-01", "time": "09:00", "title": "Alpha"},
            {"date": "2099-01-02", "time": "10:00", "title": "Beta"},
            {"date": "2099-01-03", "time": "11:00", "title": "Gamma"},
        ]
        result = format_appointments(appts)
        assert "Alpha" in result
        assert "Beta" in result
        assert "Gamma" in result

    def test_header_line_included(self):
        appts = [{"date": "2099-01-01", "time": "09:00", "title": "X"}]
        assert "Upcoming appointments" in format_appointments(appts)

    def test_missing_optional_fields_do_not_raise(self):
        # Only required fields present
        appts = [{"date": "2099-01-01", "time": "09:00", "title": "Min"}]
        result = format_appointments(appts)
        assert "Min" in result
