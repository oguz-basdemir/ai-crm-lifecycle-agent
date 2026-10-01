from datetime import timedelta

import pytest

from crm_agent.repository import ConflictError
from tests.conftest import TODAY


def test_workflow_tick_cannot_precede_recorded_send(service):
    e = service.enroll("SYN-00003", "lead-nurture", TODAY)
    e = service.advance(e["id"], TODAY)
    tomorrow = TODAY + timedelta(days=1)
    service.transition_draft(e["draft_id"], "approve", "Reviewer", tomorrow)
    service.transition_draft(e["draft_id"], "simulate-send", "Reviewer", tomorrow)
    with pytest.raises(ConflictError, match="precede"):
        service.advance(e["id"], TODAY)
    assert service.advance(e["id"], tomorrow)["step"] == 1


def test_send_cannot_precede_approval(service):
    d = service.create_draft("SYN-00003", TODAY)
    service.transition_draft(d["id"], "approve", "Reviewer", TODAY + timedelta(days=1))
    with pytest.raises(ConflictError, match="precede approval"):
        service.transition_draft(d["id"], "simulate-send", "Reviewer", TODAY)


def test_policy_version_change_invalidates_approval(service):
    d = service.create_draft("SYN-00003", TODAY)
    service.rules.version = "new-policy"
    with pytest.raises(ConflictError, match="decision changed"):
        service.transition_draft(d["id"], "approve", "Reviewer", TODAY)
