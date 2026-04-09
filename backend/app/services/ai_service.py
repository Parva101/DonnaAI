"""AI productivity service: smart replies, priority scoring, action extraction, semantic search."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActionItem, Email


class AIService:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def generate_reply_suggestions(
        self,
        *,
        context: str,
        tone: str | None,
        platform: str,
    ) -> list[str]:
        context_clean = (context or "").strip()
        if not context_clean:
            return [
                "Thanks for the update. I will review and get back to you soon.",
                "Got it. I will take a look and reply shortly.",
                "Received. I will follow up with details shortly.",
            ]

        model_suggestions = await self._llm_reply_suggestions(
            context=context_clean,
            tone=tone,
            platform=platform,
        )
        if model_suggestions:
            return model_suggestions[:3]

        # Deterministic fallback.
        prefix = "Thanks" if platform in {"gmail", "email"} else "Got it"
        tone_suffix = f" ({tone})" if tone else ""
        return [
            f"{prefix} for the message{tone_suffix}. I will handle this and follow up soon.",
            f"Acknowledged{tone_suffix}. I am on it and will share an update shortly.",
            f"Understood{tone_suffix}. Let me check and come back with details.",
        ]

    async def _llm_reply_suggestions(
        self,
        *,
        context: str,
        tone: str | None,
        platform: str,
    ) -> list[str]:
        from app.core.config import settings

        if not settings.google_api_key:
            return []

        try:
            from google import genai
            from google.genai import types as genai_types

            client = genai.Client(vertexai=True, api_key=settings.google_api_key)
            prompt = {
                "platform": platform,
                "tone": tone or "neutral",
                "context": context[:4000],
                "instructions": "Return exactly 3 concise reply suggestions as JSON array of strings.",
            }
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=json.dumps(prompt, separators=(",", ":")),
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )
            text = (response.text or "").strip()
            await client.aio.aclose()
            if not text:
                return []
            data = json.loads(text)
            if isinstance(data, list):
                items = [str(x).strip() for x in data if str(x).strip()]
                return items[:3]
            return []
        except Exception:
            return []

    def score_emails(self, *, user_id: UUID, email_ids: list[UUID]) -> list[tuple[UUID, float, str]]:
        if not email_ids:
            return []

        stmt = select(Email).where(Email.user_id == user_id, Email.id.in_(email_ids))
        emails = list(self.db.execute(stmt).scalars())
        results: list[tuple[UUID, float, str]] = []

        for email in emails:
            score = self._heuristic_priority_score(email)
            label = "high" if score >= 0.75 else "medium" if score >= 0.4 else "low"
            email.priority_score = score
            email.priority_label = label
            self.db.add(email)
            results.append((email.id, score, label))

        self.db.commit()
        return results

    def _heuristic_priority_score(self, email: Email) -> float:
        score = 0.1

        subject = (email.subject or "").lower()
        snippet = (email.snippet or "").lower()
        text = f"{subject} {snippet}"

        if not email.is_read:
            score += 0.25
        if email.needs_review:
            score += 0.25
        if email.category in {"work", "finance", "orders", "travel"}:
            score += 0.2

        urgent_keywords = ["urgent", "asap", "today", "deadline", "payment due", "action required"]
        if any(k in text for k in urgent_keywords):
            score += 0.35

        reminder_keywords = ["reminder", "follow up", "following up", "pending"]
        if any(k in text for k in reminder_keywords):
            score += 0.15

        if email.has_attachments:
            score += 0.05

        if score > 1.0:
            score = 1.0
        return round(score, 3)

    def extract_action_items(
        self,
        *,
        user_id: UUID,
        source_platform: str,
        source_ref: str | None,
        text: str,
    ) -> list[ActionItem]:
        items = self._extract_action_lines(text)
        created: list[ActionItem] = []

        for item_text in items:
            priority = "medium"
            score = 60
            low = item_text.lower()
            if any(k in low for k in ("urgent", "asap", "today", "immediately")):
                priority = "high"
                score = 90
            elif any(k in low for k in ("later", "optional", "sometime")):
                priority = "low"
                score = 35

            action = ActionItem(
                user_id=user_id,
                source_platform=source_platform,
                source_ref=source_ref,
                title=item_text[:255],
                details=item_text,
                status="open",
                priority=priority,
                score=score,
            )
            self.db.add(action)
            created.append(action)

        self.db.commit()
        for item in created:
            self.db.refresh(item)
        return created

    def _extract_action_lines(self, text: str) -> list[str]:
        raw = (text or "").strip()
        if not raw:
            return []

        lines = [l.strip(" -\t") for l in raw.splitlines() if l.strip()]
        candidates: list[str] = []

        bullet_like = [
            l for l in lines if re.match(r"^(todo|task|action|follow up|follow-up|please|need to)\b", l, re.I)
        ]
        candidates.extend(bullet_like)

        sentence_chunks = re.split(r"(?<=[.!?])\s+", raw)
        for sentence in sentence_chunks:
            s = sentence.strip()
            if not s:
                continue
            if re.search(r"\b(please|need to|remember to|follow up|send|review|schedule|book|call)\b", s, re.I):
                candidates.append(s)

        deduped: list[str] = []
        seen = set()
        for candidate in candidates:
            normalized = re.sub(r"\s+", " ", candidate.strip()).lower()
            if len(normalized) < 8 or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(candidate.strip())

        return deduped[:10]

    def list_action_items(self, *, user_id: UUID, status: str | None = None) -> list[ActionItem]:
        stmt = select(ActionItem).where(ActionItem.user_id == user_id)
        if status:
            stmt = stmt.where(ActionItem.status == status)
        stmt = stmt.order_by(ActionItem.created_at.desc())
        return list(self.db.execute(stmt).scalars())

    def update_action_item(
        self,
        *,
        user_id: UUID,
        action_item_id: UUID,
        status: str | None,
        priority: str | None,
        due_at: datetime | None,
    ) -> ActionItem | None:
        item = self.db.get(ActionItem, action_item_id)
        if not item or item.user_id != user_id:
            return None

        if status is not None:
            item.status = status
            if status == "done":
                item.completed_at = datetime.now(timezone.utc)
        if priority is not None:
            item.priority = priority
        if due_at is not None:
            item.due_at = due_at

        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def semantic_search(self, *, user_id: UUID, query: str, limit: int) -> list[tuple[Email, float]]:
        tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", query.lower()) if len(t) > 1]
        if not tokens:
            return []

        stmt = select(Email).where(Email.user_id == user_id).order_by(Email.received_at.desc()).limit(2000)
        rows = list(self.db.execute(stmt).scalars())

        scored: list[tuple[Email, float]] = []
        for email in rows:
            hay = " ".join(
                [
                    (email.subject or "").lower(),
                    (email.snippet or "").lower(),
                    (email.from_address or "").lower(),
                    (email.body_text or "")[:1000].lower(),
                ]
            )
            if not hay:
                continue

            hits = 0
            for token in tokens:
                if token in hay:
                    hits += 1

            if hits == 0:
                continue

            score = hits / max(len(tokens), 1)
            score += float(email.priority_score or 0.0) * 0.2
            if email.needs_review:
                score += 0.05
            scored.append((email, round(min(score, 1.0), 3)))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]
