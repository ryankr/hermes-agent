"""``hermes memory`` subcommand parser.

Extracted from ``hermes_cli/main.py:main()`` (god-file Phase 2 follow-up).
Handler injected to avoid importing ``main``.
"""

from __future__ import annotations

from typing import Callable


def build_memory_parser(subparsers, *, cmd_memory: Callable) -> None:
    """Attach the ``memory`` subcommand to ``subparsers``."""
    memory_parser = subparsers.add_parser(
        "memory",
        help="Configure external memory provider",
        description=(
            "Set up and manage external memory provider plugins.\n\n"
            "Available providers: honcho, openviking, mem0, hindsight,\n"
            "holographic, retaindb, byterover.\n\n"
            "Only one external provider can be active at a time.\n"
            "Built-in memory (MEMORY.md/USER.md) is always active."
        ),
    )
    memory_sub = memory_parser.add_subparsers(dest="memory_command")
    _setup_parser = memory_sub.add_parser(
        "setup", help="Interactive provider selection and configuration"
    )
    _setup_parser.add_argument(
        "provider",
        nargs="?",
        default=None,
        help="Provider to configure directly (e.g. honcho), skipping the picker",
    )
    memory_sub.add_parser("status", help="Show current memory provider config")
    memory_sub.add_parser("off", help="Disable external provider (built-in only)")
    evaluate_parser = memory_sub.add_parser(
        "evaluate", help="Record a local reviewer label for a session's memory use"
    )
    evaluate_parser.add_argument("session_id", help="Exact or unique session-ID prefix")
    evaluate_parser.add_argument(
        "--retrieval",
        choices=["used_verified", "used_but_stale", "not_used_irrelevant", "wrong_or_conflicting", "missing"],
        help="How retrieved memory affected the work",
    )
    evaluate_parser.add_argument(
        "--outcome", choices=["helped", "neutral", "hindered"],
        help="Overall memory outcome",
    )
    evaluate_parser.add_argument(
        "--recheck", choices=["none", "ssot_check", "correction"],
        help="Whether a live source was needed to recheck memory",
    )
    evaluate_parser.add_argument("--note", help="Optional short local reviewer note")
    _reset_parser = memory_sub.add_parser(
        "reset",
        help="Erase all built-in memory (MEMORY.md and USER.md)",
    )
    _reset_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    _reset_parser.add_argument(
        "--target",
        choices=["all", "memory", "user"],
        default="all",
        help="Which store to reset: 'all' (default), 'memory', or 'user'",
    )
    memory_parser.set_defaults(func=cmd_memory)
