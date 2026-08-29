#!/usr/bin/env python3
"""
Run box_packer_3d.py, then serve this directory over HTTP and open the p5.js preview.

loadStrings('output.txt') requires a real HTTP origin (not file://) in most browsers.
p5.js is loaded from p5_libs/p5.js (no internet required).

Extra arguments are forwarded to box_packer_3d.py, e.g.:
  python3 run_box_packer_and_view.py
"""
from __future__ import annotations

import http.server
import socketserver
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKER = ROOT / "box_packer_3d.py"
P5_LIB = ROOT / "p5_libs" / "p5.js"
OUTPUT_NAME = "output.txt"  # hardcoded inside box_packer_3d.py's main()
DEFAULT_PORT = 8765
MAX_PORT_TRIES = 20


def main() -> None:
    if not PACKER.is_file():
        print(f"Missing {PACKER}", file=sys.stderr)
        sys.exit(1)
    if not P5_LIB.is_file():
        print(
            f"Missing {P5_LIB} — add the p5.js bundle (see README).",
            file=sys.stderr,
        )
        sys.exit(1)

    packer_args = sys.argv[1:]
    proc = subprocess.run(
        [sys.executable, str(PACKER), *packer_args],
        cwd=ROOT,
    )
    if proc.returncode != 0:
        sys.exit(proc.returncode)

    output_path = ROOT / OUTPUT_NAME
    if not output_path.is_file():
        print(f"No {output_path.name} found after packer run; nothing to visualize.", file=sys.stderr)
        sys.exit(1)

    class _ProjectDirHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

    httpd: socketserver.TCPServer | None = None
    port = DEFAULT_PORT
    for _ in range(MAX_PORT_TRIES):
        try:
            httpd = socketserver.TCPServer(("", port), _ProjectDirHandler)
            break
        except OSError:
            port += 1
    if httpd is None:
        print(f"No free port in {DEFAULT_PORT}..{DEFAULT_PORT + MAX_PORT_TRIES - 1}", file=sys.stderr)
        sys.exit(1)

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/index_box.html"
    print(f"Opening {url}")
    print("Press Enter to stop the local server.")
    webbrowser.open(url)

    try:
        input()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()