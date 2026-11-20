"""Runs the real compiled graph with every AWS client and LLM faked.

Checks that the KB is skipped for thanks, used for everything else,
and that retrieved policy actually reaches the drafting prompt.
"""
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from fakes import FakeComprehend, FakeKB, FakeLLM, FakeTranslate, chunk


@pytest.fixture
def wire(monkeypatch, nodes, kb_settings):
    """Call wire(intent) to fake every external dependency for one run."""

    def _wire(intent, lang="es"):
        kb = FakeKB(results=[chunk("Online gift receipts are emailed within 48 hours.", 0.9)])
        drafter = FakeLLM(AIMessage(content="Hola María, ..."))
        monkeypatch.setattr(nodes, "comprehend", FakeComprehend(lang, 0.99))
        monkeypatch.setattr(nodes, "translate", FakeTranslate("When will I get my receipt?"))
        monkeypatch.setattr(nodes, "classifier",
                            FakeLLM(SimpleNamespace(intent=intent, sentiment="neutral")))
        monkeypatch.setattr(nodes, "drafter", drafter)
        monkeypatch.setattr(nodes, "_kb", kb)
        return kb, drafter

    return _wire


def run(text="¿Cuándo recibiré mi recibo?"):
    from graph import donor_app
    return donor_app.invoke(
        {"campaign_def_lang": "en", "donor_name": "María López", "text": text}
    )


def test_thanks_skips_kb(wire):
    kb, _ = wire("thanks")
    out = run("Gracias!")
    assert kb.calls == []
    assert not out.get("kb_context")
    assert out["draft_reply"]


@pytest.mark.parametrize("intent", ["question", "pledge", "complaint", "unsubscribe"])
def test_other_intents_hit_kb(wire, intent):
    kb, _ = wire(intent)
    run()
    assert len(kb.calls) == 1


def test_thanks_still_loads_memory(wire, fake_memory):
    wire("thanks")
    run("Gracias!")
    assert len(fake_memory.calls) == 2          # facts + preferences


@pytest.mark.parametrize("intent", ["question", "pledge", "complaint", "unsubscribe"])
def test_other_intents_load_memory(wire, fake_memory, intent):
    wire(intent)
    run()
    assert len(fake_memory.calls) == 2


def test_kb_context_reaches_draft_prompt(wire):
    _, drafter = wire("question")
    out = run()
    assert "48 hours" in out["kb_context"]
    assert "48 hours" in str(drafter.calls[0])