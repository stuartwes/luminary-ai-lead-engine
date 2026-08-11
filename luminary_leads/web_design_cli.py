from __future__ import annotations

import argparse
import logging
import os

from .clickup import ClickUpClient
from .config import load_config, load_web_design_secrets
from .firecrawl import FirecrawlClient
from .places import GooglePlacesClient
from .web_design_pipeline import WebDesignLeadPipeline, write_web_design_csv
from .website_audit import WebsiteAuditClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Luminary AI weak-website lead engine")
    parser.add_argument("--config", default="config/web_design.yaml")
    parser.add_argument("--output", default="output/web-design-leads.csv")
    parser.add_argument(
        "--location",
        "--town",
        dest="town",
        help="Town/city, or London suburb in the form 'Clapham, London'",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-leads", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    if args.town:
        config["target"]["town"] = args.town.strip()
        config["enrichment"]["search_location"] = (
            f"{args.town.strip()},England,United Kingdom"
        )
    if args.max_leads is not None:
        if args.max_leads < 1:
            raise ValueError("--max-leads must be at least 1")
        config["collection"]["max_approved_leads_per_run"] = args.max_leads

    env_dry_run = os.getenv("DRY_RUN", "true").casefold() not in {"false", "0", "no"}
    dry_run = args.dry_run or env_dry_run
    secrets = load_web_design_secrets(allow_missing=True)
    always_required = ("GOOGLE_PLACES_API_KEY", "FIRECRAWL_API_KEY")
    missing = [name for name in always_required if not secrets[name]]
    clickup_list_id = secrets["WEB_DESIGN_CLICKUP_LIST_ID"] or str(
        config["clickup"].get("list_id") or ""
    )
    if not dry_run:
        missing.extend(
            name
            for name, value in (
                ("CLICKUP_API_TOKEN", secrets["CLICKUP_API_TOKEN"]),
                ("WEB_DESIGN_CLICKUP_LIST_ID", clickup_list_id),
            )
            if not value
        )
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))

    firecrawl = FirecrawlClient(secrets["FIRECRAWL_API_KEY"], config["enrichment"])
    pipeline = WebDesignLeadPipeline(
        config,
        GooglePlacesClient(secrets["GOOGLE_PLACES_API_KEY"]),
        WebsiteAuditClient(firecrawl, config["website_audit"]),
        ClickUpClient(
            secrets["CLICKUP_API_TOKEN"],
            clickup_list_id,
            config["clickup"],
        ),
    )
    leads = pipeline.run(dry_run=dry_run)
    write_web_design_csv(leads, args.output)
    logging.info(
        "Web-design run complete: %d review-ready leads; town=%s; dry_run=%s",
        len(leads),
        config["target"]["town"],
        dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
