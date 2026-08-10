# LoL Auto-Uploader

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/jasbob)

Watches your League of Legends match history and automatically uploads your ranked game recordings to YouTube.

After each game it finds the matching `.mp4` in your recordings folder, uploads it as unlisted, adds it to a playlist, and titles it like `06/02 Win 7/7/11 Kha'Zix vs Rengar`.

Track as many accounts as you like — each one gets its own YouTube playlist and privacy setting.

---

## How it works

Every few minutes the program polls the Riot API for new ranked solo/duo games on **each account** you've configured. For each new game it finds the recording whose filename timestamp falls within the game's time window, uploads it to that account's playlist, and writes the match to a local database so it's never processed again.

All accounts share one recordings folder. Since you can only play one account at a time, a recording claimed by one account's game is never reused for another's. If two of your own accounts were in the same game (duo), it's uploaded once — the first account to claim it wins.

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

Copy the `puuid` value from the response. Repeat once per account you want to track.

### 3. Set up YouTube OAuth

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project, then go to **APIs & Services > Enable APIs** and enable **YouTube Data API v3**
3. Go to **APIs & Services > Credentials > Create Credentials > OAuth client ID**
4. Application type: **Desktop app**
5. Download the JSON and save it as `client_secrets.json` next to `autouploader.exe`

The first time you run the program a browser window will open asking you to authorize it. After that a `token.pickle` file is saved and you won't be asked again.

### 4. Create a YouTube playlist

Create a playlist on YouTube and copy its ID from the URL — the part after `list=`:
```
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

Make one playlist per account if you want each account's games kept separate.

### 5. Configure

Copy `config.example.json` to `config.json` (in the same folder as the exe) and fill it in:

```json
{
  "riot_api_key": "RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "videos_dir": "C:\\Users\\YourName\\Videos\\Ascent",
  "poll_interval_seconds": 15,
  "video_match_tolerance_minutes": 8,
  "accounts": [
    {
      "description": "main account",
      "puuid": "your-puuid-here",
      "youtube_playlist_id": "PLxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "youtube_privacy": "unlisted"
    },
    {
      "description": "smurf",
      "puuid": "your-second-puuid-here",
      "youtube_playlist_id": "PLyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
      "youtube_privacy": "private"
    }
  ]
}
```

**Top-level fields:**

| Field | Description |
|---|---|
| `riot_api_key` | Your Riot dev/production API key (shared by all accounts) |
| `videos_dir` | Folder where your `.mp4` recordings are saved |
| `poll_interval_seconds` | How often to check for new games (default 15s) |
| `video_match_tolerance_minutes` | How early a recording can start before a game and still match (default 8 min). The window always closes 5 minutes after game start, so recordings that start mid-game are not considered. |
| `accounts` | One entry per League account to watch (see below) |

**Per-account fields:**

| Field | Description |
|---|---|
| `description` | A label for your own reference — PUUIDs aren't readable, so use this to note which account is which. Not used by the program; leave it `""` if you don't want one. |
| `puuid` | That account's PUUID (see step 2) |
| `youtube_playlist_id` | Playlist that this account's uploads are added to. Omit or leave empty to upload without adding to any playlist. |
| `youtube_privacy` | `unlisted`, `private`, or `public` (default `unlisted`) |

List as many accounts as you want. Each is polled independently — if one account's request fails, the others still run.

> **Upgrading from a single-account config?** Old configs with a top-level `puuid`, `youtube_playlist_id`, and `youtube_privacy` still work; they're read as a one-account list. Move them into an `accounts` array when you want to add a second account.

---

## Recording filename format

Your recorder must name files as `MM-DD-YYYY-HH-MM.mp4` in local time. For example: `06-02-2026-23-10.mp4`.

This is the default format used by [Outplayed / Overwolf](https://go.overwolf.com/outplayed) with the app name set to `Ascent` (or whichever folder name you configured).

---

## Running

**Using the exe (recommended):**

1. Download `lol-autouploader.zip` from the [latest release](https://github.com/jason-tung/lol-autouploader/releases/latest)
2. Extract the zip to a folder of your choice
3. Copy `config.example.json` to `config.json` and fill in your values (see [Configure](#5-configure) above)
4. Place `client_secrets.json` (from YouTube OAuth setup) in the same folder
5. Double-click `autouploader.exe` — it will appear in the system tray with no console window

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

## Command-line options

Running from source (`python main.py`) accepts a few flags, all useful for checking your setup before letting it upload anything:

| Flag | What it does |
|---|---|
| `--dry-run` | Poll every account and print exactly what *would* be uploaded, to which playlist, at which privacy. Uploads nothing and writes nothing to the database. |
| `--once` | Do a single poll pass instead of looping forever. |
| `--match-id ID` | Process only this match ID, even if it's older than the recent-games window. Repeatable. Implies `--once`. The match is attributed to whichever of your configured accounts played in it. |
| `--base-dir DIR` | Read `config.json` / `uploads.db` / `token.pickle` from `DIR` instead of the source folder. Use this to run against your installed copy. |

Check what a new config would do before committing to it:

```bash
python main.py --dry-run
```

Retroactively upload one specific game against your installed copy:

```bash
python main.py --match-id NA1_1234567890 --base-dir "C:\Users\You\Desktop\lol-autouploader"
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

**Startup error popup / empty log** — `config.json` is missing or still has placeholder values. Copy `config.example.json` to `config.json` and fill in your real API key, PUUID, and videos folder path. The error message names the offending account by its `description`, so give each account a description you'll recognize.

**A new account uploaded its whole back catalogue** — When you add an account, its last 20 ranked games are all unseen, so any that still have a matching recording will upload. Run `python main.py --dry-run` first to see exactly what a newly added account would do. Games with no recording are recorded as skipped and never revisited.

**Games went to the wrong playlist** — Check that each `accounts` entry pairs the right `puuid` with the right `youtube_playlist_id`; the `description` field is only a label and has no effect on routing.

**401 errors from Riot API** — Your dev key expired. Get a new one at [developer.riotgames.com](https://developer.riotgames.com) and update `config.json`. Dev keys expire every 24 hours; apply for a persistent personal key to avoid this.

**No matching video found** — The recording timestamp didn't fall within the match window. Check that your recorder is naming files in `MM-DD-YYYY-HH-MM.mp4` format and that `videos_dir` points to the right folder. You can also increase `video_match_tolerance_minutes`.

**YouTube auth popup on every run** — Delete `token.pickle` and re-authorize once cleanly.

**Game uploaded without a video / wrong video** — Each match ID is recorded in the database after upload and will never be retried. If the wrong video was uploaded, you'll need to manually delete the video from YouTube and remove that row from `uploads.db` using a SQLite browser like [DB Browser for SQLite](https://sqlitebrowser.org).
