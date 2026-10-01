"""Export reproducible synthetic examples and their decisions."""

import json
from datetime import date
from pathlib import Path

from crm_agent.config import load_rules
from crm_agent.decisions import evaluate
from crm_agent.synthetic import generate_contacts

root = Path(__file__).resolve().parents[1]
rules = load_rules(str(root / "config" / "rules.json"))
today = date(2026, 10, 1)
contacts = generate_contacts(18, today=today)
(root / "data" / "sample_contacts.json").write_text(
    json.dumps([c.model_dump(mode="json") for c in contacts], indent=2) + "\n", encoding="utf-8"
)
(root / "data" / "sample_decisions.json").write_text(
    json.dumps([evaluate(c, rules, today).model_dump(mode="json") for c in contacts], indent=2)
    + "\n",
    encoding="utf-8",
)
