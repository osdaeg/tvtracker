from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
import os
import asyncio
import logging

from database import init_db, get_db
from tmdb import search_shows, get_show_details, get_episode, get_next_episode
import httpx
from datetime import date, timedelta

TRAKT_CLIENT_ID  = os.getenv("TRAKT_CLIENT_ID", "")
TRAKT_BASE       = "https://api.trakt.tv"
CALENDAR_DAYS    = int(os.getenv("CALENDAR_DAYS", "30"))
CACHE_TTL_HOURS  = 6
SONARR_URL       = os.getenv("SONARR_URL", "").rstrip("/")
SONARR_API_KEY   = os.getenv("SONARR_API_KEY", "")
TMDB_IMG_ORIG    = "https://image.tmdb.org/t/p/w500"

logger = logging.getLogger("tvtracker")

REFRESH_INTERVAL_HOURS = float(os.getenv("REFRESH_INTERVAL_HOURS", "24"))


async def refresh_all_shows():
    """Reconsulta TMDB para todas las series y actualiza total_seasons, status y next_air_date."""
    logger.info("Refresh automático iniciado")
    conn = get_db()
    rows = conn.execute("SELECT * FROM shows").fetchall()
    conn.close()

    for row in rows:
        show = dict(row)
        try:
            details = await get_show_details(show["tmdb_id"])
            ep = await get_episode(show["tmdb_id"], show["current_season"], show["current_episode"])

            conn = get_db()
            conn.execute("""
                UPDATE shows SET
                    total_seasons    = ?,
                    status           = ?,
                    poster_path      = ?,
                    network          = ?,
                    network_logo     = ?,
                    next_ep_info     = ?
                WHERE id = ?
            """, (
                details["total_seasons"],
                details["status"],
                details["poster_path"],
                details.get("network"),
                details.get("network_logo"),
                details.get("next_ep_info"),
                show["id"],
            ))
            # Desmarcar finished si la serie sigue en emisión o creció en temporadas
            if show["finished"] and (
                details["status"] in ("Returning Series", "In Production", "Planned") or
                details["total_seasons"] > show["total_seasons"]
            ):
                conn.execute("UPDATE shows SET finished = 0, next_air_date = NULL WHERE id = ?", (show["id"],))
            conn.commit()
            conn.close()
            logger.info(f"Refresh OK: {show['name']}")
        except Exception as e:
            logger.warning(f"Refresh error {show['name']}: {e}")

    logger.info("Refresh automático completado")


async def refresh_scheduler():
    while True:
        await asyncio.sleep(REFRESH_INTERVAL_HOURS * 3600)
        await refresh_all_shows()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(refresh_scheduler())
    yield


app = FastAPI(title="TVTracker", lifespan=lifespan)


# ── Schemas ──────────────────────────────────────────────────────────────────

class AddShowRequest(BaseModel):
    tmdb_id: int


class ShowRow(BaseModel):
    id: int
    tmdb_id: int
    name: str
    poster_path: str | None
    synopsis: str | None
    total_seasons: int
    status: str | None
    current_season: int
    current_episode: int
    current_ep_title: str | None
    next_air_date: str | None
    finished: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def row_to_dict(row) -> dict:
    d = dict(row)
    d["finished"] = bool(d["finished"])
    return d


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/search")
async def search(q: str):
    if not q or len(q) < 2:
        raise HTTPException(400, "Query too short")
    results = await search_shows(q)
    return results


@app.get("/api/shows")
def list_shows():
    conn = get_db()
    rows = conn.execute("SELECT * FROM shows ORDER BY added_at DESC").fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.post("/api/shows")
