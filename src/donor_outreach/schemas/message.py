from pydantic import BaseModel, ValidationError, Field
from typing import Literal
from datetime import datetime

class OutboundMessageCreate(BaseModel):
    donor_name: str = Field(min_length=2, max_length=100)
    original_text: str = Field(min_length=1)
    target_language: str = Field(min_length=2, max_length=10)

class InboundMessageCreate(BaseModel):
    donor_name: str = Field(min_length=1, max_length=100)
    original_text: str = Field(min_length=1)

class MessageUpdate(BaseModel):
    """Correcting a message's original text after logging."""

    original_text: str = Field(min_length=1)


class MessageApprove(BaseModel):
    """Staff approval. Omit reply_text to send the agent's draft as-is."""

    reply_text: str | None = Field(default=None, min_length=1)


class MessageRead(BaseModel):
    """Shape returned to the client when reading a message."""

    id: int
    campaign_id: int
    direction: Literal["outbound", "inbound"]
    donor_name: str
    original_text: str
    original_language: str
    translated_text: str | None
    target_language: str
    intent: str | None = None
    sentiment: str | None = None
    draft_reply: str | None = None
    status: Literal["pending_review", "approved", "rejected"] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApproveResult(BaseModel):
    """Response for POST /messages/<id>/approve."""

    inbound: MessageRead
    reply: MessageRead
    memory_saved: bool