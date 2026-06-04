import os
from datetime import datetime, timedelta
from pathlib import Path


def _parse_video_datetime(filename: str) -> datetime | None:
    stem = Path(filename).stem
    try:
        return datetime.strptime(stem, "%m-%d-%Y-%H-%M")
    except ValueError:
        return None


def find_matching_video(videos_dir: str, game_info: dict, tolerance_minutes: int = 90,
                        excluded_paths: set[str] | None = None) -> str | None:
    """
    Find the video whose recording start time best matches the game.

    The recording filename encodes its start time. A match is valid if the
    recording started within [game_start - tolerance, game_start + 5min].
    Returns the best matching video path, or None if none found.
    """
    game_start: datetime = game_info["game_start_local"]

    # Recordings start in lobby/champ-select, so always near game_start — not mid-game.
    # Using game_end as the window anchor would let a short game's window bleed into
    # the next game's recording start time and steal the wrong video.
    window_open = game_start - timedelta(minutes=tolerance_minutes)
    window_close = game_start + timedelta(minutes=5)

    excluded_normalized = {os.path.normcase(p) for p in (excluded_paths or set())}

    candidates = []
    for fname in os.listdir(videos_dir):
        if not fname.lower().endswith(".mp4"):
            continue
        rec_start = _parse_video_datetime(fname)
        if rec_start is None:
            continue
        full_path = os.path.join(videos_dir, fname)
        if os.path.normcase(full_path) in excluded_normalized:
            continue
        if window_open <= rec_start <= window_close:
            candidates.append((rec_start, fname))

    if not candidates:
        return None

    # Pick closest to game_start
    candidates.sort(key=lambda x: abs((x[0] - game_start).total_seconds()))
    best_fname = candidates[0][1]
    return os.path.join(videos_dir, best_fname)


def get_newest_video(videos_dir: str) -> str | None:
    mp4s = [
        f for f in os.listdir(videos_dir)
        if f.lower().endswith(".mp4") and _parse_video_datetime(f) is not None
    ]
    if not mp4s:
        return None
    mp4s.sort(key=lambda f: _parse_video_datetime(f), reverse=True)
    return os.path.join(videos_dir, mp4s[0])
