"""Tests for Langfuse credential detection and the startup check.

Tracing silently did nothing for the life of the project: ``.env`` held the
placeholders from ``.env.example``, the emptiness check passed them, and every
trace 401'd in a background thread that swallows its own errors. These tests
pin the two behaviours that make that state visible instead.
"""

import pytest

from backend.app.services.llm import tracing


@pytest.fixture(autouse=True)
def _reset_client(monkeypatch):
    """Clear the module-level singleton so each test builds its own."""
    monkeypatch.setattr(tracing, "_langfuse", None)


def _set_keys(monkeypatch, public: str, secret: str, host: str = "http://localhost:3000") -> None:
    monkeypatch.setattr(tracing.settings, "langfuse_public_key", public)
    monkeypatch.setattr(tracing.settings, "langfuse_secret_key", secret)
    monkeypatch.setattr(tracing.settings, "langfuse_host", host)


# ── Placeholder detection ───────────────────────────────────────────────────


def test_env_example_placeholders_count_as_unconfigured(monkeypatch) -> None:
    """The exact values .env.example ships. These passed the old check."""
    _set_keys(monkeypatch, "your-langfuse-public-key-here", "your-langfuse-secret-key-here")

    assert tracing.tracing_configured() is False
    assert tracing.verify_tracing() == "disabled"


def test_empty_keys_count_as_unconfigured(monkeypatch) -> None:
    _set_keys(monkeypatch, "", "")

    assert tracing.tracing_configured() is False


def test_one_placeholder_is_enough_to_disable(monkeypatch) -> None:
    """A half-filled .env is still not a usable credential pair."""
    _set_keys(monkeypatch, "pk-lf-real", "your-langfuse-secret-key-here")

    assert tracing.tracing_configured() is False


def test_locally_seeded_keys_are_accepted(monkeypatch) -> None:
    """`make langfuse-up` mints these; they must not read as placeholders."""
    _set_keys(monkeypatch, "pk-lf-devlogplus-local", "sk-lf-devlogplus-local")

    assert tracing.tracing_configured() is True


def test_unusual_self_hosted_keys_are_accepted(monkeypatch) -> None:
    """Headless init allows arbitrary key shapes, so the check stays narrow:
    anything that isn't placeholder-shaped is treated as real and left to
    auth_check to validate."""
    _set_keys(monkeypatch, "totally-custom-public", "totally-custom-secret")

    assert tracing.tracing_configured() is True


def test_placeholder_match_is_case_and_whitespace_insensitive(monkeypatch) -> None:
    _set_keys(monkeypatch, "  YOUR-Langfuse-Public-Key-HERE  ", "your-langfuse-secret-key-here")

    assert tracing.tracing_configured() is False


# ── Startup verification ────────────────────────────────────────────────────


class _StubClient:
    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc
        self.calls = 0

    def auth_check(self) -> bool:
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return True


def test_valid_credentials_report_ok(monkeypatch) -> None:
    _set_keys(monkeypatch, "pk-lf-devlogplus-local", "sk-lf-devlogplus-local")
    stub = _StubClient()
    monkeypatch.setattr(tracing, "_get_langfuse", lambda: stub)

    assert tracing.verify_tracing() == "ok"
    assert stub.calls == 1


def test_rejected_credentials_report_unauthorized_without_raising(monkeypatch) -> None:
    """A wrong-region key is a 401. Startup must survive it — tracing is
    optional, and losing observability must not stop the app serving."""
    _set_keys(monkeypatch, "pk-lf-eu-key", "sk-lf-eu-key", host="https://us.cloud.langfuse.com")
    monkeypatch.setattr(tracing, "_get_langfuse", lambda: _StubClient(RuntimeError("401")))

    assert tracing.verify_tracing() == "unauthorized"


class _RecordingLogger:
    """Captures formatted warnings.

    Not ``caplog``: the test database is migrated with Alembic, whose
    ``fileConfig()`` runs with ``disable_existing_loggers=True`` and silences
    every app logger created before it. That makes ``caplog`` assertions pass
    alone and fail in the full suite.
    """

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str, *args: object) -> None:
        self.warnings.append(msg % args if args else msg)

    def info(self, msg: str, *args: object) -> None:
        pass

    def exception(self, msg: str, *args: object) -> None:
        pass


def test_unauthorized_warning_names_the_host(monkeypatch) -> None:
    """Region mismatch is the likeliest cause, so the host has to be in the
    message — without it a 401 reads as a revoked key."""
    _set_keys(monkeypatch, "pk-lf-x", "sk-lf-x", host="https://cloud.langfuse.com")
    monkeypatch.setattr(tracing, "_get_langfuse", lambda: _StubClient(RuntimeError("401")))
    recorder = _RecordingLogger()
    monkeypatch.setattr(tracing, "logger", recorder)

    tracing.verify_tracing()

    assert any("https://cloud.langfuse.com" in w and "region" in w for w in recorder.warnings)


def test_disabled_warning_explains_the_consequence(monkeypatch) -> None:
    """The reason this mattered: no trace means no recoverable request body
    when an LLM response fails to parse."""
    _set_keys(monkeypatch, "your-langfuse-public-key-here", "your-langfuse-secret-key-here")
    recorder = _RecordingLogger()
    monkeypatch.setattr(tracing, "logger", recorder)

    tracing.verify_tracing()

    assert any("untraced" in w for w in recorder.warnings)


def test_client_construction_failure_degrades_to_disabled(monkeypatch) -> None:
    _set_keys(monkeypatch, "pk-lf-x", "sk-lf-x")
    monkeypatch.setattr(tracing, "_get_langfuse", lambda: None)

    assert tracing.verify_tracing() == "disabled"