async def add_show(req: AddShowRequest):
    # Check duplicate
    conn = get_db()
    existing = conn.execute("SELECT id FROM shows WHERE tmdb_id = ?", (req.tmdb_id,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(409, "Show already added")

    details = await get_show_details(req.tmdb_id)
    ep = await get_episode(req.tmdb_id, 1, 1)

    conn.execute("""
        INSERT INTO shows
            (tmdb_id, name, poster_path, synopsis, total_seasons, status,
             current_season, current_episode, current_ep_title, next_air_date,
             network, network_logo, next_ep_info)
        VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?, ?)
    """, (
        details["tmdb_id"],
        details["name"],
        details["poster_path"],
        details["synopsis"],
        details["total_seasons"],
        details["status"],
        ep["title"] if ep else "",
        ep["air_date"] if ep else None,
        details.get("network"),
        details.get("network_logo"),
        details.get("next_ep_info"),
    ))
    conn.commit()

    row = conn.execute("SELECT * FROM shows WHERE tmdb_id = ?", (req.tmdb_id,)).fetchone()
    conn.close()
    return row_to_dict(row)


@app.post("/api/shows/{show_id}/seen")
async def mark_seen(show_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM shows WHERE id = ?", (show_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Show not found")

    show = row_to_dict(row)
    next_ep = await get_next_episode(
        show["tmdb_id"],
        show["current_season"],
        show["current_episode"],
        show["total_seasons"],
    )

    if next_ep is None:
        returning = show.get("status") in ("Returning Series", "In Production", "Planned")
        if returning:
            next_season = show["current_season"] + 1
            conn.execute("""
                UPDATE shows SET
                    current_season   = ?,
                    current_episode  = 1,
                    current_ep_title = '',
                    next_air_date    = NULL,
                    finished         = 0
                WHERE id = ?
            """, (next_season, show_id))
        else:
            conn.execute("UPDATE shows SET finished = 1 WHERE id = ?", (show_id,))
    else:
        conn.execute("""
            UPDATE shows SET
                current_season  = ?,
                current_episode = ?,
                current_ep_title = ?,
                next_air_date   = ?,
                finished        = 0
            WHERE id = ?
        """, (
            next_ep["season"],
            next_ep["episode"],
            next_ep.get("title", ""),
            next_ep.get("air_date"),
            show_id,
        ))

    conn.commit()
    row = conn.execute("SELECT * FROM shows WHERE id = ?", (show_id,)).fetchone()
    conn.close()
    return row_to_dict(row)


@app.post("/api/shows/{show_id}/season-done")
async def season_done(show_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM shows WHERE id = ?", (show_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Show not found")

    show = row_to_dict(row)
    next_season = show["current_season"] + 1
    returning = show.get("status") in ("Returning Series", "In Production", "Planned")

    if next_season > show["total_seasons"]:
        if returning:
            # Avanzar a la temporada siguiente desconocida, limpiar fecha
            conn.execute("""
                UPDATE shows SET
                    current_season   = ?,
                    current_episode  = 1,
                    current_ep_title = '',
                    next_air_date    = NULL,
                    finished         = 0
                WHERE id = ?
            """, (next_season, show_id))
        else:
            conn.execute("UPDATE shows SET finished = 1 WHERE id = ?", (show_id,))
        conn.commit()
        row = conn.execute("SELECT * FROM shows WHERE id = ?", (show_id,)).fetchone()
        conn.close()
        return row_to_dict(row)

    ep = await get_episode(show["tmdb_id"], next_season, 1)

    conn.execute("""
        UPDATE shows SET
            current_season   = ?,
            current_episode  = 1,
            current_ep_title = ?,
            next_air_date    = ?,
            finished         = 0
        WHERE id = ?
    """, (
        next_season,
        ep["title"] if ep else "",
        ep["air_date"] if ep else None,
        show_id,
    ))
    conn.commit()
    row = conn.execute("SELECT * FROM shows WHERE id = ?", (show_id,)).fetchone()
    conn.close()
    return row_to_dict(row)


@app.post("/api/refresh")
async def trigger_refresh():
    asyncio.create_task(refresh_all_shows())
    return {"ok": True, "message": "Refresh iniciado"}


@app.get("/api/discover")
async def discover():
    if not TRAKT_CLIENT_ID:
        raise HTTPException(500, "TRAKT_CLIENT_ID not configured")

    import json
    from datetime import datetime as dt

    conn = get_db()

    # Check cache
    cached = conn.execute("SELECT data, fetched_at FROM calendar_cache WHERE id = 1").fetchone()
    if cached:
        fetched = dt.fromisoformat(cached["fetched_at"])
        age_hours = (dt.utcnow() - fetched).total_seconds() / 3600
        if age_hours < CACHE_TTL_HOURS:
            conn.close()
            return json.loads(cached["data"])

    # Fetch from Trakt
    start = date.today().strftime("%Y-%m-%d")
    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": TRAKT_CLIENT_ID,
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{TRAKT_BASE}/calendars/all/shows/{start}/{CALENDAR_DAYS}",
                headers=headers,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        # Return cached data even if stale on error
        if cached:
            conn.close()
            logger.warning(f"Trakt error, returning stale cache: {e}")
            return json.loads(cached["data"])
        conn.close()
        raise HTTPException(503, f"Trakt unavailable: {e}")

    # Parse flat array, filter only S01E01 (new series premieres)
    results = []
    for entry in data:
        ep   = entry.get("episode", {})
        show = entry.get("show", {})
        # Only season 1 episode 1 — new series premieres
        if ep.get("season") != 1 or ep.get("number") != 1:
            continue
        air_date = (entry.get("first_aired") or "")[:10]
        ids = show.get("ids", {})
        results.append({
            "date":      air_date,
            "show_name": show.get("title", ""),
            "network":   show.get("network", ""),
            "season":    ep.get("season", 1),
            "episode":   ep.get("number", 1),
            "ep_title":  ep.get("title", ""),
            "tmdb_id":   ids.get("tmdb"),
            "year":      show.get("year"),
        })

    # Sort by date
    results.sort(key=lambda x: x["date"])

    # Save to cache
    conn.execute(
        "INSERT OR REPLACE INTO calendar_cache (id, data, fetched_at) VALUES (1, ?, ?)",
        (json.dumps(results), dt.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return results


@app.get("/api/show-info/{tmdb_id}")
async def show_info(tmdb_id: int):
    import json
    from datetime import datetime as dt

    conn = get_db()
    cached = conn.execute(
        "SELECT data, fetched_at FROM show_info_cache WHERE tmdb_id = ?", (tmdb_id,)
    ).fetchone()
    if cached:
        fetched = dt.fromisoformat(cached["fetched_at"])
        age_hours = (dt.utcnow() - fetched).total_seconds() / 3600
        if age_hours < 24 * 7:  # cache de 7 días para info de series
            conn.close()
            return json.loads(cached["data"])

    headers = {}
    params = {"language": "es-ES", "append_to_response": "credits"}
    api_key = os.getenv("TMDB_API_KEY", "")
    if len(api_key) > 50:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.themoviedb.org/3/tv/{tmdb_id}",
            headers=headers, params=params, timeout=10
        )
        r.raise_for_status()
        d = r.json()

    networks = d.get("networks", [])
    genres   = [g["name"] for g in d.get("genres", [])]
    countries = d.get("origin_country", [])
    cast = []
    if "credits" in d:
        cast = [
            {"name": c["name"], "character": c.get("character", "")}
            for c in d["credits"].get("cast", [])[:8]
        ]
    creators = [p["name"] for p in d.get("created_by", [])]

    result = {
        "tmdb_id":       d["id"],
        "name":          d.get("name", ""),
        "tagline":       d.get("tagline", ""),
        "overview":      d.get("overview", ""),
        "poster_path":   (TMDB_IMG_ORIG + d["poster_path"]) if d.get("poster_path") else None,
        "backdrop_path": (TMDB_IMG_ORIG + d["backdrop_path"]) if d.get("backdrop_path") else None,
        "first_air_date": d.get("first_air_date", ""),
        "status":        d.get("status", ""),
        "networks":      [n.get("name") for n in networks],
        "genres":        genres,
        "origin_country": countries,
        "created_by":    creators,
        "total_seasons": d.get("number_of_seasons", 0),
        "total_episodes": d.get("number_of_episodes", 0),
        "episode_run_time": d.get("episode_run_time", []),
        "vote_average":  round(d.get("vote_average", 0), 1),
        "cast":          cast,
    }

    conn.execute(
        "INSERT OR REPLACE INTO show_info_cache (tmdb_id, data, fetched_at) VALUES (?, ?, ?)",
        (tmdb_id, json.dumps(result), dt.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return result


class SonarrAddRequest(BaseModel):
    tmdb_id: int
    show_name: str


@app.post("/api/sonarr-add")
async def sonarr_add(req: SonarrAddRequest):
    if not SONARR_URL or not SONARR_API_KEY:
        raise HTTPException(503, "Sonarr not configured")

    # Get tvdb_id from TMDB external ids
    api_key = os.getenv("TMDB_API_KEY", "")
    headers = {}
    params = {}
    if len(api_key) > 50:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.themoviedb.org/3/tv/{req.tmdb_id}/external_ids",
            headers=headers, params=params, timeout=10
        )
        r.raise_for_status()
        ext = r.json()

    tvdb_id = ext.get("tvdb_id")
    if not tvdb_id:
        raise HTTPException(422, "No TVDB ID found for this series")

    # Get root folders from Sonarr
    sonarr_headers = {"X-Api-Key": SONARR_API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        rf = await client.get(f"{SONARR_URL}/api/v3/rootfolder", headers=sonarr_headers, timeout=10)
        rf.raise_for_status()
        root_folders = rf.json()

    if not root_folders:
        raise HTTPException(500, "No root folders in Sonarr")

    root_path = root_folders[0]["path"]

    # Get quality profiles
    async with httpx.AsyncClient() as client:
        qp = await client.get(f"{SONARR_URL}/api/v3/qualityprofile", headers=sonarr_headers, timeout=10)
        qp.raise_for_status()
        profiles = qp.json()

    quality_profile_id = profiles[0]["id"] if profiles else 1

    # Add to Sonarr
    payload = {
        "title": req.show_name,
        "tvdbId": tvdb_id,
        "qualityProfileId": quality_profile_id,
        "rootFolderPath": root_path,
        "monitored": True,
        "addOptions": {
            "searchForMissingEpisodes": False,
            "monitor": "future"
        }
    }
    async with httpx.AsyncClient() as client:
        sr = await client.post(
            f"{SONARR_URL}/api/v3/series",
            headers=sonarr_headers,
            json=payload,
            timeout=15
        )
        if sr.status_code == 400:
            body = sr.json()
            msg = body[0].get("errorMessage", "Already exists") if isinstance(body, list) else "Error"
            raise HTTPException(409, msg)
        sr.raise_for_status()

    return {"ok": True, "tvdb_id": tvdb_id}


@app.get("/api/sonarr-status")
async def sonarr_status():
    """Verifica si Sonarr está configurado y accesible."""
    if not SONARR_URL or not SONARR_API_KEY:
        return {"configured": False}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{SONARR_URL}/api/v3/system/status",
                headers={"X-Api-Key": SONARR_API_KEY},
                timeout=5
            )
            r.raise_for_status()
        return {"configured": True}
    except Exception:
        return {"configured": False, "error": "unreachable"}


@app.delete("/api/shows/{show_id}")
def delete_show(show_id: int):
    conn = get_db()
    conn.execute("DELETE FROM shows WHERE id = ?", (show_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ── Static frontend ───────────────────────────────────────────────────────────

FRONTEND_DIR = "/app/frontend"

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
