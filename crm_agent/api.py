"""FastAPI adapter; dependencies constructed at lifespan for isolated tests."""

import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from crm_agent.config import Settings, load_rules
from crm_agent.decisions import evaluate
from crm_agent.llm import OpenAICompatibleProvider
from crm_agent.models import Contact, Workflow
from crm_agent.providers import MockCRMProvider
from crm_agent.repository import ConflictError, Repository
from crm_agent.service import CRMService
from crm_agent.synthetic import generate_contacts
from crm_agent.workflows import default_workflows

logger = logging.getLogger(__name__)


class DraftRequest(BaseModel):
    contact_id: str
    as_of: date = Field(default_factory=date.today)
    use_ai: bool = False


class ReviewRequest(BaseModel):
    actor: str = Field(min_length=2, max_length=80, pattern=r".*\S.*")
    as_of: date = Field(default_factory=date.today)
    human_approval: bool = False


class EnrollmentRequest(BaseModel):
    contact_id: str
    workflow: str
    as_of: date = Field(default_factory=date.today)


class TickRequest(BaseModel):
    as_of: date = Field(default_factory=date.today)


class TaskRequest(BaseModel):
    contact_id: str
    title: str = Field(min_length=1, max_length=200)


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configuration = settings or Settings()
        repo = Repository(configuration.database_path)
        repo.initialize()
        rules = load_rules(configuration.rules_path)
        repo.seed(generate_contacts(configuration.seed_count, configuration.seed))
        provider = OpenAICompatibleProvider(configuration) if configuration.ai_enabled else None
        app.state.service = CRMService(repo, rules, provider)
        if not repo.objects("workflow"):
            for workflow in default_workflows():
                app.state.service.save_workflow(workflow)
        logger.info(
            "Synthetic CRM initialized; policy=%s; AI enabled=%s",
            rules.version,
            configuration.ai_enabled,
        )
        yield

    app = FastAPI(
        title="AI CRM Lifecycle & Lead Scoring Agent",
        version="1.0.0",
        description="Synthetic portfolio prototype. No real CRM or email delivery.",
        lifespan=lifespan,
    )

    @app.exception_handler(KeyError)
    async def missing_handler(request: Request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": str(exc.args[0])})

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def validation_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def service() -> CRMService:
        return app.state.service

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "synthetic": True,
            "delivery": "simulation-only",
            "policy_version": service().rules.version,
        }

    @app.get("/rules")
    def rules():
        return service().rules

    @app.get("/contacts")
    def contacts(as_of: date = Query(default_factory=date.today)):
        return service().profiles(as_of)

    @app.post("/contacts", status_code=201, response_model=Contact)
    def create_contact(contact: Contact):
        evaluate(contact, service().rules, date.today())
        return service().repo.save_contact(contact, create=True)

    @app.get("/contacts/{contact_id}", response_model=Contact)
    def get_contact(contact_id: str):
        return service().repo.contact(contact_id)

    @app.put("/contacts/{contact_id}", response_model=Contact)
    def update_contact(contact_id: str, contact: Contact):
        if contact_id != contact.contact_id:
            raise HTTPException(422, "Path and contact_id must match")
        evaluate(contact, service().rules, date.today())
        return MockCRMProvider(service()).update_contact(contact)

    @app.get("/contacts/{contact_id}/decision")
    def decision(contact_id: str, as_of: date = Query(default_factory=date.today)):
        return evaluate(service().repo.contact(contact_id), service().rules, as_of)

    @app.post("/agent")
    def agent(body: DraftRequest):
        return service().advice(body.contact_id, body.as_of, body.use_ai)

    @app.get("/drafts")
    def drafts():
        return service().repo.objects("draft")

    @app.post("/drafts", status_code=201)
    def create_draft(body: DraftRequest):
        return service().create_draft(body.contact_id, body.as_of, body.use_ai)

    @app.post("/drafts/{draft_id}/{operation}")
    def review(
        draft_id: str, operation: Literal["approve", "reject", "simulate-send"], body: ReviewRequest
    ):
        if operation == "approve" and not body.human_approval:
            raise HTTPException(422, "Human must explicitly approve the reviewed message")
        return service().transition_draft(draft_id, operation, body.actor, body.as_of)

    @app.get("/workflows")
    def workflows():
        return service().repo.objects("workflow")

    @app.post("/workflows", status_code=201)
    def create_workflow(body: Workflow):
        return service().save_workflow(body)

    @app.get("/enrollments")
    def enrollments():
        return service().repo.objects("enrollment")

    @app.post("/enrollments", status_code=201)
    def enroll(body: EnrollmentRequest):
        return MockCRMProvider(service()).enroll_in_workflow(
            body.contact_id, body.workflow, body.as_of
        )

    @app.post("/enrollments/{enrollment_id}/advance")
    def advance(enrollment_id: str, body: TickRequest):
        return service().advance(enrollment_id, body.as_of)

    @app.get("/tasks")
    def tasks():
        return service().repo.objects("task")

    @app.post("/tasks", status_code=201)
    def task(body: TaskRequest):
        return MockCRMProvider(service()).create_task(body.contact_id, body.title)

    @app.get("/reports")
    def reports(as_of: date = Query(default_factory=date.today)):
        return service().report(as_of)

    @app.get("/audit")
    def audit():
        return service().repo.events()

    return app


app = create_app()
