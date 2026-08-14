from __future__ import annotations

import argparse
import logging
import os

from .clickup import ClickUpClient
from .config import load_config
from .instantly import InstantlyClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync approved Landscaper Lead Engine prospects")
    parser.add_argument("--config", default="config/landscaper_lead_engine.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    route = config["instantly"]
    dry_run = args.dry_run or os.getenv("DRY_RUN", "true").casefold() not in {"false", "0", "no"}
    token = os.getenv("CLICKUP_API_TOKEN", "").strip()
    list_id = os.getenv(route["clickup_list_id_env"], "").strip() or str(
        route.get("clickup_list_id") or ""
    )
    api_key = os.getenv("INSTANTLY_API_KEY", "").strip()
    campaign_id = os.getenv(route["campaign_id_env"], "").strip() or str(
        route.get("campaign_id") or ""
    )
    missing = [name for name, value in (("CLICKUP_API_TOKEN", token), (route["clickup_list_id_env"], list_id), ("INSTANTLY_API_KEY", api_key), (route["campaign_id_env"], campaign_id)) if not value]
    if missing and not dry_run:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    clickup = ClickUpClient(token, list_id, config["clickup"])
    instantly = InstantlyClient(api_key, campaign_id, route)
    if dry_run and missing:
        logging.info("Preview configuration valid; live credentials were not required")
        return 0
    leads = clickup.approved_leads(route["approved_clickup_status"], required_lead_type=route["lead_type"])
    for lead in leads:
        if dry_run:
            logging.info("Dry run: would import %s", lead.company_name)
            continue
        result = instantly.add_lead(lead)
        clickup.mark_instantly_synced(lead, instantly.outcome(result), campaign_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
