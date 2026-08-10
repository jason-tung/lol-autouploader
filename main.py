"""
Riot Games → YouTube auto-uploader.

Polls for new ranked solo/duo games, matches them to video recordings in
Videos\\Ascent, and uploads with title: "<W/L> <K/D/A> vs <Enemy Jungler>".

Configure config.json before running. Place client_secrets.json alongside this
script (or the .exe) for YouTube OAuth.

Riot dev keys expire every 24h — get a persistent key from the Riot developer
portal once you've set up a project.
"""

import argparse
import json
import os
import sys
import threading
import time
import winreg
from datetime import datetime

from database import Database
from riot_api import RiotAPI, RiotAPIError
from version import __version__
from video_finder import find_matching_video
from youtube_api import upload_video

_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REGISTRY_NAME = "LoLAutoUploader"

_VALID_PRIVACY = ("public", "unlisted", "private")


def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _load_accounts(cfg: dict) -> list[dict]:
    """
    Normalize the "accounts" list, filling in defaults and rejecting placeholders.

    Configs written before multi-account support kept a single puuid /
    youtube_playlist_id / youtube_privacy at the top level; those are folded
    into a one-entry list so existing installs keep working after an update.
    """
    accounts = cfg.get("accounts")
    if accounts is None:
        accounts = [{
            "description": "",
            "puuid": cfg.get("puuid", ""),
            "youtube_playlist_id": cfg.get("youtube_playlist_id"),
            "youtube_privacy": cfg.get("youtube_privacy", "unlisted"),
        }]

    if not isinstance(accounts, list) or not accounts:
        raise ValueError(
            'config.json: "accounts" must be a non-empty list.\n\n'
            "See config.example.json for the expected shape."
        )

    normalized = []
    for i, account in enumerate(accounts):
        where = f'config.json: accounts[{i}] ("{account.get("description", "")}")'
        if not isinstance(account, dict):
            raise ValueError(f"{where} is not an object.")

        puuid = account.get("puuid", "")
        if not puuid or puuid.startswith("your-"):
            raise ValueError(
                f'{where}: "puuid" is not set.\n\n'
                "Open config.json and fill in your real PUUID before running."
            )

        privacy = account.get("youtube_privacy", "unlisted")
        if privacy not in _VALID_PRIVACY:
            raise ValueError(
                f'{where}: "youtube_privacy" is "{privacy}".\n\n'
                f"It must be one of: {', '.join(_VALID_PRIVACY)}."
            )

        playlist_id = account.get("youtube_playlist_id") or None
        if playlist_id and playlist_id.startswith("your-"):
            playlist_id = None

        normalized.append({
            "description": account.get("description", ""),
            "puuid": puuid,
            "youtube_playlist_id": playlist_id,
            "youtube_privacy": privacy,
        })

    seen: set[str] = set()
    for account in normalized:
        if account["puuid"] in seen:
            raise ValueError(
                f'config.json: the PUUID for "{account["description"]}" is listed twice.\n\n'
                "Each account entry needs a distinct puuid."
            )
        seen.add(account["puuid"])

    return normalized


def load_config(base_dir: str) -> dict:
    path = os.path.join(base_dir, "config.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"config.json not found at {path}\n\n"
            "Copy config.example.json to config.json and fill in your API key, PUUID, and videos folder."
        )
    with open(path) as f:
        cfg = json.load(f)

    key = cfg.get("riot_api_key", "")
    if not key or key == "RGAPI-" or key.endswith("xxxxxxxxxxxx"):
        raise ValueError(
            'config.json: "riot_api_key" is not set.\n\n'
            "Open config.json and fill in your real values before running."
        )

    cfg["accounts"] = _load_accounts(cfg)
    return cfg


def account_label(account: dict) -> str:
    return account["description"] or f"puuid {account['puuid'][:8]}"


