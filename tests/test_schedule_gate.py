from datetime import date

from luminary_leads.schedule_gate import scheduled_run_allowed


def test_manual_sync_is_always_allowed():
    assert scheduled_run_allowed(
        "",
        local_date=date(2026, 8, 16),
        timezone="Europe/London",
        local_hour=18,
    )


def test_sync_uses_five_pm_utc_during_bst():
    assert scheduled_run_allowed(
        "0 17 * * *",
        local_date=date(2026, 8, 16),
        timezone="Europe/London",
        local_hour=18,
    )
    assert not scheduled_run_allowed(
        "0 18 * * *",
        local_date=date(2026, 8, 16),
        timezone="Europe/London",
        local_hour=18,
    )


def test_sync_uses_six_pm_utc_during_gmt():
    assert scheduled_run_allowed(
        "0 18 * * *",
        local_date=date(2026, 12, 16),
        timezone="Europe/London",
        local_hour=18,
    )
    assert not scheduled_run_allowed(
        "0 17 * * *",
        local_date=date(2026, 12, 16),
        timezone="Europe/London",
        local_hour=18,
    )
