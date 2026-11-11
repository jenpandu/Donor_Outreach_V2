# check_kb.py — calls the knowledge base directly, bypassing the graph
from donor_outreach.config import get_settings
import boto3

s = get_settings()
print(f"KB_ID={s.kb_id}  region={s.aws_region}  profile={s.aws_profile}  min_score={s.kb_min_score}")

kb = boto3.Session(profile_name=s.aws_profile, region_name=s.aws_region).client("bedrock-agent-runtime")

for q in ["When will I receive my tax receipt?",
          "Please remove me from your mailing list"]:
    resp = kb.retrieve(
    knowledgeBaseId=s.kb_id,
    retrievalQuery={"text": q},
    retrievalConfiguration={
        "managedSearchConfiguration": {"numberOfResults": 4}
    },
)
    results = resp["retrievalResults"]
    print(f"\n=== {q}  ({len(results)} results)")
    for r in results:
        print(f"  score={r.get('score', 0):.3f}  {r['location']['s3Location']['uri']}")
        print(f"     {r['content']['text'][:100]!r}")