def build_title(game_info: dict) -> str:
    outcome = "Win" if game_info["win"] else "Loss"
    kda = f"{game_info['kills']}/{game_info['deaths']}/{game_info['assists']}"
    date = game_info["game_start_local"].strftime("%m/%d")
    minutes = game_info["game_duration_s"] / 60
    cspm = game_info["cs"] / minutes if minutes else 0
    cs = f"{cspm:.1f} cs/m"
    return f"{date} {outcome} {kda} {cs} {game_info['my_champion']} vs {game_info['enemy_jungler']}"


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

    from updater import check_for_update, download_and_apply

    base_dir = os.path.dirname(exe_path)
    update_info = {"version": None, "url": None}

    # --- Update handling ---------------------------------------------------

    def do_check(icon, notify_if_none=False):
        """Query GitHub once; on a newer release, surface it in the menu + notify."""
        try:
            result = check_for_update()
        except Exception as e:
            log(f"Update check failed: {e}")
            if notify_if_none:
                icon.notify("Couldn't check for updates (network?).", "LoL Auto-Uploader")
            return
        if result:
            update_info["version"], update_info["url"] = result
            icon.update_menu()
            icon.notify(
                f"Version {result[0]} is available. Right-click the tray icon to update.",
                "LoL Auto-Uploader update",
            )
            log(f"Update available: v{result[0]} (current v{__version__})")
        elif notify_if_none:
            icon.notify(f"You're up to date (v{__version__}).", "LoL Auto-Uploader")

    def update_checker(icon):
        """Check ~10s after startup, then once a day, until the app stops."""
        if stop_event.wait(10):
            return
        while not stop_event.is_set():
            do_check(icon)
            if stop_event.wait(24 * 3600):
                return

    def update_available(item):
        return update_info["version"] is not None

    def update_text(item):
        return f"Update to v{update_info['version']}"

    def on_update(icon, item):
        url = update_info["url"]
        if not url:
            return

        def worker():
            try:
                icon.notify("Downloading update...", "LoL Auto-Uploader")
                download_and_apply(url, exe_path, log=log)
                stop_event.set()
                icon.stop()
            except Exception as e:
                log(f"Update failed: {e}")
                icon.notify(f"Update failed: {e}", "LoL Auto-Uploader")

        threading.Thread(target=worker, daemon=True).start()

    def on_check_now(icon, item):
        threading.Thread(target=do_check, args=(icon, True), daemon=True).start()

    # --- Standard menu actions ---------------------------------------------

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
        pystray.MenuItem(update_text, on_update, visible=update_available),
        pystray.MenuItem("Check for Updates", on_check_now),
        pystray.MenuItem("Open Log", on_open_log),
        pystray.MenuItem("Start on Login", on_toggle_startup, checked=startup_checked),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_exit),
    )
    icon = pystray.Icon(
        _REGISTRY_NAME, _make_tray_icon(), f"LoL Auto-Uploader v{__version__}", menu
    )
    threading.Thread(target=update_checker, args=(icon,), daemon=True).start()
    icon.run()


# ---------------------------------------------------------------------------
# Polling logic
# ---------------------------------------------------------------------------

def _fmt_game(g: dict, account: dict | None = None) -> str:
    outcome = "Win" if g["win"] else "Loss"
    kda = f"{g['kills']}/{g['deaths']}/{g['assists']}"
    started = g["game_start_local"].strftime("%m/%d %H:%M")
    who = f"[{account_label(account)}] " if account else ""
    return f"  {who}{g['my_champion']} | {outcome} {kda} vs {g['enemy_jungler']} | {started}"


