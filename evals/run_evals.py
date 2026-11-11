"""Run the donor-message eval set through the real agent graph.

This calls AWS (Comprehend, Translate, Bedrock, the knowledge base), so each
full run costs a few cents. Run it from the repo root:

    python evals/run_evals.py                      # all cases
    python evals/run_evals.py --only es-receipt-q,fr-unsub-polite
    python evals/run_evals.py --show-drafts        # print every draft too

Full details for every case are saved to evals/results/<timestamp>.json.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "src" / "donor_outreach" / "donor_agent")]

import nodes  # noqa: E402
from graph import donor_app  # noqa: E402

EVAL_FILE = Path(__file__).with_name("donor_messages.jsonl")
RESULTS_DIR = Path(__file__).with_name("results")
CAMPAIGN_LANG = "en"
DONOR_NAMES = {"es": "María López", "fr": "Claire Dubois", "zh": "Wei Chen", "en": "Sam Taylor"}
PLACEHOLDER = re.compile(r"\[[^\]]{2,}\]")   # e.g. [Nombre de la Organización]
CHECKS = ["lang", "intent", "kb", "draft", "draft_lang"]


def norm(code):
    """'zh-TW' -> 'zh', None -> ''."""
    return (code or "").split("-")[0].lower()


class RecordingKB:
    """Wraps the real KB client and remembers which sources passed the threshold."""

    def __init__(self, real):
        self.real = real
        self.reset()

    def reset(self):
        self.calls, self.sources = 0, []

    def retrieve(self, **kwargs):
        self.calls += 1
        resp = self.real.retrieve(**kwargs)
        for r in resp.get("retrievalResults", []):
            if r.get("score", 0) >= nodes.settings.kb_min_score:
                loc = r.get("location", {})
                self.sources.append(loc.get("s3Location", {}).get("uri") or str(loc))
        return resp


def draft_language(text):
    try:
        resp = nodes.comprehend.detect_dominant_language(Text=text[:4000])
        return norm(max(resp["Languages"], key=lambda l: l["Score"])["LanguageCode"])
    except Exception:
        return None


def run_case(case, kb):
    kb.reset()
    expect = case["lang"] if isinstance(case["lang"], list) else [case["lang"]]   # NEW
    expect = [norm(l) for l in expect]                                            # NEW
    start = time.time()
    out = donor_app.invoke({
        "campaign_def_lang": CAMPAIGN_LANG,
        "donor_name": DONOR_NAMES.get(expect[0], "Alex Rivera"),                  # CHANGED
        "text": case["text"],
    })
    seconds = round(time.time() - start, 1)
    draft = out.get("draft_reply") or ""

    checks = {
        "lang": norm(out.get("detected_lang")) in expect,                         # CHANGED
        "intent": out.get("intent") in case["intents"],
        "draft": bool(draft) and not PLACEHOLDER.search(draft),
        "draft_lang": bool(draft) and draft_language(draft) in expect,            # CHANGED
    }
    if case.get("kb_doc"):
        checks["kb"] = any(case["kb_doc"].lower() in s.lower() for s in kb.sources)
    elif case["intents"] == ["thanks"]:
        checks["kb"] = kb.calls == 0          # thanks must skip the KB
    else:
        checks["kb"] = None                   # nothing to check

    return {
        "id": case["id"],
        "text": case["text"],
        "expected": {"lang": case["lang"], "intents": case["intents"], "kb_doc": case.get("kb_doc")},
        "got": {
            "lang": out.get("detected_lang"),
            "confidence": out.get("confidence"),
            "lang_source": out.get("lang_source"),
            "translation": out.get("translation"),
            "intent": out.get("intent"),
            "sentiment": out.get("sentiment"),
            "kb_calls": kb.calls,
            "kb_sources": kb.sources,
            "draft": draft,
        },
        "checks": checks,
        "seconds": seconds,
        "notes": case.get("notes", ""),
    }


def mark(value):
    return "-" if value is None else ("✓" if value else "✗")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--show-drafts", action="store_true")
    args = parser.parse_args()

    cases = [json.loads(line) for line in EVAL_FILE.read_text().splitlines() if line.strip()]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    kb = RecordingKB(nodes._kb)
    nodes._kb = kb

    results = []
    print(f"{'id':28} " + " ".join(f"{c:>10}" for c in CHECKS) + "     got")
    print("-" * 100)
    for case in cases:
        try:
            r = run_case(case, kb)
        except Exception as e:  # one broken case shouldn't stop the run
            r = {"id": case["id"], "text": case["text"], "error": repr(e),
                 "checks": {c: False for c in CHECKS}, "got": {}}
        results.append(r)
        got = r["got"]
        summary = r.get("error") or f"{got.get('lang')} / {got.get('intent')} / {got.get('sentiment')}"
        print(f"{r['id']:28} " + " ".join(f"{mark(r['checks'][c]):>10}" for c in CHECKS)
              + f"     {summary}")
        if args.show_drafts and got.get("draft"):
            print("    " + got["draft"].replace("\n", "\n    ") + "\n")

    print("-" * 100)
    for c in CHECKS:
        scored = [r["checks"][c] for r in results if r["checks"][c] is not None]
        print(f"{c:>12}: {sum(scored)}/{len(scored)}")

    failures = [r for r in results if any(v is False for v in r["checks"].values())]
    if failures:
        print("\nFailures:")
        for r in failures:
            bad = [c for c, v in r["checks"].items() if v is False]
            print(f"  {r['id']}: {', '.join(bad)}")
            if "error" in r:
                print(f"      error: {r['error']}")
                continue
            exp, got = r["expected"], r["got"]
            if "lang" in bad:
                print(f"      lang: expected {exp['lang']}, got {got['lang']} (conf={got['confidence']})")
            if "intent" in bad:
                print(f"      intent: expected {exp['intents']}, got {got['intent']}")
            if "kb" in bad:
                print(f"      kb: expected '{exp['kb_doc']}' in sources, got {got['kb_sources'] or got['kb_calls']}")
            if "draft" in bad or "draft_lang" in bad:
                print(f"      draft: {got['draft'][:160]!r}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out_file = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nFull results: {out_file.relative_to(ROOT)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()