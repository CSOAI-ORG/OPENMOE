"""Hierarchical agent-memory pyramid (Layer 4 / SOV3). Hermetic.

No time/datetime/random — every record carries a caller-supplied timestamp and
ids are content-derived, so the whole suite is deterministic and idempotent.
The extractor/clusterer/aggregator are tiny deterministic heuristics standing
in for an LLM behind the same plug-in interface.
"""

import openmoe_bft.memory as mem
from openmoe_bft.memory import (
    MemoryPyramid,
    MemoryEvent,
    Atom,
    Scenario,
    PersonaTrait,
    DreamStats,
    overlap_score,
    event_id,
    L0, L1, L2, L3,
)


# ── Deterministic plug-in heuristics ───────────────────────────

# Tiny keyword -> (predicate text, salience) extraction rules.
_RULES = [
    ("coffee", "user likes coffee", 0.9),
    ("tea", "user likes tea", 0.7),
    ("python", "user codes in python", 0.8),
    ("deadline", "project has a deadline", 0.95),
]


def extractor(events):
    """Heuristic L0->L1: emit one atom per matched keyword rule per event."""
    atoms = []
    for e in events:
        low = e.content.lower()
        for kw, text, sal in _RULES:
            if kw in low:
                atoms.append(
                    Atom(
                        id=f"atom-{kw}",                 # stable id -> dedup across events
                        source_event_ids=[e.id],
                        text=text,
                        salience=sal,
                        timestamp=e.timestamp,
                    )
                )
    return atoms


def clusterer(atoms):
    """Heuristic L1->L2: group atoms by topic (preference vs project)."""
    prefs = [a for a in atoms if a.text.startswith("user likes")]
    proj = [a for a in atoms if "project" in a.text or "codes" in a.text]
    scenarios = []
    if prefs:
        scenarios.append(
            Scenario(
                id="scn-preferences",
                atom_ids=[a.id for a in prefs],
                summary="user beverage preferences " + " ".join(a.text for a in prefs),
                salience=max(a.salience for a in prefs),
                timestamp=max(a.timestamp for a in prefs),
            )
        )
    if proj:
        scenarios.append(
            Scenario(
                id="scn-project",
                atom_ids=[a.id for a in proj],
                summary="work context " + " ".join(a.text for a in proj),
                salience=max(a.salience for a in proj),
                timestamp=max(a.timestamp for a in proj),
            )
        )
    return scenarios


def aggregator(scenarios):
    """Heuristic L2->L3: one durable trait per scenario."""
    traits = []
    for s in scenarios:
        if s.id == "scn-preferences":
            traits.append(PersonaTrait(
                key="beverage_preference", value="coffee",
                confidence=s.salience, evidence_scenario_ids=[s.id]))
        elif s.id == "scn-project":
            traits.append(PersonaTrait(
                key="primary_language", value="python",
                confidence=s.salience, evidence_scenario_ids=[s.id]))
    return traits


def _seed(p):
    """Observe a deterministic, redundant conversation.

    Heavily redundant on purpose: the same few facts (coffee / python /
    deadline) are repeated across many verbose raw events, so distilling to a
    handful of stable atoms and compacting L0 yields a real token saving — the
    "~61% reduction" claim measured honestly.
    """
    p.observe_message(1000.0, "user",
                      "I really love coffee in the morning, coffee is the best")
    p.observe_message(1001.0, "assistant",
                      "Noted, coffee it is, I will remember you love coffee")
    p.observe_message(1002.0, "user",
                      "Also I write everything in python these days, python python")
    p.observe_message(1003.0, "user",
                      "Remember the project has a hard deadline on friday, deadline!")
    p.observe_message(1004.0, "user",
                      "Did I mention I love coffee? more coffee please, so much coffee")
    p.observe_message(1005.0, "assistant",
                      "Understood: coffee, python, and that project deadline are noted")
    p.observe_message(1006.0, "user",
                      "Seriously the deadline for the project cannot slip, coffee helps")


# ── helpers ────────────────────────────────────────────────────

def test_overlap_score_is_lexical_and_deterministic():
    assert overlap_score("coffee tea", "I like coffee") == 0.5
    assert overlap_score("", "anything") == 0.0
    assert overlap_score("coffee", "no match here") == 0.0


def test_event_id_is_deterministic():
    a = event_id(1000.0, "user", "hello")
    b = event_id(1000.0, "user", "hello")
    c = event_id(1000.0, "user", "world")
    assert a == b
    assert a != c


# ── L0 observe ─────────────────────────────────────────────────

def test_observe_stores_l0():
    p = MemoryPyramid()
    ev = p.observe_message(1000.0, "user", "hello world")
    assert isinstance(ev, MemoryEvent)
    assert len(p.events) == 1
    assert p.events[0].content == "hello world"
    assert p.events[0].timestamp == 1000.0


def test_observe_dedupes_identical_events():
    p = MemoryPyramid()
    p.observe_message(1000.0, "user", "hello")
    p.observe_message(1000.0, "user", "hello")          # same id
    assert len(p.events) == 1


# ── L0 -> L1 distill ───────────────────────────────────────────

def test_distill_promotes_events_to_atoms():
    p = MemoryPyramid()
    _seed(p)
    added = p.distill(extractor)
    texts = {a.text for a in p.atoms}
    assert "user likes coffee" in texts
    assert "user codes in python" in texts
    assert "project has a deadline" in texts
    # coffee appears in two events but the atom id is stable -> deduped
    assert len([a for a in p.atoms if a.id == "atom-coffee"]) == 1
    assert added


