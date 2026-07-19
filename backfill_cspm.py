"""
One-shot: backfill "x.x cs/m" into the titles of already-uploaded YouTube videos.

For each row in uploads.db it:
  1. fetches the match from the Riot API to compute CS/min,
  2. reads the video's current YouTube title,
  3. inserts "x.x cs/m" right after the K/D/A token (e.g. "3/5/2"),
  4. updates the title on YouTube and in the local DB.

Titles that already contain "cs/m" are left untouched. Safe to re-run.
"""

import json
import os
import re
import sqlite3
import sys
import time

import requests

from youtube_api import _get_service

BASE = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 8
KDA_RE = re.compile(r"\d+/\d+/\d+")


def compute_cspm(key, puuid, match_id):
    r = requests.get(
        f"https://americas.api.riotgames.com/lol/match/v5/matches/{match_id}",
        headers={"X-Riot-Token": key},
        timeout=15,
    )
    r.raise_for_status()
    info = r.json()["info"]
    p = next(x for x in info["participants"] if x["puuid"] == puuid)
    cs = p["totalMinionsKilled"] + p["neutralMinionsKilled"]
    minutes = info["gameDuration"] / 60
    return cs / minutes if minutes else 0.0


def add_cspm(title, cspm):
    tag = f"{cspm:.1f} cs/m"
    if "cs/m" in title:
        return title  # already has it
    m = KDA_RE.search(title)
    if not m:
        return f"{title} {tag}"  # fallback: append
    return f"{title[:m.end()]} {tag}{title[m.end():]}"


def main():
    cfg = json.load(open(os.path.join(BASE, "config.json")))
    key, puuid = cfg["riot_api_key"], cfg["puuid"]

    conn = sqlite3.connect(os.path.join(BASE, "uploads.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT match_id, youtube_video_id, youtube_title FROM uploads ORDER BY upload_date DESC LIMIT ?",
        (LIMIT,),
    ).fetchall()

    print(f"Found {len(rows)} uploads to process.\n")
    yt = _get_service(BASE)

    for row in rows:
        vid = row["youtube_video_id"]
        # current title straight from YouTube (source of truth)
        resp = yt.videos().list(part="snippet", id=vid).execute()
        items = resp.get("items", [])
        if not items:
            print(f"[SKIP] {vid} ({row['match_id']}): video not found on YouTube.")
            continue
        snip = items[0]["snippet"]
        cur = snip["title"]

        cspm = compute_cspm(key, puuid, row["match_id"])
        new = add_cspm(cur, cspm)

        if new == cur:
            print(f"[SKIP] {vid}: already has cs/m -> {cur!r}")
            continue

        new_snippet = {
            "title": new,
            "categoryId": snip.get("categoryId", "20"),
            "description": snip.get("description", ""),
            "tags": snip.get("tags", []),
        }
        yt.videos().update(part="snippet", body={"id": vid, "snippet": new_snippet}).execute()
        conn.execute(
            "UPDATE uploads SET youtube_title = ? WHERE youtube_video_id = ?", (new, vid)
        )
        conn.commit()
        print(f"[OK]   {vid}: {cur!r}\n           -> {new!r}")
        time.sleep(0.3)  # be gentle on Riot rate limits

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
