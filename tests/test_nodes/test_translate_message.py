from types import SimpleNamespace
import pytest
from botocore.stub import Stubber
import nodes
# ---------- translate (Translate via Stubber) ----------
 
def test_translate_same_language_skips_aws():
    with Stubber(nodes.translate):
        out = nodes.translate_message({"text": "Thanks!", "detected_lang": "en",
                                       "campaign_def_lang": "en"})
    assert out["translation"] is None
 
 
def test_translate_success():
    with Stubber(nodes.translate) as stub:
        stub.add_response(
            "translate_text",
            {"TranslatedText": "Thank you!", "SourceLanguageCode": "es",
             "TargetLanguageCode": "en"},
            {"Text": "¡Gracias!", "SourceLanguageCode": "es",
             "TargetLanguageCode": "en"},
        )
        out = nodes.translate_message({"text": "¡Gracias!", "detected_lang": "es",
                                       "campaign_def_lang": "en"})
    assert out["translation"] == "Thank you!"
 
 
def test_translate_error_returns_none():
    with Stubber(nodes.translate) as stub:
        stub.add_client_error("translate_text",
                              service_error_code="ServiceUnavailableException")
        out = nodes.translate_message({"text": "¡Gracias!", "detected_lang": "es",
                                       "campaign_def_lang": "en"})
    assert out["translation"] is None

