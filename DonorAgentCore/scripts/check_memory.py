"""Show what AgentCore Memory holds for one donor.

Usage:
  python DonorAgentCore/scripts/check_memory.py                         # donor 42, campaign 1
  python DonorAgentCore/scripts/check_memory.py "Carlos Mendez" 3       # donor name (or ID), campaign ID
"""
import os, re, sys, unicodedata
from dotenv import load_dotenv
load_dotenv()
import boto3


def actor_id(donor) -> str:
    # Same rule as donor_memory.actor_id / clients.memory.actor_id
    text = unicodedata.normalize("NFKD", str(donor)).encode("ascii", "ignore").decode()
    return "donor-" + re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


donor = sys.argv[1] if len(sys.argv) > 1 else "42"
campaign = sys.argv[2] if len(sys.argv) > 2 else "1"
actor = actor_id(donor)

mem_id = os.getenv("AGENTCORE_MEMORY_ID")
region = os.getenv("AWS_REGION", "us-east-1")
print("1. Memory ID loaded:", mem_id, "| region:", region)
print(f"   Checking actor={actor} session=campaign-{campaign}")
if not mem_id:
    sys.exit("   -> AGENTCORE_MEMORY_ID not found. Check your .env.")

session = boto3.Session(profile_name=os.getenv("AWS_PROFILE"), region_name=region)
c = session.client("bedrock-agentcore")

events = c.list_events(memoryId=mem_id, actorId=actor,
                       sessionId=f"campaign-{campaign}")["events"]
print(f"2. Raw events saved (short-term): {len(events)}")

for ns in (f"/donors/{actor}/facts/", f"/donors/{actor}/preferences/"):
    recs = c.list_memory_records(memoryId=mem_id, namespace=ns)["memoryRecordSummaries"]
    print(f"3. Records in {ns}: {len(recs)}")
    for r in recs:
        print("   -", r["content"]["text"])

print("\n(Long-term records appear ~1 minute after an event is saved.)")
