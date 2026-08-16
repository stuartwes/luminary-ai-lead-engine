from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .landscaper_schedule import expected_scheduled_cron


def scheduled_run_allowed(
    event_cron: str,
    *,
    local_date: date,
    timezone: str,
    local_hour: int,
) -> bool:
    if not event_cron:
        return True
    return event_cron == expected_scheduled_cron(
        local_date,
        timezone=timezone,
        local_hour=local_hour,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate paired UTC schedules by UK local time")
    parser.add_argument("--scheduled-cron", default="")
    parser.add_argument("--timezone", default="Europe/London")
    parser.add_argument("--local-hour", type=int, required=True)
    parser.add_argument("--github-output", required=True)
    args = parser.parse_args()

    local_date = datetime.now(ZoneInfo(args.timezone)).date()
    should_run = scheduled_run_allowed(
        args.scheduled_cron,
        local_date=local_date,
        timezone=args.timezone,
        local_hour=args.local_hour,
    )
    with Path(args.github_output).open("a", encoding="utf-8") as handle:
        handle.write(f"should_run={'true' if should_run else 'false'}\n")
    print(f"Scheduled sync enabled: {should_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
