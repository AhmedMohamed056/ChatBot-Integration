"""Example tests for the Relative Date Engine (Task 6).

Run with:

    cd backend
    python test_relative_date_service.py

These tests use a fixed reference date (2026-08-01, a Saturday) so the
expected outputs are deterministic and match the task examples.
"""

from __future__ import annotations

import os
import sys
from datetime import date

# Make the backend directory importable when running this file directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from current_date_provider import CurrentDateProvider
from relative_date_service import resolve_relative_date


# Reference date used across all examples: 2026-08-01 (Saturday).
REF = date(2026, 8, 1)


def _expect(date_text: str, expected_iso: str) -> None:
    result = resolve_relative_date(date_text, reference_date=REF)
    assert result.success is True, f"Expected success for {date_text!r}, got {result}"
    assert result.resolved_date == expected_iso, (
        f"{date_text!r}: expected {expected_iso}, got {result.resolved_date}"
    )
    print(f"OK  {date_text!r:25} -> {result.resolved_date}")


def _expect_failure(date_text: str) -> None:
    result = resolve_relative_date(date_text, reference_date=REF)
    assert result.success is False, f"Expected failure for {date_text!r}, got {result}"
    assert result.resolved_date is None
    print(f"OK  {date_text!r:25} -> (unsupported, success=False)")


def test_examples() -> None:
    """Verify the exact examples from the task description."""
    print("== Task examples ==")
    _expect("غدا", "2026-08-02")
    _expect("بعد غد", "2026-08-03")
    _expect("الجمعة القادمة", "2026-08-07")
    _expect("الخميس", "2026-08-06")


def test_simple_offsets() -> None:
    print("\n== Simple day offsets ==")
    _expect("اليوم", "2026-08-01")
    _expect("غداً", "2026-08-02")
    _expect("بكرة", "2026-08-02")
    _expect("بعدغد", "2026-08-03")


def test_weekday_names() -> None:
    print("\n== Bare weekday names (this week, forward-looking) ==")
    # Reference 2026-08-01 is Saturday.
    _expect("السبت", "2026-08-01")     # today
    _expect("الأحد", "2026-08-02")
    _expect("الإثنين", "2026-08-03")
    _expect("الثلاثاء", "2026-08-04")
    _expect("الأربعاء", "2026-08-05")
    _expect("الخميس", "2026-08-06")
    _expect("الجمعة", "2026-08-07")


def test_next_weekdays() -> None:
    print("\n== <weekday> القادمة ==")
    _expect("السبت القادم", "2026-08-08")
    _expect("الأحد القادم", "2026-08-02")
    _expect("الإثنين القادم", "2026-08-03")
    _expect("الثلاثاء القادمة", "2026-08-04")
    _expect("الأربعاء القادمة", "2026-08-05")
    _expect("الخميس القادم", "2026-08-06")
    _expect("الجمعة القادمة", "2026-08-07")


def test_week_expressions() -> None:
    print("\n== Week-relative expressions ==")
    # Week starts Saturday. Reference Sat 2026-08-01.
    _expect("هذا الأسبوع", "2026-08-01")     # start of current week
    _expect("نهاية الأسبوع", "2026-08-07")   # Friday of current week
    _expect("أول الأسبوع", "2026-08-08")     # start of next week
    _expect("الأسبوع القادم", "2026-08-08")  # start of next week
    _expect("الأسبوع المقبل", "2026-08-08")  # start of next week


def test_unknown_expressions() -> None:
    print("\n== Unknown expressions (success=False, no exceptions) ==")
    _expect_failure("الشهر القادم")
    _expect_failure("بعد شهر")
    _expect_failure("2026-12-31")
    _expect_failure("")
    _expect_failure("hello world")


def test_current_date_provider() -> None:
    print("\n== CurrentDateProvider determinism ==")
    provider = CurrentDateProvider(reference_date=date(2026, 8, 1))
    result = resolve_relative_date("غدا", provider=provider)
    assert result.success and result.resolved_date == "2026-08-02"
    print(f"OK  provider-based 'غدا' -> {result.resolved_date}")


def main() -> None:
    test_examples()
    test_simple_offsets()
    test_weekday_names()
    test_next_weekdays()
    test_week_expressions()
    test_unknown_expressions()
    test_current_date_provider()
    print("\nAll relative date tests passed.")


if __name__ == "__main__":
    main()