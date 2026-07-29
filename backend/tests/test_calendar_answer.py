"""Calendar-first answer routing tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.calendar_answer_service import try_calendar_answer


class TestCalendarAnswer(unittest.TestCase):
    @patch("services.calendar_answer_service.get_prayer_engine")
    def test_maghrib_question(self, get_prayer) -> None:
        get_prayer.return_value = {"name": "المغرب", "time": "18:42"}
        reply = try_calendar_answer("What time is Maghrib?")
        self.assertIsNotNone(reply)
        self.assertIn("18:42", reply)

    @patch("services.calendar_answer_service.search_calendar_by_date")
    def test_holiday_check(self, search) -> None:
        search.return_value = [{"event_title": "Public Holiday", "event_time": ""}]
        reply = try_calendar_answer("Is tomorrow a holiday?")
        self.assertIsNotNone(reply)
        self.assertIn("Holiday", reply)


if __name__ == "__main__":
    unittest.main()
