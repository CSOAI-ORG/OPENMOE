"""MCP tool exposure for the OpenMoE router.

Exposes:
- openmoe_rank_providers
- openmoe_route_completion
- openmoe_provider_health
"""

from __future__ import annotations

from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise ImportError("Install openmoe-router[mcp] to use the MCP bridge") from exc

from .router import InferenceRouter, RouteCriteria
from .providers import ProviderRegistry

mcp = FastMCP("openmoe-router")
router = InferenceRouter()


@mcp.tool()
async def openmoe_rank_providers(model: str, optimize: str = "cost") -> dict[str, Any]:
    """Rank providers for a given model by cost, latency, or quality."""
    criteria = RouteCriteria(optimize=optimize)  # type: ignore[arg-type]
    ranked = router.rank(model, criteria)
    return {
        "model": model,
        "criterion": optimize,
        "ranking": [
            {"provider": p.id, "model": p.default_model or p.models[0], "score": round(score, 4)}
            for p, score in ranked
        ],
    }


@mcp.tool()
async def openmoe_provider_health() -> dict[str, Any]:
    """List registered providers and their configured models."""
    return {
        "providers": [
            {
                "id": p.id,
                "name": p.name,
                "base_url": p.base_url,
                "models": list(p.models),
                "default_model": p.default_model,
                "cost_tier": p.cost_tier,
            }
            for p in router.registry.list()
        ]
    }
