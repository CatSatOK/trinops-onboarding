"""Team Slack notification announcing the new hire.

DemoSlackClient (DEMO_MODE=true) writes the message to `data/outbox/` so the
demo needs no Slack workspace. SlackWebClient (DEMO_MODE=false) posts via the
Slack Web API (chat.postMessage).
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from onboarding.config import Settings
from onboarding.logging_conf import get_logger

logger = get_logger(__name__)


class SlackClient(Protocol):
    def post(self, channel: str, message: str) -> str | None:
        """Post a message to a channel. Returns a message id when available."""
        ...


class DemoSlackClient:
    def __init__(self, settings: Settings) -> None:
        self._outbox = Path(settings.outbox_dir)
        self._outbox.mkdir(parents=True, exist_ok=True)

    def post(self, channel: str, message: str) -> str | None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        safe_channel = re.sub(r"[^\w-]+", "_", channel).strip("_")
        path = self._outbox / f"{stamp}_slack_{safe_channel}.txt"
        path.write_text(f"channel: {channel}\n\n{message}\n", encoding="utf-8")
        logger.info("slack(demo): wrote %s (channel=%s)", path.name, channel)
        return f"slack-demo-{stamp}"


class SlackWebClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None

    def _web(self):
        if self._client is None:
            from slack_sdk import WebClient

            self._client = WebClient(token=self._settings.slack_bot_token)
        return self._client

    def post(self, channel: str, message: str) -> str | None:
        resp = self._web().chat_postMessage(channel=channel, text=message)
        logger.info("slack: posted to %s", channel)
        return resp.get("ts")


def get_slack_client(settings: Settings) -> SlackClient:
    return DemoSlackClient(settings) if settings.demo_mode else SlackWebClient(settings)


def render_slack_message(employee, settings: Settings) -> str:
    role = employee.role
    start = employee.start_date.isoformat()
    handle = employee.slack_handle or employee.name
    return (
        f":wave: Please welcome *{employee.name}* ({handle}) who joins as "
        f"*{role}* on *{start}*. Say hi and help them settle in!"
    )
