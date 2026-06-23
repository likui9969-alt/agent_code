"""Frontend configuration."""

from __future__ import annotations

import os

# ── Backend API ─────────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "120"))
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "")

# ── Streamlit ───────────────────────────────────────────────────────────────
PAGE_TITLE = "AI Code Assistant"
PAGE_ICON = "🧠"
LAYOUT = "wide"

# ── Theme tokens (used by global CSS injected in app.py) ────────────────────
THEME = {
    "primary": "#2563EB",      # blue-600
    "primary_hover": "#1D4ED8",  # blue-700
    "success": "#10B981",      # emerald-500
    "warning": "#F59E0B",      # amber-500
    "danger": "#EF4444",       # red-500
    "bg_card": "#F8FAFC",      # slate-50
    "border": "#E2E8F0",       # slate-200
    "text": "#1E293B",         # slate-800
    "text_muted": "#64748B",   # slate-500
    "radius": "0.5rem",
}
