"""Check the static scaffold using only the Python standard library."""

from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.language = ""
        self.title = ""
        self.in_title = False
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.language = attrs.get("lang") or ""
        if tag == "title":
            self.in_title = True
        if tag == "script" and "src" in attrs:
            self.assets.append(attrs.get("src") or "")
        if tag == "link" and "stylesheet" in (attrs.get("rel") or "").split():
            self.assets.append(attrs.get("href") or "")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def main():
    errors = []
    for name in ("index.html", "styles.css", "script.js"):
        path = ROOT / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"Missing or empty starter file: {name}")

    page = PageParser()
    if (ROOT / "index.html").is_file():
        page.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    if not page.language.strip():
        errors.append("index.html needs an html lang attribute.")
    if not page.title.strip():
        errors.append("index.html needs a nonempty title.")
    for reference in page.assets:
        url = urlsplit(reference)
        if url.scheme or url.netloc:
            continue
        path = (ROOT / unquote(url.path).lstrip("/")).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            errors.append(f"Missing or invalid local asset: {reference!r}")

    node = shutil.which("node")
    if node:
        result = subprocess.run([node, "--check", str(ROOT / "script.js")],
                                capture_output=True, text=True)
        if result.returncode:
            errors.append(result.stderr.strip() or "JavaScript syntax check failed.")
        else:
            print("PASS: script.js syntax")
    else:
        print("SKIP: JavaScript syntax check (Node.js is not on PATH)")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: static scaffold and local asset references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
