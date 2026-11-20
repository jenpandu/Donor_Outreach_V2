"""Shared pytest setup for the donor agent.

Place this folder at src/donor_outreach/donor_agent/tests/
"""
import os
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
AGENT_DIR = TESTS_DIR.parent            # .../donor_agent  (for `import nodes`, `state`, `prompt`)
SRC_DIR = TESTS_DIR.parents[2]          # .../src          (for `donor_outreach.config`)

for p in (AGENT_DIR, SRC_DIR, TESTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Settings must load even without a real .env (real env vars win over .env).
os.environ.setdefault("KB_ID", "TESTKB0001")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("BEDROCK_MODEL_ID", "deepseek.v3.2")


@pytest.fixture(autouse=True)
def no_live_memory(monkeypatch):
    """Your .env has a real AGENTCORE_MEMORY_ID; make sure no test ever calls it.
    Tests that need memory install a FakeMemory via the fake_memory fixture."""
    import donor_memory
    from donor_outreach.api.messages import store
    from donor_outreach.clients.memory import MemoryClient
    monkeypatch.setattr(donor_memory, "_client", None)
    monkeypatch.setattr(donor_memory, "MEMORY_ID", "TESTMEM0001")
    # Flask side: a MemoryClient with no memory ID never calls AWS.
    monkeypatch.setattr(store, "MemoryClient", lambda: MemoryClient(memory_id=""))
    # Same for the AgentCore Runtime: off unless a test installs fake_agent.
    from donor_outreach.clients.agent import AgentClient
    monkeypatch.setattr(store, "AgentClient", lambda: AgentClient(enabled=False))


@pytest.fixture
def fake_memory(monkeypatch):
    from fakes import FakeMemory
    import donor_memory
    mem = FakeMemory()
    monkeypatch.setattr(donor_memory, "_client", mem)
    return mem


@pytest.fixture
def nodes():
    import nodes as n
    return n


@pytest.fixture
def kb_settings(monkeypatch, nodes):
    """Pin the retrieval knobs so tests don't depend on your .env values."""
    monkeypatch.setattr(nodes.settings, "kb_min_score", 0.4)
    monkeypatch.setattr(nodes.settings, "kb_num_results", 4)
    return nodes.settings


# --- Flask app -----------------------------------------------------------------

class _FakeComprehendClient:
    """Stands in for clients.comprehend.ComprehendClient: everything is confident English."""

    def detect_language(self, text):
        return "en", 0.99


class _FakeTranslateClient:
    def translate_text(self, text, src_lang, trg_lang):
        return f"[{trg_lang}] {text}"


@pytest.fixture
def app(monkeypatch):
    """Flask app on TEST_DATABASE_URL with fresh tables per test and no live AWS."""
    from donor_outreach.api.messages import store
    from donor_outreach.app import create_app
    from donor_outreach.config import get_settings
    from donor_outreach.extensions import db

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", settings.test_database_url)
    monkeypatch.setattr(store, "ComprehendClient", _FakeComprehendClient)
    monkeypatch.setattr(store, "TranslateClient", _FakeTranslateClient)

    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


class FakeRuntime:
    """Stands in for the bedrock-agentcore boto client's invoke_agent_runtime."""

    def __init__(self):
        self.body = {}
        self.error = None
        self.calls = []

    def invoke_agent_runtime(self, **kwargs):
        import io, json
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        raw = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        return {"response": io.BytesIO(raw)}


@pytest.fixture
def fake_agent(monkeypatch):
    """Route inbound messages through a fake AgentCore Runtime."""
    from donor_outreach.api.messages import store
    from donor_outreach.clients.agent import AgentClient

    runtime = FakeRuntime()
    arn = "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/Test-abc"
    monkeypatch.setattr(store, "AgentClient",
                        lambda: AgentClient(boto_client=runtime, runtime_arn=arn, enabled=True))
    return runtime


@pytest.fixture
def fake_memory_client(monkeypatch):
    """Records what the approve endpoint writes to Memory (Flask side)."""
    from donor_outreach.api.messages import store
    from donor_outreach.clients.memory import MemoryClient
    from fakes import FakeMemory

    boto = FakeMemory()
    monkeypatch.setattr(store, "MemoryClient",
                        lambda: MemoryClient(boto_client=boto, memory_id="TESTMEM0001"))
    return boto