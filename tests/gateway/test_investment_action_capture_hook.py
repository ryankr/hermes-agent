from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_gateway_base_strips_and_captures_action_cards_after_successful_send():
    source = (PROJECT_ROOT / "gateway" / "platforms" / "base.py").read_text(encoding="utf-8")

    extract_idx = source.index("extract_action_cards")
    send_idx = source.index("result = await self._send_with_retry", extract_idx)
    capture_idx = source.index("capture_action_cards", send_idx)

    assert extract_idx < send_idx < capture_idx
    assert "if _investment_action_cards and result.success" in source
    assert "asyncio.to_thread" in source
