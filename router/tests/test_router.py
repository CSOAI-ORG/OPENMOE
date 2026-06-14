"""Tests for the openmoe-router core."""

import pytest

from openmoe_router.router import InferenceRouter, RouteCriteria, NoProviderAvailable
from openmoe_router.providers import Provider, ProviderRegistry


def test_registry_lists_defaults():
    registry = ProviderRegistry()
    ids = {p.id for p in registry.list()}
    assert "deepseek" in ids
    assert "kimi" in ids
    assert "minimax" in ids
    assert "qwen" in ids


def test_rank_by_cost_prefers_budget_tiers():
    registry = ProviderRegistry()
    router = InferenceRouter(registry)
    ranked = router.rank("openmoe/auto", RouteCriteria(optimize="cost"))
    providers = [p.id for p, _ in ranked]
    assert providers[0] in ("deepseek", "qwen", "local")


def test_rank_by_quality_prefers_openrouter():
    registry = ProviderRegistry()
    router = InferenceRouter(registry)
    ranked = router.rank("openmoe/auto", RouteCriteria(optimize="quality"))
    providers = [p.id for p, _ in ranked]
    assert providers[0] == "openrouter"


def test_provider_preference_filters():
    registry = ProviderRegistry()
    router = InferenceRouter(registry)
    ranked = router.rank("openmoe/auto", RouteCriteria(provider_preference="kimi"))
    assert len(ranked) == 1
    assert ranked[0][0].id == "kimi"


def test_no_provider_raises():
    registry = ProviderRegistry([Provider(id="x", name="X", base_url="http://x", models=("m",))])
    router = InferenceRouter(registry)
    with pytest.raises(NoProviderAvailable):
        router.rank("unknown-model")
