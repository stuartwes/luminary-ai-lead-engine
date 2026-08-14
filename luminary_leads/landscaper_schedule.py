from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_config


@dataclass(frozen=True, slots=True)
class Location:
    name: str
    source: str


def load_locations(paths: list[str | Path]) -> list[Location]:
    locations: list[Location] = []
    seen: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        header_index = next(
            index for index, row in enumerate(rows) if row and row[0].strip() == "Rank"
        )
        header = rows[header_index]
        name_column = header.index("Name") if "Name" in header else header.index("Borough")
        for row in rows[header_index + 1 :]:
            if not row or not row[0].strip().isdigit() or len(row) <= name_column:
                continue
            name = row[name_column].strip()
            key = name.casefold()
            if name and key not in seen:
                seen.add(key)
                locations.append(Location(name=name, source=path.name))
    if not locations:
        raise ValueError("The landscaper location queue is empty")
    return locations


def location_for_date(
    locations: list[Location], local_date: date, start_date: date
) -> Location:
    day_number = max(0, (local_date - start_date).days)
    return locations[day_number % len(locations)]


def expected_scheduled_cron(
    local_date: date, *, timezone: str, local_hour: int
) -> str:
    local_time = datetime(
        local_date.year,
        local_date.month,
        local_date.day,
        local_hour,
        tzinfo=ZoneInfo(timezone),
    )
    utc_hour = local_time.astimezone(ZoneInfo("UTC")).hour
    return f"0 {utc_hour} * * *"


def write_github_output(path: str | Path, *, should_run: bool, location: str) -> None:
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(f"should_run={'true' if should_run else 'false'}\n")
        handle.write(f"location={location}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Select the daily landscaper location")
    parser.add_argument("--config", default="config/landscaper_lead_engine.yaml")
    parser.add_argument("--manual-location", default="")
    parser.add_argument("--scheduled-cron", default="")
    parser.add_argument("--github-output", required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    schedule = config["schedule"]
    timezone = str(schedule["timezone"])
    local_date = datetime.now(ZoneInfo(timezone)).date()
    locations = load_locations(list(schedule["location_files"]))
    selected = location_for_date(
        locations, local_date, date.fromisoformat(str(schedule["start_date"]))
    )
    location = args.manual_location.strip() or selected.name
    expected_cron = expected_scheduled_cron(
        local_date,
        timezone=timezone,
        local_hour=int(schedule["local_hour"]),
    )
    should_run = not args.scheduled_cron or args.scheduled_cron == expected_cron
    write_github_output(args.github_output, should_run=should_run, location=location)
    print(
        f"Selected location: {location}; queue size: {len(locations)}; "
        f"scheduled run enabled: {should_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
