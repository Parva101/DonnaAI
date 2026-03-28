"""Classify all pending emails using Gemini 2.5 Flash (direct structured output).

Usage:
    cd backend
    python classify_pending.py
"""
import asyncio
import sys
import os
import logging

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def run():
    from app.core.db import SessionLocal
    from app.models import Email
    from app.services.email_classifier import classify_emails_batch
    from sqlalchemy import select

    db = SessionLocal()
    pending = (
        db.execute(select(Email).where(Email.category_source == "pending"))
        .scalars()
        .all()
    )
    print(f"Found {len(pending)} pending emails")
    if not pending:
        print("Nothing to do!")
        db.close()
        return

    CHUNK = 100       # emails per Gemini call (maximize with 20 RPD limit)
    DELAY = 3         # seconds between successful chunks
    BACKOFF = 15      # base backoff on failure
    RETRIES = 3
    TIMEOUT = 180     # seconds per call

    ok = 0
    fail = 0
    total = len(pending)

    for i in range(0, total, CHUNK):
        chunk = pending[i : i + CHUNK]
        done = False

        for att in range(RETRIES):
            try:
                res = await asyncio.wait_for(
                    classify_emails_batch(chunk), timeout=TIMEOUT
                )
                for email_obj, (cat, src) in zip(chunk, res):
                    email_obj.category = cat
                    email_obj.category_source = src
                db.commit()
                ok += len(chunk)
                done = True
                print(f"  ✓ {ok}/{total}  (fail: {fail})")
                break
            except asyncio.TimeoutError:
                wait = BACKOFF * (2**att)
                print(f"  ✗ TIMEOUT chunk {i // CHUNK} attempt {att + 1} — waiting {wait}s")
                db.rollback()
                await asyncio.sleep(wait)
            except Exception as ex:
                wait = BACKOFF * (2**att)
                print(f"  ✗ FAIL chunk {i // CHUNK} attempt {att + 1}: {str(ex)[:150]} — waiting {wait}s")
                db.rollback()
                await asyncio.sleep(wait)

        if not done:
            fail += len(chunk)
            print(f"  ⚠ SKIPPED chunk {i // CHUNK} after {RETRIES} retries")

        await asyncio.sleep(DELAY)

    print(f"\nDONE! {ok} classified, {fail} failed out of {total}")
    db.close()


if __name__ == "__main__":
    asyncio.run(run())
