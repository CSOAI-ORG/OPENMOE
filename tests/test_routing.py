"""BFTRouter: dispatch only on consensus, clear no-consensus otherwise. Hermetic."""

import pytest

from openmoe_bft import BFTRouter, NoConsensusError, assignment_hash


def _const(key):
    """A router replica that always proposes `key`."""
    return lambda x: key


# Three demo experts (data-driven; ids stand in for the 14 safety experts).
EXPERTS = {
    1: lambda x: f"expert-1 handled {x}",
    2: lambda x: f"expert-2 handled {x}",
    3: lambda x: f"expert-3 handled {x}",
}


def test_dispatches_on_consensus():
    # 4 replicas, quorum 3; 3 agree on expert 1.
    router = BFTRouter(
        EXPERTS,
        replicas=[_const(1), _const(1), _const(1), _const(2)],
    )
    decision = router.route("tok", session_id="s1")
    assert decision.consensus
    assert decision.expert_key == 1
    assert decision.dispatched
    assert decision.result == "expert-1 handled tok"


def test_no_dispatch_without_consensus():
    # 4 replicas, quorum 3; split 2/2 -> no consensus.
    router = BFTRouter(
        EXPERTS,
        replicas=[_const(1), _const(1), _const(2), _const(2)],
    )
    decision = router.route("tok", session_id="s2")
    assert not decision.consensus
    assert not decision.dispatched
    assert decision.expert_key is None
    assert decision.result is None


def test_strict_mode_raises_on_no_consensus():
    router = BFTRouter(
        EXPERTS,
        replicas=[_const(1), _const(2), _const(3), _const(1)],  # 2/1/1, q=3
    )
    with pytest.raises(NoConsensusError) as ei:
        router.route("tok", session_id="s3", strict=True)
    assert ei.value.decision.consensus is False


def test_byzantine_replica_outvoted():
    # 7 replicas, quorum 5; 5 honest agree, 2 byzantine disagree.
    router = BFTRouter(
        EXPERTS,
        replicas=[_const(2)] * 5 + [_const(1), _const(3)],
    )
    decision = router.route("tok", session_id="s4")
    assert decision.consensus
    assert decision.expert_key == 2
    assert decision.dispatched
    assert decision.result == "expert-2 handled tok"


def test_decide_does_not_dispatch():
    calls = []
    experts = {1: lambda x: calls.append(x) or "ran"}
    router = BFTRouter(experts, replicas=[_const(1), _const(1), _const(1)])
    decision = router.decide("tok", session_id="s5")
    assert decision.consensus
    assert decision.expert_key == 1
    assert not decision.dispatched
    assert calls == []  # expert never invoked in decide()


def test_decision_only_mode_no_callable():
    # experts as bare sequence of keys -> consensus key returned, no dispatch.
    router = BFTRouter([1, 2, 3], replicas=[_const(3), _const(3), _const(3)])
    decision = router.route("tok", session_id="s6")
    assert decision.consensus
    assert decision.expert_key == 3
    assert not decision.dispatched  # no callable to run


def test_consensus_on_unknown_expert_raises():
    router = BFTRouter(EXPERTS, replicas=[_const(99), _const(99), _const(99)])
    with pytest.raises(KeyError):
        router.route("tok", session_id="s7")


def test_requires_replicas_and_experts():
    with pytest.raises(ValueError):
        BFTRouter(EXPERTS, replicas=[])
    with pytest.raises(ValueError):
        BFTRouter({}, replicas=[_const(1)])


def test_assignment_hash_stable_and_distinct():
    assert assignment_hash(1) == assignment_hash(1)
    assert assignment_hash(1) != assignment_hash(2)
    assert assignment_hash("a") != assignment_hash("b")


def test_ledger_records_round():
    router = BFTRouter(EXPERTS, replicas=[_const(1), _const(1), _const(1)])
    router.route("tok", session_id="sess-X")
    rnd = router.ledger.status("sess-X")
    assert rnd is not None
    assert rnd.consensus_reached
