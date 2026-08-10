from __future__ import annotations

import argparse
import logging
import os

from .clickup import ClickUpClient
from .config import load_config, load_sync_secrets
from .instantly import InstantlyClient


LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync approved ClickUp leads to Instantly")
    parser.add_argument("--config", default="config/targeting.yaml")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    env_dry_run = os.getenv("DRY_RUN", "true").casefold() not in {"false", "0", "no"}
    dry_run = args.dry_run or env_dry_run
    secrets = load_sync_secrets(allow_missing=dry_run)
    clickup = ClickUpClient(
        secrets["CLICKUP_API_TOKEN"],
        secrets["CLICKUP_LIST_ID"],
        config["clickup"],
    )
    instantly_config = config["instantly"]
    instantly = InstantlyClient(
        secrets["INSTANTLY_API_KEY"],
        instantly_config["campaign_id"],
        instantly_config,
    )

    leads = clickup.approved_leads(
        instantly_config["approved_clickup_status"],
        required_lead_type=instantly_config.get("lead_type", "ai_business_lab"),
    )
    LOGGER.info("Found %d approved, unsynced ClickUp leads", len(leads))
    processed = 0
    for lead in leads:
        if dry_run:
            LOGGER.info("Dry run: would import %s (%s)", lead.company_name, lead.company_number)
            continue
        try:
            result = instantly.add_lead(lead)
            outcome = instantly.outcome(result)
            clickup.mark_instantly_synced(lead, outcome, instantly.campaign_id)
            processed += 1
            LOGGER.info("Processed %s (%s): %s", lead.company_name, lead.company_number, outcome)
        except Exception:
            LOGGER.exception("Failed to sync %s (%s)", lead.company_name, lead.company_number)

    LOGGER.info("Sync complete: %d processed; dry_run=%s", processed, dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
