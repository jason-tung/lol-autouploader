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
import time
from datetime import datetime

from database import Database
from riot_api import RiotAPI, RiotAPIError
from video_finder import find_matching_video
from youtube_api import upload_video


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
    return f"{outcome} {kda} vs {game_info['enemy_jungler']}"


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def process_new_matches(riot: RiotAPI, db: Database, config: dict, base_dir: str):
    log("Checking for new ranked games...")
    try:
        match_ids = riot.get_ranked_match_ids(count=20)
    except RiotAPIError as e:
        log(f"Riot API error: {e}")
        return

    new_ids = [mid for mid in match_ids if not db.is_uploaded(mid)]
    if not new_ids:
        log("No new games to upload.")
        return

    log(f"Found {len(new_ids)} new game(s).")

    # Track videos assigned this session so two matches in one poll don't share a video
    used_video_paths: set[str] = set()

    # Process oldest first so uploads are in chronological order
    for match_id in reversed(new_ids):
        log(f"Processing {match_id}...")
        try:
            match = riot.get_match(match_id)
            game_info = riot.parse_match(match)
        except RiotAPIError as e:
            log(f"  Error fetching match: {e}")
            continue
        except Exception as e:
            log(f"  Unexpected error parsing match: {e}")
            continue

        log(f"  {game_info['my_champion']} | {'Win' if game_info['win'] else 'Loss'} | "
            f"{game_info['kills']}/{game_info['deaths']}/{game_info['assists']} | "
            f"vs {game_info['enemy_jungler']} | "
            f"Started: {game_info['game_start_local'].strftime('%m/%d %H:%M')}")

        video_path = find_matching_video(
            config["videos_dir"],
            game_info,
            tolerance_minutes=config.get("video_match_tolerance_minutes", 90),
            excluded_paths=used_video_paths,
        )

        if not video_path:
            log(f"  No matching video found. Skipping.")
            continue

        log(f"  Matched video: {os.path.basename(video_path)}")
        title = build_title(game_info)
        log(f"  YouTube title: {title}")

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
            return  # No point continuing without YouTube credentials
        except Exception as e:
            log(f"  Upload failed: {e}")
            continue

        db.record_upload(game_info, video_path, video_id, title)
        used_video_paths.add(video_path)
        log(f"  Uploaded! https://youtube.com/watch?v={video_id}")


def main():
    base_dir = get_base_dir()
    config = load_config(base_dir)

    db_path = os.path.join(base_dir, "uploads.db")
    db = Database(db_path)
    riot = RiotAPI(api_key=config["riot_api_key"], puuid=config["puuid"])

    log("Auto-uploader started.")
    log(f"  Videos dir:    {config['videos_dir']}")
    log(f"  Poll interval: {config['poll_interval_seconds']}s")
    log(f"  DB:            {db_path}")

    while True:
        try:
            process_new_matches(riot, db, config, base_dir)
        except KeyboardInterrupt:
            log("Shutting down.")
            break
        except Exception as e:
            log(f"Unexpected error: {e}")

        interval = config.get("poll_interval_seconds", 300)
        log(f"Sleeping {interval}s until next check...")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log("Shutting down.")
            break


if __name__ == "__main__":
    main()
