"""Tests for the MCP server's stdio hygiene.

Under the stdio transport, stdout *is* the JSON-RPC channel. Anything else
written there lands mid-stream and the client fails to parse the response —
the failure looks like a malformed reply from the server, not like a log line.

This is not hypothetical: `database.py` passes `echo=(app_env ==
"development")`, and SQLAlchemy's echo installs a `StreamHandler(sys.stdout)`
(`sqlalchemy.log._add_default_handler`). With APP_ENV=development, a live probe
of the server produced:

    ValidationError: Invalid JSON: trailing characters
      input_value='... INFO sqlalchemy.engine.Engine ROLLBACK'
"""

import logging
import sys

import pytest

from backend.app.mcp_server import mcp, reroute_stdout_logging


@pytest.fixture
def scratch_logger():
    log = logging.getLogger("backend.tests.mcp_stdout_probe")
    log.handlers.clear()
    yield log
    log.handlers.clear()


def test_stdout_handler_is_moved_to_stderr(scratch_logger: logging.Logger) -> None:
    scratch_logger.addHandler(logging.StreamHandler(sys.stdout))

    reroute_stdout_logging()

    streams = [h.stream for h in scratch_logger.handlers]
    assert sys.stdout not in streams
    assert sys.stderr in streams


def test_the_handler_is_kept_not_dropped(scratch_logger: logging.Logger) -> None:
    """Redirected, so running the server by hand still shows its logging."""
    scratch_logger.addHandler(logging.StreamHandler(sys.stdout))

    reroute_stdout_logging()

    assert len(scratch_logger.handlers) == 1


def test_stderr_handlers_are_left_alone(scratch_logger: logging.Logger) -> None:
    handler = logging.StreamHandler(sys.stderr)
    scratch_logger.addHandler(handler)

    reroute_stdout_logging()

    assert handler.stream is sys.stderr


def test_sqlalchemy_echo_handler_is_caught(scratch_logger: logging.Logger) -> None:
    """The specific handler that broke the protocol, installed the real way."""
    from sqlalchemy.log import _add_default_handler

    _add_default_handler(scratch_logger)
    assert scratch_logger.handlers[0].stream is sys.stdout, "precondition: SQLAlchemy uses stdout"

    reroute_stdout_logging()

    assert scratch_logger.handlers[0].stream is sys.stderr


def test_is_idempotent(scratch_logger: logging.Logger) -> None:
    scratch_logger.addHandler(logging.StreamHandler(sys.stdout))

    reroute_stdout_logging()
    reroute_stdout_logging()

    assert len(scratch_logger.handlers) == 1
    assert scratch_logger.handlers[0].stream is sys.stderr


@pytest.mark.asyncio(loop_scope="session")
async def test_server_exposes_the_journal_tool() -> None:
    """`create_journal_entry` is the reason to reach for this server at all."""
    tools = {t.name for t in await mcp.list_tools()}

    assert "create_journal_entry" in tools
