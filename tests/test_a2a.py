"""A2A compliance-validation layer — Layer 11 meets Layer 8. Hermetic."""

import pytest

from openmoe_bft.a2a import (
    AgentCard,
    TaskEnvelope,
    A2AComplianceVerdict,
    extract_evidence,
    validate_card,
    validate_task,
    seal_verdict,
)
from openmoe_bft.eu_ai_act import CHECKS
from openmoe_bft.experts import EXPERTS
from openmoe_bft.receipts import AuditChain


# ── Fixtures ────────────────────────────────────────────────────


def _all_expert_fields() -> dict[str, object]:
    """metadata satisfying all 14 experts' a2a_field (bare key -> truthy)."""
    md = {}
    for e in EXPERTS:
        md[e.a2a_field.split(".", 1)[-1]] = {"present": True}
    return md


def _all_eu_fields() -> dict[str, object]:
    """metadata satisfying every EU AI Act check (bare key -> truthy)."""
    md = {}
    for c in CHECKS:
        md[c.evidence_field.split(".", 1)[-1]] = True
    return md


def _full_card() -> AgentCard:
    """A card whose metadata satisfies all experts AND all EU AI Act checks."""
    md = {}
    md.update(_all_expert_fields())
    md.update(_all_eu_fields())
    return AgentCard(name="fully-compliant-agent", version="1.0", metadata=md)


def _empty_card() -> AgentCard:
    return AgentCard(name="bare-agent", metadata={})


# ── extract_evidence ────────────────────────────────────────────


def test_extract_evidence_flattens_to_dotted_form():
    card = AgentCard(metadata={"riskAssessment": {"annexIII": "high"}})
    assert extract_evidence(card) == {"metadata.riskAssessment": True}


def test_extract_evidence_truthy_only():
    card = AgentCard(metadata={
        "riskAssessment": {"annexIII": "high"},  # truthy -> kept
        "humanOversight": True,                   # truthy -> kept
        "dataGovernance": "",                     # falsy -> dropped
        "biasExamination": {},                    # falsy -> dropped
        "eventLogging": 0,                        # falsy -> dropped
    })
    ev = extract_evidence(card)
    assert ev == {
        "metadata.riskAssessment": True,
        "metadata.humanOversight": True,
    }


def test_extract_evidence_accepts_raw_dict():
    ev = extract_evidence({"metadata": {"x402Receipt": "tok"}})
    assert ev == {"metadata.x402Receipt": True}


# ── validate_card: fully populated ──────────────────────────────


def test_validate_full_card_is_compliant():
    verdict = validate_card(_full_card())
    assert isinstance(verdict, A2AComplianceVerdict)
    assert verdict.compliant is True
    assert verdict.score == 1.0
    assert verdict.eu_ai_act_report.compliant is True
    assert verdict.eu_ai_act_report.blocking_failures == []
    # all 14 experts covered, none missing
    assert sorted(verdict.experts_covered) == list(range(1, 15))
    assert verdict.experts_missing == []
    assert verdict.advisory == []


# ── validate_card: empty ────────────────────────────────────────


def test_validate_empty_card_is_non_compliant():
    verdict = validate_card(_empty_card())
    assert verdict.compliant is False
    assert verdict.score == 0.0
    # every expert missing
    assert verdict.experts_missing == list(range(1, 15))
    assert verdict.experts_covered == []
    # EU AI Act blocking failures present
    assert verdict.eu_ai_act_report.blocking_failures
    # advisory tells you what to add (blockers + 14 experts)
    assert verdict.advisory
    assert len(verdict.advisory) >= 14


# ── validate_card: partial ──────────────────────────────────────


def test_validate_partial_card_splits_coverage_and_scores_between():
    # Cover experts 1, 5, 9 only; supply partial EU AI Act evidence.
    covered_experts = {1, 5, 9}
    md = {}
    for e in EXPERTS:
        if e.expert_id in covered_experts:
            md[e.a2a_field.split(".", 1)[-1]] = {"present": True}
    # add a couple of non-expert EU AI Act fields so the score moves but < 1.0
    md["humanOversight"] = True
    md["dataGovernance"] = True
    card = AgentCard(name="partial-agent", metadata=md)

    verdict = validate_card(card)
    assert sorted(verdict.experts_covered) == [1, 5, 9]
    assert verdict.experts_missing == [
        e.expert_id for e in EXPERTS if e.expert_id not in covered_experts
    ]
    # strictly between 0 and 1
    assert 0.0 < verdict.score < 1.0
    assert verdict.compliant is False
    assert verdict.advisory


# ── validate_task delegates to the card ─────────────────────────


def test_validate_task_delegates_to_card():
    card = _full_card()
    task = TaskEnvelope(task_id="t1", agent=card, input={"q": "hi"}, metadata={})
    card_verdict = validate_card(card)
    task_verdict = validate_task(task)
    assert task_verdict.compliant == card_verdict.compliant is True
    assert task_verdict.score == card_verdict.score == 1.0
    assert sorted(task_verdict.experts_covered) == list(range(1, 15))


def test_validate_task_accepts_raw_dict():
    card = _full_card()
    raw = {
        "task_id": "t2",
        "agent": {
            "name": card.name,
            "metadata": card.metadata,
        },
        "input": {},
        "metadata": {},
    }
    verdict = validate_task(raw)
    assert verdict.compliant is True
    assert verdict.score == 1.0


# ── seal_verdict -> tamper-evident receipt ──────────────────────


def test_seal_verdict_appends_receipt_and_chain_verifies():
    chain = AuditChain()
    verdict = validate_card(_full_card())
    receipt = seal_verdict(verdict, chain, timestamp=1000)
    assert receipt in chain.receipts
    assert chain.receipts == [receipt]
    assert "a2a_compliance_verdict" in receipt.payload
    assert chain.verify().ok


def test_seal_verdict_chains_multiple_and_detects_tamper():
    chain = AuditChain()
    seal_verdict(validate_card(_empty_card()), chain, timestamp=1000)
    r1 = seal_verdict(validate_card(_full_card()), chain, timestamp=1001)
    assert chain.verify().ok
    # mutate a sealed payload after the fact -> chain breaks
    r1.payload["a2a_compliance_verdict"]["compliant"] = False
    assert not chain.verify().ok


def test_seal_verdict_signed_receipt_verifies():
    chain = AuditChain()
    verdict = validate_card(_full_card())
    seal_verdict(verdict, chain, timestamp=1000, signer_key="secret")
    assert chain.verify().ok
    assert chain.verify_signatures({0: "secret"}).ok
