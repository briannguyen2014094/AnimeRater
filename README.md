# AnimeRater

A web app for browsing anime, built with FastAPI, SQLite, and plain HTML, CSS,
and JavaScript. Anime data comes from AniList.

[Demo](http://129.153.76.218/)

## Current features

- Browse and search anime, and view details.
- Save favorites to your account (login required), available across browsers and devices.
- Create accounts and log in through the website or API.
- Recover passwords through emailed, single-use links that expire after 30 minutes.

Account-based ratings are not built yet. Old guest favorites in browser storage are
not automatically imported into an account.

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
| `APP_BASE_URL` | Unset | Public site URL for reset links, for example `https://anime.example`. Use HTTPS in production. |
| `SMTP_HOST` | Unset | SMTP server used to send recovery emails with STARTTLS. |
| `SMTP_PORT` | `587` | SMTP server port. |
| `SMTP_FROM` | Unset | Sender address allowed by your SMTP provider. |
| `SMTP_USERNAME` | Unset | SMTP login, if the server requires authentication. |
| `SMTP_PASSWORD` | Unset | SMTP password or provider app password. |

Set this variable in your terminal or hosting settings. The app does not load
`.env` files automatically. The local `run.py` script sets it to `false` for its
server process only; use this script for local development.

The app creates `data/animerater.db` on startup. This file stores users, sessions,
and the favorites table. It is ignored by Git, so each developer has their own
local database. The website saves favorites in this database for each account.

### Password recovery

Set `APP_BASE_URL`, `SMTP_HOST`, and `SMTP_FROM` plus any SMTP credentials before
using password recovery. Use your hosting provider's secret settings or local
environment variables for credentials; never commit credentials or database files.
No SMTP credentials are needed to browse, register, or log in.

Signup asks for a recovery email. Existing users can log in and select **Recovery
email** to add or change theirs by confirming their current password. Accounts
without a saved recovery email cannot use email recovery. Existing databases are
migrated automatically on startup without deleting users.

Select **Forgot password?** in the login dialog and enter your username. The
response does not disclose whether the account exists or has a recovery email.
Open the emailed link and enter and confirm a new password (12–128 characters).
Resetting a password signs out all devices. A new reset link invalidates the old
one; requests for the same account are limited to once per minute. Email delivery
failures are logged without reset links or credentials; check your SMTP settings
if mail does not arrive. Delivery runs in the app process; interrupted deliveries
can be retried after the cooldown.

Passwords are stored as salted Argon2id hashes, and session and recovery tokens
are stored as SHA-256 hashes. Plaintext passwords and recovery tokens are never
stored in the database. Reset links use URL fragments, which are removed from
the browser address when opened and are not sent in HTTP requests or referrers.

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
is installed. The second tests authentication and account favorites using temporary databases.
With Node.js installed, run `node --test tests/favorites-ui.test.cjs` to test the
favorites UI login requirement, persistence, and failure handling.

## Project structure

| Folder | Purpose |
| --- | --- |
| `app/` | FastAPI setup and SQLite helpers. |
| `packages/auth/` | Account and login API code. |
| `packages/catalog/` | AniList API client. |
| `packages/favorites/` | Account favorites API code. |
| `packages/search/`, `packages/reviews/` | Placeholders for future work. |
| `static/` | Frontend HTML, CSS, and JavaScript. |
| `scripts/` | Project checks. |
| `tests/` | Automated tests. |
| `data/` | Local database, created on startup and ignored by Git. |

## API reference

With the server running, open <http://127.0.0.1:8000/docs> to view the API routes
and request formats. Authentication POST requests and favorites POST/DELETE requests require the header
`X-Requested-With: AnimeRater`.

## Deployment

- Serve the site over HTTPS.
- Leave `SESSION_COOKIE_SECURE` unset or set it to `true`.
- Give the server write access to `data/`, keep it between deployments, and back it up.
- Run a single app instance with SQLite on local, persistent storage.
- Use a production server setup without `--reload`.

Login rate limits are not built yet. Add login rate limits and deployment-level
request limits before opening account registration to the public. Recovery email
requests have a per-account cooldown; they do not replace global abuse controls.

## License

MIT; see [LICENSE](LICENSE).
