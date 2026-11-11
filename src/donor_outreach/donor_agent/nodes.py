import os
import logging
from donor_outreach.config import get_settings 
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage, HumanMessage
from state import AgentState
from prompt import (
    PROMPT,
    SYSTEM_PROMPT,
    LANGUAGE_NAMES,
    INTENT_GUIDANCE,
    Classification,
)

log = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.5

settings = get_settings()

_session = boto3.Session(profile_name=settings.aws_profile,
                         region_name=settings.aws_region)
_kb = _session.client("bedrock-agent-runtime")

MODEL_ID = settings.bedrock_model_id
KB_ID = settings.kb_id
translate = _session.client("translate")
comprehend = _session.client("comprehend")

classifier = ChatBedrockConverse(
    model=MODEL_ID, temperature=0,
    region_name=settings.aws_region,
    credentials_profile_name=settings.aws_profile,
).with_structured_output(Classification)

drafter = ChatBedrockConverse(
    model=MODEL_ID, temperature=0.3, max_tokens=400,
    region_name=settings.aws_region,
    credentials_profile_name=settings.aws_profile,
)

def detect_language(state: AgentState) -> dict:
    text = (state.get("text") or "").strip()
    default = state["campaign_def_lang"]

    if not text:
        return {"detected_lang": default, "confidence": None,
                "lang_source": "fallback_empty"}

    try:
        resp = comprehend.detect_dominant_language(Text=text)
        top = max(resp["Languages"], key=lambda l: l["Score"])
    except (BotoCoreError, ClientError, KeyError, ValueError) as e:
        log.warning("detect_language failed: %s", e)
        return {"detected_lang": default, "confidence": None,
                "lang_source": "fallback_error"}

    if top["Score"] < MIN_CONFIDENCE:
        return {"detected_lang": default, "confidence": top["Score"],
                "lang_source": "fallback_low_conf"}

    return {"detected_lang": top["LanguageCode"], "confidence": top["Score"],
            "lang_source": "comprehend"}


def translate_message(state: AgentState) -> dict:
    if state["detected_lang"] == state["campaign_def_lang"]:
        return {"translation": None}

    try:
        resp = translate.translate_text(
            Text=state["text"],
            SourceLanguageCode=state["detected_lang"],
            TargetLanguageCode=state["campaign_def_lang"],
        )
        return {"translation": resp["TranslatedText"]}
    except (BotoCoreError, ClientError) as e:
        log.warning("translate failed: %s", e)
        return {"translation": None}


def classify_message(state: AgentState) -> dict:
    """Reads the donor's message and labels its intent and sentiment."""
    text = state.get("translation") or state["text"]
    try:
        result = classifier.invoke(PROMPT.format(text=text))
        return {"intent": result.intent, "sentiment": result.sentiment}
    except Exception:
        # Safe default: still gets KB context and a careful draft for staff to review.
        log.exception("classify failed")
        return {"intent": "question", "sentiment": "neutral"}


def retrieve_kb(state: AgentState) -> dict:
    # KB docs are English, so query with the translation when there is one
    query = state.get("translation") or state["text"]
    try:
        resp = _kb.retrieve(
            knowledgeBaseId=KB_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "managedSearchConfiguration": {"numberOfResults": settings.kb_num_results}
            },
        )
        chunks = [
            r["content"]["text"]
            for r in resp["retrievalResults"]
            if r.get("score", 0) >= settings.kb_min_score
        ]
        return {"kb_context": "\n\n---\n\n".join(chunks)}
    except Exception:
        log.exception("KB retrieve failed")
        return {"kb_context": ""}  

def draft_reply(state: AgentState) -> dict:
    lang_code = state.get("detected_lang") or state.get("campaign_def_lang") or "en"
    language = LANGUAGE_NAMES.get(lang_code, lang_code)

    intent = state.get("intent") or "question"
    guidance = INTENT_GUIDANCE.get(intent, INTENT_GUIDANCE["question"])

    # Give the model the original message, plus the translation if there is one.
    message_block = f"Donor message (original):\n{state['text']}"
    if state.get("translation"):
        message_block += f"\n\nTranslation:\n{state['translation']}"

    user_prompt = f"""Donor name: {state.get('donor_name') or 'unknown'}
    Intent: {intent}
    Sentiment: {state.get('sentiment') or 'neutral'}

    {message_block}

    Org policy:
    {state.get('kb_context') or '(none)'}

    Prior conversation with this donor:
    {state.get('donor_history') or '(none)'}

    Task: {guidance}"""

    try:
        response = drafter.invoke([
            SystemMessage(content=SYSTEM_PROMPT.format(language=language)),
            HumanMessage(content=user_prompt),
        ])
        return {"draft_reply": response.content.strip()}
    except Exception:
        # Never block saving the message. Staff will see no draft and write one.
        log.exception("draft_reply failed")
        return {"draft_reply": None}


if __name__ == "__main__":
    sample = {
        "campaign_def_lang": "en",
        "donor_name": "María López",
        "text": "¿Cuándo recibiré mi recibo de impuestos?",
        "detected_lang": "es",
        "translation": "When will I receive my tax receipt?",
        "intent": "question",
        "sentiment": "neutral",
        "kb_context": "Tax receipts are emailed by January 31 for the prior year's gifts.",
    }
    print(draft_reply(sample)["draft_reply"])

    