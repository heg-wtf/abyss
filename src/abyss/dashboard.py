"""Abysscope web dashboard subprocess management.

The dashboard is a Next.js app shipped alongside the Python package. It runs
as a child subprocess of the abyss bot manager so a single ``abyss start``
boots both the API surface (``chat_server``) and the UI.

This module owns:

- Locating the bundled or source-tree ``abysscope/`` directory.
- Building the dashboard (``npm install`` + ``next build``) with progress.
- Spawning ``next start`` as a child process and tracking its PID.
- Stopping the child gracefully (SIGTERM → wait → SIGKILL fallback).
- Reading running state from the PID file (PID + port).

The CLI used to expose ``abyss dashboard start/stop/restart/status`` for
this; the subcommand was retired in v2026.05.15 in favor of folding the
lifecycle into the top-level ``abyss start / stop / restart``.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

from abyss.config import abyss_home
from abyss.dashboard_ui import BuildProgress, BuildStep, StepStatus

DEFAULT_PORT = 3847
PID_FILE_NAME = "abysscope.pid"

logger = logging.getLogger(__name__)


def pid_file() -> Path:
    """Path to the PID file (line 1 = pid, line 2 = port)."""
    return abyss_home() / PID_FILE_NAME


def find_abysscope_directory() -> Path | None:
    """Locate abysscope/: cwd → bundled package data → source-relative."""
    candidates = [
        Path.cwd() / "abysscope",
        Path(__file__).resolve().parent / "abysscope_data",
        Path(__file__).resolve().parent.parent.parent / "abysscope",
    ]
    return next((c for c in candidates if c.exists()), None)


def is_port_in_use(port: int) -> bool:
    """True when something is already listening on ``port`` on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        return connection.connect_ex(("localhost", port)) == 0


def is_running() -> tuple[bool, int | None]:
    """Return ``(running, pid)`` — falls back to port probe when PID is stale."""
    path = pid_file()
    if path.exists():
        try:
            lines = path.read_text().strip().splitlines()
            pid = int(lines[0])
            os.kill(pid, 0)
            return True, pid
        except ValueError, ProcessLookupError, PermissionError, IndexError, OverflowError:
            path.unlink(missing_ok=True)

    if is_port_in_use(DEFAULT_PORT):
        return True, None
    return False, None


def get_port() -> int | None:
    """Read the port the dashboard is listening on (line 2 of PID file)."""
    path = pid_file()
    if not path.exists():
        return None
    try:
        lines = path.read_text().strip().splitlines()
        return int(lines[1]) if len(lines) > 1 else DEFAULT_PORT
    except ValueError, IndexError:
        return DEFAULT_PORT


def stop_running() -> int | None:
    """Send SIGTERM to the PID in :func:`pid_file`. Return the killed PID."""
    running, pid = is_running()
    if not running or pid is None:
        pid_file().unlink(missing_ok=True)
        return None
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError, PermissionError:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError) as fallback_error:
            # Both killpg and kill failed — the process is already gone or
            # owned by another user. Either way nothing left to do; log for
            # diagnosability and proceed with PID-file cleanup.
            logger.debug("stop_running could not signal PID %s: %s", pid, fallback_error)
    pid_file().unlink(missing_ok=True)
    return pid


def _node_modules_present(directory: Path) -> bool:
    return (directory / "node_modules").exists()


