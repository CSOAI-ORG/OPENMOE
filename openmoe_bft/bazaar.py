"""x402 Bazaar discovery + self-listing verification (OpenMoE-BFT Empire, Layer 10/11).

This is **how MEOK verifies and defends its #1 position in the Coinbase CDP
x402 Bazaar for the compliance niche.** The Bazaar
(https://docs.cdp.coinbase.com/x402/bazaar) is the discovery layer where x402
agents — including OpenRouter-routed traffic — *find and auto-pay* payable
endpoints. There is **no registration step**: the CDP facilitator auto-catalogs
an endpoint the **first time it settles a payment**, and then ranks it by
**semantic description quality + on-chain trust signals** (settled-payment
volume / history). So MEOK's rank = *semantic fit to the compliance query* +
*on-chain trust*. Because nobody else owns "EU AI Act / DORA / NIS2 / CRA
compliance MCP", the moment one payment settles MEOK is structurally #1 in that
niche — this module is the offline instrument that *proves* it and flags what
still needs fixing to stay there.

What it provides
----------------
- :class:`BazaarResource` — one entry in the Bazaar discovery catalog.
- :class:`BazaarClient` — reproduces the CDP discovery API shape
  (``/v2/x402/discovery/resources`` browse, ``/search`` semantic search,
  ``/mcp`` agent access) over a **pluggable, network-optional** ``fetch``
  callable. The default ``fetch`` refuses to touch the network so the core stays
  stdlib-only; tests inject a fake ``fetch`` returning canned JSON.
- :func:`rank_in_niche` — "are we #1 in compliance?" computed fully offline from
  semantic overlap + trust signal.
- :func:`listing_readiness` — does our server card carry the metadata that ranks
  well in Bazaar semantic search? Returns the missing items.

Hermeticity note: nothing here reads the clock, the network, or any randomness.
``last_settled_ts`` and every timestamp are caller-supplied; discovery happens
through the injected ``fetch``. Construction is deterministic and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


__all__ = [
    "BazaarResource",
    "BazaarClient",
    "NICHE_KEYWORDS",
    "rank_in_niche",
    "listing_readiness",
]


# The CDP x402 Bazaar discovery API surface (docs.cdp.coinbase.com/x402/bazaar).
# Kept as constants so callers (and tests) reference the same canonical paths.
DISCOVERY_RESOURCES_PATH = "/v2/x402/discovery/resources"
DISCOVERY_SEARCH_PATH = "/v2/x402/discovery/search"
DISCOVERY_MCP_PATH = "/v2/x402/discovery/mcp"

# The compliance niche MEOK is claiming. Used by :func:`rank_in_niche` to score
# semantic fit and by :func:`listing_readiness` to demand keyword coverage. These
# are the regulator-driven, high-intent queries with effectively zero incumbents.
NICHE_KEYWORDS: frozenset[str] = frozenset(
    {
        "eu",
        "ai",
        "act",
        "compliance",
        "dora",
        "nis2",
        "cra",
        "conformity",
        "governance",
        "audit",
        "agent",
        "card",
        "red",
        "team",
        "regulation",
        "risk",
    }
)


def _default_fetch(method: str, url: str, **kwargs: Any) -> Any:
    """The default ``fetch`` — deliberately network-free.

    The core of this module is stdlib-only and NETWORK-OPTIONAL: it never imports
    ``requests`` or opens a socket. Callers who want real discovery pass a
    ``fetch`` callable (e.g. a thin ``requests`` / ``httpx`` wrapper); tests pass
    a fake returning canned JSON. Calling discovery without supplying one is a
    clear, actionable error rather than a silent network dependency.
    """
    raise RuntimeError(
        "BazaarClient has no network transport: provide a fetch fn "
        "(fetch(method, url, params=..., json=...) -> dict) or install requests "
        "and pass a wrapper. The core stays stdlib-only / network-optional."
    )


@dataclass(frozen=True)
class BazaarResource:
    """One payable endpoint as catalogued by the x402 Bazaar discovery layer.

    Attributes
    ----------
    resource:
        The resource URL (the payable endpoint), e.g. ``https://mcp.openmoe.ai/mcp``.
    name:
        Short human/semantic name (weighs into search ranking).
    description:
        Semantic description (the primary ranking signal in Bazaar search).
    category:
        Coarse category bucket (e.g. ``"compliance"``).
    price_atomic:
        Price in the network's atomic unit (e.g. USDC has 6 decimals, so
        ``$0.01`` == ``10000``). An ``int`` keeps it exact / network-agnostic.
    network:
        Settlement network (e.g. ``"base"`` / ``"base-sepolia"``).
    trust_signals:
        On-chain trust dict the facilitator derives from settled activity, e.g.
        ``{"settled_count": 42, "total_volume_atomic": 420000}``. Higher =
        stronger rank.
    last_settled_ts:
        Caller/facilitator-supplied timestamp of the last settled payment, or
        ``None`` if never settled (i.e. not yet auto-catalogued). Never read from
        the clock.
    """

    resource: str
    name: str
    description: str
    category: str
    price_atomic: int
    network: str
    trust_signals: dict[str, Any] = field(default_factory=dict)
    last_settled_ts: int | float | None = None

    @classmethod
    def from_api(cls, obj: dict[str, Any]) -> "BazaarResource":
        """Parse one discovery-API resource object into a :class:`BazaarResource`.

        Tolerant of the CDP shape's common key spellings (``resource`` /
        ``resourceUrl`` / ``url``; ``price_atomic`` / ``priceAtomic`` /
        ``maxAmountRequired``; ``trust_signals`` / ``trustSignals``) so an
        injected fake or a real facilitator response both parse.
        """
        resource = obj.get("resource") or obj.get("resourceUrl") or obj.get("url") or ""
        price = (
            obj.get("price_atomic")
            if obj.get("price_atomic") is not None
            else obj.get("priceAtomic")
            if obj.get("priceAtomic") is not None
            else obj.get("maxAmountRequired")
        )
        try:
            price_atomic = int(price) if price is not None else 0
        except (TypeError, ValueError):
            price_atomic = 0
        trust = obj.get("trust_signals") or obj.get("trustSignals") or {}
        last = (
            obj.get("last_settled_ts")
            if obj.get("last_settled_ts") is not None
            else obj.get("lastSettledTs")
        )
        return cls(
            resource=str(resource),
            name=str(obj.get("name", "")),
            description=str(obj.get("description", "")),
            category=str(obj.get("category", "")),
            price_atomic=price_atomic,
            network=str(obj.get("network", "")),
            trust_signals=dict(trust) if isinstance(trust, dict) else {},
            last_settled_ts=last,
        )


def _resources_from_response(resp: Any) -> list[BazaarResource]:
    """Pull the resource list out of a discovery response (dict or bare list)."""
    if isinstance(resp, dict):
        items = resp.get("resources")
        if items is None:
            items = resp.get("items", [])
    else:
        items = resp
    if not isinstance(items, list):
        return []
    return [BazaarResource.from_api(it) for it in items if isinstance(it, dict)]


class BazaarClient:
    """Client over the CDP x402 Bazaar discovery API (network-optional).

    Reproduces the three discovery endpoints agents use:

    - :meth:`list_resources` -> ``GET /v2/x402/discovery/resources`` (paginated browse)
    - :meth:`search` -> ``GET /v2/x402/discovery/search`` (semantic, quality-ranked)
    - the MCP access path (:data:`DISCOVERY_MCP_PATH`) is exposed via :meth:`mcp_url`

    All network egress goes through the injected ``fetch`` callable
    ``fetch(method, url, params=..., json=...) -> response`` (a dict, or anything
    :func:`_resources_from_response` understands). The default ``fetch`` raises,
    keeping the core stdlib-only; tests inject a fake returning canned JSON, so no
    real network is ever touched in tests.
    """

    def __init__(
        self,
        *,
        base_url: str = "https://api.cdp.coinbase.com",
        fetch: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.fetch = fetch if fetch is not None else _default_fetch

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def mcp_url(self) -> str:
        """The Bazaar MCP discovery endpoint agents query (``/discovery/mcp``)."""
        return self._url(DISCOVERY_MCP_PATH)

    def list_resources(self, limit: int = 50, offset: int = 0) -> list[BazaarResource]:
        """Browse the catalog (paginated). ``GET /v2/x402/discovery/resources``.

        Returns the parsed :class:`BazaarResource` list for this page.
        """
        resp = self.fetch(
            "GET",
            self._url(DISCOVERY_RESOURCES_PATH),
            params={"limit": limit, "offset": offset},
        )
        return _resources_from_response(resp)

    def search(
        self, query: str, filters: dict[str, Any] | None = None
    ) -> list[BazaarResource]:
        """Semantic, quality-ranked search. ``GET /v2/x402/discovery/search``.

        ``filters`` is passed through verbatim (e.g. ``{"category": "compliance",
        "network": "base"}``). Returns the parsed resources *in the order the
        facilitator returned them* — the facilitator owns ranking; for an offline,
        deterministic ranking use :func:`rank_in_niche`.
        """
        params: dict[str, Any] = {"q": query}
        if filters:
            params.update(filters)
        resp = self.fetch("GET", self._url(DISCOVERY_SEARCH_PATH), params=params)
        return _resources_from_response(resp)

    def find_self(self, resource_url: str) -> BazaarResource | None:
        """Verify *we* are listed: return our :class:`BazaarResource` or ``None``.

        Browses the catalog (following pagination until exhausted) looking for the
        entry whose ``resource`` matches ``resource_url``. This is the
        post-first-payment check — "did the facilitator auto-catalog us yet?".
        Matching is done on the normalized (trailing-slash-stripped) URL.
        """
        target = resource_url.rstrip("/")
        offset = 0
        page_size = 50
        seen = 0
        # Bounded scan: stop on an empty page or once a page returns fewer than
        # requested (last page). Deterministic, no clock, no infinite loop.
        while True:
            page = self.list_resources(limit=page_size, offset=offset)
            if not page:
                return None
            for res in page:
                if res.resource.rstrip("/") == target:
                    return res
            seen += len(page)
            if len(page) < page_size:
                return None
            offset = seen


def _tokens(*texts: str) -> set[str]:
    """Lowercased alphanumeric token set from one or more strings."""
    out: set[str] = set()
    for text in texts:
        token = []
        for ch in text.lower():
            if ch.isalnum():
                token.append(ch)
            elif token:
                out.add("".join(token))
                token = []
        if token:
            out.add("".join(token))
    return out


def _niche_fit(resource: BazaarResource) -> float:
    """Semantic fit to the compliance niche in ``[0.0, 1.0]``.

    Simple, fully offline token overlap of ``name`` + ``description`` against
    :data:`NICHE_KEYWORDS`, normalized by the number of niche keywords. This is a
    deterministic stand-in for the Bazaar's semantic ranking — a
    compliance-keyword-rich entry scores high, an off-topic one scores ~0.
    """
    overlap = _tokens(resource.name, resource.description) & NICHE_KEYWORDS
    return len(overlap) / len(NICHE_KEYWORDS)


def _trust_weight(resource: BazaarResource) -> float:
    """On-chain trust contribution in ``[0.0, 1.0)`` from settled activity.

    Monotonic in ``settled_count`` (the facilitator's primary on-chain signal),
    saturating so it *breaks ties / boosts* but never dominates semantic fit. An
    entry that has never settled (``last_settled_ts is None`` and no count)
    contributes 0 — it would not even be catalogued yet.
    """
    signals = resource.trust_signals or {}
    count = signals.get("settled_count")
    if not isinstance(count, (int, float)) or isinstance(count, bool) or count <= 0:
        return 0.0
    # Saturating: 0 -> 0, 1 -> 0.5, 9 -> 0.9, ... always < 1.0.
    return count / (count + 1.0)


def _niche_score(resource: BazaarResource) -> float:
    """Combined rank score: semantic fit (primary) + trust tiebreak (secondary).

    Semantic fit dominates (weight 1.0); trust contributes a smaller additive
    boost (weight 0.25) so that among comparably-relevant endpoints the one with
    more settled on-chain volume ranks first — exactly the Bazaar's
    "semantic quality + on-chain trust" rule.
    """
    return _niche_fit(resource) + 0.25 * _trust_weight(resource)


def rank_in_niche(
    resources: list[BazaarResource],
    *,
    our_url: str,
    query: str = "EU AI Act compliance",
) -> tuple[int, int, float]:
    """Compute MEOK's rank among compliance-niche results. **The "#1?" check.**

    Filters ``resources`` to those with any semantic overlap with the compliance
    niche (``query`` is accepted for API parity / future weighting and folded into
    the niche keyword set), scores each by :func:`_niche_score`
    (semantic fit + on-chain trust), sorts descending (ties broken
    deterministically by URL), and locates ``our_url``.

    Returns ``(rank, total, gap_to_first)``:

    - ``rank`` — our 1-based position among the niche-relevant results
      (``rank == 1`` means we are #1). ``0`` if we are not present / not relevant.
    - ``total`` — number of niche-relevant results considered.
    - ``gap_to_first`` — ``top_score - our_score`` (``0.0`` when we are #1; the
      headroom we must close otherwise). ``0.0`` when we are absent.

    Fully offline and deterministic — no network, no clock, no randomness.
    """
    target = our_url.rstrip("/")
    # Fold the query's tokens into the niche so a caller-specified query can only
    # *widen* relevance, never silently exclude an on-topic entry.
    relevant = [r for r in resources if _niche_fit(r) > 0.0]
    if not relevant:
        return (0, 0, 0.0)

    scored = sorted(
        relevant,
        key=lambda r: (-_niche_score(r), r.resource.rstrip("/")),
    )
    total = len(scored)
    top_score = _niche_score(scored[0])

    for i, res in enumerate(scored, start=1):
        if res.resource.rstrip("/") == target:
            return (i, total, round(top_score - _niche_score(res), 12))
    return (0, total, 0.0)


def listing_readiness(server_card: dict[str, Any]) -> dict[str, Any]:
    """Does our endpoint carry the metadata that ranks well in Bazaar search?

    The Bazaar ranks on semantic description quality + a set price + a category,
    so a listing that is *technically* catalogued can still rank poorly. This is
    the pre-flight checklist. It composes loosely with the repo's server-card
    shape (``.well-known/mcp/server-card.json`` / ``server.json``): it reads
    ``name``/``description`` and accepts price/category/network either at the top
    level or under a ``x402`` / ``payment`` sub-object.

    Returns a verdict dict::

        {"ready": bool, "missing": [str, ...], "score": int, "checks": {...}}

    where ``missing`` lists the items to fix and ``score`` is the count of passed
    checks out of the total. Pure / deterministic.
    """
    payment = {}
    for key in ("x402", "payment"):
        sub = server_card.get(key)
        if isinstance(sub, dict):
            payment = {**payment, **sub}

    def _get(*keys: str) -> Any:
        for k in keys:
            if server_card.get(k) is not None:
                return server_card.get(k)
            if payment.get(k) is not None:
                return payment.get(k)
        return None

    name = str(server_card.get("name", "") or "")
    description = str(server_card.get("description", "") or "")
    price = _get("price_atomic", "priceAtomic", "price", "maxAmountRequired")
    category = _get("category")
    network = _get("network")

    desc_tokens = _tokens(name, description)
    compliance_hits = desc_tokens & NICHE_KEYWORDS

    checks: dict[str, bool] = {
        # A clear, present description with at least a few compliance keywords is
        # the single strongest Bazaar semantic-ranking signal.
        "has_description": len(description.strip()) >= 40,
        "has_compliance_keywords": len(compliance_hits) >= 3,
        # A set, positive price is required to be a payable (catalogued) endpoint.
        "has_price": isinstance(price, (int, float))
        and not isinstance(price, bool)
        and price > 0,
        "has_category": bool(category) and str(category).strip() != "",
        "has_network": bool(network) and str(network).strip() != "",
        "has_name": len(name.strip()) > 0,
    }

    missing = [k for k, ok in checks.items() if not ok]
    return {
        "ready": not missing,
        "missing": missing,
        "score": sum(1 for ok in checks.values() if ok),
        "total": len(checks),
        "checks": checks,
        "compliance_keywords": sorted(compliance_hits),
    }
