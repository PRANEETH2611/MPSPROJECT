"""
Convenience launcher for local development.

Starts the Flask backend and a lightweight static file server for the frontend,
inspired by the simpler startup flow from the Mini-Project repository but
adapted to this separated frontend/backend architecture.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "5000"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "8000"))


def _start_process(args: list[str], cwd: Path) -> subprocess.Popen:
    return subprocess.Popen(args, cwd=str(cwd))


def main() -> int:
    backend_cmd = [sys.executable, "backend/app.py"]
    frontend_cmd = [sys.executable, "-m", "http.server", str(FRONTEND_PORT)]

    print("Starting AIOps local stack...")
    print(f"Backend:  http://localhost:{BACKEND_PORT}")
    print(f"Frontend: http://localhost:{FRONTEND_PORT}/index.html")

    backend = _start_process(backend_cmd, ROOT)
    frontend = _start_process(frontend_cmd, ROOT / "frontend")
    children = [backend, frontend]

    try:
        while True:
            for proc, name in ((backend, "backend"), (frontend, "frontend")):
                code = proc.poll()
                if code is not None:
                    print(f"{name} exited unexpectedly with code {code}")
                    return code
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        for proc in children:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
        deadline = time.time() + 5
        for proc in children:
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if proc.poll() is None:
                proc.kill()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
