from services.inbound_message_queue import (
    InboundBatch,
    InboundMessageQueue,
    QueuedInboundMessage,
)


def _msg(text: str) -> QueuedInboundMessage:
    return QueuedInboundMessage(update=None, context=None, message_text=text)


def test_begin_or_enqueue_and_drain():
    queue = InboundMessageQueue(debounce_ms=0, cap=5, drop_policy="summarize")
    key = "u:1"

    assert queue.begin_or_enqueue(key, _msg("first")) is True
    assert queue.begin_or_enqueue(key, _msg("second")) is False

    batch = queue.drain_or_finish(key)
    assert isinstance(batch, InboundBatch)
    assert [m.message_text for m in batch.messages] == ["second"]

    # No queued work left -> runner is released.
    assert queue.drain_or_finish(key) is None


def test_drop_summarize_keeps_latest_and_adds_summary():
    queue = InboundMessageQueue(debounce_ms=0, cap=1, drop_policy="summarize")
    key = "u:2"

    assert queue.begin_or_enqueue(key, _msg("active")) is True
    assert queue.begin_or_enqueue(key, _msg("old queued")) is False
    assert queue.begin_or_enqueue(key, _msg("new queued")) is False

    batch = queue.drain_or_finish(key)
    assert batch is not None
    assert [m.message_text for m in batch.messages] == ["new queued"]
    assert "dropped" in (batch.summary or "").lower()


def test_build_collect_message_combines_messages():
    batch = InboundBatch(messages=[_msg("a"), _msg("b")], summary="1 dropped")
    text = InboundMessageQueue.build_collect_message(batch)
    assert "Message #1: a" in text
    assert "Message #2: b" in text
    assert "1 dropped" in text
