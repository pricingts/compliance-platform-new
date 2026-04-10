"""Tests for timezone utilities."""
import pytest
from datetime import datetime, timezone
from utils.timezone import get_colombia_tz, now_colombia, to_colombia_tz

class TestTimezone:
    def test_get_colombia_tz_returns_zoneinfo(self):
        tz = get_colombia_tz()
        assert str(tz) == "America/Bogota"

    def test_now_colombia_has_timezone(self):
        dt = now_colombia()
        assert dt.tzinfo is not None

    def test_to_colombia_tz_naive_assumes_utc(self):
        naive = datetime(2025, 1, 1, 12, 0, 0)
        result = to_colombia_tz(naive)
        assert result.tzinfo is not None
        # Colombia is UTC-5
        assert result.hour == 7

    def test_to_colombia_tz_aware_converts(self):
        utc_dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = to_colombia_tz(utc_dt)
        assert result.hour == 7

    def test_to_colombia_tz_none_returns_now(self):
        result = to_colombia_tz(None)
        assert result.tzinfo is not None
