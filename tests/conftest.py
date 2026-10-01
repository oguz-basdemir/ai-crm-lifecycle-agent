from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crm_agent.api import create_app
from crm_agent.config import Settings, load_rules
from crm_agent.repository import Repository
from crm_agent.service import CRMService
from crm_agent.synthetic import generate_contacts
from crm_agent.workflows import default_workflows

TODAY = date(2026, 10, 1)
RULES_PATH = str(Path(__file__).resolve().parents[1] / "config" / "rules.json")


@pytest.fixture
def rules():
    return load_rules(RULES_PATH)


@pytest.fixture
def contacts():
    return generate_contacts(18, 42, TODAY)


@pytest.fixture
def service(tmp_path, rules, contacts):
    repo = Repository(str(tmp_path / "test.db"))
    repo.initialize()
    repo.seed(contacts)
    service = CRMService(repo, rules)
    for w in default_workflows():
        service.save_workflow(w)
    return service


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        _env_file=None,
        database_path=str(tmp_path / "api.db"),
        rules_path=RULES_PATH,
        seed_count=18,
        ai_enabled=False,
    )
    with TestClient(create_app(settings)) as client:
        yield client
