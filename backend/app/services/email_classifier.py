"""Multi-agent email classification with human-review feedback examples.

Pipeline:
1. Coarse router (super-group classification)
2. Specialist per routed group
3. Arbiter only for disputed/low-confidence/review cases
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.db import SessionLocal
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

COARSE_GROUPS = {
    "transactional",
    "marketing",
    "institutional",
    "personal",
    "needs_human_review",
}

SPECIALIST_CATEGORIES_BY_GROUP: dict[str, set[str]] = {
    "transactional": {"finance", "travel", "orders"},
    "marketing": {"promotions", "newsletters"},
    "institutional": {"work", "school", "notifications"},
    "personal": {"personal"},
}

FALLBACK_CATEGORY_BY_GROUP = {
    "transactional": "orders",
    "marketing": "promotions",
    "institutional": "notifications",
    "personal": "personal",
}

AI_SOURCE = "ai-gemini"
MODEL_EMAIL_BATCH_SIZE = 20
COARSE_CONFIDENCE_THRESHOLD = 0.70
SPECIALIST_CONFIDENCE_THRESHOLD = 0.70
COARSE_BODY_LIMIT = 6000
ARBITER_BODY_LIMIT = 6000
SPECIALIST_BODY_LIMIT = 10000

# Human-reviewed examples used as few-shot guidance.
MAX_PROMPT_EXAMPLES = 3
MAX_EXAMPLE_POOL = 30
EXAMPLE_BODY_LIMIT = 400


class CoarseEmailClassification(BaseModel):
    email_no: int = Field(description="Email number (1-indexed)")
    coarse_group: str = Field(
        description=(
            "One of: transactional, marketing, institutional, personal, "
            "needs_human_review"
        )
    )
    confidence: float = Field(description="Confidence score between 0 and 1")


class CoarseBatchClassificationResult(BaseModel):
    classifications: list[CoarseEmailClassification] = Field(
        description="One coarse routing decision per email_no"
    )


class SpecialistEmailClassification(BaseModel):
    email_no: int = Field(description="Email number (1-indexed)")
    category: str = Field(description="Specialist category proposal")
    review_decision: str = Field(
        default="",
        description=(
            "If coarse router seems wrong, suggest a different coarse group; "
            "else empty string"
        ),
    )
    confidence: float = Field(description="Confidence score between 0 and 1")


class SpecialistBatchClassificationResult(BaseModel):
    classifications: list[SpecialistEmailClassification] = Field(
        description="One specialist decision per email_no"
    )


class ArbiterEmailClassification(BaseModel):
    email_no: int = Field(description="Email number (1-indexed)")
    final_category: str = Field(
        description="One of the seed categories or uncategorized"
    )
    confidence: float = Field(description="Confidence score between 0 and 1")


class ArbiterBatchClassificationResult(BaseModel):
    decisions: list[ArbiterEmailClassification] = Field(
        description="Final category decision per email_no"
    )


@dataclass(slots=True)
class SpecialistDecision:
    category: str | None
    confidence: float
    review_decision: str


COARSE_ROUTER_SYSTEM = """\
You are the coarse routing agent for a personal inbox classifier.
For each email, output one coarse_group from:
- transactional
- marketing
- institutional
- personal
- needs_human_review

Use these rules:
- transactional: actual purchase/payment/order/travel transactions and receipts.
- marketing: promotions, sales, feature announcements, admissions pitches, bulk offers.
- institutional: school/work/system communications not primarily promotional.
- personal: direct personal conversations from real people.
- needs_human_review: ambiguous or very low-signal content.

Be conservative with confidence and return one classification per email_no.
"""

ARBITER_SYSTEM = f"""\
You are the final arbiter for inbox classification.
You will receive:
- emails to classify
- coarse router output
- specialist output
- recent human-reviewed examples

Choose exactly one final_category for each email_no from:
{SEED_CATEGORIES + ["uncategorized"]}

Rules:
- Use human-reviewed examples as guidance when relevant.
- Prefer specialist category when confidence is high and consistent.
- If coarse and specialist disagree, resolve using email content.
- If still uncertain, choose "uncategorized".
Return one decision per email_no.
"""


def _specialist_system_prompt(coarse_group: str) -> str:
    allowed = sorted(SPECIALIST_CATEGORIES_BY_GROUP[coarse_group])
    return f"""\
You are the specialist classifier for coarse_group="{coarse_group}".
You may receive recent human-reviewed examples in matching categories.

For each email, output:
- category: one of {allowed}
- confidence: between 0 and 1
- review_decision: empty string if coarse group is correct,
  otherwise one of {sorted(COARSE_GROUPS)}.

