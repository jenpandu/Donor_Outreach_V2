from langgraph.graph import StateGraph, START, END
from nodes import detect_language, translate_message, classify_message, retrieve_kb, draft_reply
from state import AgentState

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("detect_language", detect_language)
    g.add_node("translate", translate_message)
    g.add_node("classify", classify_message)
    g.add_node("retrieve_kb", retrieve_kb)
    g.add_node("draft_reply", draft_reply)

    g.add_edge(START, "detect_language")
    g.add_edge("detect_language", "translate")
    g.add_edge("translate", "classify")
    g.add_conditional_edges(
    "classify",
    lambda s: "draft_reply" if s["intent"] == "thanks" else "retrieve_kb",
    )
    g.add_edge("retrieve_kb", "draft_reply")
    g.add_edge("draft_reply", END)
    return g.compile()

donor_app = build_graph()


def donor_agent(state: AgentState):
    return donor_app.invoke(state)
    

if __name__ == "__main__":
    samples = [
        {"campaign_def_lang": "en", "donor_name": "María López",
         "text": "¿Cuándo recibiré mi recibo de impuestos?"},
        {"campaign_def_lang": "en", "donor_name": "Luis Ortega",
         "text": "Gracias!"},
        {"campaign_def_lang": "en", "donor_name": "Claire Dubois",
         "text": "Merci, mais veuillez me retirer de votre liste."},
    ]
    

    for s in samples:
        result = donor_agent(s)
        print("=" * 60)
        print(f"text:      {s['text']}")
        print(f"lang:      {result.get('detected_lang')} "
                 f"(conf={result.get('confidence')}, src={result.get('lang_source')})")
        print(f"translate: {result.get('translation')}")
        print(f"intent:    {result.get('intent')} / {result.get('sentiment')}")
        kb = result.get("kb_context")
        print(f"kb:        {'skipped' if result.get('intent') == 'thanks' else f'{len(kb or '')} chars'}")
        print(f"draft:\n{result.get('draft_reply')}")
        