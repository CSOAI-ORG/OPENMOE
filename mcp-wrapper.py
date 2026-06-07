#!/usr/bin/env python3
"""Streamable-HTTP wrapper for the openmoe-bft MCP server.

Imports the FastMCP instance from ``server.py``, mounts the MCP discovery
endpoints (``/.well-known/mcp/server-card.json`` and a manifest + health
route), and serves everything on the ``streamable-http`` transport. This is the
container entrypoint used by ``Dockerfile.glama``.
"""

import os
import sys

sys.path.insert(0, os.getcwd())

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from server import mcp


SERVICE_NAME = "openmoe-bft"
REPO_URL = "https://github.com/CSOAI-ORG/OPENMOE"


@mcp.custom_route("/.well-known/mcp/server-card.json", methods=["GET"])
async def server_card(request: Request) -> Response:
    """Serve the MCP server card for registry discovery."""
    return JSONResponse(
        {
            "$schema": "https://static.modelcontextprotocol.io/schemas/2025-07-09/server.schema.json",
            "name": SERVICE_NAME,
            "description": "OpenMoE-BFT compliance + governance MCP server.",
            "version": "0.1.0",
            "vendor": "MEOK AI Labs",
            "homepage": "https://openmoe.ai",
            "repository": REPO_URL,
            "protocolVersion": "2025-11-25",
            "transport": {"type": "streamable-http", "url": "http://localhost:8000/mcp"},
            "capabilities": {"tools": {"listChanged": False}},
        },
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
    )


@mcp.custom_route("/.well-known/mcp", methods=["GET"])
async def mcp_manifest(request: Request) -> Response:
    """Serve a minimal MCP transport manifest."""
    return JSONResponse(
        {
            "mcp_version": "2025-11-25",
            "endpoints": [
                {"type": "streamable-http", "path": "/mcp", "url": "http://localhost:8000/mcp"}
            ],
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    """Liveness probe."""
    return JSONResponse({"status": "ok", "service": SERVICE_NAME})


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="streamable-http")
