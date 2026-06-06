"""Expert registry integrity + MCP->Expert registration protocol. Hermetic."""

import pytest

from openmoe_bft import (
    EXPERTS,
    ExpertDomain,
    by_id,
    by_domain,
    by_regulation,
    expert_ids,
    register_expert,
)


def test_exactly_fourteen_experts():
    assert len(EXPERTS) == 14


def test_ids_are_one_through_fourteen_unique():
    ids = expert_ids()
    assert ids == list(range(1, 15))
    assert len(set(ids)) == 14


def test_a2a_fields_unique():
    fields = [e.a2a_field for e in EXPERTS]
    assert len(set(fields)) == 14, "a2a_field must be unique per expert"


def test_names_unique():
    names = [e.name for e in EXPERTS]
    assert len(set(names)) == 14


def test_lookups():
    assert by_id(1).name == "EU AI Act Compliance"
    assert by_id(14).name == "Web Crawler / Extractor"
    assert by_id(99) is None
    assert by_id(0) is None


def test_by_domain_and_regulation():
    sec = by_domain(ExpertDomain.SECURITY)
    assert {e.expert_id for e in sec} == {6, 9, 10, 11, 12}
    eu = by_regulation("eu_ai_act")
    assert [e.expert_id for e in eu] == [1]
    dora = by_regulation("dora")
    assert [e.expert_id for e in dora] == [3]


def _valid_card(expert_id=1):
    e = by_id(expert_id)
    # build the nested dict carrying evidence at the dotted a2a_field path
    parts = e.a2a_field.split(".")
    node = "evidence-present"
    for p in reversed(parts[1:]):
        node = {p: node}
    card = {
        "expert_id": expert_id,
        "name": e.name,
        "tools": [{"name": "scan_card"}, {"name": "report"}],
        parts[0]: node,
    }
    return card


# ── Registration: accept ───────────────────────────────────────

def test_register_valid_candidate():
    res = register_expert(_valid_card(1))
    assert res.accepted
    assert res.expert_id == 1
    assert res.reasons == []
    assert "scan_card" in res.matched_tools


def test_register_valid_candidate_other_expert():
    res = register_expert(_valid_card(5))
    assert res.accepted
    assert res.expert_id == 5


# ── Registration: reject ───────────────────────────────────────

def test_reject_non_dict():
    res = register_expert("not a dict")
    assert not res.accepted
    assert res.expert_id is None


def test_reject_unknown_expert_id():
    card = _valid_card(1)
    card["expert_id"] = 99
    res = register_expert(card)
    assert not res.accepted
    assert any("expert_id" in r for r in res.reasons)


def test_reject_name_mismatch():
    card = _valid_card(1)
    card["name"] = "Totally Wrong Name"
    res = register_expert(card)
    assert not res.accepted
    assert any("name" in r for r in res.reasons)


def test_reject_no_tools():
    card = _valid_card(1)
    card["tools"] = []
    res = register_expert(card)
    assert not res.accepted
    assert any("tools" in r for r in res.reasons)


def test_reject_tools_without_names():
    card = _valid_card(1)
    card["tools"] = [{"description": "no name"}]
    res = register_expert(card)
    assert not res.accepted
    assert any("name" in r for r in res.reasons)


def test_reject_missing_evidence():
    e = by_id(2)
    card = {
        "expert_id": 2,
        "name": e.name,
        "tools": [{"name": "score"}],
        # no metadata.nistRmfScore evidence
    }
    res = register_expert(card)
    assert not res.accepted
    assert any("a2a_field" in r or "evidence" in r for r in res.reasons)


def test_reject_empty_evidence_value():
    e = by_id(2)
    card = {
        "expert_id": 2,
        "name": e.name,
        "tools": [{"name": "score"}],
        "metadata": {"nistRmfScore": ""},  # empty -> no evidence
    }
    res = register_expert(card)
    assert not res.accepted


def test_rejection_accumulates_multiple_reasons():
    res = register_expert({"expert_id": 99})
    assert not res.accepted
    assert len(res.reasons) >= 2  # unknown id + missing tools at least
