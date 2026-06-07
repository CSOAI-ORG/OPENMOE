"""x402 Bazaar discovery + self-listing verification (Layer 10/11).

Hermetic: stdlib only, no clock, no network. The BazaarClient's network egress
is an *injected fake fetch* returning canned JSON — no real HTTP is ever made.
Timestamps (last_settled_ts) are passed explicitly.
"""

import pytest

from openmoe_bft.bazaar import (
    BazaarClient,
    BazaarResource,
    DISCOVERY_RESOURCES_PATH,
    DISCOVERY_SEARCH_PATH,
    DISCOVERY_MCP_PATH,
    listing_readiness,
    rank_in_niche,
)


OUR_URL = "https://mcp.openmoe.ai/mcp"


def _our_resource(settled_count=12):
    return BazaarResource(
        resource=OUR_URL,
        name="OpenMoE-BFT EU AI Act compliance",
        description=(
            "EU AI Act conformity scoring, DORA / NIS2 / CRA compliance audit, "
            "A2A Agent Card validation, and red-team risk governance."
        ),
        category="compliance",
        price_atomic=10000,
        network="base",
        trust_signals={"settled_count": settled_count},
        last_settled_ts=1000,
    )


def _offtopic_resource(name="catpics", settled_count=99):
    return BazaarResource(
        resource=f"https://example.com/{name}",
        name=name,
        description="Random pictures of cats, dogs, and weather forecasts.",
        category="media",
        price_atomic=500,
        network="base",
        trust_signals={"settled_count": settled_count},
        last_settled_ts=1000,
    )


# ── BazaarClient with injected fake fetch ──────────────────────────


