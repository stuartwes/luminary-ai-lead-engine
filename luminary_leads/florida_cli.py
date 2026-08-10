from __future__ import annotations

import argparse
import logging
import os
from datetime import date

from .clickup import ClickUpClient
from .config import load_config, load_florida_secrets
from .firecrawl import FirecrawlClient
from .florida import FloridaSunbizClient
from .florida_pipeline import FloridaLeadPipeline
from .pipeline import write_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Florida Sunbiz new-business pilot")
    parser.add_argument("--config", default="config/florida.yaml")
    parser.add_argument("--output", default="output/florida-leads.csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-leads", type=int)
    parser.add_argument("--source-date", type=date.fromisoformat)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    if args.max_leads is not None:
        if args.max_leads < 1:
            raise ValueError("--max-leads must be at least 1")
        config["collection"]["max_review_leads_per_run"] = args.max_leads
    env_dry_run = os.getenv("DRY_RUN", "true").casefold() not in {"false", "0", "no"}
    dry_run = args.dry_run or env_dry_run
    secrets = load_florida_secrets()
    pipeline = FloridaLeadPipeline(
        config,
        FloridaSunbizClient(config["sunbiz"]),
        FirecrawlClient(secrets["FIRECRAWL_API_KEY"], config["enrichment"]),
        ClickUpClient(
            secrets["CLICKUP_API_TOKEN"], secrets["CLICKUP_LIST_ID"], config["clickup"]
        ),
    )
    leads = pipeline.run(today=args.source_date, dry_run=dry_run)
    write_csv(leads, args.output)
    logging.info("Florida run complete: %d review leads; dry_run=%s", len(leads), dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
