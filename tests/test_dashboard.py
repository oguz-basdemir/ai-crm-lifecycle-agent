"""Exercise every Streamlit view against the real API through an in-process client."""

from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

PAGES = [
    "CRM Overview",
    "Funnel",
    "Lead Scoring",
    "Segments",
    "Lifecycle Journeys",
    "At-Risk Customers",
    "AI Recommendations",
]


@pytest.mark.parametrize("page", PAGES)
def test_dashboard_views(page, client, monkeypatch):
    def request(method, url, **kwargs):
        path = httpx.URL(url).path
        kwargs.pop("timeout", None)
        return client.request(method, path, **kwargs)

    monkeypatch.setattr(httpx, "request", request)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py"))
    app.run(timeout=20)
    if page != "CRM Overview":
        app.sidebar.radio[0].set_value(page).run(timeout=20)
    assert not app.exception
    assert not app.error
    assert page in app.markdown[1].value


def test_dashboard_review_controls(client, monkeypatch):
    def request(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return client.request(method, httpx.URL(url).path, **kwargs)

    monkeypatch.setattr(httpx, "request", request)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")).run(
        timeout=20
    )
    app.sidebar.radio[0].set_value("AI Recommendations").run()
    app.selectbox[0].select("SYN-00005").run()
    app.button[1].click().run()
    assert client.get("/drafts").json()[0]["status"] == "pending"
    assert app.button[2].disabled  # Approval unavailable until explicit review.
    app.checkbox[0].check().run()
    app.button[2].click().run()
    assert client.get("/drafts").json()[0]["status"] == "approved"
    app.button[4].click().run()
    assert client.get("/reports").json()["simulated_sends"] == 1
    assert not app.exception
