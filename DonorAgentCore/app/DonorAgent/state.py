from typing import TypedDict

class AgentState(TypedDict, total=False):
    donor_id: str | None
    campaign_def_lang: str
    donor_name: str
    text: str
    detected_lang: str
    confidence: float
    translation: str | None
    intent: str
    sentiment: str
    kb_context: str
    donor_memory: str
    draft_reply: str
    lang_source: str | None