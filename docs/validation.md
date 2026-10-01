# Validation record

Validated locally on October 1, 2026 using Python 3.14 on Windows.

- **58 tests passed**, including domain boundaries, persistence, approval gates, concurrent idempotency, temporal ordering, policy invalidation, three journeys, mock CRM integration, mocked LLM HTTP/schema failures, all seven dashboard views, and UI approval controls.
- `ruff check` and `ruff format --check` passed.
- `pip check` found no dependency conflicts.
- FastAPI `/health` verified `synthetic: true` and `delivery: simulation-only`.
- The live Streamlit app was inspected through headless Chrome; five actual screenshots are committed under `docs/screenshots/`.
- README relative links were checked for existing targets.

One dependency emits a deprecation warning for Starlette’s use of AnyIO’s `BlockingPortal` alias. It does not fail the tests.

Docker is not installed on the authoring machine, so the image and Compose startup were not locally executed. GitHub Actions includes container build, Compose startup, and both service health checks. Remote results are available in the [Actions tab](https://github.com/oguz-basdemir/ai-crm-lifecycle-agent/actions).

No live LLM call was made. Provider behavior is verified with a mocked compatible HTTP transport, and the running demo uses deterministic templates.
