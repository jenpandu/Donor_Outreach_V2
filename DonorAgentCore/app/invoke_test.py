import json, uuid, boto3

ARN = "arn:aws:bedrock-agentcore:us-east-1:397345411365:runtime/DonorAgentCore_DonorAgent-ev7yoEA6UA"
client = boto3.client("bedrock-agentcore", region_name="us-east-1")

resp = client.invoke_agent_runtime(
    agentRuntimeArn=ARN,
    runtimeSessionId=str(uuid.uuid4()),   # must be at least 33 characters; a UUID is 36
     payload=json.dumps({
        "text": "Merci, mais veuillez me retirer de votre liste.",
        "campaign_def_lang": "en",
        "donor_name": "Claire",
    }).encode(),
)
print(json.loads(resp["response"].read()))