class _FakeFetch:
    """Records calls and returns canned discovery JSON. No network."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def __call__(self, method, url, params=None, json=None):
        self.calls.append((method, url, params))
        if url.endswith(DISCOVERY_SEARCH_PATH):
            return {"resources": self.pages.get("search", [])}
        if url.endswith(DISCOVERY_RESOURCES_PATH):
            offset = (params or {}).get("offset", 0)
            return {"resources": self.pages.get(offset, [])}
        return {"resources": []}


def test_default_client_has_no_network():
    client = BazaarClient()
    with pytest.raises(RuntimeError, match="provide a fetch fn"):
        client.list_resources()


def test_list_resources_parses_injected_json():
    canned = {
        0: [
            {
                "resource": OUR_URL,
                "name": "OpenMoE-BFT EU AI Act compliance",
                "description": "EU AI Act conformity + DORA/NIS2/CRA audit.",
                "category": "compliance",
                "price_atomic": 10000,
                "network": "base",
                "trust_signals": {"settled_count": 3},
                "last_settled_ts": 1000,
            }
        ]
    }
    fetch = _FakeFetch(canned)
    client = BazaarClient(fetch=fetch)
    out = client.list_resources(limit=50, offset=0)
    assert len(out) == 1
    res = out[0]
    assert isinstance(res, BazaarResource)
    assert res.resource == OUR_URL
    assert res.price_atomic == 10000
    assert res.category == "compliance"
    assert res.trust_signals["settled_count"] == 3
    # the GET hit the canonical discovery path
    assert fetch.calls[0][0] == "GET"
    assert fetch.calls[0][1].endswith(DISCOVERY_RESOURCES_PATH)


def test_from_api_tolerates_camelcase_shape():
    res = BazaarResource.from_api(
        {
            "resourceUrl": OUR_URL,
            "name": "x",
            "description": "y",
            "category": "compliance",
            "maxAmountRequired": "10000",
            "network": "base",
            "trustSignals": {"settled_count": 5},
            "lastSettledTs": 1234,
        }
    )
    assert res.resource == OUR_URL
    assert res.price_atomic == 10000  # parsed from string maxAmountRequired
    assert res.trust_signals == {"settled_count": 5}
    assert res.last_settled_ts == 1234


def test_search_passes_query_and_filters():
    fetch = _FakeFetch(
        {"search": [{"resource": OUR_URL, "name": "n", "description": "d"}]}
    )
    client = BazaarClient(fetch=fetch)
    out = client.search("EU AI Act compliance", filters={"category": "compliance"})
    assert len(out) == 1 and out[0].resource == OUR_URL
    _, url, params = fetch.calls[0]
    assert url.endswith(DISCOVERY_SEARCH_PATH)
    assert params["q"] == "EU AI Act compliance"
    assert params["category"] == "compliance"


def test_find_self_present_and_absent():
    canned = {
        0: [
            {"resource": "https://example.com/other", "name": "o", "description": "d"},
            {"resource": OUR_URL, "name": "n", "description": "d"},
        ]
    }
    client = BazaarClient(fetch=_FakeFetch(canned))
    found = client.find_self(OUR_URL)
    assert found is not None and found.resource == OUR_URL
    # trailing-slash insensitive
    assert client.find_self(OUR_URL + "/") is not None
    # absent -> None
    assert client.find_self("https://nope.example/mcp") is None


def test_find_self_none_on_empty_catalog():
    client = BazaarClient(fetch=_FakeFetch({0: []}))
    assert client.find_self(OUR_URL) is None


def test_mcp_url_is_discovery_mcp_path():
    client = BazaarClient(fetch=_FakeFetch({}))
    assert client.mcp_url().endswith(DISCOVERY_MCP_PATH)


# ── rank_in_niche: are we #1 in compliance? ────────────────────────


def test_rank_in_niche_compliance_entry_is_first():
    resources = [
        _offtopic_resource("catpics"),
        _our_resource(settled_count=12),
        _offtopic_resource("weather"),
    ]
    rank, total, gap = rank_in_niche(resources, our_url=OUR_URL)
    assert rank == 1
    assert gap == 0.0
    # off-topic entries don't even clear the niche filter -> total is just us
    assert total == 1


def test_rank_in_niche_offtopic_high_trust_does_not_outrank_us():
    # an off-topic entry with HUGE settled volume must still rank below us,
    # because semantic fit dominates and it has ~zero niche overlap.
    whale = _offtopic_resource("whale", settled_count=100000)
    resources = [whale, _our_resource(settled_count=1)]
    rank, total, gap = rank_in_niche(resources, our_url=OUR_URL)
    assert rank == 1


def test_rank_in_niche_two_compliance_entries_trust_breaks_tie():
    # a rival with the same strong description but FEWER settlements ranks below us
    rival = BazaarResource(
        resource="https://rival.example/mcp",
        name="OpenMoE-BFT EU AI Act compliance",
        description=(
            "EU AI Act conformity scoring, DORA / NIS2 / CRA compliance audit, "
            "A2A Agent Card validation, and red-team risk governance."
        ),
        category="compliance",
        price_atomic=10000,
        network="base",
        trust_signals={"settled_count": 1},
        last_settled_ts=1000,
    )
    resources = [rival, _our_resource(settled_count=50)]
    rank, total, gap = rank_in_niche(resources, our_url=OUR_URL)
    assert total == 2
    assert rank == 1
    assert gap == 0.0
    # and the rival is rank 2 with a positive gap
    r_rank, r_total, r_gap = rank_in_niche(resources, our_url="https://rival.example/mcp")
    assert r_rank == 2
    assert r_gap > 0.0


def test_rank_in_niche_absent_returns_zero():
    resources = [_our_resource()]
    rank, total, gap = rank_in_niche(resources, our_url="https://absent.example/mcp")
    assert rank == 0
    assert gap == 0.0


def test_rank_in_niche_deterministic():
    resources = [_our_resource(settled_count=7), _offtopic_resource()]
    a = rank_in_niche(resources, our_url=OUR_URL)
    b = rank_in_niche(resources, our_url=OUR_URL)
    assert a == b


# ── listing_readiness ──────────────────────────────────────────────


def test_listing_readiness_ready_card():
    card = {
        "name": "OpenMoE-BFT EU AI Act compliance",
        "description": (
            "EU AI Act conformity scoring, DORA / NIS2 / CRA compliance audit, "
            "A2A Agent Card validation, red-team governance."
        ),
        "category": "compliance",
        "network": "base",
        "x402": {"price_atomic": 10000},
    }
    verdict = listing_readiness(card)
    assert verdict["ready"] is True
    assert verdict["missing"] == []
    assert verdict["score"] == verdict["total"]


def test_listing_readiness_flags_missing_price():
    card = {
        "name": "OpenMoE-BFT EU AI Act compliance",
        "description": (
            "EU AI Act conformity scoring, DORA / NIS2 / CRA compliance audit."
        ),
        "category": "compliance",
        "network": "base",
        # no price anywhere
    }
    verdict = listing_readiness(card)
    assert verdict["ready"] is False
    assert "has_price" in verdict["missing"]


def test_listing_readiness_flags_missing_keywords():
    card = {
        "name": "Cat Picture Service",
        "description": "Returns adorable random pictures of cats and dogs all day.",
        "category": "media",
        "network": "base",
        "price_atomic": 500,
    }
    verdict = listing_readiness(card)
    assert verdict["ready"] is False
    assert "has_compliance_keywords" in verdict["missing"]


def test_listing_readiness_reads_real_server_card_shape():
    # loosely mirrors .well-known/mcp/server-card.json
    card = {
        "name": "openmoe-bft",
        "description": (
            "EU AI Act compliance MCP server: scores high-risk AI system "
            "conformity, validates A2A Agent Cards, and runs red-team scans "
            "(DORA / NIS2 / CRA aware)."
        ),
        "category": "compliance",
        "payment": {"network": "base", "price_atomic": 10000},
    }
    verdict = listing_readiness(card)
    assert verdict["ready"] is True
    assert len(verdict["compliance_keywords"]) >= 3
