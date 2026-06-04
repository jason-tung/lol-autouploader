# LoL Auto-Uploader

Watches your League of Legends match history and automatically uploads your ranked game recordings to YouTube.

After each game it finds the matching `.mp4` in your recordings folder, uploads it as unlisted, adds it to a playlist, and titles it like `06/02 Win 7/7/11 Kha'Zix vs Rengar`.

---

## How it works

Every few minutes the program polls the Riot API for new ranked solo/duo games. For each new game it finds the recording whose filename timestamp falls within the game's time window, uploads it to YouTube, and writes the match to a local database so it's never processed again.

The program runs silently in the system tray — right-click the tray icon to open the log, toggle start on login, or exit.

---

## Requirements

- Windows (the exe is Windows-only; Python path also works on Mac/Linux)
- Python 3.12+ (only needed if running from source)
- A Riot Games developer API key
- A Google Cloud project with the YouTube Data API v3 enabled

---

## Setup

### 1. Get a Riot API key

1. Go to [developer.riotgames.com](https://developer.riotgames.com) and sign in
2. Copy your development API key (top of the dashboard)
3. For long-term use, register a personal app to get a persistent key — dev keys expire every 24 hours

### 2. Find your PUUID

Run this in a browser or curl, substituting your key and summoner info:

```
https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/YourName/TAG?api_key=RGAPI-...
```

Copy the `puuid` value from the response.

### 3. Set up YouTube OAuth

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project, then go to **APIs & Services > Enable APIs** and enable **YouTube Data API v3**
3. Go to **APIs & Services > Credentials > Create Credentials > OAuth client ID**
4. Application type: **Desktop app**
5. Download the JSON and save it as `client_secrets.json` next to `autouploader.exe`

The first time you run the program a browser window will open asking you to authorize it. After that a `token.pickle` file is saved and you won't be asked again.

### 4. Create a YouTube playlist

Create a playlist on YouTube and copy its ID from the URL:
```
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

### 5. Configure

Copy `config.example.json` to `config.json` (in the same folder as the exe) and fill it in:

```json
{
  "riot_api_key": "RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "puuid": "your-puuid-here",
  "videos_dir": "C:\\Users\\YourName\\Videos\\Ascent",
  "poll_interval_seconds": 300,
  "video_match_tolerance_minutes": 90,
  "youtube_privacy": "unlisted",
  "youtube_playlist_id": "PLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

| Field | Description |
|---|---|
| `riot_api_key` | Your Riot dev/production API key |
| `puuid` | Your account PUUID (see step 2) |
| `videos_dir` | Folder where your `.mp4` recordings are saved |
| `poll_interval_seconds` | How often to check for new games (default 300 = 5 min) |
| `video_match_tolerance_minutes` | How early a recording can start before a game and still match (default 90). The window always closes 5 minutes after game start, so recordings that start mid-game are not considered. |
| `youtube_privacy` | `unlisted`, `private`, or `public` |
| `youtube_playlist_id` | The playlist to add uploads to |

---

## Recording filename format

Your recorder must name files as `MM-DD-YYYY-HH-MM.mp4` in local time. For example: `06-02-2026-23-10.mp4`.

This is the default format used by [Outplayed / Overwolf](https://go.overwolf.com/outplayed) with the app name set to `Ascent` (or whichever folder name you configured).

---

## Running

**Using the exe (recommended):**

Place `autouploader.exe`, `config.json`, and `client_secrets.json` in the same folder. Double-click to run — it will appear in the system tray with no console window.

Right-click the tray icon to:
- **Open Log** — view `run.log` (cleared on each launch)
- **Start on Login** — toggle automatic startup with Windows
- **Exit** — stop the uploader

**From source:**

```bash
pip install -r requirements.txt
make run
# or: python -u main.py
```

---

## Building the exe from source

```bash
make build        # builds dist\autouploader.exe
make release      # builds exe + packages lol-autouploader.zip for distribution
```

---

## Files created at runtime

| File | Purpose |
|---|---|
| `token.pickle` | Saved YouTube OAuth token — delete to re-authorize |
| `uploads.db` | SQLite database of every uploaded match — do not delete or games will re-upload |
| `run.log` | Log of the current session — cleared on each launch, open via tray menu |

---

## Troubleshooting

**401 errors from Riot API** — Your dev key expired. Get a new one at [developer.riotgames.com](https://developer.riotgames.com) and update `config.json`. Dev keys expire every 24 hours; apply for a persistent personal key to avoid this.

**No matching video found** — The recording timestamp didn't fall within the match window. Check that your recorder is naming files in `MM-DD-YYYY-HH-MM.mp4` format and that `videos_dir` points to the right folder. You can also increase `video_match_tolerance_minutes`.

**YouTube auth popup on every run** — Delete `token.pickle` and re-authorize once cleanly.

**Game uploaded without a video / wrong video** — Each match ID is recorded in the database after upload and will never be retried. If the wrong video was uploaded, you'll need to manually delete the video from YouTube and remove that row from `uploads.db` using a SQLite browser like [DB Browser for SQLite](https://sqlitebrowser.org).