def _collect_new_games(clients: list[tuple[dict, RiotAPI]], db: Database) -> tuple[list[tuple[dict, dict]], bool]:
    """
    Poll every configured account for unseen ranked games.

    Returns (games, success), where games is a list of (game_info, account) and
    success=False means at least one account hit an API/network error. A failing
    account never blocks the others — its matches stay unseen and get retried.
    """
    games: list[tuple[dict, dict]] = []
    success = True

    for account, riot in clients:
        label = account_label(account)
        try:
            match_ids = riot.get_ranked_match_ids(count=20)
        except RiotAPIError as e:
            log(f"[{label}] Riot API error: {e}")
            success = False
            continue

        new_ids = [mid for mid in match_ids if not db.is_seen(mid)]
        if not new_ids:
            continue

        log(f"[{label}] {len(match_ids) - len(new_ids)} already seen, {len(new_ids)} new.")
        for match_id in reversed(new_ids):  # oldest first
            try:
                games.append((riot.parse_match(riot.get_match(match_id)), account))
            except Exception as e:
                log(f"[{label}]   Error fetching {match_id}: {e}")

    return games, success


def _collect_targeted_games(clients: list[tuple[dict, RiotAPI]],
                            match_ids: list[str]) -> list[tuple[dict, dict]]:
    """Fetch specific match IDs, attributing each to whichever account played in it."""
    games: list[tuple[dict, dict]] = []
    for match_id in match_ids:
        try:
            raw = clients[0][1].get_match(match_id)  # the API key is shared
        except Exception as e:
            log(f"  Error fetching {match_id}: {e}")
            continue

        participants = set(raw["metadata"]["participants"])
        owner = next(((a, r) for a, r in clients if a["puuid"] in participants), None)
        if owner is None:
            log(f"  {match_id}: none of your configured accounts played in this match.")
            continue

        account, riot = owner
        try:
            games.append((riot.parse_match(raw), account))
        except Exception as e:
            log(f"  Error parsing {match_id}: {e}")

    return games


def process_new_matches(clients: list[tuple[dict, RiotAPI]], db: Database, config: dict,
                        base_dir: str, dry_run: bool = False,
                        only_match_ids: list[str] | None = None) -> tuple[bool, bool]:
    """Return (found_new, success). success=False means an API/network error occurred."""
    if only_match_ids:
        games, success = _collect_targeted_games(clients, only_match_ids), True
    else:
        games, success = _collect_new_games(clients, db)

    if not games:
        return False, success

    # One recording folder serves every account — you can only play one account at
    # a time, so a video claimed by one account's game is off-limits to the others.
    games.sort(key=lambda ga: ga[0]["game_start_local"])

    used_video_paths: set[str] = set()
    no_video: list[tuple[dict, dict]] = []
    to_upload: list[tuple[dict, dict, str]] = []

    for game_info, account in games:
        video_path = find_matching_video(
            config["videos_dir"],
            game_info,
            tolerance_minutes=config.get("video_match_tolerance_minutes", 8),
            excluded_paths=used_video_paths,
        )
        if video_path:
            used_video_paths.add(video_path)
            to_upload.append((game_info, account, video_path))
        else:
            no_video.append((game_info, account))

    # --- Summary ---
    if no_video:
        log(f"Skipping {len(no_video)} (no video):")
        for game_info, account in no_video:
            log(_fmt_game(game_info, account))
            if not dry_run:
                db.record_skipped(game_info["match_id"])

    if not to_upload:
        return True, success

    log(f"{'Would upload' if dry_run else 'Uploading'} {len(to_upload)}:")
    for game_info, account, video_path in to_upload:
        log(_fmt_game(game_info, account))
        log(f'      {os.path.basename(video_path)}  ->  "{build_title(game_info)}"')
        log(f"      {account['youtube_privacy']} -> playlist {account['youtube_playlist_id'] or '(none)'}")

    if dry_run:
        log("Dry run - nothing uploaded, nothing written to the database.")
        return True, success

    for game_info, account, video_path in to_upload:
        title = build_title(game_info)
        log(f"Starting: {_fmt_game(game_info, account).strip()}")
        try:
            video_id = upload_video(
                video_path=video_path,
                title=title,
                privacy=account["youtube_privacy"],
                base_dir=base_dir,
                playlist_id=account["youtube_playlist_id"],
            )
        except FileNotFoundError as e:
            log(f"  {e}")
            return True, success
        except Exception as e:
            log(f"  Upload failed: {e}")
            continue

        db.record_upload(game_info, video_path, video_id, title)
        log(f"  Uploaded -> https://youtube.com/watch?v={video_id}")
    return True, success