Only use the provided category options.
Return one classification per email_no.
"""


def _truncate(text: str | None, limit: int) -> str:
    return (text or "").strip()[:limit]


def _extract_body(email: Email, body_limit: int) -> str:
    body_html = _truncate(email.body_html, body_limit)
    if body_html:
        return body_html
    return _truncate(email.body_text, body_limit)


def _email_to_prompt_obj(email: Email, *, body_limit: int) -> dict[str, str]:
    return {
        "from_name": _truncate(email.from_name, 200),
        "from_address": _truncate(email.from_address, 320),
        "subject": _truncate(email.subject, 600),
        "snippet": _truncate(email.snippet, 700),
        "body": _extract_body(email, body_limit),
    }


def _normalize_coarse_group(value: str | None) -> str:
    raw = (value or "").strip().lower().replace("-", "_")
    aliases = {
        "transaction": "transactional",
        "institution": "institutional",
        "human_review": "needs_human_review",
        "needs_review": "needs_human_review",
        "review": "needs_human_review",
        "unknown": "needs_human_review",
    }
    normalized = aliases.get(raw, raw)
    if normalized in COARSE_GROUPS:
        return normalized
    return "needs_human_review"


def _normalize_category(value: str | None) -> str | None:
    cat = (value or "").strip().lower().replace("-", "_")
    return cat if cat in SEED_CATEGORIES else None


def _normalize_specialist_category(value: str | None, coarse_group: str) -> str | None:
    cat = _normalize_category(value)
    if not cat:
        return None
    allowed = SPECIALIST_CATEGORIES_BY_GROUP.get(coarse_group)
    if not allowed:
        return None
    return cat if cat in allowed else None


def _normalize_review_decision(value: str | None) -> str:
    review = _normalize_coarse_group(value)
    if review == "needs_human_review":
        raw = (value or "").strip().lower().replace("-", "_")
        if raw in {"", "none", "null", "n/a"}:
            return ""
    return review


def _clamp_confidence(value: float | int | None) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    if num < 0:
        return 0.0
    if num > 1:
        return 1.0
    return num


def _build_email_payload(
    email_objs: list[Email],
    *,
    body_limit: int,
) -> dict[int, dict[str, str]]:
    return {i: _email_to_prompt_obj(e, body_limit=body_limit) for i, e in enumerate(email_objs, 1)}


def _serialize_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _fetch_recent_human_examples(user_id: UUID) -> list[dict[str, str]]:
    """Fetch latest human-reviewed examples from needs_review cases."""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Email)
            .where(
                Email.user_id == user_id,
                Email.category_source == "user",
                Email.human_reviewed_at.is_not(None),
            )
            .order_by(Email.human_reviewed_at.desc())
            .limit(MAX_EXAMPLE_POOL)
        ).scalars().all()
    finally:
        db.close()

    examples: list[dict[str, str]] = []
    for email in rows:
        category = _normalize_category(email.category)
        if not category:
            continue
        body_preview = _extract_body(email, EXAMPLE_BODY_LIMIT)
        if not body_preview:
            body_preview = _truncate(email.snippet, EXAMPLE_BODY_LIMIT)
        examples.append(
            {
                "final_category": category,
                "from_address": _truncate(email.from_address, 180),
                "subject": _truncate(email.subject, 220),
                "body_preview": _truncate(body_preview, EXAMPLE_BODY_LIMIT),
                "reviewed_at": (
                    email.human_reviewed_at.isoformat() if email.human_reviewed_at else ""
                ),
            }
        )
    return examples


def _examples_for_specialist(
    recent_examples: list[dict[str, str]],
    *,
    coarse_group: str,
) -> list[dict[str, str]]:
    allowed = SPECIALIST_CATEGORIES_BY_GROUP.get(coarse_group, set())
    if not allowed:
        return []
    filtered = [e for e in recent_examples if e["final_category"] in allowed]
    return filtered[:MAX_PROMPT_EXAMPLES]


def _examples_for_arbiter(recent_examples: list[dict[str, str]]) -> list[dict[str, str]]:
    return recent_examples[:MAX_PROMPT_EXAMPLES]


def _build_arbiter_payload(
    arbiter_email_payload: dict[int, dict[str, str]],
    coarse_by_no: dict[int, CoarseEmailClassification],
    specialist_by_no: dict[int, SpecialistDecision],
    email_nos: list[int],
) -> dict[int, dict]:
    arbiter_payload: dict[int, dict] = {}
    for email_no in email_nos:
        coarse = coarse_by_no.get(email_no)
        specialist = specialist_by_no.get(email_no)
        arbiter_payload[email_no] = {
            "email": arbiter_email_payload[email_no],
            "coarse_group": coarse.coarse_group if coarse else "needs_human_review",
            "coarse_confidence": coarse.confidence if coarse else 0.0,
            "specialist_category": specialist.category if specialist else None,
            "specialist_confidence": specialist.confidence if specialist else 0.0,
            "specialist_review_decision": specialist.review_decision if specialist else "",
        }
    return arbiter_payload


def _get_model() -> ChatGoogleGenerativeAI:
    from app.core.config import settings

    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")

    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.google_api_key,
        temperature=0,
    )


async def _invoke_structured(
    model: ChatGoogleGenerativeAI,
    schema: type[BaseModel],
    system_prompt: str,
    payload: dict,
) -> BaseModel:
    runnable = model.with_structured_output(schema)
    return await runnable.ainvoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=_serialize_payload(payload)),
        ]
    )


async def _run_coarse_router(
    model: ChatGoogleGenerativeAI,
    coarse_payload: dict[int, dict[str, str]],
) -> dict[int, CoarseEmailClassification]:
    structured = await _invoke_structured(
        model,
        CoarseBatchClassificationResult,
        COARSE_ROUTER_SYSTEM,
        coarse_payload,
    )

    coarse_by_no: dict[int, CoarseEmailClassification] = {}
    if isinstance(structured, CoarseBatchClassificationResult):
        for item in structured.classifications:
            if 1 <= item.email_no <= len(coarse_payload):
                coarse_by_no[item.email_no] = CoarseEmailClassification(
                    email_no=item.email_no,
                    coarse_group=_normalize_coarse_group(item.coarse_group),
                    confidence=_clamp_confidence(item.confidence),
                )

    for email_no in coarse_payload:
        coarse_by_no.setdefault(
            email_no,
            CoarseEmailClassification(
                email_no=email_no,
                coarse_group="needs_human_review",
                confidence=0.0,
            ),
        )

    return coarse_by_no


async def _run_specialists(
    model: ChatGoogleGenerativeAI,
    specialist_email_payload: dict[int, dict[str, str]],
    coarse_by_no: dict[int, CoarseEmailClassification],
    recent_examples: list[dict[str, str]],
) -> dict[int, SpecialistDecision]:
    specialist_by_no: dict[int, SpecialistDecision] = {}

    emails_by_group: dict[str, list[int]] = {}
    for email_no, coarse in coarse_by_no.items():
        if coarse.coarse_group in SPECIALIST_CATEGORIES_BY_GROUP:
            emails_by_group.setdefault(coarse.coarse_group, []).append(email_no)

    for coarse_group, email_nos in emails_by_group.items():
        payload_subset = {n: specialist_email_payload[n] for n in email_nos}
        specialist_examples = _examples_for_specialist(
            recent_examples,
            coarse_group=coarse_group,
        )
        payload = {
            "emails": payload_subset,
            "human_labeled_examples": specialist_examples,
        }
        try:
            structured = await _invoke_structured(
                model,
                SpecialistBatchClassificationResult,
                _specialist_system_prompt(coarse_group),
                payload,
            )
        except Exception:
            logger.exception(
                "Specialist stage failed for group=%s; falling back to arbiter",
                coarse_group,
            )
            continue

        if not isinstance(structured, SpecialistBatchClassificationResult):
            continue

        for item in structured.classifications:
            if item.email_no not in payload_subset:
                continue
            specialist_by_no[item.email_no] = SpecialistDecision(
                category=_normalize_specialist_category(item.category, coarse_group),
                confidence=_clamp_confidence(item.confidence),
                review_decision=_normalize_review_decision(item.review_decision),
            )

    return specialist_by_no


async def _run_arbiter(
    model: ChatGoogleGenerativeAI,
    arbiter_payload: dict[int, dict],
    recent_examples: list[dict[str, str]],
) -> dict[int, ArbiterEmailClassification]:
    payload = {
        "emails": arbiter_payload,
        "human_labeled_examples": _examples_for_arbiter(recent_examples),
    }
    structured = await _invoke_structured(
        model,
        ArbiterBatchClassificationResult,
        ARBITER_SYSTEM,
        payload,
    )

    final_by_no: dict[int, ArbiterEmailClassification] = {}
    if isinstance(structured, ArbiterBatchClassificationResult):
        for item in structured.decisions:
            if item.email_no in arbiter_payload:
                normalized = _normalize_category(item.final_category)
                final_by_no[item.email_no] = ArbiterEmailClassification(
                    email_no=item.email_no,
                    final_category=normalized or "uncategorized",
                    confidence=_clamp_confidence(item.confidence),
                )
    return final_by_no


async def _classify_batch_multiagent(
    model: ChatGoogleGenerativeAI,
    email_objs: list[Email],
    *,
    global_offset: int,
) -> list[tuple[str, str, bool]]:
    coarse_payload = _build_email_payload(email_objs, body_limit=COARSE_BODY_LIMIT)
    specialist_payload = _build_email_payload(email_objs, body_limit=SPECIALIST_BODY_LIMIT)
    arbiter_email_payload = _build_email_payload(email_objs, body_limit=ARBITER_BODY_LIMIT)

    user_id = email_objs[0].user_id if email_objs and email_objs[0].user_id else None
    recent_examples = _fetch_recent_human_examples(user_id) if user_id else []

    coarse_by_no = await _run_coarse_router(model, coarse_payload)
    specialist_by_no = await _run_specialists(
        model,
        specialist_payload,
        coarse_by_no,
        recent_examples,
    )

    results: list[tuple[str, str, bool]] = [("uncategorized", AI_SOURCE, True)] * len(email_objs)
    needs_arbiter: list[int] = []

    for email_no in coarse_payload:
        coarse = coarse_by_no[email_no]
        specialist = specialist_by_no.get(email_no)
        specialist_category = specialist.category if specialist else None
        specialist_confidence = specialist.confidence if specialist else 0.0
        review_decision = specialist.review_decision if specialist else ""

        if not specialist_category and coarse.coarse_group in FALLBACK_CATEGORY_BY_GROUP:
            specialist_category = FALLBACK_CATEGORY_BY_GROUP[coarse.coarse_group]

        disputed = bool(review_decision and review_decision != coarse.coarse_group)
        low_confidence = (
            coarse.confidence < COARSE_CONFIDENCE_THRESHOLD
            or specialist_confidence < SPECIALIST_CONFIDENCE_THRESHOLD
        )
        unresolved = (
            coarse.coarse_group == "needs_human_review"
            or disputed
            or low_confidence
            or specialist_category not in SEED_CATEGORIES
        )

        if unresolved:
            needs_arbiter.append(email_no)
            continue

        results[email_no - 1] = (specialist_category, AI_SOURCE, False)

    if needs_arbiter:
        arbiter_payload = _build_arbiter_payload(
            arbiter_email_payload,
            coarse_by_no,
            specialist_by_no,
            needs_arbiter,
        )
        try:
            final_by_no = await _run_arbiter(model, arbiter_payload, recent_examples)
        except Exception:
            logger.exception("Arbiter stage failed; using deterministic fallback")
            final_by_no = {}

        for email_no in needs_arbiter:
            arbiter_item = final_by_no.get(email_no)
            if arbiter_item and arbiter_item.final_category in SEED_CATEGORIES:
                final_category = arbiter_item.final_category
            else:
                coarse_group = coarse_by_no[email_no].coarse_group
                final_category = FALLBACK_CATEGORY_BY_GROUP.get(
                    coarse_group,
                    "uncategorized",
                )
            results[email_no - 1] = (final_category, AI_SOURCE, True)

    for i, (category, _, needs_review) in enumerate(results, 1):
        email_obj = email_objs[i - 1]
        logger.info(
            "[Gemini Multiagent] Email %s/%s (global %s) | %s | %s -> %s | needs_review=%s",
            i,
            len(email_objs),
            global_offset + i,
            email_obj.from_address or "",
            (email_obj.subject or "(no subject)")[:80],
            category,
            needs_review,
        )

    return results


async def classify_emails_batch(email_objs: list[Email]) -> list[tuple[str, str, bool]]:
    """Classify emails via multi-agent Gemini pipeline.

    Returns list[(category, source, needs_review)] in the input order.
    """
    if not email_objs:
        return []

    model = _get_model()
    logger.info(
        "Classifying %s emails via Gemini multi-agent pipeline",
        len(email_objs),
    )

    all_results: list[tuple[str, str, bool]] = []
    for offset in range(0, len(email_objs), MODEL_EMAIL_BATCH_SIZE):
        batch = email_objs[offset : offset + MODEL_EMAIL_BATCH_SIZE]
        batch_results = await _classify_batch_multiagent(
            model,
            batch,
            global_offset=offset,
        )
        all_results.extend(batch_results)

    classified_count = sum(1 for _, source, _ in all_results if source == AI_SOURCE)
    logger.info(
        "Gemini multi-agent classification complete: %s/%s classified",
        classified_count,
        len(email_objs),
    )
    return all_results


async def classify_email(email_obj: Email) -> tuple[str, str, bool]:
    """Classify a single email using the batch pipeline."""
    results = await classify_emails_batch([email_obj])
    return results[0] if results else ("uncategorized", "fallback", True)
