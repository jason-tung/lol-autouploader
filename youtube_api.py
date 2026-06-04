import os
import pickle
import sys
import time
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Upload + playlist management both require this scope
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def _get_service(base_dir: str):
    secrets_path = os.path.join(base_dir, "client_secrets.json")
    token_path = os.path.join(base_dir, "token.pickle")

    if not os.path.exists(secrets_path):
        raise FileNotFoundError(
            f"Missing {secrets_path}\n\n"
            "Setup steps:\n"
            "  1. Go to https://console.cloud.google.com/\n"
            "  2. Create a project, enable 'YouTube Data API v3'\n"
            "  3. APIs & Services > Credentials > Create Credentials > OAuth client ID\n"
            "  4. Application type: Desktop app\n"
            "  5. Download JSON and save it as client_secrets.json next to this program\n"
        )

    creds = None
    if os.path.exists(token_path):
        with open(token_path, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


def _fmt_size(b: int) -> str:
    return f"{b / 1024 / 1024:.0f} MB"


def _fmt_eta(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    return f"{int(seconds // 60)}m {int(seconds % 60)}s"


def upload_video(video_path: str, title: str, privacy: str, base_dir: str,
                 playlist_id: str | None = None) -> str:
    youtube = _get_service(base_dir)

    total_bytes = os.path.getsize(video_path)
    body = {
        "snippet": {
            "title": title,
            "description": "",
            "tags": ["League of Legends", "LoL", "Jungle", "Ranked"],
            "categoryId": "20",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=10 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"  Uploading '{os.path.basename(video_path)}' ({_fmt_size(total_bytes)})...")
    start_time = time.time()
    response = None
    while response is None:
        chunk_start = time.time()
        status, response = request.next_chunk()
        if status:
            pct = status.progress()
            uploaded = int(pct * total_bytes)
            elapsed = time.time() - start_time
            speed = uploaded / elapsed if elapsed > 0 else 0
            remaining = (total_bytes - uploaded) / speed if speed > 0 else 0
            bar_filled = int(pct * 20)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            print(
                f"  [{bar}] {int(pct * 100)}%  "
                f"{_fmt_size(uploaded)}/{_fmt_size(total_bytes)}  "
                f"{_fmt_size(int(speed))}/s  ETA {_fmt_eta(remaining)}   ",
                end="\r",
                file=sys.stderr,
            )

    elapsed = time.time() - start_time
    avg_speed = total_bytes / elapsed if elapsed > 0 else 0
    print(" " * 80, end="\r", file=sys.stderr)  # clear progress line
    print(f"  Done in {_fmt_eta(elapsed)} (avg {_fmt_size(int(avg_speed))}/s)")

    video_id = response["id"]

    if playlist_id:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    }
                },
            ).execute()
            print(f"  Added to playlist.")
        except Exception as e:
            print(f"  Warning: playlist insert failed ({e}). Video uploaded but not added to playlist.")

    return video_id
