from donor_outreach.schemas.message import (
    ApproveResult, MessageApprove, MessageRead, OutboundMessageCreate,
    InboundMessageCreate, MessageUpdate,
)
from donor_outreach.db_models import Message, Campaign, MessageDirection
from donor_outreach.db_models.message import (
    STATUS_APPROVED, STATUS_PENDING_REVIEW, STATUS_REJECTED,
)
from sqlalchemy import select
from donor_outreach.extensions import db
from donor_outreach.clients.translate import TranslateClient
from donor_outreach.clients.comprehend import ComprehendClient
from donor_outreach.clients.memory import MemoryClient
from donor_outreach.clients.agent import AgentClient
from botocore.exceptions import ClientError
from donor_outreach.errors import ConflictError, NotFoundError, ValidationFailedError
from sqlalchemy import or_


def list_messages(
    campaign_id: int,
    direction: str | None = None,
    language: str | None = None,
    sort: str = "asc",
) -> list[MessageRead]:
    stmt = select(Message).where(Message.campaign_id == campaign_id)

    if direction is not None:
        stmt = stmt.where(Message.direction == direction)

    if language is not None:
        stmt = stmt.where(
            or_(Message.original_language == language, Message.target_language == language)
        )

    if sort == "desc":
        stmt = stmt.order_by(Message.created_at.desc())
    else:
        stmt = stmt.order_by(Message.created_at.asc())

    rows = db.session.execute(stmt)
    return [MessageRead.model_validate(row[0]) for row in rows]

def find_message_by_id(message_id: int) -> MessageRead:
    row = db.session.get(Message, message_id)
    if row is None:
        raise NotFoundError(f"Message {message_id} not found")
    return MessageRead.model_validate(row)


CONFIDENCE_THRESHOLD = 0.5


def create_outbound_message(campaign_id: int, message: dict) -> MessageRead | None:
    campaign = db.session.get(Campaign, campaign_id)
    if campaign is None:
        return None

    valid_message = OutboundMessageCreate.model_validate(message)

    if valid_message.target_language == campaign.def_lang:
        translated_text = valid_message.original_text
    else:
        translator = TranslateClient()
        try:
            translated_text = translator.translate_text(
                text=valid_message.original_text,
                src_lang=campaign.def_lang,
                trg_lang=valid_message.target_language,
            )
        except ClientError:
            translated_text = None

    new_message = Message(
        campaign_id=campaign_id,
        direction=MessageDirection.OUTBOUND,
        donor_name=valid_message.donor_name,
        original_text=valid_message.original_text,
        original_language=campaign.def_lang,
        translated_text=translated_text,
        target_language=valid_message.target_language,
    )
    db.session.add(new_message)
    db.session.commit()
    return MessageRead.model_validate(new_message)


def create_inbound_message(campaign_id: int, message: dict) -> MessageRead | None:
    campaign = db.session.get(Campaign, campaign_id)
    if campaign is None:
        return None

    valid_message = InboundMessageCreate.model_validate(message)
    text, def_lang = valid_message.original_text, campaign.def_lang

    # v2: the AgentCore triage agent detects, translates, classifies and drafts.
    result = AgentClient().triage(text, def_lang, valid_message.donor_name)

    if result is not None:
        detected_language = result.detected_lang or def_lang
        # Agent returns translation=None when no translation was needed; v1 stores the text itself.
        translated_text = text if detected_language == def_lang else result.translation
        intent, sentiment, draft = result.intent, result.sentiment, result.draft_reply
    else:
        # Agent off or failed: v1 translate-only path. The message still saves.
        detected_language, translated_text = _detect_and_translate_v1(text, def_lang)
        intent = sentiment = draft = None

    new_message = Message(
        campaign_id=campaign_id,
        direction=MessageDirection.INBOUND,
        donor_name=valid_message.donor_name,
        original_text=text,
        original_language=detected_language,
        translated_text=translated_text,
        target_language=def_lang,
        intent=intent,
        sentiment=sentiment,
        draft_reply=draft,
        status=STATUS_PENDING_REVIEW,
    )
    db.session.add(new_message)
    db.session.commit()
    return MessageRead.model_validate(new_message)


def _detect_and_translate_v1(text: str, def_lang: str) -> tuple[str, str | None]:
    """v1 inbound path: Comprehend detection + Translate into the campaign language."""
    comprehend = ComprehendClient()
    try:
        detected_language, confidence = comprehend.detect_language(text)
        if confidence < CONFIDENCE_THRESHOLD:
            detected_language = def_lang
    except ClientError:
        detected_language = def_lang

    if detected_language == def_lang:
        return detected_language, text

    translator = TranslateClient()
    try:
        return detected_language, translator.translate_text(
            text=text, src_lang=detected_language, trg_lang=def_lang
        )
    except ClientError:
        return detected_language, None

