"""
Self-updater for the packaged (frozen) app.

Checks GitHub Releases for a newer version, and — when the user opts in — downloads
the release zip, extracts the new autouploader.exe, and swaps it in via a small
helper batch script (Windows won't let a running .exe overwrite itself).

Only meaningful when running as the frozen .exe; in dev mode there's nothing to swap.
"""

import io
import os
import subprocess
import tempfile
import zipfile

import requests

from version import __version__

REPO = "jason-tung/lol-autouploader"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
EXE_IN_ZIP = "autouploader.exe"  # name of the exe inside the release zip

_CHECK_TIMEOUT = 15
_DOWNLOAD_TIMEOUT = 180
_CREATE_NO_WINDOW = 0x08000000


def _parse_version(v: str) -> tuple:
    """'v1.2.10' -> (1, 2, 10). Non-numeric parts degrade to 0."""
    parts = []
    for chunk in v.lstrip("v").strip().split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_for_update():
    """
    Return (latest_version_str, zip_download_url) if a newer release exists,
    otherwise None. Raises on network/HTTP errors (caller should catch).
    """
    resp = requests.get(
        LATEST_URL,
        timeout=_CHECK_TIMEOUT,
        headers={"Accept": "application/vnd.github+json"},
    )
    resp.raise_for_status()
    data = resp.json()

    tag = data.get("tag_name", "")
    if not tag or _parse_version(tag) <= _parse_version(__version__):
        return None

    zip_url = None
    for asset in data.get("assets", []):
        if asset.get("name", "").endswith(".zip"):
            zip_url = asset.get("browser_download_url")
            break
    if not zip_url:
        return None

    return tag.lstrip("v"), zip_url


def download_and_apply(zip_url: str, exe_path: str, log=print):
    """
    Download the release zip, stage the new exe next to exe_path, and spawn a
    helper that swaps it in after this process exits, then relaunches.

    The caller should stop the app (tray + poll loop) right after this returns.
    """
    log(f"Downloading update from {zip_url} ...")
    resp = requests.get(zip_url, timeout=_DOWNLOAD_TIMEOUT)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        exe_bytes = zf.read(EXE_IN_ZIP)

    new_exe = exe_path + ".new"
    with open(new_exe, "wb") as f:
        f.write(exe_bytes)
    log(f"Staged new version at {new_exe} ({len(exe_bytes) // 1024} KB)")

    _spawn_swap_helper(exe_path, new_exe)
    log("Restarting to apply update...")


def _spawn_swap_helper(exe_path: str, new_exe: str):
    """
    Write and launch a detached .bat that waits for this PID to exit, moves the
    new exe over the old one, relaunches it, and deletes itself.
    """
    pid = os.getpid()
    script = f"""@echo off
:waitloop
tasklist /FI "PID eq {pid}" 2>nul | find /I "autouploader.exe" >nul
if not errorlevel 1 (
  ping -n 2 127.0.0.1 >nul
  goto waitloop
)
move /y "{new_exe}" "{exe_path}" >nul
start "" "{exe_path}"
del "%~f0"
"""
    fd, bat_path = tempfile.mkstemp(suffix=".bat")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(script)

    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=_CREATE_NO_WINDOW,
        close_fds=True,
    )
