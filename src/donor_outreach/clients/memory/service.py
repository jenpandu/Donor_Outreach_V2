"""Writes approved donor exchanges to AgentCore Memory.

Flask only writes; the agent (DonorAgentCore) reads. AgentCore turns these events
into long-term facts/preferences in the background (~1 minute).
"""
import re
import unicodedata
from datetime import datetime, timezone

import structlog
from botocore.exceptions import BotoCoreError, ClientError

from donor_outreach.clients.aws import get_client
from donor_outreach.config import get_settings

logger = structlog.get_logger()


def actor_id(donor) -> str | None:
    """'María López' -> 'donor-maria-lopez', '42' -> 'donor-42'.

    Must match actor_id() in the agent's donor_memory.py, or the agent will
    read from a different actor than Flask writes to (a test checks this).
    """
    text = unicodedata.normalize("NFKD", str(donor or "")).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return f"donor-{slug}" if slug else None


class MemoryClient:

    def __init__(self, boto_client=None, memory_id: str | None = None):
        self.memory_id = memory_id if memory_id is not None else get_settings().agentcore_memory_id
        self._client = boto_client
        if self._client is None and self.memory_id:
            self._client = get_client("bedrock-agentcore")

    def save_exchange(self, donor, campaign_id: int, inbound_text: str, reply_text: str) -> bool:
        """Record the donor's message and the approved reply. Returns True if saved.
        Never raises: a Memory failure must not undo an approval."""
        actor = actor_id(donor)
        if not self.memory_id or not actor:
            return False
        try:
            self._client.create_event(
                memoryId=self.memory_id,
                actorId=actor,
                sessionId=f"campaign-{campaign_id}",
                eventTimestamp=datetime.now(timezone.utc),
                payload=[
                    {"conversational": {"content": {"text": inbound_text}, "role": "USER"}},
                    {"conversational": {"content": {"text": reply_text}, "role": "ASSISTANT"}},
                ],
            )
            return True
        except (BotoCoreError, ClientError) as exc:
            logger.warning("memory_write_failed", actor_id=actor, error=str(exc))
            return False
