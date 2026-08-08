"""Local-only measurement of memory retrieval coverage, quality, and cost.

The engine derives usage from already-persisted session transcripts.  It never
records recalled content or contacts a third party; quality and outcome fields
come only from explicit human evaluations stored by :class:`SessionDB`.
"""

from __future__ import annotations

import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from hermes_constants import get_hermes_home

_RETRIEVAL_LABELS = {
    "used_verified", "used_but_stale", "not_used_irrelevant",
    "wrong_or_conflicting", "missing",
}
_OUTCOME_LABELS = {"helped", "neutral", "hindered"}
_RECHECK_LABELS = {"none", "ssot_check", "correction"}


def _median(values: Iterable[float | int]) -> float | int | None:
    values = list(values)
    return statistics.median(values) if values else None


class MemoryObservabilityEngine:
    """Generate an observational memory-use report from a ``SessionDB``."""

    def __init__(self, db, vault_roots: Iterable[str | Path] | None = None):
        self.db = db
        self._conn = db._conn
        if vault_roots is None:
            roots: list[str | Path] = [get_hermes_home() / "memories"]
            vault_roots = roots
            # This is a local config convenience, not outbound telemetry.  A
            # user can add memory.observability.vault_roots to include a
            # Git-backed Markdown vault in the coverage metric.
            try:
                from hermes_cli.config import load_config
                configured = load_config().get("memory", {}).get("observability", {}).get("vault_roots", [])
                if isinstance(configured, str):
                    try:
                        configured = json.loads(configured)
                    except json.JSONDecodeError:
                        configured = []
                if isinstance(configured, list):
                    vault_roots.extend(item for item in configured if isinstance(item, str))
            except Exception:
                pass
        self.vault_roots = tuple(
            Path(root).expanduser().resolve() for root in vault_roots
        )

    def generate(self, *, days: int = 30, source: str | None = None) -> dict[str, Any]:
        cutoff = time.time() - days * 86400
        sessions = self._sessions(cutoff, source)
        uses = self._memory_uses(cutoff, source)
        used_session_ids = set(uses)
        labels = self._evaluations(cutoff, source)
        return {
            "days": days,
            "source_filter": source,
            "coverage": self._coverage(sessions, uses),
            "precision": self._precision(labels),
            "outcomes": self._outcomes(labels),
            "cohorts": self._cohorts(sessions, used_session_ids),
            "note": (
                "Cohorts are observational only: task complexity and user intent are "
                "not controlled, so they do not establish memory-caused savings."
            ),
        }

    def _sessions(self, cutoff: float, source: str | None) -> list[dict[str, Any]]:
        sql = """SELECT id, started_at, ended_at, input_tokens, output_tokens,
                         cache_read_tokens, cache_write_tokens, tool_call_count
                  FROM sessions WHERE started_at >= ?"""
        params: list[Any] = [cutoff]
        if source:
            sql += " AND source = ?"
            params.append(source)
        return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

    def _memory_uses(self, cutoff: float, source: str | None) -> dict[str, Counter[str]]:
        sql = """SELECT m.session_id, m.tool_name, m.tool_calls
                 FROM messages m JOIN sessions s ON s.id = m.session_id
                 WHERE s.started_at >= ? AND m.role = 'assistant'"""
        params: list[Any] = [cutoff]
        if source:
            sql += " AND s.source = ?"
            params.append(source)
        uses: dict[str, Counter[str]] = defaultdict(Counter)
        for row in self._conn.execute(sql, params):
            for name, args in self._calls(row["tool_name"], row["tool_calls"]):
                kind = self._source_kind(name, args)
                if kind:
                    uses[row["session_id"]][kind] += 1
        return uses

    @staticmethod
    def _calls(tool_name: str | None, tool_calls: str | None):
        if tool_name:
            yield tool_name, {}
        if not tool_calls:
            return
        try:
            calls = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(calls, list):
            return
        for call in calls:
            func = call.get("function", {}) if isinstance(call, dict) else {}
            name = func.get("name")
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (TypeError, json.JSONDecodeError):
                    args = {}
            yield name, args if isinstance(args, dict) else {}

    def _source_kind(self, name: str | None, args: dict[str, Any]) -> str | None:
        if name == "memory":
            return "built_in"
        if isinstance(name, str) and name.startswith("mcp_mem0_"):
            return "mem0"
        if name == "session_search":
            return "session_archive"
        if name in {"read_file", "search_files"}:
            path = args.get("path", "")
            try:
                resolved = Path(path).expanduser().resolve()
            except (TypeError, OSError):
                return None
            if any(resolved.is_relative_to(root) for root in self.vault_roots):
                return "markdown_vault"
        return None

    def _evaluations(self, cutoff: float, source: str | None) -> list[dict[str, Any]]:
        sql = """SELECT e.session_id, e.retrieval, e.outcome, e.recheck
                 FROM memory_evaluations e JOIN sessions s ON s.id = e.session_id
                 WHERE s.started_at >= ?"""
        params: list[Any] = [cutoff]
        if source:
            sql += " AND s.source = ?"
            params.append(source)
        return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

    @staticmethod
    def _coverage(sessions: list[dict[str, Any]], uses: dict[str, Counter[str]]) -> dict[str, Any]:
        sources = {kind: {"sessions": 0, "calls": 0} for kind in (
            "built_in", "mem0", "session_archive", "markdown_vault"
        )}
        for counter in uses.values():
            for kind, count in counter.items():
                sources[kind]["sessions"] += 1
                sources[kind]["calls"] += count
        total = len(sessions)
        used = len(uses)
        return {
            "sessions": total,
            "memory_used_sessions": used,
            "memory_used_session_rate": used / total if total else 0.0,
            "sources": sources,
        }

    @staticmethod
    def _precision(labels: list[dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(label["retrieval"] for label in labels if label["retrieval"])
        labelled = sum(counts.values())
        return {
            "labelled_sessions": labelled,
            "counts": {label: counts[label] for label in sorted(_RETRIEVAL_LABELS)},
            "precision": counts["used_verified"] / labelled if labelled else None,
            "staleness_or_conflict_rate": (
                (counts["used_but_stale"] + counts["wrong_or_conflicting"]) / labelled
                if labelled else None
            ),
        }

    @staticmethod
    def _outcomes(labels: list[dict[str, Any]]) -> dict[str, Any]:
        outcome_counts = Counter(label["outcome"] for label in labels if label["outcome"])
        recheck_counts = Counter(label["recheck"] for label in labels if label["recheck"])
        return {
            "labelled_sessions": sum(outcome_counts.values()),
            "counts": {label: outcome_counts[label] for label in sorted(_OUTCOME_LABELS)},
            "rechecks": {label: recheck_counts[label] for label in sorted(_RECHECK_LABELS)},
        }

    @staticmethod
    def _cohorts(sessions: list[dict[str, Any]], used_session_ids: set[str]) -> dict[str, Any]:
        def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
            durations = [row["ended_at"] - row["started_at"] for row in rows
                         if row.get("ended_at") and row["ended_at"] >= row["started_at"]]
            return {
                "sessions": len(rows),
                "median_duration_seconds": _median(durations),
                "median_input_tokens": _median([row.get("input_tokens") or 0 for row in rows]),
                "median_output_tokens": _median([row.get("output_tokens") or 0 for row in rows]),
                "median_cache_read_tokens": _median([row.get("cache_read_tokens") or 0 for row in rows]),
                "median_tool_calls": _median([row.get("tool_call_count") or 0 for row in rows]),
            }
        return {
            "memory_used": summarize([row for row in sessions if row["id"] in used_session_ids]),
            "no_memory": summarize([row for row in sessions if row["id"] not in used_session_ids]),
        }
