"""Inbound messages go through the AgentCore Runtime, falling back to v1. No live AWS."""
import json

import pytest
from botocore.exceptions import ClientError

from donor_outreach.clients.agent import AgentClient

AGENT_OK = {
    "detected_lang": "es", "confidence": 0.99, "lang_source": "comprehend",
    "translation": "Can you email me my receipt, please?",
    "intent": "question", "sentiment": "neutral",
    "draft_reply": "¡Claro, Carlos! Le enviaremos su recibo por correo esta semana.",
    "error": None,
}


@pytest.fixture
def campaign_id(client):
    return client.post("/campaigns", json={
        "name": "Agent Test", "goal_amt": 1000, "description": "x", "def_lang": "en",
    }).get_json()["id"]


def post_inbound(client, campaign_id, text="¿Me pueden enviar mi recibo por correo?"):
    return client.post(f"/campaigns/{campaign_id}/messages/inbound",
                       json={"donor_name": "Carlos Mendez", "original_text": text})


# --- Agent succeeds ---------------------------------------------------------

def test_agent_fields_are_saved(client, campaign_id, fake_agent):
    fake_agent.body = AGENT_OK
    resp = post_inbound(client, campaign_id)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["original_language"] == "es"
    assert data["translated_text"] == "Can you email me my receipt, please?"
    assert data["intent"] == "question"
    assert data["sentiment"] == "neutral"
    assert data["draft_reply"].startswith("¡Claro, Carlos!")
    assert data["status"] == "pending_review"


def test_payload_sent_to_runtime(client, campaign_id, fake_agent):
    fake_agent.body = AGENT_OK
    post_inbound(client, campaign_id)
    call = fake_agent.calls[0]
    assert call["agentRuntimeArn"].startswith("arn:aws:bedrock-agentcore:")
    assert len(call["runtimeSessionId"]) >= 33
    assert json.loads(call["payload"]) == {
        "text": "¿Me pueden enviar mi recibo por correo?",
        "campaign_def_lang": "en",
        "donor_name": "Carlos Mendez",
    }


def test_same_language_stores_text_as_translation(client, campaign_id, fake_agent):
    fake_agent.body = AGENT_OK | {"detected_lang": "en", "translation": None, "intent": "thanks"}
    data = post_inbound(client, campaign_id, "Thanks so much!").get_json()
    assert data["original_language"] == "en"
    assert data["translated_text"] == "Thanks so much!"   # matches v1 behaviour


def test_drafted_message_can_be_approved_without_reply_text(client, campaign_id, fake_agent):
    fake_agent.body = AGENT_OK
    msg = post_inbound(client, campaign_id).get_json()
    resp = client.post(f"/messages/{msg['id']}/approve", json={})
    assert resp.status_code == 201
    assert resp.get_json()["reply"]["original_text"].startswith("¡Claro, Carlos!")


# --- Agent fails: v1 fallback, message still saves --------------------------

def _assert_v1_fallback(data):
    assert data["original_language"] == "en"          # from the fake Comprehend in conftest
    assert data["translated_text"] == data["original_text"]
    assert data["intent"] is None and data["draft_reply"] is None
    assert data["status"] == "pending_review"


def test_runtime_aws_error_falls_back(client, campaign_id, fake_agent):
    fake_agent.error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "InvokeAgentRuntime"
    )
    resp = post_inbound(client, campaign_id)
    assert resp.status_code == 201
    _assert_v1_fallback(resp.get_json())


def test_agent_error_field_falls_back(client, campaign_id, fake_agent):
    fake_agent.body = {"error": "graph failed"}
    _assert_v1_fallback(post_inbound(client, campaign_id).get_json())


def test_bad_json_falls_back(client, campaign_id, fake_agent):
    fake_agent.body = b"not json"
    _assert_v1_fallback(post_inbound(client, campaign_id).get_json())


def test_agent_disabled_uses_v1(client, campaign_id):
    # no fake_agent: the autouse guard leaves the agent switched off
    _assert_v1_fallback(post_inbound(client, campaign_id).get_json())


# --- Config guard -------------------------------------------------------------

@pytest.mark.parametrize("enabled, arn", [(False, "arn:aws:x"), (True, ""), (True, "X")])
def test_not_configured_makes_no_call(enabled, arn):
    class Boom:
        def invoke_agent_runtime(self, **kw):
            raise AssertionError("should not be called")
    client = AgentClient(boto_client=Boom(), runtime_arn=arn, enabled=enabled)
    assert client.triage("hi", "en", "x") is None
