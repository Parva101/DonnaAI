"""Email classifier — Gemini via LangChain direct structured output.

Uses a single Gemini model call with `with_structured_output` to classify
emails in one shot. No agent loop — just prompt → structured response.
"""

from __future__ import annotations

import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from app.models.email import Email

logger = logging.getLogger(__name__)

SEED_CATEGORIES = [
    "work",
    "personal",
    "school",
    "finance",
    "travel",
    "promotions",
    "orders",
    "notifications",
    "newsletters",
]

# ─────────────────────────────────────────────────────────────────
# Structured output model
# ─────────────────────────────────────────────────────────────────

class EmailClassification(BaseModel):
    """Classification result for a single email."""
    email_no: int = Field(description="The email number being classified (1-indexed)")
    category: str = Field(description="The category assigned to the email")

class BatchClassificationResult(BaseModel):
    """Batch of classification results."""
    classifications: list[EmailClassification] = Field(
        description="List of classifications, one per email in order"
    )

# ─────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────

CLASSIFIER_SYSTEM = f"""\
You are an email classifier for a personal inbox.
Your PRIMARY job is to distinguish promotional/marketing emails from genuinely transactional or personal emails.
You will receive a dictionary containing email details and an email_no for each email.
For each one you must assign it to EXACTLY ONE of the following categories: {SEED_CATEGORIES}

CATEGORIES AND RULES:

promotions — ANY email that is marketing, advertising, feature announcement, product update, sale/deal, admission/enrollment pitch, or bulk-sent content. This includes:
  • Sales, deals, coupons from ANY company (Amazon, Target, Shein, Priceline, etc.)
  • New feature announcements from SaaS/tech companies (Retell AI, Notion, etc.)
  • University admissions marketing (e.g. RIT, Kaplan promoting programs)
  • Streaming service promos (HBO Max, Netflix, Spotify, Disney+)
  • Cart abandonment, "we miss you", "come back" emails
  • Any email with "unsubscribe" that is NOT a direct personal transaction
  • Recruitment/job board mass emails

orders — actual order confirmations, shipping updates, delivery notifications, return labels for real purchases the user made or similar.

travel — actual booking confirmations, boarding passes, ride receipts, hotel check-in details, itineraries for real trips or similar. NOT travel deal promotions.

school — emails about the user's actual classes, assignments, grades, tuition bills, financial aid and similar. NOT university admissions marketing or test-prep promotions.

finance — actual bank statements, payment confirmations, fraud alerts, tax documents, bills and similar. NOT credit card promos or loan offers.

work — Emails from colleagues, clients, or work tools about actual projects/tasks/meetings and similar. NOT recruiter spam or job board promotions.

personal — Direct 1:1 emails from real people (friends, family).

notifications — Automated alerts from apps the user actually uses (GitHub commits, social media activity, calendar reminders that aren't work, security codes, OTPs).

newsletters — Weekly/monthly digests, roundups, newsletters.

Respond with a classification for each email_no."""

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _format_email(e: dict) -> str:
    """Format a single email for the prompt."""
    return (
        f"From: {e.get('from_name', '')} <{e.get('from_address', '')}>\n"
        f"Subject: {e.get('subject', '(no subject)')}\n"
        f"Snippet: {(e.get('snippet', '') or '')[:500]}"
    )


def _get_model():
    """Create the Gemini model instance."""
    from app.core.config import settings

    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")

    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.google_api_key,
        temperature=0,
    )


def _build_classifier():
    """Build the classifier as a structured-output model (no agent loop)."""
    model = _get_model()
    return model.with_structured_output(BatchClassificationResult)


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

async def classify_emails_batch(email_objs: list[Email]) -> list[tuple[str, str]]:
    """Classify a list of Email objects using Gemini structured output.

    Sends all emails in one direct model call as a numbered dict.
    Returns a list of (category, source) tuples, one per email.
    """
    if not email_objs:
        return []

    # Build numbered email dict
    email_dict: dict[int, str] = {}
    for i, e in enumerate(email_objs, 1):
        email_dict[i] = _format_email({
            "from_name": e.from_name or "",
            "from_address": e.from_address or "",
            "subject": e.subject or "",
            "snippet": e.snippet or "",
        })

    logger.info(f"Classifying {len(email_objs)} emails via Gemini (direct structured output)...")

    classifier = _build_classifier()

    # Direct model call — no agent loop, properly cancellable
    structured: BatchClassificationResult = await classifier.ainvoke([
        SystemMessage(content=CLASSIFIER_SYSTEM),
        HumanMessage(content=str(email_dict)),
    ])

    # Build results, defaulting to uncategorized
    results: list[tuple[str, str]] = [("uncategorized", "pending")] * len(email_objs)

    if structured and structured.classifications:
        for item in structured.classifications:
            idx = item.email_no - 1  # 1-indexed → 0-indexed
            if 0 <= idx < len(email_objs):
                cat = item.category.strip().lower()
                if cat in SEED_CATEGORIES:
                    results[idx] = (cat, "ai-gemini")
                else:
                    results[idx] = ("uncategorized", "ai-gemini")

                logger.info(
                    f"[Gemini] Email {item.email_no}/{len(email_objs)} "
                    f"| {email_objs[idx].from_address or ''} "
                    f"| {(email_objs[idx].subject or '(no subject)')[:60]} "
                    f"→ {cat}"
                )
    else:
        logger.warning("[Gemini] No classifications in structured response")

    classified_count = sum(1 for cat, src in results if src == "ai-gemini")
    logger.info(f"Classification complete: {classified_count}/{len(email_objs)} classified")

    return results


async def classify_email(email_obj: Email) -> tuple[str, str]:
    """Classify a single email (convenience wrapper)."""
    results = await classify_emails_batch([email_obj])
    return results[0] if results else ("uncategorized", "fallback")

