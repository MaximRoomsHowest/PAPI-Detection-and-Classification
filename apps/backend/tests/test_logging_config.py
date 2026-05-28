"""Tests for the structured-logging primitives (audit B-IMP-4)."""

from __future__ import annotations

import json
import logging

from app.logging_config import JsonFormatter, configure_logging, request_id_ctx


def test_json_formatter_emits_valid_json_line():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    out = formatter.format(record)

    parsed = json.loads(out)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert parsed["message"] == "hello world"
    assert "ts" in parsed


def test_json_formatter_includes_request_id_when_in_context():
    formatter = JsonFormatter()
    token = request_id_ctx.set("test-request-id-123")
    try:
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
    finally:
        request_id_ctx.reset(token)

    assert parsed["request_id"] == "test-request-id-123"


def test_json_formatter_forwards_extra_kwargs():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="analysis.success",
        args=(),
        exc_info=None,
    )
    # Simulate logger.info("...", extra={"foo": 42}).
    record.runway_id = "papi_24"
    record.processing_ms = 1234
    parsed = json.loads(formatter.format(record))

    assert parsed["runway_id"] == "papi_24"
    assert parsed["processing_ms"] == 1234


def test_json_formatter_stringifies_non_serialisable_extras():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    # Set() is not JSON-serialisable by default.
    record.weird = {1, 2, 3}
    parsed = json.loads(formatter.format(record))
    assert isinstance(parsed["weird"], str)
    assert "1" in parsed["weird"]


def test_configure_logging_is_idempotent():
    """Calling twice should replace the handler, not stack a duplicate."""
    configure_logging()
    handler_count_after_first = len(logging.getLogger().handlers)
    configure_logging()
    handler_count_after_second = len(logging.getLogger().handlers)
    assert handler_count_after_first == handler_count_after_second == 1