def test_distill_is_idempotent_with_no_new_events():
    p = MemoryPyramid()
    _seed(p)
    p.distill(extractor)
    n = len(p.atoms)
    again = p.distill(extractor)
    assert again == []
    assert len(p.atoms) == n


# ── L1 -> L2 consolidate ───────────────────────────────────────

def test_consolidate_groups_atoms_into_scenarios():
    p = MemoryPyramid()
    _seed(p)
    p.distill(extractor)
    scenarios = p.consolidate(clusterer)
    ids = {s.id for s in scenarios}
    assert ids == {"scn-preferences", "scn-project"}
    prefs = next(s for s in p.scenarios if s.id == "scn-preferences")
    assert "atom-coffee" in prefs.atom_ids


# ── L2 -> L3 form personas ─────────────────────────────────────

def test_form_personas_builds_traits():
    p = MemoryPyramid()
    _seed(p)
    p.distill(extractor)
    p.consolidate(clusterer)
    traits = p.form_personas(aggregator)
    keys = {t.key for t in traits}
    assert keys == {"beverage_preference", "primary_language"}
    bev = next(t for t in p.traits if t.key == "beverage_preference")
    assert bev.value == "coffee"
    assert 0.0 <= bev.confidence <= 1.0


# ── recall ─────────────────────────────────────────────────────

def test_recall_returns_most_relevant_topk():
    p = MemoryPyramid()
    _seed(p)
    p.dream(extractor, clusterer, aggregator)
    hits = p.recall("coffee", k=3)
    assert hits, "expected at least one hit"
    assert hits[0].score > 0.0
    # everything returned must actually mention the query token
    assert all("coffee" in h.text.lower() for h in hits)
    assert len(hits) <= 3


def test_recall_respects_tier_filter():
    p = MemoryPyramid()
    _seed(p)
    p.dream(extractor, clusterer, aggregator)
    only_traits = p.recall("coffee", tiers=[L3], k=10)
    assert only_traits
    assert all(h.tier == L3 for h in only_traits)
    only_atoms = p.recall("coffee", tiers=[L1], k=10)
    assert all(h.tier == L1 for h in only_atoms)


def test_recall_excludes_zero_overlap():
    p = MemoryPyramid()
    _seed(p)
    p.distill(extractor)
    assert p.recall("xyzzy-nonexistent-token") == []


def test_recall_ranks_by_score_then_salience():
    p = MemoryPyramid()
    # two atoms tie on score for query "fact"; higher salience must win.
    p._atoms = [
        Atom("a-low", [], "fact one", 0.2, 1.0),
        Atom("a-high", [], "fact two", 0.9, 1.0),
    ]
    hits = p.recall("fact", tiers=[L1], k=2)
    assert hits[0].id == "a-high"
    assert hits[1].id == "a-low"


# ── dream() ────────────────────────────────────────────────────

def test_dream_runs_full_pass_and_compacts():
    p = MemoryPyramid()
    _seed(p)
    raw_events = len(p.events)
    stats = p.dream(extractor, clusterer, aggregator)
    assert isinstance(stats, DreamStats)
    assert stats.atoms_added > 0
    assert stats.scenarios_added == 2
    assert stats.traits_added == 2
    # every distilled raw event is pruned from L0
    assert stats.events_compacted == raw_events
    assert p.events == []
    # but the distilled knowledge survives up the pyramid
    assert p.atoms and p.scenarios and p.traits


def test_dream_is_idempotent():
    p = MemoryPyramid()
    _seed(p)
    p.dream(extractor, clusterer, aggregator)
    second = p.dream(extractor, clusterer, aggregator)
    assert second.atoms_added == 0
    assert second.scenarios_added == 0
    assert second.traits_added == 0
    assert second.events_compacted == 0


def test_dream_promotes_new_input_on_later_pass():
    p = MemoryPyramid()
    _seed(p)
    p.dream(extractor, clusterer, aggregator)
    # new conversation arrives after the first dream
    p.observe_message(2000.0, "user", "switching to tea now")
    stats = p.dream(extractor, clusterer, aggregator)
    assert stats.atoms_added == 1                 # the new "tea" atom
    assert any(a.text == "user likes tea" for a in p.atoms)
    assert stats.events_compacted == 1


# ── stats() token savings ──────────────────────────────────────

def test_stats_token_savings_positive_after_dream():
    p = MemoryPyramid()
    _seed(p)
    before = p.stats()
    assert before["token_savings_ratio"] == 0.0   # nothing distilled/compacted yet
    p.dream(extractor, clusterer, aggregator)
    after = p.stats()
    assert after["l0_events"] == 0
    assert after["l1_atoms"] > 0
    assert after["token_savings_ratio"] > 0.0


def test_stats_token_savings_is_computed_not_hardcoded():
    p = MemoryPyramid()
    _seed(p)
    p.dream(extractor, clusterer, aggregator)
    s = p.stats()
    raw = s["raw_chars_ever"]
    retained = s["retained_chars"]
    assert raw > 0
    expected = (raw - retained) / raw
    assert abs(s["token_savings_ratio"] - expected) < 1e-12
    assert s["token_savings_ratio"] != 0.61       # not the spec's headline number


def test_no_wallclock_or_random_imports():
    src = open(mem.__file__).read()
    assert "import random" not in src
    assert "import time" not in src
    assert "import datetime" not in src
    assert "from datetime" not in src
