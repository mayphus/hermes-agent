"""``attached = {kind, id}``: what a session is about, set once, listed by the dashboard.

Real store under the isolated HERMES_HOME; the dashboard is driven through its TestClient.
"""
import pytest

from gateway import session_attached
from persistence.core.errors import AuthorityRefusal
from tests.fixtures.storage_seed import seed_session


@pytest.fixture
def store(_isolate_hermes_home):
    from persistence_assembly import open_persistence, profile_scope
    db = open_persistence(profile_scope())
    yield db
    db.close()


@pytest.fixture
def auth_client(_isolate_hermes_home):
    from starlette.testclient import TestClient
    from hermes_cli.web_server import app, _SESSION_HEADER_NAME, _SESSION_TOKEN
    client = TestClient(app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return client


@pytest.mark.parametrize("value", [
    {"kind": "errand", "id": "x"}, {"kind": "task", "id": ""}, {"kind": "task", "id": "x" * 129},
    {"kind": "task"}, {"kind": "task", "id": "x", "extra": 1}, "task:x", {"kind": "task", "id": 7}])
def test_malformed_attachment_is_refused(value):
    with pytest.raises(AuthorityRefusal):
        session_attached.parse(value)


def test_first_writer_wins_and_the_dashboard_lists_by_attachment(store, auth_client):
    for sid in ("chat-a", "chat-b", "chat-c"):
        seed_session(store, sid, "desktop")
    task = session_attached.parse({"kind": "task", "id": "t_123"})
    assert session_attached.set_if_unset(store, "chat-a", task) == task
    # A later prompt naming something else never moves the session.
    assert session_attached.set_if_unset(store, "chat-a", {"kind": "decision", "id": "d1"}) == task
    session_attached.set_if_unset(store, "chat-b", {"kind": "project", "id": "p1"})

    listed = auth_client.get("/api/sessions", params={"attached_kind": "task", "attached_id": "t_123"}).json()
    assert [row["id"] for row in listed["sessions"]] == ["chat-a"] and listed["total"] == 1
    assert listed["sessions"][0]["attached"] == {"kind": "task", "id": "t_123"}
    assert "system_prompt" not in listed["sessions"][0]
    assert auth_client.get("/api/sessions", params={"attached_kind": "decision", "attached_id": "d1"}).json()["total"] == 0
    assert auth_client.get("/api/sessions", params={"attached_kind": "errand", "attached_id": "x"}).status_code == 400


def test_task_listing_includes_the_session_its_kanban_card_names(store, auth_client):
    from hermes_cli import kanban_db as kb
    from hermes_cli.kanban_db_connect import connect_closing
    seed_session(store, "errand-chat", "desktop")
    kb.init_db()
    with connect_closing() as conn:
        task_id = kb.create_task(conn, title="buy filters", triage=True, session_id="errand-chat")
    listed = auth_client.get("/api/sessions", params={"attached_kind": "task", "attached_id": task_id}).json()
    assert [row["id"] for row in listed["sessions"]] == ["errand-chat"]


def test_unauthenticated_listing_is_refused(_isolate_hermes_home):
    from starlette.testclient import TestClient
    from hermes_cli.web_server import app
    response = TestClient(app).get("/api/sessions", params={"attached_kind": "task", "attached_id": "t"})
    assert response.status_code == 401
