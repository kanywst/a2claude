"""CLI argument validation that must fail before the server starts."""

from __future__ import annotations

import re
from unittest.mock import patch

from typer.testing import CliRunner

from a2claude.cli import app

runner = CliRunner()


def _plain(output: str) -> str:
    """Reduce Typer's Rich-rendered error to bare tokens.

    The BadParameter message is drawn in a bordered panel whose width follows the
    terminal, so it wraps differently across environments (CI at 80 columns
    splits ``--permission-mode`` across the box border). Strip ANSI codes and
    keep only word characters and hyphens so the message text can be matched
    regardless of where the panel wrapped it.
    """
    no_ansi = re.sub(r"\x1b\[[0-9;]*m", "", output)
    return re.sub(r"[^a-zA-Z0-9-]", "", no_ansi)


@patch("a2claude.cli.uvicorn.run")
def test_serve_rejects_invalid_permission_mode(mock_run):
    # Validation fails before uvicorn.run, so the server never starts.
    result = runner.invoke(
        app, ["serve", "--backend", "echo", "--permission-mode", "bogus"]
    )
    assert result.exit_code != 0
    mock_run.assert_not_called()
    plain = _plain(result.output)
    assert "permission-mode" in plain
    assert "bogus" in plain


@patch("a2claude.cli.uvicorn.run")
def test_serve_accepts_a_valid_permission_mode(mock_run):
    # 'plan' is valid, so validation passes and execution proceeds to uvicorn.run
    # (mocked here so no socket is bound).
    result = runner.invoke(
        app, ["serve", "--backend", "echo", "--permission-mode", "plan"]
    )
    assert result.exit_code == 0
    mock_run.assert_called_once()
