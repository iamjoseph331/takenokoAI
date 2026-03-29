#!/usr/bin/env python3
"""
Standalone visualization viewer for TakenokoAI.

Serves viz_ui.html on a local HTTP port. The browser's WebSocket
connects directly to the agent's VizBroadcaster on a separate port.

Usage (from repo root):
  python admin/run_viz.py                              # defaults
  python admin/run_viz.py --connect ws://host:7899/ws  # remote agent
  python admin/run_viz.py --port 8080                  # custom viewer port
  python admin/run_viz.py --no-open                    # skip browser auto-open
"""

from __future__ import annotations

import argparse
import http.server
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

_HTML = Path(__file__).parent / "viz_ui.html"


# ── Argument parsing ──────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="TakenokoAI visualization viewer — connects to a running agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python admin/run_viz.py
  python admin/run_viz.py --connect ws://192.168.1.10:7899/ws
  python admin/run_viz.py --port 8080 --no-open
        """,
    )
    p.add_argument(
        "--connect",
        default="ws://localhost:7899/ws",
        metavar="WS_URL",
        help="Agent WebSocket data URL (default: ws://localhost:7899/ws)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=7900,
        help="Local HTTP port to serve the UI on (default: 7900)",
    )
    p.add_argument(
        "--no-open",
        action="store_true",
        help="Don't auto-open browser on start",
    )
    return p.parse_args(argv)


# ── HTTP handler ──────────────────────────────────────────────────────────────


class _VizHandler(http.server.BaseHTTPRequestHandler):
    """Serves viz_ui.html for every GET request, regardless of path."""

    def do_GET(self) -> None:
        if not _HTML.exists():
            self.send_error(404, f"viz_ui.html not found at {_HTML}")
            return
        content = _HTML.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # suppress per-request access logs


# ── Entry point ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if not _HTML.exists():
        print(f"[viz] ERROR: viz_ui.html not found at {_HTML}", file=sys.stderr)
        print(
            "[viz] Run from the repo root: python admin/run_viz.py",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build URL the browser will open, with the agent WS URL as a query param
    encoded_ws = urllib.parse.quote(args.connect, safe="")
    ui_url = f"http://localhost:{args.port}/?agent={encoded_ws}"

    print(f"[viz] UI:     {ui_url}", file=sys.stderr)
    print(f"[viz] Agent:  {args.connect}", file=sys.stderr)
    print("[viz] Press Ctrl+C to stop.", file=sys.stderr)

    server = http.server.HTTPServer(("0.0.0.0", args.port), _VizHandler)

    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(ui_url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[viz] Stopped.", file=sys.stderr)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
