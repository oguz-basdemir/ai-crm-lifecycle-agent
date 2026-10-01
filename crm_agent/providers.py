"""CRM adapter port; mock writes local records and never contacts a real CRM."""

from datetime import date
from typing import Protocol

from crm_agent.decisions import evaluate
from crm_agent.models import Contact
from crm_agent.service import CRMService


class CRMProvider(Protocol):
    def get_contacts(self) -> list[Contact]: ...
    def update_contact(self, contact: Contact) -> Contact: ...
    def create_task(self, contact_id: str, title: str) -> dict: ...
    def enroll_in_workflow(self, contact_id: str, workflow: str, today: date) -> dict: ...


class MockCRMProvider:
    def __init__(self, service: CRMService):
        self.service = service

    def get_contacts(self) -> list[Contact]:
        return self.service.repo.contacts()

    def update_contact(self, contact: Contact) -> Contact:
        evaluate(contact, self.service.rules, date.today())
        return self.service.repo.save_contact(contact)

    def create_task(self, contact_id: str, title: str) -> dict:
        with self.service.repo.transaction() as db:
            self.service.repo.contact(contact_id, db)
            task = self.service.repo.put_object(
                "task", {"contact_id": contact_id, "title": title, "status": "open"}, db
            )
            self.service.repo.audit(db, "mock_task_created", contact_id, {"task_id": task["id"]})
            return task

    def enroll_in_workflow(self, contact_id: str, workflow: str, today: date) -> dict:
        return self.service.enroll(contact_id, workflow, today)
