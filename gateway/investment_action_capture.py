"""Capture structured investment action cards from gateway responses.

This is deliberately an edge hook, not a model tool. It watches final response
text for an explicit ``HERMES_ACTION_CARD`` block, strips that metadata before
platform delivery, and (when enabled in config.yaml) writes a sidecar JSON and
invokes the user's stock-analysis-system adapter.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

_CARD_COMMENT_RE = re.compile(
    r"<!--\s*HERMES_ACTION_CARD\s*(?P<payload>\{.*?\}|\[.*?\])\s*-->",
    re.DOTALL,
)
_CARD_FENCE_RE = re.compile(
    r"```(?:hermes_action_card|action_card)\s*(?P<payload>\{.*?\}|\[.*?\])\s*```",
    re.DOTALL | re.IGNORECASE,
)


@dataclasses.dataclass(frozen=True)
class InvestmentActionCaptureConfig:
    enabled: bool = False
    capture_dir: Path | None = None
    stock_analysis_system_path: Path | None = None
    adapter_timeout_seconds: int = 5


@dataclasses.dataclass(frozen=True)
class CaptureResult:
    captured: int = 0
    adapter_invoked: int = 0
    errors: tuple[str, ...] = ()
    sidecar_paths: tuple[Path, ...] = ()


def _coerce_cards(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def extract_action_cards(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(cleaned_text, cards)`` from explicit action-card blocks.

    Supported forms:
    - ``<!-- HERMES_ACTION_CARD { ... } -->`` (preferred, normally hidden-ish)
    - fenced `````action_card`` blocks for manual testing/debugging

    Invalid JSON is stripped from delivery but ignored for capture; malformed
    metadata should not leak to the user or break response delivery.
    """
    if not text:
        return text, []

    cards: list[dict[str, Any]] = []

    def _replace(match: re.Match[str]) -> str:
        raw = match.group("payload")
        try:
            cards.extend(_coerce_cards(json.loads(raw)))
        except Exception as exc:
            logger.warning("Invalid HERMES_ACTION_CARD JSON ignored: %s", exc)
        return ""

    cleaned = _CARD_COMMENT_RE.sub(_replace, text)
    cleaned = _CARD_FENCE_RE.sub(_replace, cleaned)
    # Collapse excessive blank lines created by removing metadata blocks.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, cards


def config_from_mapping(config: dict[str, Any] | None) -> InvestmentActionCaptureConfig:
    cfg = (config or {}).get("investment_action_review", {}) if isinstance(config, dict) else {}
    if not isinstance(cfg, dict):
        cfg = {}
    capture_dir_raw = cfg.get("capture_dir")
    capture_dir = Path(str(capture_dir_raw)).expanduser() if capture_dir_raw else get_hermes_home() / "investment_action_cards"
    stock_path_raw = cfg.get("stock_analysis_system_path")
    stock_path = Path(str(stock_path_raw)).expanduser() if stock_path_raw else None
    try:
        timeout = int(cfg.get("adapter_timeout_seconds", 5))
    except (TypeError, ValueError):
        timeout = 5
    return InvestmentActionCaptureConfig(
        enabled=bool(cfg.get("enabled", False)),
        capture_dir=capture_dir,
        stock_analysis_system_path=stock_path,
        adapter_timeout_seconds=max(1, min(timeout, 30)),
    )


def load_capture_config() -> InvestmentActionCaptureConfig:
    try:
        from hermes_cli.config import load_config
        return config_from_mapping(load_config() or {})
    except Exception as exc:
        logger.debug("investment action capture config unavailable: %s", exc)
        return InvestmentActionCaptureConfig()


def _safe_component(value: Any, fallback: str) -> str:
    raw = str(value or fallback).strip() or fallback
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)[:80]


def _enrich_card(card: dict[str, Any], source_metadata: dict[str, Any] | None) -> dict[str, Any]:
    enriched = dict(card)
    source = dict(enriched.get("source") or {}) if isinstance(enriched.get("source"), dict) else {}
    for key, value in (source_metadata or {}).items():
        if value is not None:
            source[key] = value
    if source:
        enriched["source"] = source
    enriched.setdefault("captured_at", datetime.now().isoformat(timespec="seconds"))
    return enriched


def _write_sidecar(card: dict[str, Any], capture_dir: Path) -> Path:
    capture_dir.mkdir(parents=True, exist_ok=True)
    date_key = datetime.now().strftime("%Y%m%d")
    key = _safe_component(card.get("stock_code") or card.get("sector") or card.get("market"), "market")
    ts = datetime.now().strftime("%H%M%S%f")
    out = capture_dir / date_key / f"{ts}_{key}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _invoke_adapter(sidecar: Path, cfg: InvestmentActionCaptureConfig) -> bool:
    stock_path = cfg.stock_analysis_system_path
    if not stock_path:
        return False
    adapter = stock_path / "scripts" / "hermes_action_adapter.py"
    if not adapter.exists():
        logger.warning("Investment action adapter not found: %s", adapter)
        return False
    pred_dir = stock_path / "data" / "predictions"
    cmd = [sys.executable, str(adapter), str(sidecar), "--pred-dir", str(pred_dir)]
    result = subprocess.run(
        cmd,
        cwd=str(stock_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=cfg.adapter_timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        logger.warning(
            "Investment action adapter failed rc=%s stdout=%r stderr=%r",
            result.returncode,
            result.stdout[-500:],
            result.stderr[-500:],
        )
        return False
    return True


def capture_action_cards(
    cards: list[dict[str, Any]],
    cfg: InvestmentActionCaptureConfig | None = None,
    *,
    source_metadata: dict[str, Any] | None = None,
) -> CaptureResult:
    """Persist and optionally adapt action cards.

    Disabled capture is a no-op; callers should still strip blocks from visible
    text separately via :func:`extract_action_cards`.
    """
    cfg = cfg or load_capture_config()
    if not cards or not cfg.enabled:
        return CaptureResult()

    errors: list[str] = []
    sidecars: list[Path] = []
    adapter_invoked = 0
    for card in cards:
        try:
            enriched = _enrich_card(card, source_metadata)
            sidecar = _write_sidecar(enriched, cfg.capture_dir or (get_hermes_home() / "investment_action_cards"))
            sidecars.append(sidecar)
            if _invoke_adapter(sidecar, cfg):
                adapter_invoked += 1
        except Exception as exc:
            logger.warning("Investment action capture failed: %s", exc, exc_info=True)
            errors.append(str(exc))
    return CaptureResult(
        captured=len(sidecars),
        adapter_invoked=adapter_invoked,
        errors=tuple(errors),
        sidecar_paths=tuple(sidecars),
    )
