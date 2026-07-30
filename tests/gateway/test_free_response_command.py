"""Tests for the gateway /free-response Discord command."""

from types import SimpleNamespace

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from gateway.slash_commands import GatewaySlashCommandsMixin


class Runner(GatewaySlashCommandsMixin):
    def __init__(self, *, existing=""):
        self.config = GatewayConfig()
        self.config.platforms[Platform.DISCORD] = PlatformConfig(
            enabled=True,
            extra={"free_response_channels": existing},
        )
        self.adapter = SimpleNamespace(
            config=self.config.platforms[Platform.DISCORD],
            _discord_free_response_channels=lambda: {
                part.strip() for part in existing.split(",") if part.strip()
            },
        )
        self.adapters = {Platform.DISCORD: self.adapter}


def event(text="/free-response on"):
    return MessageEvent(
        text=text,
        source=SessionSource(
            platform=Platform.DISCORD,
            chat_id="thread-1",
            chat_type="thread",
            thread_id="thread-1",
            parent_chat_id="parent-123",
        ),
    )


@pytest.mark.asyncio
async def test_free_response_on_persists_and_updates_live_adapter(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "cli.save_config_value",
        lambda key, value: saved.setdefault(key, value) or True,
    )
    runner = Runner(existing="existing-1")

    result = await runner._handle_free_response_command(event())

    assert "No restart needed" in result
    assert saved["discord.free_response_channels"] == "existing-1,parent-123"
    assert runner.config.platforms[Platform.DISCORD].extra["free_response_channels"] == "existing-1,parent-123"
    assert runner.adapter.config.extra["free_response_channels"] == "existing-1,parent-123"


@pytest.mark.asyncio
async def test_free_response_off_removes_current_parent_channel(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "cli.save_config_value",
        lambda key, value: saved.setdefault(key, value) or True,
    )
    runner = Runner(existing="existing-1,parent-123")

    result = await runner._handle_free_response_command(event("/free-response off"))

    assert "OFF" in result
    assert saved["discord.free_response_channels"] == "existing-1"


@pytest.mark.asyncio
async def test_free_response_status_uses_parent_channel():
    runner = Runner(existing="parent-123")

    result = await runner._handle_free_response_command(event("/free-response status"))

    assert "ON" in result
    assert "channel_id=parent-123" in result
