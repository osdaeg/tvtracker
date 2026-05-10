# 📺 TVTracker

Personal TV series tracking dashboard with a 1960s CRT aesthetic.

Keep track of which episode you're on, mark episodes and seasons as watched, and get notified when new seasons are coming — all self-hosted, no accounts, no tracking.

![TVTracker screenshot](screenshot.png)

---

## Features

- **Episode tracking** — know exactly where you left off on each series
- **Smart ordering** — shows with recently aired episodes float to the top, sorted by air date
- **Waiting state** — when you're caught up on a returning series, it shows "WAITING FOR SEASON N" instead of cluttering your list
- **Season status** — badges for RENEWED, CANCELED, and ENDED series pulled from TMDB
- **Next episode info** — upcoming episode and air date shown directly on the card
- **Auto-refresh** — periodically syncs metadata from TMDB (configurable interval)
- **Manual refresh** — one-click refresh button in the UI
- **Retro CRT aesthetic** — scanlines, amber phosphor glow, sepia posters

---

## Stack

- **Backend**: FastAPI + SQLite (no ORM)
- **Frontend**: Single-file HTML/CSS/JS, served by FastAPI
- **External API**: [TMDB](https://www.themoviedb.org/) (free account required)
- **Container**: Docker

---

## Project Structure

```
tvtracker/
├── docker-compose.yml
├── .env
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── database.py
│   └── tmdb.py
└── frontend/
    └── index.html
```

---

## Setup

### 1. Get a TMDB API token

Create a free account at [themoviedb.org](https://www.themoviedb.org/), go to **Settings → API**, and copy your **API Read Access Token** (the long one starting with `eyJ...`).

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
TMDB_API_KEY=YourLongTMDBAccessTokenHere
DB_PATH=/data/tvtracker.db
REFRESH_INTERVAL_HOURS=24
```

### 3. Configure Docker Compose

```bash
cp docker-compose.example.yml docker-compose.yml
```

Edit `docker-compose.yml` and set your paths and network name:

```yaml
volumes:
  - /path/to/tvtracker/data:/data
  - /path/to/tvtracker/frontend:/app/frontend

networks:
  - YourNetworkName
```

### 4. Build and run

```bash
docker compose up -d --build
```

Access at `http://localhost:7950` (or your configured host/port).

---

## Usage

### Adding a series
Click **+ ADD SERIES**, type the name, and select from the search results. The series is added starting from S01E01.

### Marking episodes
- **✓ WATCHED** — marks the current episode as watched and advances to the next one. Only shown when the episode has already aired.
- **» SEASON DONE** — marks the entire current season as watched and jumps to the first episode of the next season.

### Series states
| State | Description |
|-------|-------------|
| Normal | Episode has aired, ready to watch |
| `AÚN NO EMITIDO` | Episode exists but hasn't aired yet |
| `⟳ ESPERANDO TEMPORADA N` | You're caught up, waiting for the next season |
| `✦ SERIE FINALIZADA` | Series has ended or been canceled |

### Refresh
Click **⟳ REFRESH** to sync metadata from TMDB for all series. This updates total seasons, status, network, and upcoming episode info — but never changes your current episode position.

Auto-refresh runs in the background at the interval set in `REFRESH_INTERVAL_HOURS`.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/search?q=...` | Search TMDB for series |
| `GET` | `/api/shows` | List all tracked series |
| `POST` | `/api/shows` | Add a series `{"tmdb_id": 123}` |
| `POST` | `/api/shows/{id}/seen` | Mark current episode as watched |
| `POST` | `/api/shows/{id}/season-done` | Mark current season as watched |
| `POST` | `/api/refresh` | Trigger metadata refresh |
| `DELETE` | `/api/shows/{id}` | Remove a series |

---

## Notes

- The frontend is mounted as a volume, so changes to `index.html` take effect immediately without rebuilding.
- Rebuild is only needed when backend files change.
- Series with status `Returning Series`, `In Production`, or `Planned` are never marked as finished — they transition to "waiting for next season" state instead.

---

## License

AGPL
