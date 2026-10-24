"""Invalid launch options must not inspect configuration they bypass."""
from argparse import Namespace


def test_invalid_options_are_reported_before_reading_profile(monkeypatch, capsys):
    from hermes_cli.gateway_chat_startup import launch_gateway_chat

    def unexpected():
        raise AssertionError("Unsupported launch read profile configuration")

    monkeypatch.setattr("hermes_cli.main._has_any_provider_configured", unexpected)
    assert launch_gateway_chat(Namespace(worktree=True)) == 2
    assert "--worktree" in capsys.readouterr().err
    # A bypass launch skips provider probing and the profile cost guard entirely.
    monkeypatch.setattr("hermes_cli.main._confirm_startup_expensive_model_override", lambda args: unexpected())
    from hermes_cli.gateway_client import GatewayClientError

    def refused():
        raise GatewayClientError("transport reached")
    monkeypatch.setattr("hermes_cli.gateway_chat.connect_gateway", refused)
    assert launch_gateway_chat(Namespace(safe_mode=True, model="explicit", provider="custom", query="x")) == 1
    assert "transport reached" in capsys.readouterr().err


def test_invalid_source_is_reported_before_model_or_session_startup(monkeypatch, capsys):
    """A session surface typo is a local CLI usage error, not a gateway/provider failure."""
    from hermes_cli.gateway_chat_startup import launch_gateway_chat

    def unexpected(*_args, **_kwargs):
        raise AssertionError("invalid --source initialized model or session startup")

    monkeypatch.setattr("hermes_cli.main._confirm_startup_expensive_model_override", unexpected)
    monkeypatch.setattr("hermes_cli.main._has_any_provider_configured", unexpected)
    monkeypatch.setattr("hermes_cli.gateway_chat.launch_from_args", unexpected)

    assert launch_gateway_chat(Namespace(source="goal-smoke-default")) == 2
    error = capsys.readouterr().err
    assert "--source" in error
    assert "session surface label" in error
    assert "cli" in error and "tui" in error and "oneshot" in error
    assert "provider" not in error.lower() and "model" not in error.lower()
