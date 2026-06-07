"""Agent FICO + outcome-based billing (Layer 10/11).

Hermetic: stdlib only, no clock, no network, no randomness. Timestamps are
passed explicitly; trust signals are passed in or read from a caller-built
AuditChain.
"""

import pytest

from openmoe_bft.covenants import (
    Action,
    Covenant,
    CovenantRegistry,
    NO_ACTION_BASELINE,
)
from openmoe_bft.receipts import AuditChain
from openmoe_bft.reputation import (
    AgentScore,
    FICO_MAX,
    FICO_MIN,
    OutcomeBilling,
    OutcomeSettlement,
    agent_fico,
    web_of_trust_score,
)


# ── agent_fico ─────────────────────────────────────────────────────


def test_fico_bounds_and_defaults():
    score = agent_fico("agent-1", computed_ts=1000)
    assert isinstance(score, AgentScore)
    assert FICO_MIN <= score.score <= FICO_MAX
    # all-default signals: covenant=0.5, payment=0, redteam=0.5
    assert score.factors["covenant_trust"] == NO_ACTION_BASELINE
    assert score.factors["payment_history"] == 0.0
    assert score.factors["redteam"] == 0.5


def test_fico_high_signals_high_score():
    high = agent_fico(
        "good",
        computed_ts=1000,
        covenant_trust=1.0,
        payment_signal=1.0,
        redteam_risk=1.0,  # higher risk_score == better defended
    )
    assert high.score == FICO_MAX


def test_fico_low_signals_low_score():
    low = agent_fico(
        "bad",
        computed_ts=1000,
        covenant_trust=0.0,
        payment_signal=0.0,
        redteam_risk=0.0,
    )
    assert low.score == FICO_MIN


def test_fico_high_beats_low():
    high = agent_fico(
        "good", computed_ts=1000, covenant_trust=0.9, payment_signal=0.8, redteam_risk=0.9
    )
    low = agent_fico(
        "bad", computed_ts=1000, covenant_trust=0.1, payment_signal=0.1, redteam_risk=0.2
    )
    assert high.score > low.score


def test_fico_deterministic():
    a = agent_fico("a", computed_ts=1000, covenant_trust=0.7, payment_signal=0.6, redteam_risk=0.8)
    b = agent_fico("a", computed_ts=1000, covenant_trust=0.7, payment_signal=0.6, redteam_risk=0.8)
    assert a == b


def test_fico_composes_real_covenant_trust():
    reg = CovenantRegistry()
    reg.inscribe(
        Covenant.inscribe(
            agent_id="payee", allowed_actions={"audit"}, timestamp=1000
        )
    )
    # one clean action -> covenant trust_score == 1.0
    reg.record(Action("a1", "payee", "audit", {}, timestamp=1001))
    ct = reg.trust_score("payee")
    assert ct == 1.0
    score = agent_fico("payee", computed_ts=1002, covenant_trust=ct, redteam_risk=0.5)
    # covenant alone (0.5 weight) at 1.0 plus default-less signals
    assert score.factors["covenant_trust"] == 1.0


def test_fico_reads_settled_payment_history_from_receipts():
    chain = AuditChain()
    # three settled-payment receipts crediting "payee"
    for i, ts in enumerate((1000, 1005, 1010)):
        chain.append(
            {"kind": "settled_payment", "agent_id": "payee", "amount_atomic": 10000},
            trace_id="pay",
            timestamp=ts,
        )
    # an unrelated receipt that must NOT count
    chain.append({"kind": "other", "agent_id": "payee"}, trace_id="x", timestamp=1011)

    deep = agent_fico(
        "payee",
        computed_ts=1010,
        covenant_trust=0.5,
        redteam_risk=0.5,
        payment_chain=chain,
        recency_window=100,
        depth_target=3,
    )
    none = agent_fico(
        "newbie",
        computed_ts=1010,
        covenant_trust=0.5,
        redteam_risk=0.5,
        payment_chain=chain,
        recency_window=100,
        depth_target=3,
    )
    assert deep.factors["payment_history"] > 0.0
    assert none.factors["payment_history"] == 0.0
    assert deep.score > none.score


