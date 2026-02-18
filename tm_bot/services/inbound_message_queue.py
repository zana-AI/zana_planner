"""
Inbound message queue for per-session message coalescing.

This queue serializes inbound runs by session key (typically user_id + chat_id),
and supports a lightweight collect/debounce/cap/drop policy to reduce overlapping
LLM runs when users send rapid follow-ups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


QueueDropPolicy = str  # "summarize" | "old" | "new"


@dataclass
class QueuedInboundMessage:
    update: Any
    context: Any
    message_text: str


@dataclass
class InboundBatch:
    messages: List[QueuedInboundMessage]
    summary: Optional[str] = None


@dataclass
class _SessionQueueState:
    running: bool = False
    items: List[QueuedInboundMessage] = field(default_factory=list)
    dropped_count: int = 0
    summary_lines: List[str] = field(default_factory=list)


class InboundMessageQueue:
    """
    In-memory queue keyed by session (user/chat).

    Mode is intentionally fixed to collect for now:
    - First message runs immediately.
    - While running, new messages are queued.
    - On drain, all queued messages are coalesced into a single follow-up turn.
    """

    def __init__(
        self,
        debounce_ms: int = 1000,
        cap: int = 20,
        drop_policy: QueueDropPolicy = "summarize",
    ) -> None:
        self.debounce_ms = max(0, int(debounce_ms))
        self.cap = max(1, int(cap))
        policy = (drop_policy or "summarize").strip().lower()
        self.drop_policy: QueueDropPolicy = policy if policy in {"summarize", "old", "new"} else "summarize"
        self._states: dict[str, _SessionQueueState] = {}
        self._lock = Lock()

    @property
    def debounce_seconds(self) -> float:
        return float(self.debounce_ms) / 1000.0

    def begin_or_enqueue(self, key: str, item: QueuedInboundMessage) -> bool:
        """
        Try to become active runner for this key.

        Returns:
        - True: caller should process now.
        - False: caller was queued (or dropped by policy).
        """
        with self._lock:
            state = self._states.get(key)
            if state is None:
                state = _SessionQueueState()
                self._states[key] = state

            if not state.running:
                state.running = True
                return True

            self._enqueue_locked(state, item)
            return False

    def drain_or_finish(self, key: str) -> Optional[InboundBatch]:
        """
        Atomically fetch the next coalesced batch, or finish the session if idle.
        """
        with self._lock:
            state = self._states.get(key)
            if state is None:
                return None

            if not state.items and state.dropped_count <= 0:
                del self._states[key]
                return None

            items = list(state.items)
            state.items.clear()
            summary = self._format_summary(state)
            state.dropped_count = 0
            state.summary_lines = []
            return InboundBatch(messages=items, summary=summary)

    def force_release(self, key: str) -> None:
        """Best-effort escape hatch to avoid stuck running flags on unexpected failure."""
        with self._lock:
            self._states.pop(key, None)

    @staticmethod
    def build_collect_message(batch: InboundBatch) -> str:
        if not batch.messages:
            return ""

        if len(batch.messages) == 1 and not (batch.summary or "").strip():
            return batch.messages[0].message_text

        lines = ["[Queued follow-up messages while previous request was processing]"]
        for idx, msg in enumerate(batch.messages, start=1):
            lines.append(f"Message #{idx}: {msg.message_text}")
        if batch.summary:
            lines.append(batch.summary)
        lines.append("Please handle them together and prioritize the latest message if intents conflict.")
        return "\n\n".join(lines)

    def _enqueue_locked(self, state: _SessionQueueState, item: QueuedInboundMessage) -> None:
        if len(state.items) < self.cap:
            state.items.append(item)
            return

        if self.drop_policy == "new":
            logger.debug("Inbound queue full, dropping newest message due to drop_policy='new'")
            return

        dropped = state.items.pop(0)
        if self.drop_policy == "summarize":
            state.dropped_count += 1
            preview = self._message_preview(dropped.message_text)
            if preview:
                state.summary_lines.append(preview)
                if len(state.summary_lines) > 5:
                    state.summary_lines = state.summary_lines[-5:]
        state.items.append(item)

    @staticmethod
    def _message_preview(text: str, max_len: int = 120) -> str:
        msg = " ".join((text or "").split()).strip()
        if not msg:
            return ""
        return msg if len(msg) <= max_len else msg[: max_len - 3] + "..."

    @staticmethod
    def _format_summary(state: _SessionQueueState) -> Optional[str]:
        if state.dropped_count <= 0:
            return None
        if not state.summary_lines:
            return f"{state.dropped_count} queued message(s) were dropped due to queue capacity."
        bullets = "\n".join([f"- {line}" for line in state.summary_lines])
        return (
            f"{state.dropped_count} queued message(s) were dropped due to queue capacity.\n"
            f"Summary of dropped messages:\n{bullets}"
        )
