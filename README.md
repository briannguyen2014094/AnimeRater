# AnimeRater

A web app for browsing anime, built with FastAPI, SQLite, and plain HTML, CSS,
and JavaScript. Anime data comes from AniList.

[Demo](http://129.153.76.218/)

## Current features

- Browse and search anime, and view details.
- Save favorites in the browser.
- Create accounts and manage login sessions through the API.

Login and signup forms, account-based favorites, and ratings are not built yet.

## Requirements

- Python 3.10 or newer.
- Internet access to load anime from AniList. No API key is needed.

SQLite is included with Python. No separate database server is needed.

## Getting started

Open a terminal in the AnimeRater folder.

### Windows (PowerShell)

```powershell
python run.py
```

### macOS or Linux

```sh
python3 run.py
```

Open <http://127.0.0.1:8000>. Press Ctrl+C to stop the server.

Use the same command each time. It creates `.venv` if needed, installs missing
dependencies, sets up local login cookies, and starts the server. Python changes
restart the server automatically; refresh the browser to see frontend changes.

If port 8000 is busy, add `--port 8001` to the command and open
<http://127.0.0.1:8001>.

## Configuration

| Setting | Default | Use |
| --- | --- | --- |
| `SESSION_COOKIE_SECURE` | `true` | Requires HTTPS for login cookies. Set to `false` only for local HTTP use. |

Set this variable in your terminal or hosting settings. The app does not load
`.env` files automatically. The local `run.py` script sets it to `false` for its
server process only; use this script for local development.

The app creates `data/animerater.db` on startup. This file stores users, sessions,
and the favorites table. It is ignored by Git, so each developer has their own
local database. The website still saves favorites in the browser.

## Testing

Run these commands with the virtual environment's Python.

On Windows:

```powershell
.\.venv\Scripts\python.exe scripts/check.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On macOS or Linux:

```sh
.venv/bin/python scripts/check.py
.venv/bin/python -m unittest discover -s tests -v
```

The first command checks page files and links, plus JavaScript syntax if Node.js
is installed. The second tests the login API using a temporary database.

## Project structure

| Folder | Purpose |
| --- | --- |
| `app/` | FastAPI setup and SQLite helpers. |
| `packages/auth/` | Account and login API code. |
| `packages/catalog/` | AniList API client. |
| `packages/search/`, `packages/reviews/` | Placeholders for future work. |
| `static/` | Frontend HTML, CSS, and JavaScript. |
| `scripts/` | Project checks. |
| `tests/` | Automated tests. |
| `data/` | Local database, created on startup and ignored by Git. |

## API reference

With the server running, open <http://127.0.0.1:8000/docs> to view the API routes
and request formats. Authentication POST requests require the header
`X-Requested-With: AnimeRater`.

## Deployment

- Serve the site over HTTPS.
- Leave `SESSION_COOKIE_SECURE` unset or set it to `true`.
- Give the server write access to `data/`, keep it between deployments, and back it up.
- Run a single app instance with SQLite on local, persistent storage.
- Use a production server setup without `--reload`.

Login rate limits and password recovery are not built yet. Add login rate limits
before opening account registration to the public.

## License

MIT; see [LICENSE](LICENSE).
