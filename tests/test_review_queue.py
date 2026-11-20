"""GET /campaigns/<id>/review-queue and POST /messages/<id>/reject. No live AWS."""
import pytest


@pytest.fixture
def campaign_id(client):
    return client.post("/campaigns", json={
        "name": "Queue Test", "goal_amt": 1000, "description": "x", "def_lang": "en",
    }).get_json()["id"]


def inbound(client, campaign_id, text="Hello?"):
    return client.post(f"/campaigns/{campaign_id}/messages/inbound",
                       json={"donor_name": "Jane Doe", "original_text": text}).get_json()["id"]


def queue_ids(client, campaign_id):
    data = client.get(f"/campaigns/{campaign_id}/review-queue").get_json()
    assert data["count"] == len(data["items"])
    return [m["id"] for m in data["items"]]


# --- Review queue -------------------------------------------------------------

def test_new_inbound_messages_appear_oldest_first(client, campaign_id):
    first, second = inbound(client, campaign_id, "one"), inbound(client, campaign_id, "two")
    assert queue_ids(client, campaign_id) == [first, second]


def test_queue_excludes_outbound(client, campaign_id):
    client.post(f"/campaigns/{campaign_id}/messages/outbound", json={
        "donor_name": "Jane Doe", "original_text": "Thanks!", "target_language": "en",
    })
    assert queue_ids(client, campaign_id) == []


def test_approved_and_rejected_leave_the_queue(client, campaign_id):
    a, r, waiting = (inbound(client, campaign_id) for _ in range(3))
    client.post(f"/messages/{a}/approve", json={"reply_text": "Hi Jane"})
    client.post(f"/messages/{r}/reject")
    assert queue_ids(client, campaign_id) == [waiting]


def test_queue_is_per_campaign(client, campaign_id):
    other = client.post("/campaigns", json={
        "name": "Other", "goal_amt": 1, "description": "x", "def_lang": "en",
    }).get_json()["id"]
    inbound(client, other)
    assert queue_ids(client, campaign_id) == []


def test_queue_includes_agent_fields(client, campaign_id, fake_agent):
    fake_agent.body = {"detected_lang": "es", "translation": "Hi", "intent": "question",
                       "sentiment": "neutral", "draft_reply": "Hola", "error": None}
    inbound(client, campaign_id, "Hola")
    item = client.get(f"/campaigns/{campaign_id}/review-queue").get_json()["items"][0]
    assert item["draft_reply"] == "Hola"
    assert item["intent"] == "question"


def test_queue_unknown_campaign_is_404(client):
    assert client.get("/campaigns/99999/review-queue").status_code == 404


# --- Reject -------------------------------------------------------------------

def test_reject_marks_rejected_and_writes_no_memory(client, campaign_id, fake_memory_client):
    mid = inbound(client, campaign_id)
    resp = client.post(f"/messages/{mid}/reject")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "rejected"
    assert fake_memory_client.calls == []


def test_reject_sends_nothing(client, campaign_id):
    mid = inbound(client, campaign_id)
    client.post(f"/messages/{mid}/reject")
    out = client.get(f"/campaigns/{campaign_id}/messages?direction=outbound").get_json()
    assert out["count"] == 0


def test_reject_twice_is_409(client, campaign_id):
    mid = inbound(client, campaign_id)
    client.post(f"/messages/{mid}/reject")
    assert client.post(f"/messages/{mid}/reject").status_code == 409


def test_cannot_reject_approved(client, campaign_id):
    mid = inbound(client, campaign_id)
    client.post(f"/messages/{mid}/approve", json={"reply_text": "Hi"})
    assert client.post(f"/messages/{mid}/reject").status_code == 409


def test_rejected_can_still_be_approved_with_new_text(client, campaign_id):
    # Staff throw away the draft, then write their own reply
    mid = inbound(client, campaign_id)
    client.post(f"/messages/{mid}/reject")
    resp = client.post(f"/messages/{mid}/approve", json={"reply_text": "Hand-written reply"})
    assert resp.status_code == 201


def test_cannot_reject_outbound(client, campaign_id):
    ob = client.post(f"/campaigns/{campaign_id}/messages/outbound", json={
        "donor_name": "Jane Doe", "original_text": "Thanks!", "target_language": "en",
    }).get_json()["id"]
    assert client.post(f"/messages/{ob}/reject").status_code == 422


def test_reject_unknown_is_404(client):
    assert client.post("/messages/99999/reject").status_code == 404
