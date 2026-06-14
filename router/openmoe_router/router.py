"""Core routing engine: rank providers and dispatch requests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from .providers import Provider, ProviderRegistry


@dataclass(frozen=True)
class RouteCriteria:
    """User-supplied routing preferences."""

    optimize: Literal["cost", "latency", "quality"] = "cost"
    required_capabilities: frozenset[str] = frozenset()
    max_cost_per_1m_tokens: float | None = None
    provider_preference: str | None = None
    use_bft: bool = False


@dataclass(frozen=True)
class RoutingReceipt:
    """Metadata returned with every routed request."""

    provider_id: str
    model: str
    criterion: str
    estimated_cost_per_1m: float | None
    latency_ms: int | None
    bft_consensus: bool | None


class InferenceRouter:
    """Route inference requests across a provider fleet."""

    def __init__(self, registry: ProviderRegistry | None = None, client: httpx.AsyncClient | None = None):
        self.registry = registry or ProviderRegistry()
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    def rank(
        self,
        model: str,
        criteria: RouteCriteria | None = None,
    ) -> list[tuple[Provider, float]]:
        """Return providers ranked by the chosen criterion (higher is better)."""
        criteria = criteria or RouteCriteria()
        candidates = self.registry.providers_for_model(model)

        # Filter by capability and explicit provider preference.
        def ok(p: Provider) -> bool:
            if criteria.required_capabilities and not criteria.required_capabilities.issubset(p.capabilities):
                return False
            if criteria.provider_preference and p.id != criteria.provider_preference:
                return False
            return True

        candidates = [p for p in candidates if ok(p)]
        if not candidates:
            raise NoProviderAvailable(f"No provider available for model={model} with criteria={criteria}")

        # Simple scoring stubs. Real implementation pulls live benchmarks.
        scores: list[tuple[Provider, float]] = []
        for p in candidates:
            score = _score_provider(p, criteria)
            scores.append((p, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    async def route(
        self,
        model: str,
        payload: dict[str, Any],
        criteria: RouteCriteria | None = None,
    ) -> tuple[dict[str, Any], RoutingReceipt]:
        """Pick the best provider and proxy the request."""
        ranked = self.rank(model, criteria)
        provider, score = ranked[0]
        selected_model = model if provider.supports(model) else (provider.default_model or provider.models[0])

        api_key = _api_key_for(provider)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Normalize payload to provider-specific model name.
        body = {**payload, "model": selected_model}

        url = f"{provider.base_url.rstrip('/')}/chat/completions"
        response = await self.client.post(url, headers=headers, json=body)
        response.raise_for_status()

        receipt = RoutingReceipt(
            provider_id=provider.id,
            model=selected_model,
            criterion=(criteria or RouteCriteria()).optimize,
            estimated_cost_per_1m=_estimate_cost(provider),
            latency_ms=None,
            bft_consensus=False,
        )
        return response.json(), receipt


class NoProviderAvailable(Exception):
    pass


# --- Stub helpers: replace with live benchmark feed ---

_TIER_SCORE = {
    "budget": 1.0,
    "standard": 0.7,
    "premium": 0.4,
}

_QUALITY_SCORE = {
    "deepseek": 0.85,
    "kimi": 0.88,
    "minimax": 0.86,
    "qwen": 0.87,
    "openrouter": 0.90,
    "local": 0.75,
}

_LATENCY_SCORE = {
    "deepseek": 0.80,
    "kimi": 0.85,
    "minimax": 0.90,
    "qwen": 0.82,
    "openrouter": 0.75,
    "local": 0.98,
}


def _score_provider(provider: Provider, criteria: RouteCriteria) -> float:
    optimize = criteria.optimize
    if optimize == "cost":
        return _TIER_SCORE.get(provider.cost_tier, 0.5) + _QUALITY_SCORE.get(provider.id, 0.5) * 0.2
    if optimize == "latency":
        return _LATENCY_SCORE.get(provider.id, 0.5)
    if optimize == "quality":
        return _QUALITY_SCORE.get(provider.id, 0.5)
    return 0.5


def _api_key_for(provider: Provider) -> str | None:
    if provider.api_key_env:
        return os.environ.get(provider.api_key_env) or None
    return None


def _estimate_cost(provider: Provider) -> float | None:
    return {
        "budget": 0.5,
        "standard": 2.0,
        "premium": 10.0,
    }.get(provider.cost_tier)
