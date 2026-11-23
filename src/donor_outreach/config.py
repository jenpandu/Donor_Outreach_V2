from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Adjust parents[n] so this points at the folder that holds your .env
ROOT = Path(__file__).resolve().parents[2]

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    log_level: str = "DEBUG"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/donor_outreach"
    test_database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/donor_outreach_test"

    aws_profile: str | None = None      # None in AgentCore, where the role supplies credentials
    aws_region: str = "us-east-1"

    bedrock_model_id: str = "deepseek.v3.2"   # reads BEDROCK_MODEL_ID
    kb_id: str | None = None                  # reads KB_ID; only the agent uses it (its own config requires it)
    kb_num_results: int = 4
    kb_min_score: float = 0.4

    agentcore_memory_id: str | None = None    # reads AGENTCORE_MEMORY_ID; unset = memory off

    # Flask -> AgentCore Runtime. Off, or no ARN, = v1 translate-only path.
    agent_enabled: bool = False               # reads AGENT_ENABLED
    agent_runtime_arn: str | None = None      # reads AGENT_RUNTIME_ARN
    agent_timeout_s: int = 60                 # reads AGENT_TIMEOUT_S

    # Browser origins allowed to call the API (the React dev server). Comma-separated.
    cors_origins: str = "http://localhost:5173"   # reads CORS_ORIGINS

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