def test_web_of_trust_score_wrapper():
    reg = CovenantRegistry()
    for aid in ("a", "voucher"):
        reg.inscribe(Covenant.inscribe(agent_id=aid, allowed_actions={"x"}, timestamp=1000))
        reg.record(Action(f"{aid}-1", aid, "x", {}, timestamp=1001))
    out = web_of_trust_score(reg, {"a": ["voucher"]})
    assert "a" in out
    assert 0.0 <= out["a"] <= 1.0


# ── OutcomeBilling ─────────────────────────────────────────────────


def _compliant(outcome):
    return outcome.get("compliant") is True


def test_outcome_billing_releases_on_passing_predicate():
    billing = OutcomeBilling(
        payer="agent-buyer",
        payee="mcp-meok",
        amount_atomic=10000,
        tool_call="evaluate_eu_ai_act",
    )
    settlement = billing.settle(
        {"compliant": True}, _compliant, timestamp=1000
    )
    assert isinstance(settlement, OutcomeSettlement)
    assert settlement.released is True
    assert settlement.outcome_ok is True
    assert settlement.amount_atomic == 10000
    # the settlement is a verifiable receipt
    assert billing.chain.verify().ok
    assert settlement.receipt.payload["direction"] == "release"
    # credited agent is the payee, so it counts toward payee's payment history
    assert settlement.receipt.payload["agent_id"] == "mcp-meok"
    assert settlement.receipt.payload["kind"] == "settled_payment"


def test_outcome_billing_refunds_on_failing_predicate():
    billing = OutcomeBilling(
        payer="agent-buyer",
        payee="mcp-meok",
        amount_atomic=10000,
        tool_call="evaluate_eu_ai_act",
    )
    settlement = billing.settle(
        {"compliant": False}, _compliant, timestamp=1000
    )
    assert settlement.released is False
    assert settlement.outcome_ok is False
    assert settlement.receipt.payload["direction"] == "refund"
    # refund credits the payer
    assert settlement.receipt.payload["agent_id"] == "agent-buyer"
    # still a verifiable receipt
    assert billing.chain.verify().ok


def test_outcome_billing_settlement_receipt_is_signed_and_verifiable():
    billing = OutcomeBilling(
        payer="buyer", payee="seller", amount_atomic=5000, tool_call="red_team_scan"
    )
    settlement = billing.settle(
        {"compliant": True}, _compliant, timestamp=1000, signer_key="secret"
    )
    assert settlement.receipt.signature is not None
    assert billing.chain.verify().ok
    assert billing.chain.verify_signatures({0: "secret"}).ok


def test_outcome_billing_settles_exactly_once():
    billing = OutcomeBilling(
        payer="buyer", payee="seller", amount_atomic=5000, tool_call="t"
    )
    billing.settle({"compliant": True}, _compliant, timestamp=1000)
    with pytest.raises(RuntimeError, match="already settled"):
        billing.settle({"compliant": True}, _compliant, timestamp=1001)


def test_released_outcome_feeds_payee_fico():
    # end-to-end composition: a released outcome-billing settlement is on-chain
    # payment history that lifts the payee's Agent FICO.
    billing = OutcomeBilling(
        payer="buyer", payee="mcp-meok", amount_atomic=10000, tool_call="t"
    )
    billing.settle({"compliant": True}, _compliant, timestamp=1000)
    score = agent_fico(
        "mcp-meok",
        computed_ts=1000,
        covenant_trust=0.5,
        redteam_risk=0.5,
        payment_chain=billing.chain,
        recency_window=100,
        depth_target=1,
    )
    assert score.factors["payment_history"] > 0.0
