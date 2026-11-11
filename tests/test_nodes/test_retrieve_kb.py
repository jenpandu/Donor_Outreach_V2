"""Unit tests for the retrieve_kb node. No AWS calls are made."""
import logging

import pytest
from botocore.exceptions import ClientError

from fakes import FakeKB, chunk


@pytest.fixture
def fake_kb(monkeypatch, nodes, kb_settings):
    kb = FakeKB()
    monkeypatch.setattr(nodes, "_kb", kb)
    return kb


def state(**overrides):
    base = {
        "campaign_def_lang": "en",
        "donor_name": "María López",
        "text": "¿Cuándo recibiré mi recibo de impuestos?",
        "translation": "When will I receive my tax receipt?",
        "intent": "question",
    }
    base.update(overrides)
    return base


# --- What gets sent to the KB ---------------------------------------------

def test_queries_with_translation_when_present(nodes, fake_kb):
    nodes.retrieve_kb(state())
    assert fake_kb.calls[0]["retrievalQuery"] == {"text": "When will I receive my tax receipt?"}


def test_falls_back_to_original_text_without_translation(nodes, fake_kb):
    nodes.retrieve_kb(state(text="When is my receipt coming?", translation=None))
    assert fake_kb.calls[0]["retrievalQuery"] == {"text": "When is my receipt coming?"}


def test_uses_managed_search_config_and_kb_id(nodes, fake_kb):
    nodes.retrieve_kb(state())
    call = fake_kb.calls[0]
    assert call["knowledgeBaseId"] == nodes.KB_ID
    assert call["retrievalConfiguration"] == {
        "managedSearchConfiguration": {"numberOfResults": 4}
    }


# --- What comes back --------------------------------------------------------

def test_joins_chunks_above_threshold(nodes, fake_kb):
    fake_kb.results = [
        chunk("Online gift receipts are emailed within 48 hours.", 0.92),
        chunk("Check gifts are receipted within 10 business days.", 0.71),
    ]
    out = nodes.retrieve_kb(state())
    assert "48 hours" in out["kb_context"]
    assert "10 business days" in out["kb_context"]
    assert "\n\n---\n\n" in out["kb_context"]


def test_drops_chunks_below_threshold(nodes, fake_kb):
    fake_kb.results = [
        chunk("Receipt policy: 48 hours.", 0.90),
        chunk("Unrelated volunteer schedule.", 0.10),
    ]
    out = nodes.retrieve_kb(state())
    assert "48 hours" in out["kb_context"]
    assert "volunteer" not in out["kb_context"]
    assert "schedule" not in out["kb_context"]


def test_result_without_score_is_dropped(nodes, fake_kb):
    no_score = chunk("No score here.", 0)
    del no_score["score"]
    fake_kb.results = [no_score]
    assert nodes.retrieve_kb(state())["kb_context"] == ""


def test_no_results_returns_empty_string(nodes, fake_kb):
    fake_kb.results = []
    assert nodes.retrieve_kb(state())["kb_context"] == ""


# --- Failures never break the pipeline -------------------------------------

def test_aws_error_returns_empty_and_logs(nodes, fake_kb, caplog):
    fake_kb.error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "nope"}}, "Retrieve"
    )
    with caplog.at_level(logging.ERROR):
        out = nodes.retrieve_kb(state())
    assert out == {"kb_context": ""}
    assert "KB retrieve failed" in caplog.text