from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.tools.safety import (
    ConfirmationRequired,
    bounded_number,
    require_confirmation,
    require_platform,
    resolve_user_path,
    run_command,
)


def test_confirmation_is_explicit() -> None:
    with pytest.raises(ConfirmationRequired, match="confirmed=true"):
        require_confirmation("delete the file", False)
    require_confirmation("delete the file", True)


def test_resolve_user_path_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "home"
    root.mkdir()
    assert resolve_user_path(str(root / "notes.txt"), allowed_roots=(root,)) == root / "notes.txt"
    with pytest.raises(PermissionError):
        resolve_user_path(str(tmp_path / "outside.txt"), allowed_roots=(root,))


def test_resolve_user_path_requires_existing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_user_path(str(tmp_path / "missing"), must_exist=True, allowed_roots=(tmp_path,))


def test_run_command_never_uses_a_shell() -> None:
    with patch("backend.app.tools.safety.subprocess.run") as mocked:
        run_command(["safe-command", "argument"], timeout=5)
    assert mocked.call_args.kwargs["shell"] is False
    assert mocked.call_args.args[0] == ["safe-command", "argument"]


def test_platform_guard_and_number_bounds() -> None:
    with patch("backend.app.tools.safety.platform.system", return_value="Windows"):
        assert require_platform("Windows") == "Windows"
        with pytest.raises(RuntimeError, match="current platform: Windows"):
            require_platform("Darwin")
    assert bounded_number(5, minimum=0, maximum=10, field="value") == 5
    with pytest.raises(ValueError, match="between 0 and 10"):
        bounded_number(11, minimum=0, maximum=10, field="value")
