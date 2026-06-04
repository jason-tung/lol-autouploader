"""
Riot Games → YouTube auto-uploader.

Polls for new ranked solo/duo games, matches them to video recordings in
Videos\\Ascent, and uploads with title: "<W/L> <K/D/A> vs <Enemy Jungler>".

Configure config.json before running. Place client_secrets.json alongside this
script (or the .exe) for YouTube OAuth.

Riot dev keys expire every 24h — get a persistent key from the Riot developer
portal once you've set up a project.
"""

import json
import os
import sys
import threading
import time
import winreg
from datetime import datetime

from database import Database
from riot_api import RiotAPI, RiotAPIError
from video_finder import find_matching_video
from youtube_api import upload_video

_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REGISTRY_NAME = "LoLAutoUploader"


def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_config(base_dir: str) -> dict:
    path = os.path.join(base_dir, "config.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"config.json not found at {path}")
    with open(path) as f:
        return json.load(f)


def build_title(game_info: dict) -> str:
    outcome = "Win" if game_info["win"] else "Loss"
    kda = f"{game_info['kills']}/{game_info['deaths']}/{game_info['assists']}"
    date = game_info["game_start_local"].strftime("%m/%d")
    return f"{date} {outcome} {kda} {game_info['my_champion']} vs {game_info['enemy_jungler']}"


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Startup registry helpers
# ---------------------------------------------------------------------------

def _is_startup_enabled(exe_path: str) -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, _REGISTRY_NAME)
        winreg.CloseKey(key)
        return val == exe_path
    except OSError:
        return False


def _set_startup(exe_path: str, enable: bool):
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY, 0, winreg.KEY_SET_VALUE)
    if enable:
        winreg.SetValueEx(key, _REGISTRY_NAME, 0, winreg.REG_SZ, exe_path)
    else:
        try:
            winreg.DeleteValue(key, _REGISTRY_NAME)
        except OSError:
            pass
    winreg.CloseKey(key)


# ---------------------------------------------------------------------------
# System tray
# ---------------------------------------------------------------------------

def _resource_path(filename: str) -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def _make_tray_icon():
    from PIL import Image
    path = _resource_path("icon.png")
    return Image.open(path).convert("RGBA")


def run_tray(exe_path: str, stop_event: threading.Event):
    import pystray

    base_dir = os.path.dirname(exe_path)

    def on_open_log(icon, item):
        log_path = os.path.join(base_dir, "run.log")
        if os.path.exists(log_path):
            os.startfile(log_path)

    def on_toggle_startup(icon, item):
        _set_startup(exe_path, not _is_startup_enabled(exe_path))

    def startup_checked(item):
        return _is_startup_enabled(exe_path)

    def on_exit(icon, item):
        stop_event.set()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open Log", on_open_log),
        pystray.MenuItem("Start on Login", on_toggle_startup, checked=startup_checked),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_exit),
    )
    icon = pystray.Icon(_REGISTRY_NAME, _make_tray_icon(), "LoL Auto-Uploader", menu)
    icon.run()


# ---------------------------------------------------------------------------
# Polling logic
# ---------------------------------------------------------------------------

def _fmt_game(g: dict) -> str:
    outcome = "Win" if g["win"] else "Loss"
    kda = f"{g['kills']}/{g['deaths']}/{g['assists']}"
    started = g["game_start_local"].strftime("%m/%d %H:%M")
    return f"  {g['my_champion']} | {outcome} {kda} vs {g['enemy_jungler']} | {started}"


