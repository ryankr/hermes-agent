"""Validation for Slack's message-specific permalink response."""

import re
from typing import Optional
from urllib.parse import urlsplit


_SLACK_TS = re.compile(r"\d+\.\d+")


def validate_slack_permalink(permalink: object, channel_id: str, message_ts: str) -> Optional[str]:
    """Return an exact inbound Slack permalink, or ``None`` when it is not provable.

    ``chat.getPermalink`` is a remote response, not a proof that its URL identifies the event
    currently being handled.  Query parameters are Slack navigation hints; path identity is exact.
    This helper is shared with durable admission replay so a delayed user turn keeps the same gate.
    """
    if (not isinstance(permalink, str) or not isinstance(channel_id, str) or not isinstance(message_ts, str)
            or not channel_id or not _SLACK_TS.fullmatch(message_ts) or any(char.isspace() for char in permalink)):
        return None
    try:
        parsed = urlsplit(permalink)
        port = parsed.port
    except ValueError:
        return None
    host = parsed.hostname
    if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
            or port is not None or host is None or (host != "slack.com" and not host.endswith(".slack.com"))):
        return None
    expected_path = f"/archives/{channel_id}/p{message_ts.replace('.', '')}"
    return permalink if parsed.path == expected_path else None