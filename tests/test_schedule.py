from datetime import datetime
from zoneinfo import ZoneInfo

from luminary_leads.cli import scheduled_window


CONFIG = {"schedule": {"timezone": "Europe/London", "local_hour": 7}}


def test_schedule_gate_handles_bst():
    now = datetime(2026, 8, 9, 6, 0, tzinfo=ZoneInfo("UTC"))
    assert scheduled_window(CONFIG, now)


def test_schedule_gate_rejects_second_utc_run_in_bst():
    now = datetime(2026, 8, 9, 7, 0, tzinfo=ZoneInfo("UTC"))
    assert not scheduled_window(CONFIG, now)


def test_schedule_gate_handles_gmt():
    now = datetime(2026, 12, 9, 7, 0, tzinfo=ZoneInfo("UTC"))
    assert scheduled_window(CONFIG, now)

