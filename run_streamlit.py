"""Launch the Streamlit frontend.

Usage::

    python run_streamlit.py          ← correct
    # → http://localhost:8501

Make sure the backend is running first::

    python run.py

.. warning::

    Do NOT run ``streamlit run run_streamlit.py`` — this file is a
    launcher, not a Streamlit app.  Running it under Streamlit creates
    a nested process loop that continuously restarts the server.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _is_running_under_streamlit() -> bool:
    """Detect if this script is being run via ``streamlit run``.

    When Streamlit runs a script it populates ``sys.modules`` with the
    streamlit package before executing the user script.  When the script
    is run directly via ``python run_streamlit.py`` the streamlit module
    has not been imported yet.
    """
    return "streamlit" in sys.modules


if __name__ == "__main__":
    if _is_running_under_streamlit():
        sys.exit(
            "ERROR: This script is a launcher, not a Streamlit app.\n"
            "Run it directly instead:\n"
            "    python run_streamlit.py\n"
            "NOT:\n"
            "    streamlit run run_streamlit.py\n"
        )
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run",
            str(Path(__file__).resolve().parent / "frontend" / "app.py"),
            "--server.port", "8501",
            "--server.address", "0.0.0.0",
        ],
        check=True,
    )
