from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest

from crm_agent.config import Settings
from crm_agent.decisions import evaluate
from crm_agent.llm import OpenAICompatibleProvider, agent_result
from crm_agent.models import AgentAdvice, Workflow
from crm_agent.providers import MockCRMProvider
from crm_agent.repository import ConflictError, Repository
from tests.conftest import TODAY


def approve_send(service, draft_id, today=TODAY):
    service.transition_draft(draft_id, "approve", "Reviewer", today)
    return service.transition_draft(draft_id, "simulate-send", "Reviewer", today)


def test_approval_required_and_idempotent(service):
    draft = service.create_draft("SYN-00005", TODAY)
    with pytest.raises(ConflictError, match="approval"):
        service.transition_draft(draft["id"], "simulate-send", "Reviewer", TODAY)
    approve_send(service, draft["id"])
    service.transition_draft(draft["id"], "simulate-send", "Reviewer", TODAY)
    assert service.report(TODAY)["simulated_sends"] == 1
    assert sum(e["event"] == "draft_simulate-send" for e in service.repo.events()) == 1


def test_concurrent_send_is_idempotent(service):
    draft = service.create_draft("SYN-00005", TODAY)
    service.transition_draft(draft["id"], "approve", "Reviewer", TODAY)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(
            pool.map(
                lambda _: service.transition_draft(draft["id"], "simulate-send", "Reviewer", TODAY),
                range(4),
            )
        )
    assert sum(e["event"] == "draft_simulate-send" for e in service.repo.events()) == 1


def test_stale_profile_and_consent_block_send(service):
    draft = service.create_draft("SYN-00005", TODAY)
    service.transition_draft(draft["id"], "approve", "Reviewer", TODAY)
    c = service.repo.contact("SYN-00005")
    service.repo.save_contact(c.model_copy(update={"unsubscribed": True}))
    with pytest.raises(ConflictError):
        service.transition_draft(draft["id"], "simulate-send", "Reviewer", TODAY)
    with pytest.raises(ConflictError):
        service.create_draft(c.contact_id, TODAY)


def test_decision_drift_blocks_send(service):
    draft = service.create_draft("SYN-00005", TODAY)
    service.transition_draft(draft["id"], "approve", "Reviewer", TODAY)
    with pytest.raises(ConflictError, match="decision"):
        service.transition_draft(
            draft["id"], "simulate-send", "Reviewer", TODAY + timedelta(days=60)
        )


def test_rejection_blocks_send(service):
    draft = service.create_draft("SYN-00003", TODAY)
    service.transition_draft(draft["id"], "reject", "Reviewer", TODAY)
    with pytest.raises(ConflictError):
        service.transition_draft(draft["id"], "approve", "Reviewer", TODAY)


def test_optimistic_update_and_persistence(service):
    c = service.repo.contact("SYN-00001")
    updated = service.repo.save_contact(c.model_copy(update={"pages_viewed": 12}))
    assert updated.version == 2
    with pytest.raises(ConflictError):
        service.repo.save_contact(c)
    assert Repository(service.repo.path).contact(c.contact_id).pages_viewed == 12


def test_full_onboarding_journey(service):
    e = service.enroll("SYN-00006", "onboarding", TODAY)
    e = service.advance(e["id"], TODAY)
    first = e["draft_id"]
    assert first and e["step"] == 0
    assert service.advance(e["id"], TODAY)["draft_id"] == first
    approve_send(service, first)
    e = service.advance(e["id"], TODAY)
    assert e["step"] == 1 and e["next_run"] == (TODAY + timedelta(days=3)).isoformat()
    assert service.advance(e["id"], TODAY)["draft_id"] is None
    later = TODAY + timedelta(days=3)
    e = service.advance(e["id"], later)
    approve_send(service, e["draft_id"], later)
    service.advance(e["id"], later)
    service.advance(e["id"], TODAY + timedelta(days=7))
    later = TODAY + timedelta(days=9)
    e = service.advance(e["id"], later)
    approve_send(service, e["draft_id"], later)
    e = service.advance(e["id"], later)
    assert e["status"] == "completed" and len(e["history"]) == 4


def test_nurture_qualification_task(service):
    e = service.enroll("SYN-00003", "lead-nurture", TODAY)
    e = service.advance(e["id"], TODAY)
    approve_send(service, e["draft_id"])
    service.advance(e["id"], TODAY)
    c = service.repo.contact("SYN-00003")
    service.repo.save_contact(c.model_copy(update={"demo_requested": True}))
    service.advance(e["id"], TODAY + timedelta(days=5))
    e = service.advance(e["id"], TODAY + timedelta(days=5))
    assert e["status"] == "completed"
    assert service.repo.objects("task")[0]["qualification"] == "SQL ready"