def _detect_commit_sha(start: Path) -> str:
    """Best-effort ``git rev-parse --short HEAD`` from the source tree.

    Returns the short SHA when run from an editable checkout (the
    common dev path), or an empty string when ``.git`` is missing
    (e.g. a packaged wheel install). Errors are silenced because the
    SHA is a UX nicety, not a correctness signal.
    """
    candidates: list[Path] = []
    current = start.resolve()
    for _ in range(5):
        candidates.append(current)
        if current.parent == current:
            break
        current = current.parent
    for candidate in candidates:
        try:
            result = subprocess.run(  # noqa: S603 — fixed argv, no shell
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=candidate,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except OSError, subprocess.SubprocessError:
            continue
    return ""


def _next_build_artifact_size(directory: Path) -> int:
    artifact = directory / ".next"
    if not artifact.exists():
        return 0
    total = 0
    try:
        for path in artifact.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
    except OSError:
        return total
    return total


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


def _format_directory(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _run_to_log(args: list[str], cwd: Path, env: dict[str, str], log_path: Path) -> int:
    with log_path.open("ab") as log_file:
        log_file.write(f"\n$ {' '.join(args)}\n".encode())
        log_file.flush()
        proc = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return proc.returncode


@dataclass
class DashboardHandle:
    """Reference to a running dashboard subprocess."""

    process: subprocess.Popen
    port: int
    abysscope_directory: Path


def build_steps() -> list[BuildStep]:
    """Build-progress steps for boot-time UI."""
    return [
        BuildStep("Locate dashboard"),
        BuildStep("Install dependencies"),
        BuildStep("Build dashboard"),
        BuildStep("Start dashboard server"),
    ]


def build_and_start(
    port: int,
    log_path: Path,
    progress: BuildProgress,
    abyss_version: str,
) -> DashboardHandle:
    """Build the dashboard and spawn ``next start`` as a child process.

    Steps are reported through ``progress`` so the boot UI can show
    progress next to ``chat_server`` and per-bot init in a single
    checklist. ``log_path`` collects stdout/stderr from ``npm`` and
    ``next``.
    """
    abysscope_directory: Path | None = None
    next_env: dict[str, str] = {}

    with progress.step("Locate dashboard") as step:
        abysscope_directory = find_abysscope_directory()
        if abysscope_directory is None:
            step.detail = "directory not found"
            raise FileNotFoundError("abysscope directory not found")
        step.detail = _format_directory(abysscope_directory)

    with progress.step("Install dependencies") as step:
        if _node_modules_present(abysscope_directory):
            step.status = StepStatus.SKIPPED
            step.detail = "cached"
        else:
            step.detail = "running npm install"
            code = _run_to_log(
                ["npm", "install"],
                cwd=abysscope_directory,
                env=os.environ.copy(),
                log_path=log_path,
            )
            if code != 0:
                step.detail = f"npm install exited {code}"
                raise RuntimeError(step.detail)
            step.detail = "installed"

    existing_node_options = os.environ.get("NODE_OPTIONS", "")
    commit_sha = _detect_commit_sha(abysscope_directory)
    next_env = {
        **os.environ,
        "NEXT_PUBLIC_ABYSS_VERSION": abyss_version,
        "NEXT_PUBLIC_ABYSS_COMMIT": commit_sha,
        "NODE_OPTIONS": (f"{existing_node_options} --dns-result-order=ipv4first".strip()),
    }

    with progress.step("Build dashboard") as step:
        step.detail = "next build"
        code = _run_to_log(
            ["npx", "next", "build"],
            cwd=abysscope_directory,
            env=next_env,
            log_path=log_path,
        )
        if code != 0:
            step.detail = f"exit {code} — see log"
            raise RuntimeError(step.detail)
        bundle = _next_build_artifact_size(abysscope_directory)
        step.detail = f"bundle {_format_size(bundle)}" if bundle else "built"

    with progress.step("Start dashboard server") as step:
        process = subprocess.Popen(
            ["npx", "next", "start", "--port", str(port), "--hostname", "0.0.0.0"],
            cwd=abysscope_directory,
            env=next_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pid_file().write_text(f"{process.pid}\n{port}\n")
        step.detail = f"PID {process.pid} (port {port})"

    return DashboardHandle(
        process=process,
        port=port,
        abysscope_directory=abysscope_directory,
    )


def stop_handle(handle: DashboardHandle, *, timeout: float = 5.0) -> None:
    """Stop a :class:`DashboardHandle` gracefully (SIGTERM → SIGKILL)."""
    process = handle.process
    if process.poll() is not None:
        pid_file().unlink(missing_ok=True)
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except ProcessLookupError, PermissionError:
        try:
            process.terminate()
        except (ProcessLookupError, PermissionError) as terminate_error:
            # SIGTERM via pgid and process.terminate both failed — the
            # subprocess is already gone or unkillable from this user. Let
            # the wait() below time out so the SIGKILL escalation runs.
            logger.debug(
                "stop_handle could not SIGTERM PID %s: %s",
                process.pid,
                terminate_error,
            )

    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("dashboard did not exit in %.1fs, sending SIGKILL", timeout)
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError, PermissionError:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                process.kill()
    finally:
        pid_file().unlink(missing_ok=True)
