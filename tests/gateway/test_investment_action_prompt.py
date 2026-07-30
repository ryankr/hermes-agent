from gateway.config import Platform
from gateway.session import SessionContext, SessionSource, build_session_context_prompt


def test_investment_action_review_prompt_instruction_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "gateway.session._investment_action_review_enabled",
        lambda: True,
    )
    ctx = SessionContext(
        source=SessionSource(platform=Platform.DISCORD, chat_id="c1", chat_type="channel"),
        connected_platforms=[Platform.DISCORD],
        home_channels={},
    )

    prompt = build_session_context_prompt(ctx)

    assert "HERMES_ACTION_CARD" in prompt
    assert "concrete investment/trading action" in prompt
