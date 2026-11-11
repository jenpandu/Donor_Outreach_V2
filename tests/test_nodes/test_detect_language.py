from types import SimpleNamespace
import pytest
from botocore.stub import Stubber
import nodes

def test_detect_language_and_high_confidence():

    with Stubber(nodes.comprehend) as stub:
        stub.add_response(
            "detect_dominant_language",
            {"Languages": [{"LanguageCode": "es", "Score": 0.99}]},
            {"Text": "¿Cuándo recibiré mi recibo?"},
        )
        out = nodes.detect_language({"text": "¿Cuándo recibiré mi recibo?",
                                     "campaign_def_lang": "en"})
    assert out["detected_lang"] == "es"
    assert out["lang_source"] == "comprehend"

def test_detect_language_low_confidence_falls_back():
    with Stubber(nodes.comprehend) as stub:
        stub.add_response(
            "detect_dominant_language",
            {"Languages": [{"LanguageCode": "pt", "Score": 0.3}]},
        )
        out = nodes.detect_language({"text": "ok", "campaign_def_lang": "en"})
    assert out["detected_lang"] == "en"
    assert out["lang_source"] == "fallback_low_conf"

def test_detect_language_aws_error_falls_back():
    with Stubber(nodes.comprehend) as stub:
        stub.add_client_error("detect_dominant_language",
                              service_error_code="InternalServerException")
        out = nodes.detect_language({"text": "Hola", "campaign_def_lang": "en"})
    assert out["detected_lang"] == "en"
    assert out["lang_source"] == "fallback_error"

def test_detect_language_empty_text_skips_aws():
    # No stubbed responses: if the node called Comprehend, Stubber would raise.
    with Stubber(nodes.comprehend):
        out = nodes.detect_language({"text": "   ", "campaign_def_lang": "en"})
    assert out["lang_source"] == "fallback_empty"