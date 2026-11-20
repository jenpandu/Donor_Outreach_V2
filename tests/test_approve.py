"""POST /messages/<id>/approve, plus the Flask-side Memory client. No live AWS."""
import pytest
from botocore.exceptions import ClientError

import donor_memory
from donor_outreach.clients.memory import MemoryClient, actor_id
from donor_outreach.db_models import Message
from donor_outreach.extensions import db
from fakes import FakeMemory


@pytest.fixture
def campaign_id(client):
    resp = client.post("/campaigns", json={
        "name": "Spring Drive", "goal_amt": 5000,
        "description": "Approve tests", "def_lang": "en",
    })
    return resp.get_json()["id"]


@pytest.fixture
def inbound(client, campaign_id):
    """An inbound message as the agent would leave it: drafted and pending review."""
    resp = client.post(f"/campaigns/{campaign_id}/messages/inbound", json={
        "donor_name": "María López",
        "original_text": "¿Cuándo recibiré mi recibo de impuestos?",
    })
    msg = db.session.get(Message, resp.get_json()["id"])
    msg.original_language = "es"
    msg.intent, msg.sentiment = "question", "neutral"
    msg.draft_reply = "Hola María, su recibo llegará por correo esta semana."
    msg.status = "pending_review"
    db.session.commit()
    return msg.id


# --- Happy paths ------------------------------------------------------------

def test_approve_sends_draft_as_is(client, inbound, fake_memory_client):
    resp = client.post(f"/messages/{inbound}/approve", json={})
    assert resp.status_code == 201
    data = resp.get_json()

    assert data["inbound"]["status"] == "approved"
    reply = data["reply"]
    assert reply["direction"] == "outbound"
    assert reply["original_text"] == "Hola María, su recibo llegará por correo esta semana."
    assert reply["original_language"] == reply["target_language"] == "es"
    assert reply["donor_name"] == "María López"
    assert data["memory_saved"] is True


def test_approve_with_edited_text(client, inbound, fake_memory_client):
    resp = client.post(f"/messages/{inbound}/approve",
                       json={"reply_text": "Hola María, ya se lo enviamos hoy."})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["reply"]["original_text"] == "Hola María, ya se lo enviamos hoy."
    # The agent's draft is kept on the inbound row (useful for evals)
    assert data["inbound"]["draft_reply"].startswith("Hola María, su recibo")


def test_reply_shows_up_in_campaign_messages(client, inbound, campaign_id, fake_memory_client):
    client.post(f"/messages/{inbound}/approve", json={})
    out = client.get(f"/campaigns/{campaign_id}/messages?direction=outbound").get_json()
    assert out["count"] == 1


# --- What gets written to Memory --------------------------------------------

def test_memory_gets_inbound_text_and_approved_reply(client, inbound, campaign_id,
                                                     fake_memory_client):
    client.post(f"/messages/{inbound}/approve", json={"reply_text": "Edited reply"})
    call = fake_memory_client.calls[0]
    assert call["memoryId"] == "TESTMEM0001"
    assert call["actorId"] == "donor-maria-lopez"
    assert call["sessionId"] == f"campaign-{campaign_id}"
    assert call["payload"] == [
        {"conversational": {"content": {"text": "¿Cuándo recibiré mi recibo de impuestos?"},
                            "role": "USER"}},
        {"conversational": {"content": {"text": "Edited reply"}, "role": "ASSISTANT"}},
    ]


def test_memory_failure_still_approves(client, inbound, fake_memory_client):
    fake_memory_client.error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "nope"}}, "CreateEvent"
    )
    resp = client.post(f"/messages/{inbound}/approve", json={})
    assert resp.status_code == 201
    assert resp.get_json()["memory_saved"] is False
    assert db.session.get(Message, inbound).status == "approved"


def test_memory_disabled_still_approves(client, inbound):
    # no fake_memory_client: the autouse guard leaves memory switched off
    resp = client.post(f"/messages/{inbound}/approve", json={})
    assert resp.status_code == 201
    assert resp.get_json()["memory_saved"] is False


# --- Rejections ---------------------------------------------------------------

def test_unknown_message_is_404(client):
    assert client.post("/messages/99999/approve", json={}).status_code == 404


def test_approving_twice_is_409_and_writes_memory_once(client, inbound, fake_memory_client):
    client.post(f"/messages/{inbound}/approve", json={})
    resp = client.post(f"/messages/{inbound}/approve", json={})
    assert resp.status_code == 409
    assert len(fake_memory_client.calls) == 1


def test_outbound_message_cannot_be_approved(client, campaign_id, fake_memory_client):
    ob = client.post(f"/campaigns/{campaign_id}/messages/outbound", json={
        "donor_name": "Jane Doe", "original_text": "Thanks!", "target_language": "en",
    }).get_json()
    resp = client.post(f"/messages/{ob['id']}/approve", json={})
    assert resp.status_code == 422
    assert fake_memory_client.calls == []


def test_no_draft_and_no_reply_text_is_422(client, campaign_id):
    msg = client.post(f"/campaigns/{campaign_id}/messages/inbound", json={
        "donor_name": "Jane Doe", "original_text": "Hello?",
    }).get_json()
    resp = client.post(f"/messages/{msg['id']}/approve", json={})
    assert resp.status_code == 422
    assert db.session.get(Message, msg["id"]).status == "pending_review"   # unchanged


def test_no_draft_but_reply_text_is_fine(client, campaign_id):
    msg = client.post(f"/campaigns/{campaign_id}/messages/inbound", json={
        "donor_name": "Jane Doe", "original_text": "Hello?",
    }).get_json()
    resp = client.post(f"/messages/{msg['id']}/approve", json={"reply_text": "Hi Jane!"})
    assert resp.status_code == 201


def test_empty_reply_text_is_422(client, inbound):
    assert client.post(f"/messages/{inbound}/approve",
                       json={"reply_text": ""}).status_code == 422


# --- Flask writes where the agent reads ----------------------------------------

@pytest.mark.parametrize("donor", ["42", "María López", "  JOSÉ  o'brien ", "", None])
def test_actor_id_matches_agent(donor):
    assert actor_id(donor) == donor_memory.actor_id(donor)


def test_client_without_memory_id_makes_no_calls():
    boto = FakeMemory()
    assert MemoryClient(boto_client=boto, memory_id="").save_exchange("42", 1, "a", "b") is False
    assert boto.calls == []
