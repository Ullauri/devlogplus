"""Tests for the post-generation Go compile check.

The load-bearing distinction here is **skipped is not failed**. The compile
check exists to catch a model that wrote broken Go; when there is no toolchain
to run, nothing was learned either way. Collapsing that into "failed" makes a
missing `go` binary look like broken generated code, which fires the
regeneration retry — throwing away a good project and spending a second LLM
call to fix nothing.
"""

from pathlib import Path

import pytest

from backend.app.pipelines.project_pipeline import CompileCheck, _verify_go_build

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_missing_go_binary_is_skipped_not_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The observed failure: no Go on the box, so the check cannot run."""
    from backend.app.pipelines import project_pipeline

    monkeypatch.setattr(
        project_pipeline.settings, "go_executable", str(tmp_path / "definitely-not-go")
    )

    check = await _verify_go_build(tmp_path)

    assert check.status == "skipped"
    # The caller keys the retry off `.failed`; a skip must not trigger it.
    assert check.failed is False
    assert "not found" in (check.error or "")


async def test_missing_go_binary_is_skipped_even_when_go_mod_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """There are two FileNotFoundError paths — `go mod init` and `go build`.

    With no go.mod the first one runs; with one present the check falls
    straight through to `go build`. Both must report a skip.
    """
    from backend.app.pipelines import project_pipeline

    monkeypatch.setattr(
        project_pipeline.settings, "go_executable", str(tmp_path / "definitely-not-go")
    )
    (tmp_path / "go.mod").write_text("module project\n\ngo 1.22\n")

    check = await _verify_go_build(tmp_path)

    assert check.status == "skipped"
    assert check.failed is False


async def test_failed_status_reports_failed() -> None:
    assert CompileCheck("failed", "undefined: foo").failed is True


async def test_passed_status_carries_no_error() -> None:
    check = CompileCheck("passed")

    assert check.failed is False
    assert check.error is None