def update_message(message_id: int, message: dict) -> MessageRead:
    valid_update = MessageUpdate.model_validate(message)

    record = db.session.get(Message, message_id)
    if record is None:
        raise NotFoundError(f"Message {message_id} not found")

    updates = valid_update.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(record, field, value)

    # Re-trigger translation since original_text changed.
    if "original_text" in updates:
        campaign = record.campaign
        if record.direction == MessageDirection.OUTBOUND:
            source_lang, target_lang = campaign.def_lang, record.target_language
        else:
            comprehend = ComprehendClient()
            try:
                detected_language, confidence = comprehend.detect_language(record.original_text)
                if confidence < CONFIDENCE_THRESHOLD:
                    detected_language = campaign.def_lang
            except ClientError:
                detected_language = campaign.def_lang
            record.original_language = detected_language
            source_lang, target_lang = detected_language, campaign.def_lang

        if source_lang == target_lang:
            record.translated_text = record.original_text
        else:
            translator = TranslateClient()
            try:
                record.translated_text = translator.translate_text(
                    text=record.original_text, src_lang=source_lang, trg_lang=target_lang
                )
            except ClientError:
                record.translated_text = None

    db.session.commit()
    return MessageRead.model_validate(record)

def approve_message(message_id: int, body: dict) -> ApproveResult:
    """Staff approve (optionally edit) the reply to an inbound message.

    Saves the reply as an outbound message, marks the inbound one approved,
    then writes the exchange to AgentCore Memory. Memory is written only here,
    so rejected or unreviewed drafts never become "facts" about a donor.
    """
    valid = MessageApprove.model_validate(body)

    inbound = db.session.get(Message, message_id)
    if inbound is None:
        raise NotFoundError(f"Message {message_id} not found")
    if inbound.direction != MessageDirection.INBOUND:
        raise ValidationFailedError("Only inbound messages can be approved")
    if inbound.status == STATUS_APPROVED:
        raise ConflictError(f"Message {message_id} is already approved")

    reply_text = valid.reply_text or inbound.draft_reply
    if not reply_text:
        raise ValidationFailedError("This message has no draft; send reply_text to approve it")

    # The reply is written in the donor's language, so no translation is needed.
    reply = Message(
        campaign_id=inbound.campaign_id,
        direction=MessageDirection.OUTBOUND,
        donor_name=inbound.donor_name,
        original_text=reply_text,
        original_language=inbound.original_language,
        translated_text=reply_text,
        target_language=inbound.original_language,
    )
    inbound.status = STATUS_APPROVED
    db.session.add(reply)
    db.session.commit()

    # After the commit: a Memory failure must never undo the approval.
    memory_saved = MemoryClient().save_exchange(
        donor=inbound.donor_name,
        campaign_id=inbound.campaign_id,
        inbound_text=inbound.original_text,
        reply_text=reply_text,
    )

    return ApproveResult(
        inbound=MessageRead.model_validate(inbound),
        reply=MessageRead.model_validate(reply),
        memory_saved=memory_saved,
    )


def reject_message(message_id: int) -> MessageRead:
    """Staff discard the agent's draft. Nothing is sent and nothing reaches Memory,
    so a bad draft never becomes a "fact" about the donor."""
    inbound = db.session.get(Message, message_id)
    if inbound is None:
        raise NotFoundError(f"Message {message_id} not found")
    if inbound.direction != MessageDirection.INBOUND:
        raise ValidationFailedError("Only inbound messages can be rejected")
    if inbound.status in (STATUS_APPROVED, STATUS_REJECTED):
        raise ConflictError(f"Message {message_id} is already {inbound.status}")

    inbound.status = STATUS_REJECTED
    db.session.commit()
    return MessageRead.model_validate(inbound)


def get_review_queue(campaign_id: int) -> list[MessageRead]:
    """Inbound messages waiting for staff review, oldest first."""
    if db.session.get(Campaign, campaign_id) is None:
        raise NotFoundError(f"Campaign {campaign_id} not found")

    stmt = (
        select(Message)
        .where(
            Message.campaign_id == campaign_id,
            Message.direction == MessageDirection.INBOUND,
            Message.status == STATUS_PENDING_REVIEW,
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return [MessageRead.model_validate(m) for m in db.session.scalars(stmt)]


def delete_message(message_id: int) -> None:
    record = db.session.get(Message, message_id)
    if record is None:
        raise NotFoundError(f"Message {message_id} not found")

    db.session.delete(record)
    db.session.commit()


def get_inbox(campaign_id: int) -> list[MessageRead] | None:
    """Return all inbound messages for a campaign, translated at creation
    time. Returns None if the campaign itself doesn't exist.
    """
    campaign = db.session.get(Campaign, campaign_id)
    if campaign is None:
        return None

    stmt = (
        select(Message)
        .where(Message.campaign_id == campaign_id, Message.direction == MessageDirection.INBOUND)
        .order_by(Message.created_at.desc())
    )
    rows = db.session.execute(stmt)
    return [MessageRead.model_validate(row[0]) for row in rows]