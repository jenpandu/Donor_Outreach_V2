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

def test_classify_uses_translation(monkeypatch):
    fake = FakeLLM(SimpleNamespace(intent="question", sentiment="neutral"))
    monkeypatch.setattr(nodes, "classifier", fake)
    out = nodes.classify_message({"text": "¿Cuándo?", "translation": "When?"})
    assert out == {"intent": "question", "sentiment": "neutral"}
    assert "When?" in fake.calls[0]
 
 
def test_classify_error_defaults_to_question(monkeypatch):
    monkeypatch.setattr(nodes, "classifier", FakeLLM(error=RuntimeError("boom")))
    out = nodes.classify_message({"text": "Hi", "translation": None})
    assert out == {"intent": "question", "sentiment": "neutral"}