"""Streamlit presentation adapter. All mutations go through FastAPI."""

import json
from datetime import date

import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from crm_agent.config import Settings

load_dotenv()
settings = Settings()
st.set_page_config(page_title="Lifecycle Lab | AI CRM", page_icon="◈", layout="wide")
st.markdown(
    """<style>
.stApp { background: #0b1220; }
[data-testid="stMetric"] {background:#152238;border:1px solid #293b55;border-radius:12px;padding:18px;}
.hero {padding:24px 28px;background:linear-gradient(110deg,#152b47,#163b40);border:1px solid #315570;border-radius:16px;margin-bottom:24px;}
.eyebrow {font-size:12px;letter-spacing:3px;color:#60dec0;}
.hero h1 {font-size:36px;margin:8px 0;color:#f4f7fc;}
.hero p {color:#c6d7e8;margin:0;}
</style>""",
    unsafe_allow_html=True,
)


def api(method: str, path: str, body: dict | None = None, params: dict | None = None):
    try:
        response = httpx.request(
            method, settings.api_url.rstrip("/") + path, json=body, params=params, timeout=65
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", "Request failed")
        except ValueError:
            detail = "API returned an invalid response"
        st.error(f"API {exc.response.status_code}: {detail}")
    except httpx.RequestError:
        st.error("Cannot reach the CRM API. Start: python -m uvicorn crm_agent.api:app --port 8000")
    return None


with st.sidebar:
    st.markdown("## ◈ Lifecycle Lab")
    st.caption("MARKETING OPERATIONS WORKSPACE")
    page = st.radio(
        "Workspace",
        [
            "CRM Overview",
            "Funnel",
            "Lead Scoring",
            "Segments",
            "Lifecycle Journeys",
            "At-Risk Customers",
            "AI Recommendations",
        ],
    )
    as_of = st.date_input("Simulation date", date.today())
    st.caption(
        "Use a future date to evaluate inactivity and workflow delays. Profile edits use today’s date."
    )
    st.divider()
    st.info("Synthetic portfolio prototype. No real CRM, no real people, no email delivery.")

st.markdown(
    f"""<div class="hero"><div class="eyebrow">AI CRM · LIFECYCLE INTELLIGENCE</div>
<h1>{page}</h1><p>Turn customer signals into explainable decisions and human-reviewed journeys.</p></div>""",
    unsafe_allow_html=True,
)
query = {"as_of": as_of.isoformat()}
profiles = api("GET", "/contacts", params=query)
report = api("GET", "/reports", params=query)
if profiles is None or report is None:
    st.stop()
frame = pd.DataFrame(
    [
        {**p, "lead_score": p["score"]["value"], "segments": ", ".join(p["segments"])}
        for p in profiles
    ]
)
columns = [
    "contact_id",
    "company",
    "industry",
    "lifecycle",
    "lead_score",
    "segments",
    "action",
    "product_usage",
]


def contact_select(key: str, options: list[dict] | None = None) -> dict | None:
    items = options if options is not None else profiles
    if not items:
        st.info("No contacts match this view.")
        return None
    selected = st.selectbox(
        "Contact",
        [p["contact_id"] for p in items],
        key=key,
        format_func=lambda value: next(
            f"{p['company']} · {value}" for p in items if p["contact_id"] == value
        ),
    )
    return next(p for p in items if p["contact_id"] == selected)


def show_decision(p: dict) -> None:
    left, right = st.columns([1, 2])
    with left:
        st.metric("Explainable lead score", p["score"]["value"])
        st.write(f"**{p['lifecycle']}** · {p['action']}")
        st.caption(p["lifecycle_reason"])
        st.caption(p["action_reason"])
    with right:
        st.dataframe(pd.DataFrame(p["score"]["contributions"]), hide_index=True, width="stretch")
        st.caption(
            f"Raw score {p['score']['raw_value']}; capped to 0–100. Policy {p['policy_version']}."
        )


if page == "CRM Overview":
    a, b, c, d = st.columns(4)
    a.metric("Synthetic contacts", report["contacts"])
    b.metric("Average lead score", report["average_score"])
    c.metric("Customers at risk", report["at_risk"])
    d.metric("Simulated purchase value · USD", f"${report['purchase_value']:,.0f}")
    st.subheader("Customer signal workspace")
    search = st.text_input("Search company or contact ID")
    filtered = frame[
        frame["company"].str.contains(search, case=False, regex=False)
        | frame["contact_id"].str.contains(search, case=False, regex=False)
    ]
    st.dataframe(filtered[columns], hide_index=True, width="stretch")
    st.download_button(
        "Export synthetic decision report",
        frame[columns].to_csv(index=False),
        "synthetic_crm_report.csv",
        "text/csv",
    )
    with st.expander("Add a synthetic lead or update a profile"):
        selected = contact_select("edit")
        if selected:
            current = api("GET", f"/contacts/{selected['contact_id']}")
            text = st.text_area(
                "Validated profile JSON · change ID for a new contact",
                json.dumps(current, indent=2),
                height=280,
            )
            left, right = st.columns(2)
            if left.button("Save profile update"):
                try:
                    result = api("PUT", f"/contacts/{selected['contact_id']}", json.loads(text))
                    if result:
                        st.rerun()
                except ValueError:
                    st.error("Enter valid JSON")
            if right.button("Create new synthetic contact"):
                try:
                    result = api("POST", "/contacts", json.loads(text))
                    if result:
                        st.rerun()
                except ValueError:
                    st.error("Enter valid JSON")
    with st.expander("Audit trail"):
        st.dataframe(pd.DataFrame(api("GET", "/audit") or []), hide_index=True, width="stretch")

elif page == "Funnel":
    st.subheader("Lifecycle distribution")
    stages = [
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
    funnel = pd.DataFrame(
        {"stage": stages, "contacts": [report["stages"].get(s, 0) for s in stages]}
    ).set_index("stage")
    st.bar_chart(funnel, color="#5cddbf", horizontal=True)
    st.caption(report["funnel_note"])
    st.subheader("Operations queue")
    st.dataframe(
        pd.DataFrame(
            {
                "metric": [
                    "Pending approval",
                    "Simulated sends",
                    "Active workflows",
                    "Suppressed contacts",
                ],
                "count": [
                    report["pending_approvals"],
                    report["simulated_sends"],
                    report["active_workflows"],
                    report["suppressed"],
                ],
            }
        ),
        hide_index=True,
    )

elif page == "Lead Scoring":
    st.subheader("Every point has a reason")
    p = contact_select("score")
    if p:
        show_decision(p)
    st.subheader("Score distribution")
    bands = pd.cut(
        frame["lead_score"],
        bins=[-1, 24, 44, 64, 79, 100],
        labels=["0–24", "25–44", "45–64", "65–79", "80–100"],
    )
    st.bar_chart(bands.value_counts(sort=False), color="#5cddbf")
    with st.expander("Configured business rules"):
        st.json(api("GET", "/rules"))

elif page == "Segments":
    st.subheader("Actionable audiences")
    all_segments = [
        "high-intent prospects",
        "inactive leads",
        "new customers",
        "expansion candidates",
        "churn-risk customers",
        "win-back candidates",
    ]
    segment = st.selectbox("Segment", all_segments)
    matches = [p for p in profiles if segment in p["segments"]]
    st.metric("Segment members", len(matches))
    st.caption("Segments may overlap; suppression still applies to every communication.")
    st.dataframe(
        frame[frame["contact_id"].isin([p["contact_id"] for p in matches])][columns],
        hide_index=True,
        width="stretch",
    )

elif page == "At-Risk Customers":
    risks = [p for p in profiles if p["lifecycle"] == "At Risk"]
    st.metric(
        "Revenue exposure · synthetic USD", f"${sum(p['purchase_value'] for p in risks):,.0f}"
    )
    p = contact_select("risk", risks)
    if p:
        show_decision(p)
        a, b, c = st.columns(3)
        a.metric("Usage decline", f"{p['usage_decline']}%")
        b.metric("Support tickets", p["support_tickets"])
        c.metric("Product usage", f"{p['product_usage']} / 100")
    st.dataframe(
        frame[frame["lifecycle"] == "At Risk"][columns + ["usage_decline", "support_tickets"]],
        hide_index=True,
        width="stretch",
    )

elif page == "Lifecycle Journeys":
    workflows = api("GET", "/workflows") or []
    tabs = st.tabs(["Journey studio", "Enrollments", "Workflow builder"])
    with tabs[0]:
        workflow = st.selectbox("Journey template", workflows, format_func=lambda w: w["name"])
        if workflow:
            st.write(workflow["description"])
            st.dataframe(pd.DataFrame(workflow["steps"]), hide_index=True, width="stretch")
            eligible = [
                p
                for p in profiles
                if p["lifecycle"] in workflow["entry_stages"] and not p["suppressed"]
            ]
            p = contact_select("enroll", eligible)
            if p and st.button("Enroll in simulated journey"):
                if api(
                    "POST",
                    "/enrollments",
                    {
                        "contact_id": p["contact_id"],
                        "workflow": workflow["name"],
                        "as_of": as_of.isoformat(),
                    },
                ):
                    st.success(
                        "Enrolled. Advance the journey to create a draft for human approval."
                    )
    with tabs[1]:
        enrollments = api("GET", "/enrollments") or []
        if enrollments:
            e = st.selectbox(
                "Enrollment",
                enrollments,
                format_func=lambda e: (
                    f"{e['contact_id']} · {e['workflow']['name']} · {e['status']} · step {e['step'] + 1}"
                ),
            )
            st.write(f"Next run: {e['next_run']} · Draft: {e['draft_id'] or 'none'}")
            st.json(e["history"])
            if st.button("Advance one step at simulation date"):
                if api("POST", f"/enrollments/{e['id']}/advance", {"as_of": as_of.isoformat()}):
                    st.rerun()
        else:
            st.info(
                "Enroll a contact to begin. Message steps wait for approval and simulated send in AI Recommendations."
            )
        st.subheader("Sales qualification tasks")
        st.dataframe(pd.DataFrame(api("GET", "/tasks") or []), hide_index=True, width="stretch")
    with tabs[2]:
        with st.form("workflow_builder"):
            name = st.text_input("Unique workflow name", "custom-journey")
            description = st.text_input("Description", "A human-reviewed education journey")
            entry = st.multiselect(
                "Entry lifecycle stages",
                [
                    "Subscriber",
                    "Lead",
                    "MQL",
                    "SQL",
                    "Opportunity",
                    "Customer",
                    "At Risk",
                    "Win-back",
                ],
                default=["MQL"],
            )
            steps = st.data_editor(
                pd.DataFrame(
                    [
                        {"kind": "message", "label": "Relevant education", "delay_days": 0},
                        {"kind": "check", "label": "Engagement review", "delay_days": 5},
                    ]
                ),
                num_rows="dynamic",
                hide_index=True,
                column_config={
                    "kind": st.column_config.SelectboxColumn(
                        options=["message", "check", "task"], required=True
                    )
                },
            )
            exit_reactivated = st.checkbox("Exit when customer reactivates")
            if st.form_submit_button("Save workflow template"):
                if api(
                    "POST",
                    "/workflows",
                    {
                        "name": name,
                        "description": description,
                        "entry_stages": entry,
                        "steps": steps.to_dict("records"),
                        "exit_on_reactivation": exit_reactivated,
                    },
                ):
                    st.rerun()

elif page == "AI Recommendations":
    p = contact_select("ai")
    use_ai = st.toggle("Use optional external LLM", value=False)
    st.caption(
        "External AI requires .env configuration. Disabled or unavailable AI falls back to deterministic content. AI receives synthetic behavioral fields."
    )
    if p:
        show_decision(p)
        left, right = st.columns(2)
        if left.button("Run CRM Agent"):
            result = api(
                "POST",
                "/agent",
                {"contact_id": p["contact_id"], "as_of": as_of.isoformat(), "use_ai": use_ai},
            )
            if result:
                st.session_state["advice"] = result
        if right.button("Create unapproved message draft", disabled=p["action"] == "no action"):
            if api(
                "POST",
                "/drafts",
                {"contact_id": p["contact_id"], "as_of": as_of.isoformat(), "use_ai": use_ai},
            ):
                st.success("Draft created. Review below before approving.")
        if st.session_state.get("advice", {}).get("contact_id") == p["contact_id"]:
            st.json(st.session_state["advice"])
    st.divider()
    st.subheader("Human approval inbox")
    drafts = api("GET", "/drafts") or []
    if drafts:
        draft = st.selectbox(
            "Draft",
            list(reversed(drafts)),
            format_func=lambda d: f"{d['contact_id']} · {d['status']} · {d['id'][:8]}",
        )
        st.write(f"**{draft['message']['subject']}**")
        st.text(draft["message"]["email"])
        st.write(f"CTA: {draft['message']['cta']}")
        st.caption(f"Angle: {draft['message']['angle']} · Mode: {draft['mode']}")
        if draft.get("warning"):
            st.warning(draft["warning"])
        actor = st.text_input("Reviewer name (demo identity)", "Portfolio reviewer")
        approved = st.checkbox(
            "I reviewed this exact message and approve its simulated send",
            key=f"approval-{draft['id']}",
        )
        a, b, c = st.columns(3)
        body = {"actor": actor, "as_of": as_of.isoformat(), "human_approval": approved}
        if a.button(
            "Approve reviewed draft", disabled=not approved or draft["status"] != "pending"
        ):
            if api("POST", f"/drafts/{draft['id']}/approve", body):
                st.rerun()
        if b.button("Reject draft", disabled=draft["status"] != "pending"):
            if api("POST", f"/drafts/{draft['id']}/reject", body):
                st.rerun()
        if c.button("Record simulated send", disabled=draft["status"] != "approved"):
            if api("POST", f"/drafts/{draft['id']}/simulate-send", body):
                st.rerun()
    else:
        st.info("No drafts yet. Create a recommendation draft or advance a workflow message step.")
