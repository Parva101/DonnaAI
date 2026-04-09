from datetime import datetime

from pydantic import BaseModel


class MessageSearchResult(BaseModel):
    id: str
    tenant_id: str
    platform: str
    account_id: str
    thread_key: str
    chat_key: str
    source_message_id: str
    sender_key: str | None
    body_text: str | None
    sent_at: datetime

    model_config = {"from_attributes": True}

