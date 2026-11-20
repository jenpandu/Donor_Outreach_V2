"""Stand-ins for the AWS clients and LLMs used in nodes.py.

Each fake records the calls it receives so tests can check what was sent,
not just what came back.
"""


def chunk(text, score, uri="s3://jp-donor-outreach-bucket/kb-docs-2/doc.md"):
    """One item shaped like a Bedrock Retrieve result."""
    return {
        "content": {"text": text},
        "score": score,
        "location": {"type": "S3", "s3Location": {"uri": uri}},
    }


class FakeKB:
    """Replaces nodes._kb (bedrock-agent-runtime client)."""

    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls = []

    def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"retrievalResults": self.results}


class FakeComprehend:
    """Replaces nodes.comprehend."""

    def __init__(self, lang="es", score=0.99):
        self.lang, self.score = lang, score

    def detect_dominant_language(self, Text):
        return {"Languages": [{"LanguageCode": self.lang, "Score": self.score}]}


class FakeTranslate:
    """Replaces nodes.translate."""

    def __init__(self, translated="translated text"):
        self.translated = translated

    def translate_text(self, **kwargs):
        return {"TranslatedText": self.translated}


class FakeLLM:
    """Replaces nodes.classifier or nodes.drafter (anything with .invoke)."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def invoke(self, messages, *args, **kwargs):
        self.calls.append(messages)
        return self.response


def memory_record(text):
    """One item shaped like a MemoryClient.retrieve_memories result."""
    return {"content": {"text": text}}


class FakeMemory:
    """Replaces donor_memory._client (bedrock_agentcore MemoryClient).

    records maps a namespace (e.g. "/donors/donor-42/facts/") to its records.
    """

    def __init__(self, records=None, error=None):
        self.records = records or {}
        self.error = error
        self.calls = []

    def retrieve_memories(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.records.get(kwargs["namespace"], [])

    def create_event(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error