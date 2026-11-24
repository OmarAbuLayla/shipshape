"""``shipshape-api``: start the local server."""

from __future__ import annotations

import argparse

import uvicorn

from shipshape_api.app import create_app


def main() -> None:
    """Serve on 127.0.0.1 only; this is a tool for your own machine."""
    parser = argparse.ArgumentParser(description="Run the Shipshape web API locally.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"Shipshape API on http://127.0.0.1:{args.port}  (docs: /docs)")
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
