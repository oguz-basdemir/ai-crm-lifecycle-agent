from datetime import date


def test_health_reports_and_missing(client):
    assert client.get("/health").json()["delivery"] == "simulation-only"
    assert client.get("/reports").json()["contacts"] == 18
    assert client.get("/contacts/SYN-99999").status_code == 404
    assert client.get("/rules").json()["mql_score"] == 45
    assert len(client.get("/workflows").json()) == 3
    assert client.get("/openapi.json").status_code == 200


def test_api_review_flow(client):
    draft = client.post("/drafts", json={"contact_id": "SYN-00005"}).json()
    path = f"/drafts/{draft['id']}"
    assert client.post(path + "/simulate-send", json={"actor": "Reviewer"}).status_code == 409
    assert client.post(path + "/approve", json={"actor": "Reviewer"}).status_code == 422
    assert (
        client.post(
            path + "/approve", json={"actor": "Reviewer", "human_approval": True}
        ).status_code
        == 200
    )
    assert (
        client.post(path + "/simulate-send", json={"actor": "Reviewer"}).json()["status"]
        == "simulated"
    )
    assert client.get("/reports").json()["simulated_sends"] == 1


def test_create_update_invalid_and_conflicts(client):
    c = client.get("/contacts/SYN-00001").json()
    c["pages_viewed"] = 12
    assert client.put("/contacts/SYN-00001", json=c).json()["version"] == 2
    assert client.put("/contacts/SYN-00001", json=c).status_code == 409
    c["contact_id"] = "SYN-99999"
    assert client.post("/contacts", json=c).status_code == 201
    assert client.post("/contacts", json=c).status_code == 409
    c["synthetic"] = False
    assert client.post("/contacts", json=c).status_code == 422


def test_agent_and_workflow_api(client):
    advice = client.post("/agent", json={"contact_id": "SYN-00003", "use_ai": True}).json()
    assert advice["mode"] == "fallback"
    assert client.get("/drafts").json() == []
    e = client.post("/enrollments", json={"contact_id": "SYN-00003", "workflow": "lead-nurture"})
    assert e.status_code == 201
    result = client.post(
        f"/enrollments/{e.json()['id']}/advance", json={"as_of": date.today().isoformat()}
    ).json()
    assert result["draft_id"]
    assert (
        client.post(
            "/enrollments", json={"contact_id": "SYN-00001", "workflow": "onboarding"}
        ).status_code
        == 409
    )
    assert (
        client.post("/tasks", json={"contact_id": "SYN-00003", "title": "Review demo"}).status_code
        == 201
    )
    assert client.get("/audit").json()
