import sqlite3
import os
from datetime import datetime


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT UNIQUE NOT NULL,
                    video_file TEXT NOT NULL,
                    youtube_video_id TEXT NOT NULL,
                    youtube_title TEXT NOT NULL,
                    upload_date TEXT NOT NULL,
                    win INTEGER NOT NULL,
                    kills INTEGER NOT NULL,
                    deaths INTEGER NOT NULL,
                    assists INTEGER NOT NULL,
                    my_champion TEXT NOT NULL,
                    enemy_jungler TEXT NOT NULL,
                    game_start TEXT NOT NULL,
                    game_duration_s INTEGER NOT NULL
                )
            """)

    def is_uploaded(self, match_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM uploads WHERE match_id = ?", (match_id,)
            ).fetchone()
            return row is not None

    def record_upload(self, game_info: dict, video_file: str, youtube_video_id: str, title: str):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO uploads
                    (match_id, video_file, youtube_video_id, youtube_title, upload_date,
                     win, kills, deaths, assists, my_champion, enemy_jungler, game_start, game_duration_s)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                game_info["match_id"],
                video_file,
                youtube_video_id,
                title,
                datetime.now().isoformat(),
                int(game_info["win"]),
                game_info["kills"],
                game_info["deaths"],
                game_info["assists"],
                game_info["my_champion"],
                game_info["enemy_jungler"],
                game_info["game_start_local"].isoformat(),
                game_info["game_duration_s"],
            ))

    def get_all_uploads(self) -> list[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM uploads ORDER BY upload_date DESC").fetchall()
            return [dict(r) for r in rows]
