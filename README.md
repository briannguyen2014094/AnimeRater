# AnimeRater

A starting point for an anime rating web app, built with plain HTML, CSS, and
JavaScript. The current page is a minimal scaffold; rating features are not yet
implemented. There is no backend, build step, or external dependency.

## Local development

Requires Python 3.10 or newer. From the repository root:

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Open <http://127.0.0.1:8000>. Edit the files and refresh the browser to see changes.
Stop the server with Ctrl+C. If port 8000 is occupied, choose another port.
On systems where Python is named `python3`, use that command instead.
This server is for local development only.

## Validation

```sh
python scripts/check.py
```

Checks that the starter files exist, the HTML has a language and title, and local
script and stylesheet references resolve within the repository. If Node.js is
installed, it also checks JavaScript syntax; otherwise it explicitly reports that
check as skipped. No packages need to be installed.

For UI changes, also open the page in a browser, check the console, and verify
keyboard access and narrow-screen layout. The automated check does not validate
CSS, accessibility, or application behavior.

## Project map

- `index.html`: page structure and accessible markup.
- `styles.css`: page styles and responsive layout.
- `script.js`: browser behavior.
- `scripts/check.py`: dependency-free scaffold checks.
- `AGENTS.md`: instructions for LLM coding agents.

## Working with an LLM

Open this repository as the agent's workspace and have it read `AGENTS.md` before
making changes. Give it a concrete feature or bug, expected behavior, and any
constraints. The agent can use the local server and validation command above.
No model API key or hosted service is required for the project itself.

Install Git separately if your environment does not provide it on PATH; it is
needed for reviewing diffs and version control, but not for running the site.
Keep credentials out of browser code and committed files.

## License

MIT; see [LICENSE](LICENSE).
