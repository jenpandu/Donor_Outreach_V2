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
    kb_id: str                                # reads KB_ID; required, so it fails loudly if missing
    kb_num_results: int = 4
    kb_min_score: float = 0.4

@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
