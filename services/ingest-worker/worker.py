"""
Phase 0 ingest worker skeleton.

Real queue consumption and connector subscriptions will be added in Phase 1.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("donnaai.ingest_worker")


def run() -> None:
    logger.info("ingest-worker started")
    while True:
        # Placeholder heartbeat loop until queue wiring is implemented.
        logger.debug("ingest-worker heartbeat")
        time.sleep(10)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()

