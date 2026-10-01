"""Validated environment configuration and versioned business policy."""

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CRM_", extra="ignore")
    database_path: str = "data/crm.db"
    rules_path: str = "config/rules.json"
    seed_count: int = Field(default=180, ge=1, le=2000)
    seed: int = 42
    ai_enabled: bool = False
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=20, ge=1, le=60)
    api_url: str = "http://127.0.0.1:8000"


class Weights(BaseModel):
    demo: int = Field(default=20, ge=0, le=30)
    icp_size: int = Field(default=15, ge=0, le=30)
    icp_industry: int = Field(default=10, ge=0, le=30)
    pages: int = Field(default=10, ge=0, le=30)
    downloads: int = Field(default=10, ge=0, le=30)
    opens: int = Field(default=5, ge=0, le=30)
    clicks: int = Field(default=10, ge=0, le=30)
    recent: int = Field(default=10, ge=0, le=30)
    inactive: int = Field(default=-15, ge=-30, le=0)
    aging: int = Field(default=-5, ge=-30, le=0)


class Rules(BaseModel):
    version: str = "demo-v1"
    mql_score: int = Field(default=45, ge=1, le=100)
    sql_score: int = Field(default=65, ge=1, le=100)
    opportunity_score: int = Field(default=80, ge=1, le=100)
    inactive_days: int = Field(default=30, ge=15, le=365)
    risk_days: int = Field(default=21, ge=1, le=365)
    new_customer_days: int = Field(default=30, ge=1, le=365)
    expansion_usage: int = Field(default=75, ge=1, le=100)
    icp_min_size: int = Field(default=50, ge=1)
    icp_max_size: int = Field(default=1000, ge=1)
    icp_industries: list[str] = Field(default_factory=lambda: ["Software"])
    weights: Weights = Field(default_factory=Weights)
    source_points: dict[str, int] = Field(default_factory=lambda: {"Referral": 10})

    @model_validator(mode="after")
    def validate_policy(self) -> "Rules":
        if not self.mql_score < self.sql_score < self.opportunity_score:
            raise ValueError("Require MQL < SQL < Opportunity thresholds")
        if self.icp_min_size > self.icp_max_size:
            raise ValueError("ICP minimum must not exceed maximum")
        if any(not 0 <= p <= 30 for p in self.source_points.values()):
            raise ValueError("Source points must be between 0 and 30")
        return self


def load_rules(path: str) -> Rules:
    return Rules.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
