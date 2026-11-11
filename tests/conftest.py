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