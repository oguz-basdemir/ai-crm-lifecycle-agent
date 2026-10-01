"""Domain contracts shared by storage, API, and decision engines."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Stage = Literal[
    "Subscriber", "Lead", "MQL", "SQL", "Opportunity", "Customer", "At Risk", "Churned", "Win-back"
]
Action = Literal[
    "nurture email", "sales outreach", "product education", "upsell", "reactivation", "no action"
]


class Contact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: str = Field(pattern=r"^SYN-\d{5}$")
    synthetic: Literal[True] = True
    company: str = Field(min_length=1, max_length=120)
    industry: str = Field(min_length=1, max_length=80)
    company_size: int = Field(ge=1, le=100000)
    acquisition_source: str = Field(min_length=1, max_length=80)
    country: str = Field(min_length=2, max_length=80)
    pages_viewed: int = Field(ge=0, le=10000)
    content_downloads: int = Field(ge=0, le=1000)
    email_opens: int = Field(ge=0, le=10000)
    email_clicks: int = Field(ge=0, le=10000)
    demo_requested: bool
    last_activity: date
    created_at: date
    customer_since: date | None = None
    customer_status: Literal["prospect", "active", "inactive", "churned"]
    purchase_value: float = Field(ge=0)
    product_usage: int = Field(ge=0, le=100)
    support_tickets: int = Field(ge=0, le=100)
    usage_decline: int = Field(ge=0, le=100)
    unsubscribed: bool = False
    marketing_consent: bool = True
    winback_eligible: bool = True
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def chronology(self) -> "Contact":
        if self.last_activity < self.created_at:
            raise ValueError("Activity cannot precede contact creation")
        if self.customer_since and not self.created_at <= self.customer_since <= self.last_activity:
            raise ValueError("Customer date must fall between creation and last activity")
        if self.customer_status != "prospect" and self.customer_since is None:
            raise ValueError("Customer records require customer_since")
        return self


class Contribution(BaseModel):
    factor: str
    points: int
    reason: str


class Score(BaseModel):
    value: int = Field(ge=0, le=100)
    raw_value: int
    contributions: list[Contribution]
    model: str = "deterministic-v1"


class Decision(BaseModel):
    contact_id: str
    as_of: date
    policy_version: str
    score: Score
    lifecycle: Stage
    lifecycle_reason: str
    segments: list[str]
    action: Action
    action_reason: str
    suppressed: bool


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=1, max_length=180)
    email: str = Field(min_length=1, max_length=4000)
    cta: str = Field(min_length=1, max_length=180)
    angle: str = Field(min_length=1, max_length=500)


class AgentAdvice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=1000)
    opportunity_risk: str = Field(min_length=1, max_length=1000)
    interpretation: str = Field(min_length=1, max_length=1500)
    suggested_message: Message


class WorkflowStep(BaseModel):
    kind: Literal["message", "check", "task"]
    label: str = Field(min_length=1, max_length=100)
    delay_days: int = Field(default=0, ge=0, le=90)


class Workflow(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,40}$")
    description: str = Field(min_length=1, max_length=400)
    entry_stages: list[Stage] = Field(min_length=1)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=10)
    exit_on_reactivation: bool = False
