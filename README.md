# AnimeRater

A starter website for rating anime, made with HTML, CSS, JavaScript, and a
Python FastAPI backend. Rating features are not available yet. You do not
need to build the site.

## Run the site on your computer

You need Python 3.10 or newer. Open a terminal in the AnimeRater folder.
Create a virtual environment and install the dependencies, including Uvicorn
to run the FastAPI app.

On Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt uvicorn
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On macOS or Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt uvicorn
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000> in your browser. After editing a file, refresh the
page to see your changes.

Keep the terminal running while using the site. On subsequent runs, use only
the Uvicorn command for your operating system. Internet access is needed to
fetch anime from AniList; no API key or database setup is required for the
current catalog page. Use the FastAPI app rather than `python -m http.server`,
which does not provide the catalog API.

Press Ctrl+C in the terminal to stop the site. If port 8000 is already in use,
replace `8000` with `8001` in both the command and the browser address.
This server command is only for testing the site on your own computer.

## Check the files

Run this command from the AnimeRater folder:

```sh
python scripts/check.py
```

This checks that the required files exist, the page has a language and title,
and links to local JavaScript and CSS files point to files inside the project.
If Node.js is installed, it also checks for JavaScript syntax errors. Otherwise,
it tells you that this check was skipped. No extra packages are needed.

After changing how the page looks or works, also test it in your browser:

- Look for errors in the browser's developer console.
- Make sure you can use the page with a keyboard.
- Check that the page fits a narrow window, such as a phone screen.

The check command does not test page styles, ease of use for people with
disabilities, or whether the site's features work.

## What each file does

- `static/index.html`: the page's content and structure.
- `static/styles.css`: how the page looks and fits different screen sizes.
- `static/script.js`: what the page does when you interact with it.
- `scripts/check.py`: checks the basic project files.

## License

MIT; see [LICENSE](LICENSE).
