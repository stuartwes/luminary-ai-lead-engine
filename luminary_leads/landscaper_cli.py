from __future__ import annotations

import argparse
import logging
import os

from .clickup import ClickUpClient
from .config import load_config
from .firecrawl import FirecrawlClient
from .landscaper_lead_engine import LandscaperLeadEvaluator
from .landscaper_pipeline import LandscaperLeadPipeline
from .places import GooglePlacesClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LuminaryAI – Landscaper Lead Engine – V1")
    parser.add_argument("--config", default="config/landscaper_lead_engine.yaml")
    parser.add_argument("--location", required=True)
    parser.add_argument("--max-leads", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.max_leads < 1:
        raise ValueError("--max-leads must be at least 1")
    config = load_config(args.config)
    config["target"]["town"] = args.location.strip()
    config["enrichment"]["search_location"] = f"{args.location.strip()},United Kingdom"
    config["collection"]["max_approved_leads_per_run"] = args.max_leads
    env_dry_run = os.getenv("DRY_RUN", "true").casefold() not in {"false", "0", "no"}
    dry_run = args.dry_run or env_dry_run
    places_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    clickup_token = os.getenv("CLICKUP_API_TOKEN", "").strip()
    list_id = os.getenv(str(config["clickup"]["list_id_env"]), "").strip() or str(
        config["clickup"].get("list_id") or ""
    )
    missing = [name for name, value in (("GOOGLE_PLACES_API_KEY", places_key), ("FIRECRAWL_API_KEY", firecrawl_key)) if not value]
    if not dry_run:
        missing.extend(name for name, value in (("CLICKUP_API_TOKEN", clickup_token), (config["clickup"]["list_id_env"], list_id)) if not value)
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    firecrawl = FirecrawlClient(firecrawl_key, config["enrichment"])
    pipeline = LandscaperLeadPipeline(
        config,
        GooglePlacesClient(places_key),
        LandscaperLeadEvaluator(firecrawl, config),
        ClickUpClient(clickup_token, list_id, config["clickup"]),
    )
    leads = pipeline.run(dry_run=dry_run)
    logging.info("Landscaper Lead Engine complete: %d campaign-ready leads; dry_run=%s", len(leads), dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
