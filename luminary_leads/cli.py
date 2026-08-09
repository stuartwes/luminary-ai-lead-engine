from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .clickup import ClickUpClient
from .companies_house import CompaniesHouseClient
from .config import load_config, load_secrets
from .firecrawl import FirecrawlClient
from .pipeline import LeadPipeline, write_csv


def scheduled_window(config: dict, now: datetime | None = None) -> bool:
    timezone = ZoneInfo(config["schedule"]["timezone"])
    local_now = now.astimezone(timezone) if now else datetime.now(timezone)
    return local_now.hour == int(config["schedule"]["local_hour"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Luminary AI new-business lead engine")
    parser.add_argument("--config", default="config/targeting.yaml")
    parser.add_argument("--output", default="output/leads.csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--max-leads",
        type=int,
        help="Override the configured lead cap for this run (useful for a small live pilot)",
    )
    parser.add_argument("--scheduled", action="store_true", help="Exit unless this is the configured local hour")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    if args.max_leads is not None:
        if args.max_leads < 1:
            raise ValueError("--max-leads must be at least 1")
        config["collection"]["max_approved_leads_per_run"] = args.max_leads
        logging.info("Lead cap overridden for this run: %d", args.max_leads)
    if args.scheduled and not scheduled_window(config):
        logging.info("Outside the configured local run hour; exiting safely")
        return 0

    env_dry_run = os.getenv("DRY_RUN", "true").casefold() not in {"false", "0", "no"}
    dry_run = args.dry_run or env_dry_run
    secrets = load_secrets()
    pipeline = LeadPipeline(
        config,
        CompaniesHouseClient(secrets["COMPANIES_HOUSE_API_KEY"]),
        FirecrawlClient(secrets["FIRECRAWL_API_KEY"], config["enrichment"]),
        ClickUpClient(
            secrets["CLICKUP_API_TOKEN"], secrets["CLICKUP_LIST_ID"], config["clickup"]
        ),
    )
    leads = pipeline.run(dry_run=dry_run)
    write_csv(leads, args.output)
    logging.info("Run complete: %d review-ready leads; dry_run=%s", len(leads), dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
