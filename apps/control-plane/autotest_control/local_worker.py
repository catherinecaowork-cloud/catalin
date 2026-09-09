"""本机执行器启停。给控制台顶栏按钮用，只管理这台机器上的 worker 进程。"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from autotest_control.settings import settings

_stop_event = threading.Event()


def request_local_stop() -> None:
    _stop_event.set()


def clear_local_stop() -> None:
    _stop_event.clear()


def local_stop_requested() -> bool:
    return _stop_event.is_set()


def _pid_path() -> Path:
    return settings.var_dir / "local-worker.pid"


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            raw = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                encoding="gbk",
                errors="replace",
                timeout=5,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False
        for line in raw.splitlines():
            if "INFO:" in line or "信息:" in line:
                continue
            if f'"{pid}"' in line:
                return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except SystemError:
        return False
    return True


def _read_pid() -> int | None:
    path = _pid_path()
    if not path.exists():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        path.unlink(missing_ok=True)
        return None
    try:
        living = _alive(pid)
    except Exception:
        living = False
    if not living:
        path.unlink(missing_ok=True)
        return None
    return pid


def _worker_pids() -> list[int]:
    pids: list[int] = []
    saved = _read_pid()
    if saved:
        pids.append(saved)
    if sys.platform == "win32":
        pids.extend(_windows_worker_pids())
    else:
        pids.extend(_posix_worker_pids())
    seen: set[int] = set()
    out: list[int] = []
    me = os.getpid()
    for pid in pids:
        if pid in seen or pid == me or not _alive(pid):
            continue
        seen.add(pid)
        out.append(pid)
    return out


def _is_worker_command(cmd: str) -> bool:
    low = (cmd or "").lower().replace("\\", "/")
    if "uvicorn" in low or "autotest_control" in low:
        return False
    if "autotest_executor" in low and "worker" in low:
        return True
    if "runner" in low and "worker" in low:
        return True
    return False


def _windows_worker_pids() -> list[int]:
    rows = _windows_process_rows()
    pids: list[int] = []
    for pid, cmd in rows:
        if _is_worker_command(cmd):
            pids.append(pid)
    return pids


def _windows_process_rows() -> list[tuple[int, str]]:
    try:
        raw = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter "
                "\"Name='python.exe' OR Name='pythonw.exe' OR Name='runner.exe'\" | "
                "Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress",
            ],
            text=True,
            timeout=15,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return []
    import json

    data = json.loads(raw or "[]")
    if isinstance(data, dict):
        data = [data]
    rows: list[tuple[int, str]] = []
    for row in data:
        try:
            rows.append((int(row["ProcessId"]), str(row.get("CommandLine") or "")))
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def _posix_worker_pids() -> list[int]:
    try:
        raw = subprocess.check_output(["ps", "-eo", "pid,args"], text=True, timeout=10)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return []
    pids: list[int] = []
    for line in raw.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        pid_s, _, cmd = line.partition(" ")
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        if _is_worker_command(cmd):
            pids.append(pid)
    return pids


def start_local_worker() -> dict:
    clear_local_stop()
    saved = _read_pid()
    if saved:
        return {"ok": True, "already": True, "pid": saved, "leftover": []}

    settings.ensure_dirs()
    log_path = settings.var_dir / "worker-ui.log"
    logf = open(log_path, "ab", buffering=0)
    cmd = [
        sys.executable,
        "-u",
        "-m",
        "autotest_executor.cli",
        "worker",
        "--server",
        f"http://{settings.host}:{settings.port}",
        "--name",
        "local-ui",
        "--workspace",
        str(settings.var_dir / "worker-ui"),
    ]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    kwargs: dict = {
        "cwd": str(settings.var_dir.parent),
        "stdout": logf,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
        "env": env,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        )
        kwargs["close_fds"] = False
    proc = subprocess.Popen(cmd, **kwargs)
    _pid_path().write_text(str(proc.pid), encoding="utf-8")
    time.sleep(0.8)
    if proc.poll() is not None:
        tail = _log_tail(log_path)
        _pid_path().unlink(missing_ok=True)
        return {
            "ok": False,
            "already": False,
            "pid": proc.pid,
            "leftover": [],
            "error": tail or f"执行器进程 {proc.pid} 立刻退出，exit={proc.returncode}",
        }
    return {"ok": True, "already": False, "pid": proc.pid, "leftover": []}


def _log_tail(path: Path, n: int = 12) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:]).strip()


def stop_local_worker() -> dict:
    request_local_stop()
    pids = _worker_pids()
    killed: list[int] = []
    for pid in pids:
        _kill(pid)
        killed.append(pid)

    deadline = time.time() + 12
    pending = list(killed)
    while pending and time.time() < deadline:
        pending = [pid for pid in pending if _alive(pid)]
        if not pending:
            break
        for pid in pending:
            _kill(pid)
        time.sleep(0.3)

    leftover = [pid for pid in killed if _alive(pid)] or _worker_pids()
    if leftover:
        for pid in leftover:
            _kill(pid)
            if pid not in killed:
                killed.append(pid)
        leftover = _worker_pids()

    if not leftover:
        _pid_path().unlink(missing_ok=True)
        # 停止指令只在杀进程期间有效，否则新点的「开始」会立刻收到退出。
        clear_local_stop()
        return {"ok": True, "killed": killed, "leftover": []}

    clear_local_stop()
    return {"ok": False, "killed": killed, "leftover": leftover}


def _kill(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
