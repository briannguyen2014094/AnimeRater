# AnimeRater

A starter website for rating anime, made with HTML, CSS, and JavaScript.
Rating features are not available yet. There is no server-side app, and you
do not need to build the site or install extra packages.

## Run the site on your computer

You need Python 3.10 or newer. Open a terminal in the AnimeRater folder and run:

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Open <http://127.0.0.1:8000> in your browser. After editing a file, refresh the
page to see your changes.

Press Ctrl+C in the terminal to stop the site. If port 8000 is already in use,
replace `8000` with `8001` in both the command and the browser address.
If your computer uses `python3` instead of `python`, use `python3` in the commands.
This command is only for testing the site on your own computer.

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

- `index.html`: the page's content and structure.
- `styles.css`: how the page looks and fits different screen sizes.
- `script.js`: what the page does when you interact with it.
- `scripts/check.py`: checks the basic project files.

## License

MIT; see [LICENSE](LICENSE).
