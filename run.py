"""Start the AI Code Assistant MVP server.

Usage::

    python run.py          # → http://0.0.0.0:8000
    python run.py --port 9000

Then::

    curl -X POST http://localhost:8000/chat \\
      -H "Content-Type: application/json" \\
      -d '{"input": "Write a quicksort function"}'
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the `app` package is importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Code Assistant MVP server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
