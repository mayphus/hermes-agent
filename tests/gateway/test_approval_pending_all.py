"""Behaviour contract of ``approval.pending_all``: the cross-session list of prompts parked on the user.

Runs against real ``PendingControls``; only the authority's session table and its read gate are stubbed.
"""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from gateway.session_ancillary import pending_all
from gateway.session_pending_controls import PendingControls
from persistence.core.errors import AuthorityRefusal


class _Events:
    def __init__(self):
        self.lock = threading.RLock()
        self.published = []

    def publish(self, session_id, payload, event_type=None):
        self.published.append(event_type)


def _clarify(controls, session_id, prompt_id, question, generation=1):
    entry = SimpleNamespace(clarify_id=prompt_id, question=question, choices=["A", "B"], multi_select=False,
                            event=threading.Event())
    controls.register_clarify(session_id, generation, entry)
    return entry


def _connection(sessions, *, readable, capabilities=frozenset({"session:read"})):
    def authorize(actor, ref, capability):
        if ref.session_id not in readable:
            raise AuthorityRefusal("permission_denied")
    authority = SimpleNamespace(sessions=sessions, authorize=authorize)
    return SimpleNamespace(authority=authority, actor=SimpleNamespace(profile_id="p", capabilities=capabilities))


def test_lists_open_prompts_across_readable_sessions_without_settling_them():
    mine, other, answered = (PendingControls(_Events()) for _ in range(3))
    _clarify(mine, "s1", "q1", "Pick a colour")
    mine.register("s1", None, 2, {"request_id": "a1", "command": "rm -rf build", "description": "delete build"})
    mine.remote_responders["a1"] = lambda *args: None  # a worker-held approval reads as open
    _clarify(other, "s2", "q2", "Not yours")
    _clarify(answered, "s3", "q3", "Already answered").event.set()
    published = {sid: list(c.events.published) for sid, c in (("s1", mine), ("s2", other), ("s3", answered))}
    sessions = {sid: SimpleNamespace(controls=c) for sid, c in (("s1", mine), ("s2", other), ("s3", answered))}

    rows = asyncio.run(pending_all(_connection(sessions, readable={"s1", "s3"}), None, {}))["prompts"]

    assert [(r["session_id"], r["request_id"], r["kind"]) for r in rows] == [("s1", "q1", "clarify"),
                                                                            ("s1", "a1", "approval")]
    assert rows[0]["choices"] == ["A", "B"] and rows[1]["choices"] == ["once", "deny", "session", "always"]
    assert rows[1]["summary"] == "delete build — rm -rf build" and rows[1]["execution_generation"] == 2
    assert all(isinstance(r["since"], float) for r in rows)
    # Read-only: nothing settled or re-published, the answered prompt is still held for its own viewer.
    assert {sid: list(c.events.published) for sid, c in (("s1", mine), ("s2", other), ("s3", answered))} == published
    assert "q3" in answered.pending


def test_summary_is_redacted_and_bounded():
    controls = PendingControls(_Events())
    secret = "sk-ant-api03-" + "x" * 40
    _clarify(controls, "s1", "q1", f"Use key {secret}? " + "word " * 100)
    rows = asyncio.run(pending_all(_connection({"s1": SimpleNamespace(controls=controls)}, readable={"s1"}),
                                   None, {}))["prompts"]
    assert secret not in rows[0]["summary"] and len(rows[0]["summary"]) <= 200


def test_refuses_without_read_capability_or_unknown_params():
    connection = _connection({}, readable=set(), capabilities=frozenset())
    with pytest.raises(AuthorityRefusal):
        asyncio.run(pending_all(connection, None, {}))
    with pytest.raises(AuthorityRefusal):
        asyncio.run(pending_all(_connection({}, readable=set()), None, {"session_id": "s1"}))
