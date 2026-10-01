"""Pure, explainable decisions. AI never changes the authoritative policy output."""

from datetime import date

from crm_agent.config import Rules
from crm_agent.models import Contact, Contribution, Decision, Score, Stage


def score_contact(contact: Contact, rules: Rules, as_of: date) -> Score:
    if contact.last_activity > as_of or contact.created_at > as_of:
        raise ValueError("Contact dates cannot be in the future")
    days = (as_of - contact.last_activity).days
    w = rules.weights
    factors: list[Contribution] = []

    def add(condition: bool, factor: str, points: int, reason: str) -> None:
        if condition:
            factors.append(Contribution(factor=factor, points=points, reason=reason))

    add(contact.demo_requested, "demo", w.demo, "Demo requested: explicit buying intent")
    add(
        rules.icp_min_size <= contact.company_size <= rules.icp_max_size,
        "icp_size",
        w.icp_size,
        "Company size matches the ideal customer profile",
    )
    add(
        contact.industry in rules.icp_industries,
        "icp_industry",
        w.icp_industry,
        "Industry matches the ideal customer profile",
    )
    add(contact.pages_viewed >= 10, "pages", w.pages, "At least 10 website pages viewed")
    add(contact.content_downloads >= 2, "downloads", w.downloads, "At least 2 content downloads")
    add(contact.email_opens >= 3, "opens", w.opens, "At least 3 email opens (weak signal)")
    add(contact.email_clicks >= 2, "clicks", w.clicks, "At least 2 email clicks")
    source = rules.source_points.get(contact.acquisition_source, 0)
    add(source > 0, "source", source, f"Acquisition source: {contact.acquisition_source}")
    add(days <= 7, "recent", w.recent, "Active in the last 7 days")
    add(14 <= days < rules.inactive_days, "aging", w.aging, "No activity for at least 14 days")
    add(
        days >= rules.inactive_days,
        "inactive",
        w.inactive,
        f"No activity for at least {rules.inactive_days} days",
    )
    raw = sum(item.points for item in factors)
    return Score(value=max(0, min(100, raw)), raw_value=raw, contributions=factors)


def classify(c: Contact, score: Score, r: Rules, today: date) -> tuple[Stage, str]:
    """First matching rule wins; customer retention takes precedence over acquisition."""
    days = (today - c.last_activity).days
    if c.customer_status == "churned":
        if c.winback_eligible and c.marketing_consent and not c.unsubscribed:
            return "Win-back", "Churned customer is eligible for a consented win-back journey"
        return "Churned", "Churned customer is not eligible for win-back"
    if c.customer_status != "prospect":
        if (
            c.customer_status == "inactive"
            or days >= r.risk_days
            or c.usage_decline >= 40
            or c.support_tickets >= 4
        ):
            return "At Risk", "Customer has inactivity, declining usage, or elevated support needs"
        return "Customer", "Active customer without configured risk signals"
    if c.demo_requested and score.value >= r.opportunity_score:
        return (
            "Opportunity",
            "Demo requested and opportunity score threshold reached (simulated deal proxy)",
        )
    if c.demo_requested and score.value >= r.sql_score:
        return "SQL", "Demo requested and SQL threshold reached"
    if score.value >= r.mql_score:
        return "MQL", "Marketing qualification score threshold reached"
    if c.pages_viewed or c.content_downloads or c.email_clicks or c.demo_requested:
        return "Lead", "Prospect has measurable activity below the MQL threshold"
    return "Subscriber", "Prospect has only subscription-level engagement"


def evaluate(c: Contact, r: Rules, today: date) -> Decision:
    score = score_contact(c, r, today)
    stage, reason = classify(c, score, r, today)
    days = (today - c.last_activity).days
    segments: list[str] = []
    if c.customer_status == "prospect" and (c.demo_requested or stage in ("SQL", "Opportunity")):
        segments.append("high-intent prospects")
    if c.customer_status == "prospect" and days >= r.inactive_days:
        segments.append("inactive leads")
    if (
        stage == "Customer"
        and c.customer_since
        and (today - c.customer_since).days <= r.new_customer_days
    ):
        segments.append("new customers")
    if stage == "Customer" and c.product_usage >= r.expansion_usage:
        segments.append("expansion candidates")
    if stage == "At Risk":
        segments.append("churn-risk customers")
    if stage == "Win-back":
        segments.append("win-back candidates")
    suppressed = c.unsubscribed or not c.marketing_consent
    if suppressed or stage == "Churned":
        action, why = (
            "no action",
            "Communication suppressed by consent, unsubscribe, or win-back eligibility",
        )
    elif stage in ("SQL", "Opportunity"):
        action, why = "sales outreach", "Qualified demo intent merits a human sales conversation"
    elif stage in ("At Risk", "Win-back") or "inactive leads" in segments:
        action, why = (
            "reactivation",
            "Address inactivity or retention risk with a helpful reactivation message",
        )
    elif "new customers" in segments:
        action, why = "product education", "Recent customers benefit from activation and onboarding"
    elif "expansion candidates" in segments:
        action, why = "upsell", "Healthy, high product usage suggests an expansion conversation"
    elif stage == "Customer":
        action, why = (
            "product education",
            "Provide practical adoption guidance for a healthy customer",
        )
    else:
        action, why = (
            "nurture email",
            "Relevant education can build intent before sales qualification",
        )
    return Decision(
        contact_id=c.contact_id,
        as_of=today,
        policy_version=r.version,
        score=score,
        lifecycle=stage,
        lifecycle_reason=reason,
        segments=segments,
        action=action,
        action_reason=why,
        suppressed=suppressed,
    )
