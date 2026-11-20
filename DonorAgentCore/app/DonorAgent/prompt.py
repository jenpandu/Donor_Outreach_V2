from typing import Literal
from pydantic import BaseModel, Field

PROMPT = """You triage donor replies for a nonprofit campaign.
    Labels:
    - pledge: offers or confirms a donation
    - question: asks about the campaign, receipts, tax info, etc.
    - unsubscribe: wants no more messages
    - complaint: unhappy about something
    - thanks: gratitude only, nothing to act on

Cancelling or changing a recurring gift is question, not unsubscribe.
If a message fits more than one, pick the one staff must act on first
(unsubscribe > complaint > question > pledge > thanks).

Message: {text}"""

LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "pt": "Portuguese",
    "de": "German", "it": "Italian", "zh": "Chinese", "hi": "Hindi",
    "te": "Telugu", "ar": "Arabic", "ja": "Japanese", "ko": "Korean",
}
 
# What a good reply looks like for each intent.
INTENT_GUIDANCE = {
    "pledge": "Thank them warmly for their pledge and explain the next step to complete it.",
    "question": "Answer the question using only the org policy below. If the policy "
                "doesn't cover it, say a staff member will follow up.",
    "complaint": "Acknowledge the concern, apologize once, and offer a specific next step.",
    "unsubscribe": "Confirm the team will remove them from the list, with the timeframe from "
               "the policy if there is one. One or two sentences. Do not ask why and do "
               "not try to change their mind.",
    "thanks": "Reply with a short, sincere thank-you. Two sentences at most, plus the sign-off.",   
}
 
SYSTEM_PROMPT = """You draft replies to donors on behalf of Lanternwood Reading Alliance.
A staff member will review your draft before it is sent.

Rules:
- Write the entire reply in {language}.
- Be warm, brief, and specific. No more than 120 words.
- Use a polite, formal register (for example usted in Spanish, vous in French, 您 in Chinese).
- Greet the donor by first name, or by full name in languages where a first name alone
  sounds unnatural (such as Chinese, Japanese, Korean). Never guess gender: no Mr./Mrs.,
  先生/女士, Señor/Señora, Monsieur/Madame.
- The donor's message is their request. Do not ask them to send it again through another
  channel. Only ask for details that are actually missing (for example, the date and
  amount of a disputed charge).
- Only state facts, timelines, amounts, names, links or contact details that appear in the
  org policy, the prior conversation, or what we know about this donor. If a needed detail is not there, leave it out and say
  a team member will follow up. Never write bracketed placeholders such as [Name].
- Never say an action has already been taken (cancelled, refunded, removed, processed).
  You cannot act on accounts. Say the team will handle the request, with the timeframe
  from the policy if there is one.
- End with exactly this sign-off on its own line: Lanternwood Reading Alliance
- Output only the reply text: no subject line, no notes to staff.
"""
 
 


class Classification(BaseModel):
    intent: Literal["pledge", "question", "unsubscribe", "complaint", "thanks"]
    sentiment: Literal["positive", "negative", "neutral", "mixed"]
    reasoning: str = Field(description="One short sentence explaining the label")