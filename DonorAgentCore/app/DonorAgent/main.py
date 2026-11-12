from opentelemetry.instrumentation.langchain import LangchainInstrumentor
LangchainInstrumentor().instrument()          # before the graph is imported

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from graph import donor_app

app = BedrockAgentCoreApp()
log = app.logger

OUT_KEYS = ("detected_lang", "confidence", "lang_source", "translation",
            "intent", "sentiment", "draft_reply")

@app.entrypoint
async def invoke(payload, context):
    if not payload.get("text") or not payload.get("campaign_def_lang"):
        return {"error": "text and campaign_def_lang are required"}
    try:
        state = await donor_app.ainvoke({
            "text": payload["text"],
            "campaign_def_lang": payload["campaign_def_lang"],
            "donor_name": payload.get("donor_name", ""),
        })
        return {k: state.get(k) for k in OUT_KEYS} | {"error": None}
    except Exception as e:
        log.exception("graph failed")
        return {"error": str(e)}

if __name__ == "__main__":
    app.run()