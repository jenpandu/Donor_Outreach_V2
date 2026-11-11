from types import SimpleNamespace
import pytest
from botocore.stub import Stubber
import nodes

class FakeLLM:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []
 
    def invoke(self, prompt):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return self.result
# ---------- draft_reply (LLM via monkeypatch) ----------
 
def test_draft_reply_writes_in_donor_language(monkeypatch):
    fake = FakeLLM(SimpleNamespace(content="  Hola María  "))
    monkeypatch.setattr(nodes, "drafter", fake)
    out = nodes.draft_reply({"text": "¿Cuándo?", "detected_lang": "es",
                             "campaign_def_lang": "en", "intent": "question"})
    assert out["draft_reply"] == "Hola María"
    system_msg = fake.calls[0][0].content
    assert "Spanish" in system_msg
 
 
def test_draft_reply_error_returns_none(monkeypatch):
    monkeypatch.setattr(nodes, "drafter", FakeLLM(error=RuntimeError("boom")))
    out = nodes.draft_reply({"text": "Hi", "detected_lang": "en",
                             "campaign_def_lang": "en", "intent": "thanks"})
    assert out["draft_reply"] is None