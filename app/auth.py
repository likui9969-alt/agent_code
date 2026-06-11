"""API authentication — Bearer Token dependency.

Usage::

    from app.auth import require_auth

    @app.post("/chat")
    async def chat(request: ChatRequest, _token: str = Depends(require_auth)):
        ...

When ``API_AUTH_TOKEN`` is set in the environment, ALL protected routes
require ``Authorization: Bearer <token>``.  If the env var is empty or
missing, authentication is skipped (dev-friendly default).

Swagger UI
----------
Click the **Authorize** button (lock icon) and paste the token.  Swagger
will attach it to every request automatically.

Security
--------
Token comparison uses :func:`secrets.compare_digest` — a constant-time
string comparison that eliminates timing side-channels.  Python's ``!=``
short-circuits on the first differing byte, leaking the position of the
first mismatch through response-time measurements.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    description="Paste your API_AUTH_TOKEN here.  Leave empty if auth is disabled.",
    auto_error=False,
)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """FastAPI dependency — validate Bearer token.

    Returns the token string if valid, otherwise raises 401.

    Authentication is skipped entirely when ``API_AUTH_TOKEN`` is not
    configured (empty string), so existing dev setups keep working.
    """
    expected = settings.api_auth_token
    if not expected:
        # Auth not configured — allow all requests
        return ""

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header.  "
                   "Provide 'Authorization: Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials
