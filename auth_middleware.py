"""Bearer-token authentication middleware for the openmoe-bft MCP server.

A small Starlette/ASGI middleware that gates the MCP transport behind a
shared bearer token. Discovery endpoints (``/.well-known/...``, ``/health``)
stay public so registries and load balancers can probe the server unauthenticated;
everything else requires ``Authorization: Bearer <token>``.

The expected token is read from the ``OPENMOE_BFT_TOKEN`` environment variable.
When it is unset the middleware fails open (dev mode) and simply annotates the
request scope — production deployments MUST set the variable.
"""

from __future__ import annotations

import hmac
import os
from typing import Awaitable, Callable, Iterable

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


#: Path prefixes that never require authentication (discovery + health).
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/.well-known/",
    "/health",
)

#: Environment variable holding the expected shared bearer token.
TOKEN_ENV = "OPENMOE_BFT_TOKEN"


def _is_public(path: str, public_prefixes: Iterable[str]) -> bool:
    return any(path == p or path.startswith(p) for p in public_prefixes)


def _extract_bearer(header_value: str) -> str | None:
    parts = header_value.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


class BearerAuthMiddleware:
    """ASGI middleware enforcing a constant-time bearer-token comparison.

    Construct with ``BearerAuthMiddleware(app, token=...)`` or rely on the
    ``OPENMOE_BFT_TOKEN`` environment variable. Non-HTTP scopes (lifespan,
    websocket) pass straight through.
    """

    def __init__(
        self,
        app: ASGIApp,
        token: str | None = None,
        public_prefixes: Iterable[str] = PUBLIC_PREFIXES,
    ) -> None:
        self.app = app
        self._token = token if token is not None else os.environ.get(TOKEN_ENV, "")
        self._public_prefixes = tuple(public_prefixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not self._token or _is_public(path, self._public_prefixes):
            await self.app(scope, receive, send)
            return

        conn = HTTPConnection(scope)
        presented = _extract_bearer(conn.headers.get("authorization", ""))

        if presented is None:
            await self._deny(send, "missing bearer token")
            return
        if not hmac.compare_digest(presented, self._token):
            await self._deny(send, "invalid bearer token")
            return

        await self.app(scope, receive, send)

    async def _deny(self, send: Send, detail: str) -> None:
        response = JSONResponse(
            {"error": "unauthorized", "detail": detail},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(  # type: ignore[call-arg]
            {"type": "http", "path": "/", "headers": []}, _empty_receive, send
        )


async def _empty_receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


def require_bearer(
    handler: Callable[..., Awaitable], token: str | None = None
) -> Callable[..., Awaitable]:
    """Decorator form for ad-hoc Starlette routes outside the ASGI stack."""
    expected = token if token is not None else os.environ.get(TOKEN_ENV, "")

    async def _wrapped(request, *args, **kwargs):
        presented = _extract_bearer(request.headers.get("authorization", ""))
        if expected and (presented is None or not hmac.compare_digest(presented, expected)):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await handler(request, *args, **kwargs)

    return _wrapped
