# Contributing

Use synthetic records only. Keep lifecycle and scoring decisions deterministic and explainable. Any new communication flow must preserve explicit human review, re-check consent, reject stale contact versions, and record an audit event. Do not add an email transport to this prototype.

Install `pip install -e '.[dev]'`, then run `python -m ruff check .`, `python -m ruff format --check .`, and `python -m pytest -q`. Tests use temporary SQLite files and do not need network access or API keys. Add behavioral tests for changed decision rules and state transitions.

If you change the UI, update screenshots using a fresh synthetic database. Never include `.env`, local database files, or credential values in a pull request.
