import os
import httpx

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG  = "https://image.tmdb.org/t/p/w300"
API_KEY   = os.getenv("TMDB_API_KEY", "")


def _headers():
    return {"Authorization": f"Bearer {API_KEY}"} if len(API_KEY) > 50 else {}


def _params(extra: dict = None):
    base = {"language": "es-ES"}
    if len(API_KEY) <= 50 and API_KEY:
        base["api_key"] = API_KEY
    if extra:
        base.update(extra)
    return base


async def search_shows(query: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{TMDB_BASE}/search/tv",
            headers=_headers(),
            params=_params({"query": query}),
            timeout=10,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        return [
            {
                "tmdb_id": s["id"],
                "name": s.get("name", ""),
                "year": (s.get("first_air_date") or "")[:4],
                "poster_url": (TMDB_IMG + s["poster_path"]) if s.get("poster_path") else None,
                "overview": s.get("overview", ""),
            }
            for s in results[:8]
        ]


async def get_show_details(tmdb_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{TMDB_BASE}/tv/{tmdb_id}",
            headers=_headers(),
            params=_params(),
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()
        networks = d.get("networks", [])
        network = networks[0].get("name") if networks else None
        network_logo = (TMDB_IMG.replace("w300", "w45") + networks[0]["logo_path"]) if networks and networks[0].get("logo_path") else None

        neta = d.get("next_episode_to_air")
        next_ep_info = None
        if neta:
            next_ep_info = f"S{str(neta.get('season_number',1)).zfill(2)}E{str(neta.get('episode_number',1)).zfill(2)} · {neta.get('air_date','')}"

        return {
            "tmdb_id": d["id"],
            "name": d.get("name", ""),
            "poster_path": (TMDB_IMG + d["poster_path"]) if d.get("poster_path") else None,
            "synopsis": d.get("overview", ""),
            "total_seasons": d.get("number_of_seasons", 1),
            "status": d.get("status", ""),
            "network": network,
            "network_logo": network_logo,
            "next_ep_info": next_ep_info,
        }


async def get_episode(tmdb_id: int, season: int, episode: int) -> dict | None:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{TMDB_BASE}/tv/{tmdb_id}/season/{season}/episode/{episode}",
            headers=_headers(),
            params=_params(),
            timeout=10,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        d = r.json()
        return {
            "season": season,
            "episode": episode,
            "title": d.get("name", ""),
            "air_date": d.get("air_date"),
        }


async def get_season_episode_count(tmdb_id: int, season: int) -> int:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{TMDB_BASE}/tv/{tmdb_id}/season/{season}",
            headers=_headers(),
            params=_params(),
            timeout=10,
        )
        r.raise_for_status()
        episodes = r.json().get("episodes", [])
        return len(episodes)


async def get_next_episode(tmdb_id: int, current_season: int, current_episode: int, total_seasons: int) -> dict | None:
    """Returns next episode info, or None if show is finished."""
    next_ep = current_episode + 1
    next_season = current_season

    ep_count = await get_season_episode_count(tmdb_id, current_season)

    if next_ep > ep_count:
        next_season += 1
        next_ep = 1
        if next_season > total_seasons:
            return None  # finished

    return await get_episode(tmdb_id, next_season, next_ep)
