"""Worker provenance is not a dependency edge or a transient runtime session."""
import json

import pytest

from hermes_state import SessionDB


@pytest.mark.parametrize("linked,explicit", [(False, None), (True, None), (False, "override")])
def test_worker_create_keeps_durable_origin(tmp_path, monkeypatch, linked, explicit):
    from hermes_cli import kanban_db as kb, kanban_db_connect as kbc, kanban_db_notify as kn
    from tools import kanban_tools as kt, async_delegation
    from gateway.session_context import set_session_vars, clear_session_vars

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    kb.init_db()
    with kbc.connect_closing() as conn:
        owner = kb.create_task(conn, title="owner", session_id="durable")
        kn.add_notify_sub(conn, task_id=owner, platform="discord", chat_id="chat",
                          user_id="user", notifier_profile="default", delivery_mode="notify",
                          delivery_metadata={"scope_id": "guild", "parent_chat_id": "forum"})
        expected = kn.list_notify_subs(conn, owner)[0]
    if explicit:
        state = SessionDB(db_path=tmp_path / "state.db")
        state.create_session(explicit, source="cli")
        state.close()
    monkeypatch.setenv("HERMES_KANBAN_TASK", owner)
    monkeypatch.setenv("HERMES_SESSION_ID", "ephemeral")
    monkeypatch.setattr(async_delegation, "_current_origin_session_id", lambda: "api-origin")
    # Even a matching current channel must not upgrade an inherited passive policy.
    tokens = set_session_vars(platform="discord", chat_id="chat", profile="default")
    try:
        result = json.loads(kt._handle_create(dict(title="child", assignee="default",
                            parents=[owner] if linked else [], session_id=explicit)))
    finally:
        clear_session_vars(tokens)
    assert result["ok"], result
    with kbc.connect_closing() as conn:
        child = kb.get_task(conn, result["task_id"])
        assert child.session_id == (explicit or "durable")
        subs = kn.list_notify_subs(conn, child.id)
        assert len(subs) == 1
        for key in ("platform", "chat_id", "user_id", "delivery_mode", "delivery_metadata", "notifier_profile"):
            assert subs[0][key] == expected[key]
        assert bool(conn.execute("SELECT 1 FROM task_links WHERE child_id = ?", (child.id,)).fetchone()) == linked


def test_tool_subscription_captures_conversation_anchors(tmp_path, monkeypatch):
    from hermes_cli import kanban_db as kb, kanban_db_connect as kbc, kanban_db_notify as kn
    from tools import kanban_tools as kt
    from gateway.session_context import set_session_vars, clear_session_vars

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    kb.init_db()
    tokens = set_session_vars(platform="discord", chat_id="thread", chat_type="thread",
                             scope_id="guild", parent_chat_id="forum", profile="default")
    try:
        result = json.loads(kt._handle_create(dict(title="direct", assignee="default")))
    finally:
        clear_session_vars(tokens)
    assert result["ok"], result
    with kbc.connect_closing() as conn:
        metadata = kn.list_notify_subs(conn, result["task_id"])[0]["delivery_metadata"]
        assert metadata["scope_id"] == "guild"
        assert metadata["parent_chat_id"] == "forum"


@pytest.mark.parametrize(("session_id", "persisted"), [
    ("phantom-session", False),
    ("persisted-session", True),
])
def test_tool_create_only_stamps_persisted_ambient_session(tmp_path, monkeypatch, session_id, persisted):
    """Ambient worker ids are provenance only after their state.db row exists."""
    from hermes_cli import kanban_db as kb, kanban_db_connect as kbc
    from tools import kanban_tools as kt
    from gateway.session_context import scoped_current_session_id

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    kb.init_db()
    state = SessionDB(db_path=tmp_path / "state.db")
    if persisted:
        state.create_session(session_id, source="cli")
    state.close()

    # Bound the way agent construction publishes it (ContextVar); a bare os.environ value is
    # masked once a surface has cleared its session vars, so it is not a stand-in here. The env
    # var is set too so the reporter's unverified-env path (the pre-fix stamping seam) is exercised.
    monkeypatch.setenv("HERMES_SESSION_ID", session_id)
    with scoped_current_session_id(session_id):
        result = json.loads(kt._handle_create({"title": "child", "assignee": "default"}))
    with kbc.connect_closing() as conn:
        task = kb.get_task(conn, result["task_id"])
    assert task.session_id == (session_id if persisted else None)


def test_tool_create_stamps_request_scoped_session_over_process_env(tmp_path, monkeypatch):
    """In a multi-session process os.environ holds the LAST agent built; the request-scoped
    binding names the conversation that actually ordered the card."""
    from hermes_cli import kanban_db as kb, kanban_db_connect as kbc
    from tools import kanban_tools as kt
    from gateway.session_context import scoped_current_session_id

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    monkeypatch.setenv("HERMES_SESSION_ID", "other-session")
    kb.init_db()
    state = SessionDB(db_path=tmp_path / "state.db")
    for sid in ("other-session", "ordering-session"):
        state.create_session(sid, source="cli")
    state.close()

    with scoped_current_session_id("ordering-session"):
        result = json.loads(kt._handle_create({"title": "child", "assignee": "default"}))
    with kbc.connect_closing() as conn:
        assert kb.get_task(conn, result["task_id"]).session_id == "ordering-session"


def test_slack_origin_permalink_persists_and_missing_or_stale_context_refuses(tmp_path, monkeypatch):
    """Slack turns fail closed without this event's permalink; other turns remain linkless."""
    from hermes_cli import kanban_db as kb, kanban_db_connect as kbc
    from tools import kanban_tools as kt
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    kb.init_db()
    permalink = "https://acme.slack.com/archives/C123/p1700000000000010"

    tokens = set_session_vars(platform="slack", source_url=permalink)
    try:
        created = json.loads(kt._handle_create({"title": "slack", "assignee": "default"}))
    finally:
        clear_session_vars(tokens)
    assert created["ok"], created
    with kbc.connect_closing() as conn:
        assert kb.get_task(conn, created["task_id"]).source_url == permalink
        count_after_linked = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

    # clear_session_vars() masks the old ContextVar value; a later Slack turn cannot borrow it.
    tokens = set_session_vars(platform="slack")
    try:
        refused = json.loads(kt._handle_create({"title": "missing", "assignee": "default"}))
    finally:
        clear_session_vars(tokens)
    assert "trusted Slack permalink" in refused["error"]
    with kbc.connect_closing() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == count_after_linked

    tokens = set_session_vars(platform="slack", source_url="https://evil.test/not-slack")
    try:
        malformed = json.loads(kt._handle_create({"title": "malformed", "assignee": "default"}))
    finally:
        clear_session_vars(tokens)
    assert "valid trusted Slack permalink" in malformed["error"]
    with kbc.connect_closing() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == count_after_linked

    tokens = set_session_vars(platform="discord")
    try:
        non_slack = json.loads(kt._handle_create({"title": "discord", "assignee": "default"}))
    finally:
        clear_session_vars(tokens)
    assert non_slack["ok"], non_slack
    with kbc.connect_closing() as conn:
        assert kb.get_task(conn, non_slack["task_id"]).source_url is None
