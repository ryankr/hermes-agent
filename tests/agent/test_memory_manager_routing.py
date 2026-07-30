from __future__ import annotations

from typing import Any

from agent.memory_manager import MemoryManager
from agent.memory_provider import MemoryProvider


class RecordingProvider(MemoryProvider):
    def __init__(self, result: str = "provider context") -> None:
        self.prefetch_queries: list[str] = []
        self.queue_queries: list[str] = []
        self.result = result

    @property
    def name(self) -> str:
        return "recording"

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        pass

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        self.prefetch_queries.append(query)
        return self.result

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        self.queue_queries.append(query)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return []


def test_prefetch_routes_external_memory_query_and_injects_route_context():
    manager = MemoryManager()
    provider = RecordingProvider("matched holdings context")
    manager.add_provider(provider)

    context = manager.prefetch_all("하이닉스 지금 어때?", session_id="s1")

    assert len(provider.prefetch_queries) == 1
    routed_query = provider.prefetch_queries[0]
    assert routed_query.startswith("하이닉스 지금 어때? | domains: kr_stock | slots:")
    assert "holdings" in routed_query
    assert "average_cost" in routed_query
    assert "current_kr_positions" in routed_query
    assert "watchlist_and_no_trade_list" in routed_query
    assert "## Memory Routing" in context
    assert "domains: kr_stock" in context
    assert "risk: high" in context
    assert "matched holdings context" in context


def test_queue_prefetch_uses_rewritten_query_for_next_turn():
    manager = MemoryManager()
    provider = RecordingProvider()
    manager.add_provider(provider)

    manager.queue_prefetch_all("하이닉스 지금 어때?", session_id="s1")
    manager._drain_sync_executor()

    assert provider.queue_queries
    assert provider.queue_queries[0].startswith("하이닉스 지금 어때? | domains: kr_stock | slots:")
    assert "holdings" in provider.queue_queries[0]
    assert "average_cost" in provider.queue_queries[0]


def test_unrouted_prefetch_does_not_add_route_block_or_rewrite_query():
    manager = MemoryManager()
    provider = RecordingProvider("generic context")
    manager.add_provider(provider)

    context = manager.prefetch_all("Can you communicate the approach clearly?")

    assert provider.prefetch_queries == ["Can you communicate the approach clearly?"]
    assert "## Memory Routing" not in context
    assert context == "generic context"