def poll_loop(clients: list[tuple[dict, RiotAPI]], db: Database, config: dict, base_dir: str,
              stop_event: threading.Event):
    log(f"Auto-uploader started (v{__version__}).")
    log(f"  Videos dir:    {config['videos_dir']}")
    log(f"  Poll interval: {config['poll_interval_seconds']}s")
    log(f"  DB:            {os.path.join(base_dir, 'uploads.db')}")
    log(f"  Accounts:      {len(clients)}")
    for account, _ in clients:
        log(f"    {account_label(account)} -> {account['youtube_privacy']}, "
            f"playlist {account['youtube_playlist_id'] or '(none)'}")

    had_error = False

    while not stop_event.is_set():
        try:
            found_new, success = process_new_matches(clients, db, config, base_dir)
        except Exception as e:
            log(f"Unexpected error: {e}")
            success = False
            found_new = False

        if success and had_error:
            log("Back online — loop is still running.")
            had_error = False
        elif not success:
            had_error = True

        interval = config.get("poll_interval_seconds", 15)
        stop_event.wait(interval)

    log("Auto-uploader stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="autouploader",
        description="Upload new League ranked recordings to YouTube.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be uploaded without uploading or touching the database")
    parser.add_argument("--once", action="store_true",
                        help="run a single poll pass instead of looping")
    parser.add_argument("--match-id", action="append", default=[], metavar="ID",
                        help="process only this match ID (repeatable); implies --once")
    parser.add_argument("--base-dir", metavar="DIR",
                        help="folder holding config.json / uploads.db / token.pickle "
                             "(default: alongside this script or the exe)")
    return parser.parse_args(argv)


def main():
    frozen = getattr(sys, "frozen", False)

    # Redirect before argparse: the --noconsole exe has no stdout/stderr, so any
    # argparse output (--help, a usage error) would otherwise crash on None.
    if frozen:
        log_path = os.path.join(get_base_dir(), "run.log")
        log_file = open(log_path, "w", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file

    args = parse_args()
    base_dir = os.path.abspath(args.base_dir) if args.base_dir else get_base_dir()

    try:
        config = load_config(base_dir)
    except (FileNotFoundError, ValueError) as e:
        log(str(e))
        if frozen:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(e), "LoL Auto-Uploader — Setup Error", 0x10)
        return

    db_path = os.path.join(base_dir, "uploads.db")
    db = Database(db_path)
    clients = [
        (account, RiotAPI(api_key=config["riot_api_key"], puuid=account["puuid"]))
        for account in config["accounts"]
    ]

    stop_event = threading.Event()

    if args.dry_run or args.once or args.match_id:
        log(f"Single pass over {len(clients)} account(s)"
            f"{' (dry run)' if args.dry_run else ''}.")
        found_new, success = process_new_matches(
            clients, db, config, base_dir,
            dry_run=args.dry_run,
            only_match_ids=args.match_id or None,
        )
        if not found_new:
            log("Nothing to do.")
        return

    if frozen:
        # Polling runs in background; tray icon owns the main thread
        poll_thread = threading.Thread(
            target=poll_loop,
            args=(clients, db, config, base_dir, stop_event),
            daemon=True,
        )
        poll_thread.start()
        run_tray(sys.executable, stop_event)
    else:
        # Dev mode: run polling on main thread, no tray
        try:
            poll_loop(clients, db, config, base_dir, stop_event)
        except KeyboardInterrupt:
            log("Shutting down.")


if __name__ == "__main__":
    main()
