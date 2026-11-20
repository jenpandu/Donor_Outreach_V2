"""Calls the donor triage agent deployed on AgentCore Runtime.

Returns None on any failure so the caller can fall back to the v1
translate-only path; the agent must never block saving a message.
"""
import json
import uuid
from dataclasses import dataclass

import structlog
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from donor_outreach.clients.aws import get_session
from donor_outreach.config import get_settings

logger = structlog.get_logger()


@dataclass
class TriageResult:
    detected_lang: str | None
    translation: str | None
    intent: str | None
    sentiment: str | None
    draft_reply: str | None


class AgentClient:

    def __init__(self, boto_client=None, runtime_arn: str | None = None,
                 enabled: bool | None = None):
        settings = get_settings()
        self.enabled = settings.agent_enabled if enabled is None else enabled
        self.runtime_arn = runtime_arn if runtime_arn is not None else settings.agent_runtime_arn
        self._client = boto_client
        if self._client is None and self.is_configured:
            # The graph makes several LLM/AWS calls, so allow longer than boto's default read.
            self._client = get_session().client(
                "bedrock-agentcore",
                config=Config(read_timeout=settings.agent_timeout_s, retries={"max_attempts": 1}),
            )

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.runtime_arn and self.runtime_arn.startswith("arn:"))

    def triage(self, text: str, campaign_def_lang: str, donor_name: str) -> TriageResult | None:
        if not self.is_configured:
            return None
        try:
            resp = self._client.invoke_agent_runtime(
                agentRuntimeArn=self.runtime_arn,
                runtimeSessionId=str(uuid.uuid4()),   # must be >= 33 chars; a UUID is 36
                payload=json.dumps({
                    "text": text,
                    "campaign_def_lang": campaign_def_lang,
                    "donor_name": donor_name,
                }).encode(),
            )
            body = json.loads(resp["response"].read())
        except (BotoCoreError, ClientError, ValueError, KeyError) as exc:
            logger.warning("agent_invoke_failed", error=str(exc))
            return None

        if not isinstance(body, dict) or body.get("error"):
            logger.warning("agent_returned_error", error=(body or {}).get("error") if isinstance(body, dict) else body)
            return None

        logger.info("agent_invoked", intent=body.get("intent"), detected_lang=body.get("detected_lang"))
        return TriageResult(
            detected_lang=body.get("detected_lang"),
            translation=body.get("translation"),
            intent=body.get("intent"),
            sentiment=body.get("sentiment"),
            draft_reply=body.get("draft_reply"),
        )