def test_winback_exit_on_reactivation(service):
    e = service.enroll("SYN-00007", "win-back", TODAY)
    c = service.repo.contact("SYN-00007")
    service.repo.save_contact(
        c.model_copy(
            update={
                "customer_status": "active",
                "last_activity": TODAY,
                "usage_decline": 0,
                "support_tickets": 0,
                "product_usage": 80,
            }
        )
    )
    assert service.advance(e["id"], TODAY)["status"] == "exited"
    assert not service.repo.objects("draft")


def test_workflow_consent_exit_and_duplicate_enrollment(service):
    e = service.enroll("SYN-00003", "lead-nurture", TODAY)
    with pytest.raises(ConflictError):
        service.enroll("SYN-00003", "lead-nurture", TODAY)
    c = service.repo.contact("SYN-00003")
    service.repo.save_contact(c.model_copy(update={"marketing_consent": False}))
    assert service.advance(e["id"], TODAY)["status"] == "exited"


def test_stale_workflow_draft_is_superseded(service):
    e = service.enroll("SYN-00003", "lead-nurture", TODAY)
    e = service.advance(e["id"], TODAY)
    old = e["draft_id"]
    c = service.repo.contact("SYN-00003")
    service.repo.save_contact(c.model_copy(update={"pages_viewed": 19}))
    e = service.advance(e["id"], TODAY)
    assert e["draft_id"] != old
    assert service.repo.object(old, "draft")["status"] == "superseded"


def test_rejected_workflow_exits(service):
    e = service.enroll("SYN-00003", "lead-nurture", TODAY)
    e = service.advance(e["id"], TODAY)
    service.transition_draft(e["draft_id"], "reject", "Reviewer", TODAY)
    assert service.advance(e["id"], TODAY)["status"] == "exited"


def test_custom_workflow_and_mock_provider(service):
    w = Workflow(
        name="custom-review",
        description="Qualification review",
        entry_stages=["MQL"],
        steps=[{"kind": "task", "label": "Human review", "delay_days": 0}],
    )
    service.save_workflow(w)
    with pytest.raises(ConflictError):
        service.save_workflow(w)
    provider = MockCRMProvider(service)
    assert len(provider.get_contacts()) == 18
    assert provider.create_task("SYN-00003", "Call review")["status"] == "open"
    e = provider.enroll_in_workflow("SYN-00003", w.name, TODAY)
    assert service.advance(e["id"], TODAY)["status"] == "completed"


def test_agent_no_mutations_and_disabled_fallback(service):
    result = service.advice("SYN-00003", TODAY, use_ai=True)
    assert result["mode"] == "fallback" and result["requires_human_approval"]
    assert not service.repo.objects("draft")


def test_ai_success_and_failure_keep_authoritative_decision(contacts, rules):
    c = contacts[4]
    d = evaluate(c, rules, TODAY)

    class Good:
        def advise(self, contact, decision):
            return AgentAdvice(
                summary="Synthetic summary",
                opportunity_risk="Demo intent",
                interpretation="Qualified intent",
                suggested_message={
                    "subject": "Demo",
                    "email": "Review your demo",
                    "cta": "Reply",
                    "angle": "Helpful",
                },
            )

    class Bad:
        def advise(self, contact, decision):
            raise httpx.ConnectError("offline")

    assert agent_result(c, d, Good())["mode"] == "ai-assisted"
    result = agent_result(c, d, Bad())
    assert result["mode"] == "fallback" and result["authoritative_score"] == d.score.value
    assert result["lifecycle_stage"] == "Opportunity"


def test_openai_compatible_wire_and_invalid_output(monkeypatch, contacts, rules):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"summary":"invalid"}'}}]}
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    provider = OpenAICompatibleProvider(
        Settings(
            _env_file=None,
            ai_enabled=True,
            llm_api_key="synthetic-test-key",
            llm_model="test-model",
        )
    )
    c = contacts[4]
    result = agent_result(c, evaluate(c, rules, TODAY), provider)
    assert result["mode"] == "fallback"
    assert str(requests[0].url).endswith("/v1/chat/completions")
    assert c.company.encode() not in requests[0].content


def test_backwards_dates_rejected(service):
    e = service.enroll("SYN-00003", "lead-nurture", TODAY)
    with pytest.raises(ConflictError):
        service.advance(e["id"], TODAY - timedelta(days=1))
    draft = service.create_draft("SYN-00003", TODAY)
    with pytest.raises(ConflictError):
        service.transition_draft(draft["id"], "approve", "Reviewer", TODAY - timedelta(days=1))
