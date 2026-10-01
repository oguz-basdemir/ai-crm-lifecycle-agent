from datetime import timedelta

import pytest
from pydantic import ValidationError

from crm_agent.config import Rules
from crm_agent.decisions import evaluate, score_contact
from crm_agent.models import Contact
from crm_agent.synthetic import generate_contacts
from tests.conftest import TODAY


def test_seed_is_reproducible(contacts):
    assert contacts == generate_contacts(18, 42, TODAY)
    assert all(c.synthetic and c.contact_id.startswith("SYN-") for c in contacts)


@pytest.mark.parametrize(
    "index,stage",
    list(
        enumerate(
            [
                "Subscriber",
                "Lead",
                "MQL",
                "SQL",
                "Opportunity",
                "Customer",
                "At Risk",
                "Churned",
                "Win-back",
            ]
        )
    ),
)
def test_all_lifecycle_stages(index, stage, contacts, rules):
    assert evaluate(contacts[index], rules, TODAY).lifecycle == stage


def test_score_explanation_reconciles(contacts, rules):
    for c in contacts:
        score = score_contact(c, rules, TODAY)
        assert score.raw_value == sum(x.points for x in score.contributions)
        assert score.value == min(100, max(0, score.raw_value))


def test_score_caps_high_and_low(contacts, rules):
    rules.weights.demo = 30
    assert score_contact(contacts[4], rules, TODAY).value == 100
    c = contacts[0].model_copy(
        update={"last_activity": TODAY - timedelta(days=50), "acquisition_source": "Unknown"}
    )
    assert score_contact(c, rules, TODAY).value == 0


@pytest.mark.parametrize(
    "days,factor",
    [(7, "recent"), (8, None), (13, None), (14, "aging"), (29, "aging"), (30, "inactive")],
)
def test_recency_boundaries(days, factor, contacts, rules):
    c = contacts[0].model_copy(update={"last_activity": TODAY - timedelta(days=days)})
    factors = {x.factor for x in score_contact(c, rules, TODAY).contributions}
    assert factors.intersection({"recent", "aging", "inactive"}) == ({factor} if factor else set())


@pytest.mark.parametrize("field,value", [("unsubscribed", True), ("marketing_consent", False)])
def test_suppression_overrides_high_intent(field, value, contacts, rules):
    d = evaluate(contacts[4].model_copy(update={field: value}), rules, TODAY)
    assert d.action == "no action" and d.suppressed


def test_customer_risk_precedes_score(contacts, rules):
    c = contacts[5].model_copy(update={"demo_requested": True, "usage_decline": 40})
    assert evaluate(c, rules, TODAY).lifecycle == "At Risk"


def test_segments_and_action_priorities(contacts, rules):
    new = contacts[5].model_copy(
        update={"customer_since": TODAY - timedelta(days=10), "product_usage": 90}
    )
    d = evaluate(new, rules, TODAY)
    assert set(d.segments) == {"new customers", "expansion candidates"}
    assert d.action == "product education"
    expansion = contacts[5].model_copy(
        update={"customer_since": TODAY - timedelta(days=90), "product_usage": 90}
    )
    assert evaluate(expansion, rules, TODAY).action == "upsell"
    assert evaluate(contacts[1], rules, TODAY).action == "reactivation"


def test_config_changes_classification(contacts, rules):
    rules.mql_score = 70
    rules.sql_score = 75
    rules.opportunity_score = 90
    assert evaluate(contacts[2], rules, TODAY).lifecycle == "Lead"


def test_invalid_policy_rejected():
    with pytest.raises(ValidationError):
        Rules(mql_score=80, sql_score=65)


def test_invalid_or_real_contact_rejected(contacts):
    for changes in (
        {"synthetic": False},
        {"contact_id": "REAL-1"},
        {"product_usage": -1},
        {"last_activity": "2020-01-01"},
        {"email": "person@example.com"},
    ):
        with pytest.raises(ValidationError):
            Contact.model_validate({**contacts[0].model_dump(), **changes})


def test_future_profile_rejected(contacts, rules):
    with pytest.raises(ValueError):
        evaluate(contacts[0], rules, contacts[0].created_at - timedelta(days=1))
