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

Open a terminal in the AnimeRater folder and follow the steps for your system.

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt uvicorn
$env:SESSION_COOKIE_SECURE = "false"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### macOS or Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt uvicorn
SESSION_COOKIE_SECURE=false .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Press Ctrl+C to stop the server.

For later runs, skip the first two commands. In a new PowerShell terminal,
set `SESSION_COOKIE_SECURE` again before starting the server.
If port 8000 is busy, change it to 8001 in the command and browser address.

## Configuration

| Setting | Default | Use |
| --- | --- | --- |
| `SESSION_COOKIE_SECURE` | `true` | Requires HTTPS for login cookies. Set to `false` only for local HTTP use. |

Set this variable in your terminal or hosting settings. The app does not load
`.env` files automatically.

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
