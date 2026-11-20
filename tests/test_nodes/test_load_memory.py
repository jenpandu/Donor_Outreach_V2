"""Unit tests for the load_memory node and donor_memory helpers. No AWS calls are made."""
import logging

from botocore.exceptions import ClientError

import donor_memory
from fakes import memory_record

FACTS = "/donors/donor-42/facts/"
PREFS = "/donors/donor-42/preferences/"


def state(**overrides):
    base = {
        "donor_id": "42",
        "donor_name": "María López",
        "text": "¿Cuándo recibiré mi recibo de impuestos?",
        "translation": "When will I receive my tax receipt?",
    }
    base.update(overrides)
    return base


# --- Who and what we ask Memory for -----------------------------------------

def test_reads_facts_and_preferences_for_donor(nodes, fake_memory):
    nodes.load_memory(state())
    assert [c["namespace"] for c in fake_memory.calls] == [FACTS, PREFS]
    assert all(c["memory_id"] == "TESTMEM0001" for c in fake_memory.calls)


def test_queries_with_translation_when_present(nodes, fake_memory):
    nodes.load_memory(state())
    assert fake_memory.calls[0]["query"] == "When will I receive my tax receipt?"


def test_falls_back_to_original_text_without_translation(nodes, fake_memory):
    nodes.load_memory(state(translation=None, text="When is my receipt coming?"))
    assert fake_memory.calls[0]["query"] == "When is my receipt coming?"


def test_uses_normalized_donor_name_when_no_donor_id(nodes, fake_memory):
    nodes.load_memory(state(donor_id=None))
    assert fake_memory.calls[0]["namespace"] == "/donors/donor-maria-lopez/facts/"


def test_no_donor_at_all_skips_memory(nodes, fake_memory):
    out = nodes.load_memory(state(donor_id=None, donor_name=""))
    assert out == {"donor_memory": ""}
    assert fake_memory.calls == []


# --- What comes back --------------------------------------------------------

def test_formats_records_as_bullets(nodes, fake_memory):
    fake_memory.records = {
        FACTS: [memory_record("Pledged $500 in October")],
        PREFS: [memory_record("Prefers email only")],
    }
    out = nodes.load_memory(state())
    assert out["donor_memory"] == "- Pledged $500 in October\n- Prefers email only"


def test_new_donor_returns_empty(nodes, fake_memory):
    assert nodes.load_memory(state()) == {"donor_memory": ""}


def test_records_without_text_are_skipped(nodes, fake_memory):
    fake_memory.records = {FACTS: [{"content": {}}, memory_record("Asked for a receipt")]}
    assert nodes.load_memory(state())["donor_memory"] == "- Asked for a receipt"


# --- Failures never break the pipeline -------------------------------------

def test_memory_error_returns_empty_and_logs(nodes, fake_memory, caplog):
    fake_memory.error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "nope"}}, "RetrieveMemoryRecords"
    )
    with caplog.at_level(logging.WARNING):
        out = nodes.load_memory(state())
    assert out == {"donor_memory": ""}
    assert "Memory read failed" in caplog.text


def test_memory_disabled_returns_empty(nodes):
    # no_live_memory (autouse) leaves _client as None, like an unset AGENTCORE_MEMORY_ID
    assert nodes.load_memory(state()) == {"donor_memory": ""}


# --- Memory reaches the draft -----------------------------------------------

def test_donor_memory_reaches_draft_prompt(nodes, monkeypatch):
    from langchain_core.messages import AIMessage
    from fakes import FakeLLM

    drafter = FakeLLM(AIMessage(content="Hola María, ..."))
    monkeypatch.setattr(nodes, "drafter", drafter)
    nodes.draft_reply(state(detected_lang="es", intent="question",
                            donor_memory="- Prefers email only"))
    assert "Prefers email only" in str(drafter.calls[0])


# --- Writing (used by the approve endpoint) ---------------------------------

def test_actor_id_normalizes():
    assert donor_memory.actor_id("42") == "donor-42"
    assert donor_memory.actor_id("  María López ") == "donor-maria-lopez"
    assert donor_memory.actor_id("") is None
    assert donor_memory.actor_id(None) is None


def test_save_approved_exchange_sends_event(fake_memory):
    donor_memory.save_approved_exchange("42", "1", "Can I get a receipt?", "Yes, this week.")
    call = fake_memory.calls[0]
    assert call["actor_id"] == "donor-42"
    assert call["session_id"] == "campaign-1"
    assert call["messages"] == [("Can I get a receipt?", "USER"), ("Yes, this week.", "ASSISTANT")]


def test_save_failure_is_swallowed(fake_memory, caplog):
    fake_memory.error = RuntimeError("boom")
    with caplog.at_level(logging.WARNING):
        donor_memory.save_approved_exchange("42", "1", "hi", "hello")
    assert "Memory write failed" in caplog.text