def process_new_matches(riot: RiotAPI, db: Database, config: dict, base_dir: str):
    log("Checking for new ranked games...")
    try:
        match_ids = riot.get_ranked_match_ids(count=20)
    except RiotAPIError as e:
        log(f"Riot API error: {e}")
        return

    new_ids = [mid for mid in match_ids if not db.is_uploaded(mid)]
    already_done = len(match_ids) - len(new_ids)

    if not new_ids:
        log(f"No new games ({already_done} already uploaded).")
        return

    # Fetch and parse all new matches (oldest first)
    parsed: list[dict] = []
    for match_id in reversed(new_ids):
        try:
            game_info = riot.parse_match(riot.get_match(match_id))
            parsed.append(game_info)
        except (RiotAPIError, Exception) as e:
            log(f"  Error fetching {match_id}: {e}")

    # Assign videos
    used_video_paths: set[str] = set()
    no_video: list[dict] = []
    to_upload: list[tuple[dict, str]] = []

    for game_info in parsed:
        video_path = find_matching_video(
            config["videos_dir"],
            game_info,
            tolerance_minutes=config.get("video_match_tolerance_minutes", 90),
            excluded_paths=used_video_paths,
        )
        if video_path:
            used_video_paths.add(video_path)
            to_upload.append((game_info, video_path))
        else:
            no_video.append(game_info)

    # --- Summary ---
    log(f"{already_done} already uploaded, {len(new_ids)} new.")

    if no_video:
        log(f"Skipping {len(no_video)} (no video):")
        for g in no_video:
            log(_fmt_game(g))

    if not to_upload:
        return

    log(f"Uploading {len(to_upload)}:")
    for game_info, video_path in to_upload:
        title = build_title(game_info)
        log(f"{_fmt_game(game_info)}")
        log(f'      {os.path.basename(video_path)}  ->  "{title}"')

    for game_info, video_path in to_upload:
        title = build_title(game_info)
        log(f"Starting: {_fmt_game(game_info).strip()}")
        try:
            video_id = upload_video(
                video_path=video_path,
                title=title,
                privacy=config.get("youtube_privacy", "unlisted"),
                base_dir=base_dir,
                playlist_id=config.get("youtube_playlist_id"),
            )
        except FileNotFoundError as e:
            log(f"  {e}")
            return
        except Exception as e:
            log(f"  Upload failed: {e}")
            continue

        db.record_upload(game_info, video_path, video_id, title)
        log(f"  Uploaded -> https://youtube.com/watch?v={video_id}")


def poll_loop(riot: RiotAPI, db: Database, config: dict, base_dir: str,
              stop_event: threading.Event):
    log("Auto-uploader started.")
    log(f"  Videos dir:    {config['videos_dir']}")
    log(f"  Poll interval: {config['poll_interval_seconds']}s")
    log(f"  DB:            {os.path.join(base_dir, 'uploads.db')}")

    while not stop_event.is_set():
        try:
            process_new_matches(riot, db, config, base_dir)
        except Exception as e:
            log(f"Unexpected error: {e}")

        interval = config.get("poll_interval_seconds", 300)
        log(f"Sleeping {interval}s until next check...")
        stop_event.wait(interval)

    log("Auto-uploader stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    base_dir = get_base_dir()
    frozen = getattr(sys, "frozen", False)

    if frozen:
        log_path = os.path.join(base_dir, "run.log")
        log_file = open(log_path, "w", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file

    try:
        config = load_config(base_dir)
    except FileNotFoundError as e:
        if not frozen:
            print(e)
        return

    db_path = os.path.join(base_dir, "uploads.db")
    db = Database(db_path)
    riot = RiotAPI(api_key=config["riot_api_key"], puuid=config["puuid"])

    stop_event = threading.Event()

    if frozen:
        # Polling runs in background; tray icon owns the main thread
        poll_thread = threading.Thread(
            target=poll_loop,
            args=(riot, db, config, base_dir, stop_event),
            daemon=True,
        )
        poll_thread.start()
        run_tray(sys.executable, stop_event)
    else:
        # Dev mode: run polling on main thread, no tray
        try:
            poll_loop(riot, db, config, base_dir, stop_event)
        except KeyboardInterrupt:
            log("Shutting down.")


if __name__ == "__main__":
    main()
