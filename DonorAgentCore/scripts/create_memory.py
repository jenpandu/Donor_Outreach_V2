"""One-time setup: create the AgentCore Memory resource for Donor Outreach.

Run once:  python scripts/create_memory.py
Then put the printed ID in your .env as AGENTCORE_MEMORY_ID.
Long-term memory takes ~2-3 minutes to become ACTIVE.
"""
import os

from bedrock_agentcore.memory import MemoryClient

REGION = os.getenv("AWS_REGION", "us-east-1")

client = MemoryClient(region_name=REGION)

memory = client.create_memory_and_wait(
    name="DonorOutreachMemory",
    description="Per-donor long-term memory for the inbound triage agent",
    strategies=[
        {
            # Facts: "pledged $500", "asked for a gift receipt", "prefers email"
            "semanticMemoryStrategy": {
                "name": "DonorFacts",
                "namespaces": ["/donors/{actorId}/facts/"],
            }
        },
        {
            # Preferences: reply language, tone, contact frequency
            "userPreferenceMemoryStrategy": {
                "name": "DonorPreferences",
                "namespaces": ["/donors/{actorId}/preferences/"],
            }
        },
    ],
)

print("Memory ID:", memory["id"])