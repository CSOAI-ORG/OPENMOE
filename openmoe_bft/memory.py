"""Hierarchical agent memory — the L0->L3 pyramid (OpenMoE-BFT Empire, Layer 4).

Layer 4 ("Memory & Learning" / SOV3) of the OpenMoE-BFT Empire. Cleanroom
reimplementation of the *published architecture* of Tencent Agent Memory
(github.com/TencentCloud/TencentDB-Agent-Memory, MIT — permissive). No upstream
code was fetched or copied; only the four-level pyramid + dream-consolidation
*design* is reproduced here in pure stdlib Python with zero hard dependencies.

The pyramid
-----------
Memory is organised as a four-tier pyramid, each tier distilled from the one
below it (raw conversation at the base, durable persona at the apex)::

    L3  PERSONA    durable traits / preferences across episodes  (PersonaTrait)
    L2  SCENARIO   clusters of atoms into a situation / episode   (Scenario)
    L1  ATOM       atomic facts distilled from raw events         (Atom)
    L0  RAW        append-only raw conversation events            (MemoryEvent)

Promotion between tiers is driven by *caller-supplied callables* (an extractor,
a clusterer, an aggregator) so an LLM or a heuristic plugs in behind the same
interface — this module never calls a model and never hits the network. The
test suite supplies tiny deterministic heuristics.

How it feeds the Empire
-----------------------
The pyramid is the durable memory the MoE council consults: atoms, scenarios
and persona traits become the context the 14 OpenScore safety experts read
before they vote. It pairs with :mod:`openmoe_bft.receipts` — each
consolidation pass can be sealed into the hash-chained audit trail — and with
:mod:`openmoe_bft.bft`: a reached consensus decision is exactly the kind of
high-salience fact that should be observed as an L0 event and distilled into a
durable atom.

Hermeticity
-----------
This module NEVER calls ``time``/``datetime``/``random``. Every record carries
a caller-supplied ``timestamp``; ids are derived deterministically from
content. Identical inputs in the same order always produce identical output, so
``dream()`` is idempotent and the whole thing is trivially testable.

The stdlib recall baseline
--------------------------
:meth:`MemoryPyramid.recall` scores relevance by **lexical token overlap**
between the query and each item's text (ties broken by salience, then id). This
is deliberately the dumb-but-honest stdlib baseline — no embeddings, no
network. A vector/embedding backend plugs in via the very same ``recall``
interface (swap the scorer) without changing callers.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Iterable


# ── Tier records ───────────────────────────────────────────────

@dataclass
class MemoryEvent:
    """L0 RAW — one append-only raw conversation event.

    ``id`` is content-derived (deterministic); ``timestamp`` is caller-supplied.
    """

    id: str
    timestamp: float
    role: str                                   # e.g. "user" | "assistant" | "system"
    content: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Atom:
    """L1 ATOM — an atomic fact distilled from one or more raw events."""

    id: str
    source_event_ids: list[str]
    text: str                                   # the predicate / fact text
    salience: float                             # 0.0 - 1.0
    timestamp: float                            # caller-supplied (usually source event ts)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Scenario:
    """L2 SCENARIO — a cluster of related atoms forming a situation / episode."""

    id: str
    atom_ids: list[str]
    summary: str
    salience: float                             # 0.0 - 1.0
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PersonaTrait:
    """L3 PERSONA — a durable trait / preference aggregated across scenarios."""

    key: str
    value: Any
    confidence: float                           # 0.0 - 1.0
    evidence_scenario_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Recall result ──────────────────────────────────────────────

@dataclass
class RecallHit:
    """One retrieved item with its provenance and relevance score."""

    tier: str                                   # "L0" | "L1" | "L2" | "L3"
    id: str
    text: str
    score: float                                # lexical-overlap relevance
    salience: float
    item: Any                                   # the underlying record


@dataclass
class DreamStats:
    """Outcome of a :meth:`MemoryPyramid.dream` consolidation pass."""

    events_compacted: int
    atoms_added: int
    scenarios_added: int
    traits_added: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Tier name constants (recall filter values).
L0, L1, L2, L3 = "L0", "L1", "L2", "L3"
ALL_TIERS = (L0, L1, L2, L3)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> set[str]:
    """Lowercase word tokens of ``text`` (stdlib lexical baseline)."""
    return set(_TOKEN_RE.findall(text.lower()))


def overlap_score(query: str, text: str) -> float:
    """Deterministic relevance: |query_tokens ∩ text_tokens| / |query_tokens|.

    Pure lexical token overlap — the documented stdlib baseline. Returns 0.0
    for an empty query. A vector backend swaps this scorer in place.
    """
    q = tokenize(query)
    if not q:
        return 0.0
    return len(q & tokenize(text)) / len(q)


def _digest(prefix: str, *parts: str) -> str:
    """Deterministic short content id: ``prefix-<sha256[:12]>``."""
    h = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{h[:12]}"


def event_id(timestamp: float, role: str, content: str) -> str:
    """Deterministic id for a raw event from its content + timestamp + role."""
    return _digest("ev", repr(timestamp), role, content)


# Plug-in callable signatures (documented for callers/LLM backends).
Extractor = Callable[[list[MemoryEvent]], list[Atom]]
Clusterer = Callable[[list[Atom]], list[Scenario]]
Aggregator = Callable[[list[Scenario]], list[PersonaTrait]]


class MemoryPyramid:
    """The four-tier hierarchical memory store with dream consolidation.

    Holds L0 raw events, L1 atoms, L2 scenarios and L3 persona traits. Promotion
    between tiers runs caller-supplied callables (so an LLM or a heuristic plugs
    in). Distilled raw events are tracked so :meth:`dream` only ever promotes
    *new* material — making the overnight-learning loop idempotent.
    """

    def __init__(self) -> None:
        self._events: list[MemoryEvent] = []
        self._atoms: list[Atom] = []
        self._scenarios: list[Scenario] = []
        self._traits: dict[str, PersonaTrait] = {}

        # Promotion bookkeeping — the idempotency mechanism. Each set holds the
        # ids already consumed by a promotion pass; a pass only ever feeds the
        # *un-promoted* remainder downstream, so re-running with no new input
        # promotes nothing.
        self._distilled_event_ids: set[str] = set()
        self._clustered_atom_ids: set[str] = set()
        self._aggregated_scenario_ids: set[str] = set()

        # Original raw char count, retained so the token-savings estimate can
        # measure compaction honestly even after L0 events are pruned.
        self._raw_chars_ever: int = 0

    # ── L0: observe ────────────────────────────────────────────

    def observe(self, event: MemoryEvent) -> MemoryEvent:
        """Store a raw L0 event (append-only). Duplicate ids are ignored."""
        if any(e.id == event.id for e in self._events):
            return event
        self._events.append(event)
        self._raw_chars_ever += len(event.content)
        return event

    def observe_message(
        self, timestamp: float, role: str, content: str,
        meta: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        """Convenience: build a :class:`MemoryEvent` (deterministic id) + store."""
        ev = MemoryEvent(
            id=event_id(timestamp, role, content),
            timestamp=timestamp,
            role=role,
            content=content,
            meta=dict(meta or {}),
        )
        return self.observe(ev)

    # ── L0 -> L1: distill ──────────────────────────────────────

    def distill(self, extractor: Extractor) -> list[Atom]:
        """Promote *un-distilled* L0 events to L1 atoms via ``extractor``.

        ``extractor`` is any ``list[MemoryEvent] -> list[Atom]`` callable (an
        LLM or a heuristic). Only events not yet distilled are passed in, so a
        second call with no new events produces nothing. New atom ids are
        de-duplicated against existing atoms.
        """
        pending = [e for e in self._events if e.id not in self._distilled_event_ids]
        if not pending:
            return []
        new_atoms = list(extractor(pending))
        existing = {a.id for a in self._atoms}
        added: list[Atom] = []
        for atom in new_atoms:
            if atom.id not in existing:
                self._atoms.append(atom)
                existing.add(atom.id)
                added.append(atom)
        for e in pending:
            self._distilled_event_ids.add(e.id)
        return added

    # ── L1 -> L2: consolidate ──────────────────────────────────

    def consolidate(self, clusterer: Clusterer) -> list[Scenario]:
        """Promote *un-clustered* L1 atoms to L2 scenarios via ``clusterer``."""
        pending = [a for a in self._atoms if a.id not in self._clustered_atom_ids]
        if not pending:
            return []
        new_scenarios = list(clusterer(pending))
        existing = {s.id for s in self._scenarios}
        added: list[Scenario] = []
        for sc in new_scenarios:
            if sc.id not in existing:
                self._scenarios.append(sc)
                existing.add(sc.id)
                added.append(sc)
        # Mark every atom the clusterer actually consumed as clustered.
        for sc in new_scenarios:
            for aid in sc.atom_ids:
                self._clustered_atom_ids.add(aid)
        # Any atom we offered but the clusterer ignored is still marked so it is
        # not re-offered forever (keeps the pass idempotent).
        for a in pending:
            self._clustered_atom_ids.add(a.id)
        return added

    # ── L2 -> L3: form personas ────────────────────────────────

    def form_personas(self, aggregator: Aggregator) -> list[PersonaTrait]:
        """Promote *un-aggregated* L2 scenarios to L3 traits via ``aggregator``.

        A returned trait whose ``key`` already exists overwrites the prior trait
        (later evidence wins) but only counts as "added" when the key is new, so
        re-aggregation with no new scenarios adds nothing.
        """
        pending = [
            s for s in self._scenarios
            if s.id not in self._aggregated_scenario_ids
        ]
        if not pending:
            return []
        new_traits = list(aggregator(pending))
        added: list[PersonaTrait] = []
        for trait in new_traits:
            is_new = trait.key not in self._traits
            self._traits[trait.key] = trait
            if is_new:
                added.append(trait)
        for s in pending:
            self._aggregated_scenario_ids.add(s.id)
        return added

    # ── Recall (cross-tier retrieval) ──────────────────────────

    def recall(
        self,
        query: str,
        tiers: Iterable[str] = ALL_TIERS,
        k: int = 5,
    ) -> list[RecallHit]:
        """Return the top-``k`` items most relevant to ``query`` across ``tiers``.

        Relevance is lexical token overlap (the stdlib baseline). Ranking key is
        ``(score, salience, id)`` descending — score first, salience breaks
        score ties, id breaks the rest for a fully deterministic order. Items
        with zero overlap are excluded.
        """
        want = set(tiers)
        hits: list[RecallHit] = []

        if L0 in want:
            for e in self._events:
                hits.append(RecallHit(L0, e.id, e.content,
                                      overlap_score(query, e.content), 0.0, e))
        if L1 in want:
            for a in self._atoms:
                hits.append(RecallHit(L1, a.id, a.text,
                                      overlap_score(query, a.text), a.salience, a))
        if L2 in want:
            for s in self._scenarios:
                hits.append(RecallHit(L2, s.id, s.summary,
                                      overlap_score(query, s.summary), s.salience, s))
        if L3 in want:
            for t in self._traits.values():
                text = f"{t.key} {t.value}"
                hits.append(RecallHit(L3, t.key, text,
                                      overlap_score(query, text), t.confidence, t))

        hits = [h for h in hits if h.score > 0.0]
        hits.sort(key=lambda h: (h.score, h.salience, h.id), reverse=True)
        return hits[:k]

    # ── Dream consolidation (the overnight-learning loop) ──────

    def dream(
        self,
        extractor: Extractor,
        clusterer: Clusterer,
        aggregator: Aggregator,
        compact: bool = True,
    ) -> DreamStats:
        """Run the full distill -> consolidate -> form_personas pass + prune L0.

        The Tencent design's headline move: an overnight pass that distils raw
        conversation up the pyramid and then *compresses away* the raw L0 events
        that have been fully distilled (their fact content now lives in atoms),
        slashing retained tokens. Returns per-tier add counts plus the number of
        raw events compacted.

        Idempotent: promotion bookkeeping means a second call with no new input
        distils/clusters/aggregates nothing and compacts nothing.
        """
        atoms_added = self.distill(extractor)
        scenarios_added = self.consolidate(clusterer)
        traits_added = self.form_personas(aggregator)

        compacted = 0
        if compact:
            kept: list[MemoryEvent] = []
            for e in self._events:
                if e.id in self._distilled_event_ids:
                    compacted += 1            # pruned: its facts live in atoms now
                else:
                    kept.append(e)
            self._events = kept

        return DreamStats(
            events_compacted=compacted,
            atoms_added=len(atoms_added),
            scenarios_added=len(scenarios_added),
            traits_added=len(traits_added),
        )

    # ── Introspection ──────────────────────────────────────────

    @property
    def events(self) -> list[MemoryEvent]:
        return list(self._events)

    @property
    def atoms(self) -> list[Atom]:
        return list(self._atoms)

    @property
    def scenarios(self) -> list[Scenario]:
        return list(self._scenarios)

    @property
    def traits(self) -> list[PersonaTrait]:
        return list(self._traits.values())

    def stats(self) -> dict[str, Any]:
        """Counts per tier + an honest token-savings estimate.

        ``raw_chars_ever`` is every raw char observed; ``retained_chars`` is
        what is still stored after compaction (surviving L0 events + atom +
        scenario + trait text). ``token_savings_ratio`` is the fraction of
        original raw chars no longer retained — computed from the actual data,
        never hardcoded. This backs the spec's "~61% token reduction" claim
        with a real number for the data at hand.
        """
        retained_l0 = sum(len(e.content) for e in self._events)
        retained_l1 = sum(len(a.text) for a in self._atoms)
        retained_l2 = sum(len(s.summary) for s in self._scenarios)
        retained_l3 = sum(len(f"{t.key} {t.value}") for t in self._traits.values())
        retained = retained_l0 + retained_l1 + retained_l2 + retained_l3

        raw = self._raw_chars_ever
        savings = (raw - retained) / raw if raw > 0 else 0.0
        return {
            "l0_events": len(self._events),
            "l1_atoms": len(self._atoms),
            "l2_scenarios": len(self._scenarios),
            "l3_traits": len(self._traits),
            "raw_chars_ever": raw,
            "retained_chars": retained,
            "token_savings_ratio": savings,
        }
