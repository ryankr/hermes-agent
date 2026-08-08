import json
import time

import pytest

from agent.insights import InsightsEngine
from agent.memory_observability import MemoryObservabilityEngine
from hermes_state import SessionDB


@pytest.fixture()
def db(tmp_path):
    database = SessionDB(db_path=tmp_path / "state.db")
    yield database
    database.close()


def _session(db, session_id, *, source="slack", started_at=None, input_tokens=100, output_tokens=20):
    db.create_session(session_id=session_id, source=source, model="test-model", user_id="u")
    started_at = started_at or time.time()
    db._conn.execute(
        "UPDATE sessions SET started_at=?, ended_at=?, input_tokens=?, output_tokens=?, tool_call_count=? WHERE id=?",
        (started_at, started_at + 60, input_tokens, output_tokens, 2, session_id),
    )


def _calls(*names):
    return [{"function": {"name": name, "arguments": "{}"}} for name in names]


def test_evaluation_is_upserted_and_session_bound(db):
    _session(db, "memory-session")

    assert db.upsert_memory_evaluation(
        "memory-session", retrieval="used_verified", outcome="helped", recheck="ssot_check", note="verified"
    ) is True
    assert db.upsert_memory_evaluation(
        "memory-session", retrieval="used_but_stale", outcome="neutral", recheck="correction"
    ) is True
    evaluation = db.get_memory_evaluation("memory-session")
    assert evaluation["retrieval"] == "used_but_stale"
    assert evaluation["outcome"] == "neutral"
    assert evaluation["recheck"] == "correction"
    assert evaluation["note"] is None
    assert db._conn.execute("SELECT COUNT(*) FROM memory_evaluations").fetchone()[0] == 1


def test_evaluation_rejects_unknown_session_and_invalid_labels(db):
    with pytest.raises(KeyError):
        db.upsert_memory_evaluation("unknown", retrieval="used_verified")
    _session(db, "s1")
    with pytest.raises(ValueError):
        db.upsert_memory_evaluation("s1", retrieval="made_up")


def test_report_measures_coverage_labels_and_observational_cohorts(db):
    now = time.time()
    _session(db, "mem0", started_at=now - 60, input_tokens=300, output_tokens=60)
    db.append_message("mem0", role="assistant", content="", tool_calls=_calls("mcp_mem0_memory_recall"))
    _session(db, "builtin", started_at=now - 120, input_tokens=100, output_tokens=20)
    db.append_message("builtin", role="assistant", content="", tool_calls=_calls("memory"))
    _session(db, "plain", started_at=now - 180, input_tokens=50, output_tokens=10)
    db.upsert_memory_evaluation("mem0", retrieval="used_verified", outcome="helped", recheck="none")
    db.upsert_memory_evaluation("builtin", retrieval="used_but_stale", outcome="neutral", recheck="ssot_check")

    report = MemoryObservabilityEngine(db).generate(days=1)

    assert report["coverage"]["sessions"] == 3
    assert report["coverage"]["memory_used_sessions"] == 2
    assert report["coverage"]["memory_used_session_rate"] == pytest.approx(2 / 3)
    assert report["coverage"]["sources"]["mem0"]["calls"] == 1
    assert report["coverage"]["sources"]["built_in"]["calls"] == 1
    assert report["precision"]["labelled_sessions"] == 2
    assert report["precision"]["precision"] == pytest.approx(0.5)
    assert report["precision"]["staleness_or_conflict_rate"] == pytest.approx(0.5)
    assert report["outcomes"]["counts"] == {"helped": 1, "neutral": 1, "hindered": 0}
    assert report["cohorts"]["memory_used"]["sessions"] == 2
    assert report["cohorts"]["no_memory"]["sessions"] == 1
    assert report["cohorts"]["memory_used"]["median_input_tokens"] == 200


def test_empty_report_is_safe(db):
    report = MemoryObservabilityEngine(db).generate(days=30)
    assert report["coverage"]["sessions"] == 0
    assert report["precision"]["precision"] is None
    assert report["cohorts"]["memory_used"]["sessions"] == 0


def test_markdown_vault_reads_are_detected_under_configured_root(db, tmp_path):
    vault = tmp_path / "agent-memory"
    _session(db, "vault")
    db.append_message(
        "vault", role="assistant", content="", tool_calls=[{
            "function": {"name": "read_file", "arguments": json.dumps({"path": str(vault / "decision.md")})}
        }],
    )
    report = MemoryObservabilityEngine(db, vault_roots=[vault]).generate(days=1)
    assert report["coverage"]["sources"]["markdown_vault"] == {"sessions": 1, "calls": 1}


def test_insights_includes_formatted_memory_observability(db):
    _session(db, "s1")
    db.append_message("s1", role="assistant", content="", tool_calls=_calls("memory"))

    engine = InsightsEngine(db)
    report = engine.generate(days=1)

    assert report["memory_observability"]["coverage"]["memory_used_sessions"] == 1
    assert "Memory Observability" in engine.format_terminal(report)
