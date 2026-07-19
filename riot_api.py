import requests
from datetime import datetime, timezone


class RiotAPIError(Exception):
    pass


class RiotAPI:
    BASE = "https://americas.api.riotgames.com"

    def __init__(self, api_key: str, puuid: str):
        self.api_key = api_key
        self.puuid = puuid

    def _get(self, url: str) -> dict:
        resp = requests.get(url, headers={"X-Riot-Token": self.api_key}, timeout=15)
        if resp.status_code == 401:
            raise RiotAPIError("API key is invalid or expired. Update riot_api_key in config.json.")
        if resp.status_code == 429:
            raise RiotAPIError("Rate limited by Riot API. Wait and retry.")
        resp.raise_for_status()
        return resp.json()

    def get_ranked_match_ids(self, count: int = 20) -> list[str]:
        url = f"{self.BASE}/lol/match/v5/matches/by-puuid/{self.puuid}/ids?queue=420&count={count}"
        return self._get(url)

    def get_match(self, match_id: str) -> dict:
        url = f"{self.BASE}/lol/match/v5/matches/{match_id}"
        return self._get(url)

    def parse_match(self, match: dict) -> dict:
        info = match["info"]
        match_id = match["metadata"]["matchId"]

        player = next(p for p in info["participants"] if p["puuid"] == self.puuid)
        player_team_id = player["teamId"]

        enemy_jungler = next(
            (p for p in info["participants"]
             if p["teamId"] != player_team_id and p["teamPosition"] == "JUNGLE"),
            None
        )

        game_start_utc = datetime.fromtimestamp(info["gameStartTimestamp"] / 1000, tz=timezone.utc)
        game_start_local = game_start_utc.astimezone().replace(tzinfo=None)
        game_duration_s = info["gameDuration"]

        return {
            "match_id": match_id,
            "game_start_local": game_start_local,
            "game_duration_s": game_duration_s,
            "win": player["win"],
            "kills": player["kills"],
            "deaths": player["deaths"],
            "assists": player["assists"],
            "cs": player["totalMinionsKilled"] + player["neutralMinionsKilled"],
            "enemy_jungler": enemy_jungler["championName"] if enemy_jungler else "Unknown",
            "my_champion": player["championName"],
        }
