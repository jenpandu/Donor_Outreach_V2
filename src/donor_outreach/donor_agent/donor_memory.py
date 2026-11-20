"""Thin wrapper around AgentCore Memory for the donor agent.
Errors are swallowed: memory must never block drafting or approving."""
import logging
import re
import unicodedata

import boto3
from bedrock_agentcore.memory import MemoryClient

from donor_outreach.config import get_settings

log = logging.getLogger(__name__)

settings = get_settings()
MEMORY_ID = settings.agentcore_memory_id

# Same profile/region as the other AWS clients, so local runs and AgentCore behave alike.
_session = boto3.Session(profile_name=settings.aws_profile,
                         region_name=settings.aws_region)
_client = (MemoryClient(region_name=settings.aws_region, boto3_session=_session)
           if MEMORY_ID else None)


def _slug(value) -> str:
    """'María López' -> 'maria-lopez'. Actor IDs only allow ASCII letters, digits and dashes."""
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def actor_id(donor) -> str | None:
    """Stable actor ID for a donor ID or (until messages has one) a donor name."""
    slug = _slug(donor)
    return f"donor-{slug}" if slug else None


def load_donor_memory(donor, query: str, top_k: int = 5) -> str:
    """Return remembered facts + preferences for this donor as prompt text."""
    actor = actor_id(donor)
    if not _client or not actor:
        return ""
    lines = []
    try:
        for ns in (f"/donors/{actor}/facts/", f"/donors/{actor}/preferences/"):
            records = _client.retrieve_memories(
                memory_id=MEMORY_ID, namespace=ns, query=query, top_k=top_k
            )
            for r in records:
                text = r.get("content", {}).get("text")
                if text:
                    lines.append(f"- {text}")
    except Exception as exc:
        log.warning("Memory read failed for %s: %s", actor, exc)
        return ""
    return "\n".join(lines)


def save_approved_exchange(donor, campaign_id, inbound_text: str, reply_text: str) -> None:
    """Record the donor's message and the reply staff actually approved."""
    actor = actor_id(donor)
    if not _client or not actor:
        return
    try:
        _client.create_event(
            memory_id=MEMORY_ID,
            actor_id=actor,
            session_id=f"campaign-{campaign_id}",
            messages=[(inbound_text, "USER"), (reply_text, "ASSISTANT")],
        )
    except Exception as exc:
        log.warning("Memory write failed for %s: %s", actor, exc)
