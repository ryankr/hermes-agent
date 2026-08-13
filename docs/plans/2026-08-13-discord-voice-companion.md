# Discord Voice Companion Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Let Hermes automatically join, follow, and leave Discord voice channels with an explicitly configured companion user, removing the need to type `/voice join`.

**Architecture:** Keep Discord voice lifecycle ownership in `plugins/platforms/discord/adapter.py`, where Discord voice-state events already arrive. Add an opt-in `discord.voice_companion` configuration reader and a runner callback that binds the existing agent voice pipeline to the configured text channel before joining. Manual `/voice join` behavior remains unchanged.

**Tech Stack:** Python 3.11, discord.py voice adapter, pytest/pytest-asyncio.

---

### Task 1: Define the opt-in companion configuration and tests

**Objective:** Parse only valid enabled companion settings, never implicitly opt in from the allowlist.

**Files:**
- Modify: `plugins/platforms/discord/adapter.py`
- Test: `tests/gateway/test_voice_command.py`

**Behavior:** `discord.voice_companion` is enabled only when `enabled: true`, with a positive numeric `user_id` and positive numeric `text_channel_id`. Invalid/missing values disable it safely.

**Verification:** Focused pytest proves enabled, disabled, and malformed settings behavior.

### Task 2: Bind automatic joins to the normal Hermes voice pipeline

**Objective:** Give the adapter a runner callback that receives guild, companion user, and target text channel, wires the existing voice callbacks/source metadata, then calls the existing `join_voice_channel` method.

**Files:**
- Modify: `gateway/run.py`
- Modify: `tests/gateway/test_voice_command.py`

**Behavior:** A successful companion join stores the existing text-channel/source metadata and enables TTS for that channel. Failures are logged and never crash Discord event handling.

**Verification:** Focused pytest proves the existing pipeline wiring is used and failure is contained.

### Task 3: Follow voice-state changes

**Objective:** On configured companion user join/switch, call the runner callback; on leave, keep current inactivity behavior rather than abruptly disconnecting.

**Files:**
- Modify: `plugins/platforms/discord/adapter.py`
- Test: `tests/gateway/test_voice_command.py`

**Behavior:** Joining a VC automatically joins Hermes; switching VCs moves Hermes through `join_voice_channel`; events from other users or disabled/malformed config do nothing. Voice receiver allowlist remains unchanged.

**Verification:** Focused pytest proves join, move, ignore-other-user, and disabled configuration behavior.

### Task 4: Document and deploy Ryan’s opt-in configuration

**Objective:** Add a concise voice-mode configuration reference and enable the companion only for the configured authorized Discord user on this host.

**Files:**
- Modify: `website/docs/user-guide/features/voice-mode.md`
- Modify: `/Users/ryan/.hermes/config.yaml` only after tests and merge

**Verification:** Run focused and full relevant tests, restart gateway, inspect status/logs, then validate that configuration parses in the live process. Real Discord VC entry is the final manual acceptance test.
