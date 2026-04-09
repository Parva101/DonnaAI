"""
Phase 0 action worker skeleton.

Real execution adapters (WhatsApp/Gmail/Calendar) will be integrated later.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("donnaai.action_worker")


def run() -> None:
    logger.info("action-worker started")
    while True:
        # Placeholder heartbeat loop until queue wiring is implemented.
        logger.debug("action-worker heartbeat")
        time.sleep(10)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()

