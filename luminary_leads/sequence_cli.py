from __future__ import annotations

import argparse
import logging
import os

from .config import load_config
from .instantly import InstantlyClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or apply the Luminary weak-site Instantly sequence"
    )
    parser.add_argument(
        "--config", default="config/instantly_weak_site_sequence.yaml"
    )
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    api_key = os.getenv("INSTANTLY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing required environment variable: INSTANTLY_API_KEY")

    sequence_config = load_config(args.config)
    sequences = sequence_config.get("sequences") or []
    client = InstantlyClient(api_key, args.campaign_id, {})
    campaign = client.get_campaign()
    current_steps = len(((campaign.get("sequences") or [{}])[0].get("steps") or []))
    proposed_steps = len(((sequences or [{}])[0].get("steps") or []))
    logging.info(
        "Campaign %s currently has %d steps; proposed sequence has %d steps",
        campaign.get("name") or args.campaign_id,
        current_steps,
        proposed_steps,
    )
    if not args.apply:
        logging.info("Preview only: campaign was not changed")
        return 0

    updated = client.update_sequence(sequences)
    applied_steps = len(((updated.get("sequences") or [{}])[0].get("steps") or []))
    if applied_steps != 5:
        raise RuntimeError(
            f"Instantly returned an unexpected sequence length: {applied_steps}"
        )
    logging.info("Applied and verified five-step weak-site sequence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
