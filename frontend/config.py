"""Frontend configuration."""

from __future__ import annotations

import os

# ── Backend API ─────────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "120"))

# ── Streamlit ───────────────────────────────────────────────────────────────
PAGE_TITLE = "AI Code Assistant"
PAGE_ICON = "🧠"
LAYOUT = "wide"
