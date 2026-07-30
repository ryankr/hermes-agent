import json
from pathlib import Path

from gateway.investment_action_capture import (
    InvestmentActionCaptureConfig,
    capture_action_cards,
    extract_action_cards,
)


def test_extracts_and_strips_html_comment_action_card():
    text = """요약 답변

<!-- HERMES_ACTION_CARD
{"stock_code":"005930","opinion":"매수","action":"staged_buy","time_horizon":"30D"}
-->

끝"""

    cleaned, cards = extract_action_cards(text)

    assert "HERMES_ACTION_CARD" not in cleaned
    assert cleaned == "요약 답변\n\n끝"
    assert cards == [{
        "stock_code": "005930",
        "opinion": "매수",
        "action": "staged_buy",
        "time_horizon": "30D",
    }]


def test_capture_persists_sidecar_and_invokes_adapter_when_enabled(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))

        class Result:
            returncode = 0
            stdout = "prediction.json\n"
            stderr = ""

        return Result()

    monkeypatch.setattr("gateway.investment_action_capture.subprocess.run", fake_run)

    stock_system = tmp_path / "stock-analysis-system"
    scripts = stock_system / "scripts"
    scripts.mkdir(parents=True)
    adapter = scripts / "hermes_action_adapter.py"
    adapter.write_text("# adapter", encoding="utf-8")

    cfg = InvestmentActionCaptureConfig(
        enabled=True,
        capture_dir=tmp_path / "cards",
        stock_analysis_system_path=stock_system,
        adapter_timeout_seconds=3,
    )

    result = capture_action_cards(
        [{"stock_code": "005930", "action": "staged_buy"}],
        cfg,
        source_metadata={"platform": "discord", "chat_id": "c1", "thread_id": "t1", "message_id": "m2"},
    )

    assert result.captured == 1
    assert result.adapter_invoked == 1
    sidecar = result.sidecar_paths[0]
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["stock_code"] == "005930"
    assert payload["source"]["platform"] == "discord"
    assert payload["source"]["message_id"] == "m2"
    assert calls
    cmd = calls[0][0]
    assert str(adapter) in cmd
    assert str(sidecar) in cmd
    assert "--pred-dir" in cmd


def test_disabled_capture_strips_but_does_not_persist(tmp_path):
    cfg = InvestmentActionCaptureConfig(enabled=False, capture_dir=tmp_path / "cards")
    result = capture_action_cards([{"stock_code": "005930"}], cfg)

    assert result.captured == 0
    assert result.adapter_invoked == 0
    assert not (tmp_path / "cards").exists()
