# 📺 TVTracker

Dashboard personal de seguimiento de series de TV con estética de televisor de los años 60.

Llevá el control de en qué episodio estás, marcá episodios y temporadas como vistos, descubrí qué series se estrenan en los próximos días — todo self-hosted, sin cuentas, sin tracking externo.

![TVTracker screenshot](screenshot.png)

---

## Características

- **Seguimiento de episodios** — sabés exactamente dónde quedaste en cada serie
- **Ordenamiento inteligente** — las series con episodios recientes suben al tope, ordenadas por fecha de emisión
- **Estado de espera** — cuando estás al día en una serie renovada, muestra "ESPERANDO TEMPORADA N" en lugar de marcarla como finalizada
- **Badges de estado** — RENOVADA, CANCELADA y FINALIZADA obtenidos desde TMDB
- **Próximo episodio** — episodio y fecha de estreno mostrados en la ficha
- **◈ DESCUBRIR** — calendario de estrenos de los próximos 30 días vía Trakt.tv, con botón para agregar directamente al dashboard
- **Auto-refresh** — sincroniza metadatos de TMDB periódicamente (intervalo configurable)
- **Cache de calendario** — si Trakt no responde, muestra el último resultado guardado
- **Estética CRT retro** — scanlines, brillo fósforo ámbar, posters en sepia

---

## Stack

- **Backend**: FastAPI + SQLite (sin ORM)
- **Frontend**: HTML/CSS/JS en un solo archivo, servido por FastAPI
- **APIs externas**: [TMDB](https://www.themoviedb.org/) y [Trakt.tv](https://trakt.tv/) (ambas gratuitas)
- **Contenedor**: Docker

---

## Estructura del proyecto

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

## Instalación

### 1. Obtener credenciales

**TMDB** — Creá una cuenta gratuita en [themoviedb.org](https://www.themoviedb.org/), andá a **Configuración → API** y copiá tu **Token de acceso de lectura** (el largo, empieza con `eyJ...`).

**Trakt** — Creá una cuenta en [trakt.tv](https://trakt.tv/), luego registrá una aplicación en [trakt.tv/oauth/applications/new](https://trakt.tv/oauth/applications/new) (el nombre y la redirect URI pueden ser cualquier cosa). Copiá el **Client ID**.

### 2. Configurar el entorno

```bash
cp .env.example .env
```

Editá `.env`:

```env
TMDB_API_KEY=TuLarguisimoTokenDeTMDB
DB_PATH=/data/tvtracker.db
REFRESH_INTERVAL_HOURS=24
TRAKT_CLIENT_ID=TuClientIdDeTrakt
CALENDAR_DAYS=30
```

### 3. Configurar Docker Compose

```bash
cp docker-compose.example.yml docker-compose.yml
```

Editá `docker-compose.yml` y ajustá las rutas y el nombre de tu red:

```yaml
volumes:
  - /ruta/a/tu/tvtracker/data:/data
  - /ruta/a/tu/tvtracker/frontend:/app/frontend

networks:
  - TuRed
```

### 4. Construir y levantar

```bash
docker compose up -d --build
```

Accedé en `http://localhost:7950` (o el host/puerto que hayas configurado).

---

## Uso

### Agregar una serie
Hacé clic en **+ AGREGAR SERIE**, escribí el nombre y seleccioná de los resultados. La serie se agrega desde S01E01.

### Marcar episodios
- **✓ VISTO** — marca el episodio actual como visto y avanza al siguiente. Solo aparece cuando el episodio ya se emitió.
- **» TEMP. VISTA** — marca toda la temporada actual como vista y salta al primer episodio de la siguiente.

### Descubrir series nuevas
Hacé clic en **◈ DESCUBRIR** para ver el calendario de estrenos de los próximos 30 días. Solo muestra S01E01 — es decir, series que estrenan su primera temporada. Podés agregar cualquiera directamente desde el modal con **+ AGREGAR**.

### Estados de una serie
| Estado | Descripción |
|--------|-------------|
| Normal | El episodio ya salió al aire, listo para ver |
| `AÚN NO EMITIDO` | El episodio existe pero todavía no se emitió |
| `⟳ ESPERANDO TEMPORADA N` | Estás al día, esperando la próxima temporada |
| `✦ SERIE FINALIZADA` | La serie terminó o fue cancelada |

### Refresh
Hacé clic en **⟳ REFRESH** para sincronizar los metadatos de TMDB. Actualiza total de temporadas, estado, cadena e info del próximo episodio — pero nunca modifica tu progreso actual.

El auto-refresh corre en segundo plano con el intervalo definido en `REFRESH_INTERVAL_HOURS`.

---

## Endpoints de la API

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/search?q=...` | Busca series en TMDB |
| `GET` | `/api/shows` | Lista todas las series guardadas |
| `POST` | `/api/shows` | Agrega una serie `{"tmdb_id": 123}` |
| `POST` | `/api/shows/{id}/seen` | Marca el episodio actual como visto |
| `POST` | `/api/shows/{id}/season-done` | Marca la temporada actual como vista |
| `POST` | `/api/refresh` | Dispara el refresh de metadatos TMDB |
| `GET` | `/api/discover` | Calendario de estrenos de Trakt (con cache) |
| `DELETE` | `/api/shows/{id}` | Elimina una serie |

---

## Notas

- El frontend está montado como volumen — cambios en `index.html` se ven sin rebuild.
- Rebuild solo necesario cuando cambian archivos del backend.
- Series con status `Returning Series`, `In Production` o `Planned` nunca se marcan como finalizadas — pasan al estado "esperando próxima temporada".
- El calendario de Trakt se cachea en SQLite por 6 horas. Si Trakt no responde, se muestra el último resultado guardado.

---

## Licencia

MIT
