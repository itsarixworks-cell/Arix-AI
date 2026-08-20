from __future__ import annotations

import importlib
import os
import platform
import subprocess
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

MAX_COMMAND_TIMEOUT_SECONDS = 120.0
MAX_TEXT_BYTES = 1_000_000


class ConfirmationRequired(ValueError):
    """Raised when a consequential action has not been explicitly confirmed."""


def require_confirmation(action: str, confirmed: bool) -> None:
    if not confirmed:
        label = " ".join(action.split())[:160] or "perform this action"
        raise ConfirmationRequired(
            f"Confirmation required to {label}. Ask the user, then call again with confirmed=true."
        )


def require_platform(*allowed: str) -> str:
    current = platform.system()
    if current not in allowed:
        supported = ", ".join(allowed)
        raise RuntimeError(f"This action requires one of these platforms: {supported}; current platform: {current}")
    return current


_KNOWN_FOLDER_NAMES = ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")


def _known_folder(name: str) -> Path:
    home = Path.home().resolve()
    direct = home / name
    one_drive = Path(os.environ.get("OneDrive", "")) / name if os.environ.get("OneDrive") else None
    if direct.exists() or one_drive is None or not one_drive.exists():
        return direct
    return one_drive


def _default_roots() -> tuple[Path, ...]:
    home = Path.home().resolve()
    candidates = [home]
    candidates.extend(_known_folder(name).resolve(strict=False) for name in _KNOWN_FOLDER_NAMES)
    return tuple(dict.fromkeys(candidates))


def _expand_known_folder_alias(value: str) -> Path | None:
    normalized = value.replace("\\", "/")
    head, separator, tail = normalized.partition("/")
    match = next((name for name in _KNOWN_FOLDER_NAMES if name.casefold() == head.casefold()), None)
    if match:
        return _known_folder(match) / tail if separator else _known_folder(match)
    return None


def resolve_user_path(
    raw: str,
    *,
    must_exist: bool = False,
    allowed_roots: Sequence[Path] | None = None,
) -> Path:
    value = raw.strip()
    if not value or "\x00" in value:
        raise ValueError("A valid path is required")

    home = Path.home().resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = _expand_known_folder_alias(value) or (home / candidate)
    resolved = candidate.resolve(strict=False)
    roots = tuple(Path(root).expanduser().resolve() for root in (allowed_roots or _default_roots()))
    if not any(resolved == root or resolved.is_relative_to(root) for root in roots):
        raise PermissionError("Path is outside the approved user-profile roots")

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")
    if resolved.exists():
        real = resolved.resolve(strict=True)
        if not any(real == root or real.is_relative_to(root) for root in roots):
            raise PermissionError("Resolved path escapes the approved user-profile roots")
    return resolved


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


@contextmanager
def atomic_output_path(path: Path, *, minimum_bytes: int = 1) -> Iterator[Path]:
    """Yield a sibling temporary path and atomically publish it after validation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=path.suffix or ".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        yield temporary
        verify_written_file(temporary, minimum_bytes=minimum_bytes)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def verify_written_file(path: Path, *, minimum_bytes: int = 1) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"The file was not created: {path}")
    size = path.stat().st_size
    if size < minimum_bytes:
        raise RuntimeError(f"The file was created but is unexpectedly empty: {path}")
    return {"path": str(path), "bytes": size, "exists": True}


def run_command(
    command: Sequence[str],
    *,
    timeout: float = 10.0,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    args = [str(part) for part in command]
    if not args or not args[0].strip():
        raise ValueError("A non-empty command is required")
    bounded_timeout = max(0.1, min(float(timeout), MAX_COMMAND_TIMEOUT_SECONDS))
    try:
        return subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=bounded_timeout,
            check=check,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Command timed out after {bounded_timeout:g} seconds") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "Command failed").strip()[:500]
        raise RuntimeError(detail) from error


def require_optional_dependency(module_name: str, install_hint: str = "") -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ImportError as error:
        hint = f" Install it with: {install_hint}" if install_hint else ""
        raise RuntimeError(f"Optional dependency '{module_name}' is required.{hint}") from error


def bounded_text(value: Any, *, limit: int, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return text


def bounded_number(value: Any, *, minimum: float, maximum: float, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a number") from error
    if number < minimum or number > maximum:
        raise ValueError(f"{field} must be between {minimum:g} and {maximum:g}")
    return number
