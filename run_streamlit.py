"""Launch the Streamlit frontend.

Usage::

    python run_streamlit.py
    # → http://localhost:8501

Make sure the backend is running first::

    python run.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run",
            str(Path(__file__).resolve().parent / "frontend" / "app.py"),
            "--server.port", "8501",
            "--server.address", "0.0.0.0",
        ],
        check=True,
    )
