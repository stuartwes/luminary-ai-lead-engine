from __future__ import annotations

import argparse
import logging
import os

from .config import load_config
from .instantly import InstantlyClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or apply the Landscaper Lead Engine sequence")
    parser.add_argument("--config", default="config/instantly_landscaper_lead_engine_sequence.yaml")
    parser.add_argument("--campaign-id")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    campaign_id = args.campaign_id or os.getenv("LANDSCAPER_LEAD_ENGINE_INSTANTLY_CAMPAIGN_ID", "").strip()
    api_key = os.getenv("INSTANTLY_API_KEY", "").strip()
    if not campaign_id or not api_key:
        raise RuntimeError("Missing Instantly campaign ID or INSTANTLY_API_KEY")
    sequences = load_config(args.config).get("sequences") or []
    client = InstantlyClient(api_key, campaign_id, {})
    campaign = client.get_campaign()
    logging.info("Previewing five-step sequence for %s", campaign.get("name") or campaign_id)
    if args.apply:
        client.update_sequence(sequences)
        logging.info("Applied five-step sequence; campaign activation unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
