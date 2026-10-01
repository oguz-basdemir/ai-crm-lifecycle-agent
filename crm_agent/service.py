"""Application orchestration with transactional approval and workflow gates."""

from datetime import date, timedelta
from typing import Any

from crm_agent.config import Rules
from crm_agent.decisions import evaluate
from crm_agent.llm import LLMProvider, agent_result, template_message
from crm_agent.models import Workflow
from crm_agent.repository import ConflictError, Repository


class CRMService:
    def __init__(self, repository: Repository, rules: Rules, provider: LLMProvider | None = None):
        self.repo, self.rules, self.provider = repository, rules, provider

    def profiles(self, today: date) -> list[dict]:
        return [
            {**c.model_dump(mode="json"), **evaluate(c, self.rules, today).model_dump(mode="json")}
            for c in self.repo.contacts()
        ]

    def advice(self, contact_id: str, today: date, use_ai: bool = False) -> dict:
        c = self.repo.contact(contact_id)
        result = agent_result(c, evaluate(c, self.rules, today), self.provider if use_ai else None)
        if use_ai and self.provider is None:
            result.update(mode="fallback", warning="AI disabled; deterministic template used")
        return result

    def create_draft(self, contact_id: str, today: date, use_ai: bool = False) -> dict:
        c = self.repo.contact(contact_id)
        d = evaluate(c, self.rules, today)
        if d.action == "no action":
            raise ConflictError("Contact is suppressed or has no recommended communication")
        advice = self.advice(contact_id, today, use_ai)
        with self.repo.transaction() as db:
            if self.repo.contact(contact_id, db).version != c.version:
                raise ConflictError("Profile changed during generation; regenerate the draft")
            draft = self.repo.put_object(
                "draft",
                {
                    "contact_id": contact_id,
                    "contact_version": c.version,
                    "decision": d.model_dump(mode="json"),
                    "message": advice["suggested_message"],
                    "mode": advice["mode"],
                    "warning": advice["warning"],
                    "status": "pending",
                    "created_on": today.isoformat(),
                    "approved_by": None,
                },
                db,
            )
            self.repo.audit(
                db, "draft_created", contact_id, {"draft_id": draft["id"], "mode": draft["mode"]}
            )
            return draft

    def transition_draft(self, draft_id: str, operation: str, actor: str, today: date) -> dict:
        with self.repo.transaction() as db:
            draft = self.repo.object(draft_id, "draft", db)
            if today < date.fromisoformat(draft["created_on"]):
                raise ConflictError("Review date cannot precede draft creation")
            c = self.repo.contact(draft["contact_id"], db)
            d = evaluate(c, self.rules, today)
            if operation == "reject":
                if draft["status"] != "pending":
                    raise ConflictError("Only pending drafts can be rejected")
                draft.update(status="rejected", reviewed_by=actor)
            else:
                if c.version != draft["contact_version"]:
                    raise ConflictError("Profile changed; regenerate and approve a fresh draft")
                if (
                    d.action == "no action"
                    or d.policy_version != draft["decision"]["policy_version"]
                    or d.lifecycle != draft["decision"]["lifecycle"]
                    or d.action != draft["decision"]["action"]
                ):
                    raise ConflictError("Consent or decision changed; regenerate a fresh draft")
                if operation == "approve":
                    if draft["status"] != "pending":
                        raise ConflictError("Only pending drafts can be approved")
                    draft.update(
                        status="approved", approved_by=actor, approved_on=today.isoformat()
                    )
                elif operation == "simulate-send":
                    if draft.get("approved_on") and today < date.fromisoformat(
                        draft["approved_on"]
                    ):
                        raise ConflictError("Send date cannot precede approval")
                    if draft["status"] == "simulated":
                        return draft  # Idempotent: repeated clicks cannot create duplicate sends.
                    if draft["status"] != "approved" or not draft["approved_by"]:
                        raise ConflictError("Explicit human approval required")
                    draft.update(status="simulated", simulated_on=today.isoformat())
                else:
                    raise ValueError("Unknown draft operation")
            self.repo.put_object("draft", draft, db)
            self.repo.audit(
                db, f"draft_{operation}", c.contact_id, {"draft_id": draft_id, "actor": actor}
            )
            return draft

    def save_workflow(self, workflow: Workflow) -> dict:
        with self.repo.transaction() as db:
            existing = self.repo.objects("workflow", db)
            if any(w["name"] == workflow.name for w in existing):
                raise ConflictError("Workflow name exists; use a new versioned name")
            saved = self.repo.put_object("workflow", workflow.model_dump(mode="json"), db)
            self.repo.audit(db, "workflow_created", None, {"workflow": workflow.name})
            return saved

    def enroll(self, contact_id: str, workflow_name: str, today: date) -> dict:
        with self.repo.transaction() as db:
            c = self.repo.contact(contact_id, db)
            d = evaluate(c, self.rules, today)
            templates = [w for w in self.repo.objects("workflow", db) if w["name"] == workflow_name]
            if not templates:
                raise KeyError("Workflow not found")
            workflow = templates[0]
            if (
                d.suppressed
                or d.action == "no action"
                or d.lifecycle not in workflow["entry_stages"]
            ):
                raise ConflictError("Contact does not satisfy workflow entry and consent rules")
            if any(
                e["contact_id"] == contact_id
                and e["workflow"]["name"] == workflow_name
                and e["status"] == "active"
                for e in self.repo.objects("enrollment", db)
            ):
                raise ConflictError("Contact is already active in this workflow")
            enrollment = self.repo.put_object(
                "enrollment",
                {
                    "contact_id": contact_id,
                    "workflow": workflow,
                    "status": "active",
                    "step": 0,
                    "draft_id": None,
                    "history": [],
                    "last_evaluated": today.isoformat(),
                    "next_run": (
                        today + timedelta(days=workflow["steps"][0]["delay_days"])
                    ).isoformat(),
                },
                db,
            )
            self.repo.audit(
                db,
                "workflow_enrolled",
                contact_id,
                {"enrollment_id": enrollment["id"], "workflow": workflow_name},
            )
            return enrollment

    def advance(self, enrollment_id: str, today: date) -> dict:
        """One step per explicit tick; messages block until approved AND simulated."""
        with self.repo.transaction() as db:
            e = self.repo.object(enrollment_id, "enrollment", db)
            if today < date.fromisoformat(e["last_evaluated"]):
                raise ConflictError("Simulation date cannot move backwards")
            if e["status"] != "active":
                return e
            c = self.repo.contact(e["contact_id"], db)
            d = evaluate(c, self.rules, today)
            e["last_evaluated"] = today.isoformat()
            if d.suppressed or d.action == "no action":
                e["status"] = "exited"
                e["history"].append(
                    {"date": today.isoformat(), "event": "Exited: communication suppressed"}
                )
            elif e["workflow"]["exit_on_reactivation"] and d.lifecycle == "Customer":
                e["status"] = "exited"
                e["history"].append(
                    {"date": today.isoformat(), "event": "Exited: customer reactivated"}
                )
            elif today < date.fromisoformat(e["next_run"]):
                self.repo.put_object("enrollment", e, db)
                return e
            else:
                step = e["workflow"]["steps"][e["step"]]
                if step["kind"] == "message":
                    if e["draft_id"]:
                        draft = self.repo.object(e["draft_id"], "draft", db)
                        if draft["status"] == "simulated" and today < date.fromisoformat(
                            draft["simulated_on"]
                        ):
                            raise ConflictError(
                                "Workflow tick cannot precede its simulated message send"
                            )
                        if draft["status"] == "rejected":
                            e["status"] = "exited"
                            e["history"].append(
                                {"date": today.isoformat(), "event": "Exited: draft rejected"}
                            )
                            self.repo.audit(
                                db,
                                "workflow_exited",
                                c.contact_id,
                                {"enrollment_id": e["id"], "reason": "draft rejected"},
                            )
                            return self.repo.put_object("enrollment", e, db)
                        if draft["status"] != "simulated":
                            # Stale content may never be sent; replace it for a fresh review.
                            stale = draft["contact_version"] != c.version or any(
                                draft["decision"][key] != d.model_dump(mode="json")[key]
                                for key in ("policy_version", "lifecycle", "action")
                            )
                            if not stale:
                                return self.repo.put_object("enrollment", e, db)
                            draft["status"] = "superseded"
                            self.repo.put_object("draft", draft, db)
                            e["draft_id"] = None
                    if not e["draft_id"]:
                        draft = self.repo.put_object(
                            "draft",
                            {
                                "contact_id": c.contact_id,
                                "contact_version": c.version,
                                "decision": d.model_dump(mode="json"),
                                "message": template_message(c, d, step["label"]).model_dump(),
                                "mode": "deterministic",
                                "warning": None,
                                "status": "pending",
                                "approved_by": None,
                                "created_on": today.isoformat(),
                                "enrollment_id": e["id"],
                            },
                            db,
                        )
                        e["draft_id"] = draft["id"]
                        self.repo.audit(
                            db, "workflow_draft_created", c.contact_id, {"draft_id": draft["id"]}
                        )
                        return self.repo.put_object("enrollment", e, db)
                elif step["kind"] == "task":
                    qualified = d.lifecycle in ("SQL", "Opportunity")
                    self.repo.put_object(
                        "task",
                        {
                            "contact_id": c.contact_id,
                            "title": step["label"],
                            "status": "open",
                            "qualification": "SQL ready" if qualified else "Needs further nurture",
                            "enrollment_id": e["id"],
                        },
                        db,
                    )
                e["history"].append(
                    {
                        "date": today.isoformat(),
                        "event": step["label"],
                        "lifecycle": d.lifecycle,
                        "score": d.score.value,
                        "usage": c.product_usage,
                    }
                )
                e["step"] += 1
                e["draft_id"] = None
                if e["step"] == len(e["workflow"]["steps"]):
                    e["status"] = "completed"
                else:
                    e["next_run"] = (
                        today + timedelta(days=e["workflow"]["steps"][e["step"]]["delay_days"])
                    ).isoformat()
            self.repo.put_object("enrollment", e, db)
            self.repo.audit(
                db,
                "workflow_tick",
                c.contact_id,
                {"enrollment_id": e["id"], "status": e["status"], "step": e["step"]},
            )
            return e

    def report(self, today: date) -> dict[str, Any]:
        profiles = self.profiles(today)
        stages: dict[str, int] = {}
        segments: dict[str, int] = {}
        for p in profiles:
            stages[p["lifecycle"]] = stages.get(p["lifecycle"], 0) + 1
            for segment in p["segments"]:
                segments[segment] = segments.get(segment, 0) + 1
        drafts = self.repo.objects("draft")
        return {
            "synthetic": True,
            "as_of": today.isoformat(),
            "contacts": len(profiles),
            "average_score": round(
                sum(p["score"]["value"] for p in profiles) / max(1, len(profiles)), 1
            ),
            "purchase_value": round(sum(p["purchase_value"] for p in profiles), 2),
            "at_risk": stages.get("At Risk", 0),
            "stages": stages,
            "segments": segments,
            "suppressed": sum(p["suppressed"] for p in profiles),
            "pending_approvals": sum(d["status"] == "pending" for d in drafts),
            "simulated_sends": sum(d["status"] == "simulated" for d in drafts),
            "active_workflows": sum(
                e["status"] == "active" for e in self.repo.objects("enrollment")
            ),
            "open_tasks": len(self.repo.objects("task")),
            "funnel_note": "Stage distribution is a point-in-time snapshot, not measured conversion rates.",
        }
