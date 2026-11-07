"""Command line: `python -m dcfmc serve` | `python -m dcfmc import-legacy <folder>`."""
from __future__ import annotations

import argparse
import webbrowser


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dcfmc", description="DCF Monte Carlo valuation app")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="Run the web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--open", action="store_true", help="Open the browser")
    li = sub.add_parser("import-legacy", help="Import v1 saved_analyses folder")
    li.add_argument("folder")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        import uvicorn

        from .api.app import create_app
        if a.open:
            webbrowser.open(f"http://{a.host}:{a.port}")
        uvicorn.run(create_app(), host=a.host, port=a.port)
    elif a.cmd == "import-legacy":
        from .store.db import Store
        from .store.repo import import_legacy
        print(import_legacy(Store(), a.folder))


if __name__ == "__main__":
    main()
