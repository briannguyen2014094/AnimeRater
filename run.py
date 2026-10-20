"""Start local development with: python run.py"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv


def main():
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required.")

    parser = argparse.ArgumentParser(description="Run AnimeRater locally.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")

    root = Path(__file__).resolve().parent
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        print("Creating the Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)

    # pip keeps installed packages and adds any missing dependencies.
    print("Checking dependencies...", flush=True)
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
         "-r", str(root / "requirements.txt")],
        cwd=root, check=True,
    )

    # This setting applies only to the local server process.
    server_environment = os.environ.copy()
    server_environment["SESSION_COOKIE_SECURE"] = "false"
    print(f"Open http://127.0.0.1:{args.port} (Ctrl+C to stop).", flush=True)
    result = subprocess.run(
        [str(python), "-m", "uvicorn", "app.main:app", "--reload",
         "--host", "127.0.0.1", "--port", str(args.port)],
        cwd=root, env=server_environment,
    )
    return result.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Dependency setup failed (exit code {exc.returncode}).") from None
