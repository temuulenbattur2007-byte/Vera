"""
memory/short_term.py — Rolling in-memory conversation history for the current session.
Keeps the last N messages to stay within the model's context window.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    role: str       # "system", "user", or "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class ShortTermMemory:
    """
    Manages the active conversation window.
    Automatically trims old messages when the window exceeds max_messages.
    """

    def __init__(self, max_messages: int = 40):
        self.max_messages = max_messages
        self._history: list[Message] = []

    def add(self, role: str, content: str) -> None:
        """Add a message to history."""
        self._history.append(Message(role=role, content=content))
        self._trim()

    def _trim(self) -> None:
        """Keep history within max_messages, always preserving the system message."""
        if len(self._history) <= self.max_messages:
            return

        # Find system message (always keep it at index 0)
        system_msgs = [m for m in self._history if m.role == "system"]
        non_system  = [m for m in self._history if m.role != "system"]

        # Keep the most recent non-system messages
        keep_count = self.max_messages - len(system_msgs)
        trimmed = non_system[-keep_count:]

        self._history = system_msgs + trimmed

    def get_messages(self) -> list[dict]:
        """Return history as a list of dicts for the model API."""
        return [m.to_dict() for m in self._history]

    def get_raw(self) -> list[Message]:
        """Return raw Message objects (for saving to daily log)."""
        return list(self._history)

    def clear(self) -> None:
        """Clear history (keep system message if present)."""
        system_msgs = [m for m in self._history if m.role == "system"]
        self._history = system_msgs

    def __len__(self) -> int:
        return len(self._history)

    def user_messages_only(self) -> list[str]:
        """Return just the user messages as plain strings (for summarization)."""
        return [m.content for m in self._history if m.role == "user"]
