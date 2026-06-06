"""Quorum math + consensus edge cases. Hermetic: stdlib only, no network, no HOME I/O."""

import pytest

from openmoe_bft import BFTConsensus, BFTLedger, quorum_size, tolerated_faults


@pytest.mark.parametrize(
    "n, f, q",
    [
        (1, 0, 1),    # single node: tolerate 0 faults, quorum 1
        (3, 0, 1),    # f = floor(2/3) = 0
        (4, 1, 3),    # f = floor(3/3) = 1, quorum 3 (classic min BFT)
        (7, 2, 5),    # f = floor(6/3) = 2, quorum 5
        (10, 3, 7),   # f = floor(9/3) = 3, quorum 7
    ],
)
def test_quorum_math(n, f, q):
    assert tolerated_faults(n) == f
    assert quorum_size(n) == q
    c = BFTConsensus(total_nodes=n)
    assert c.f == f
    assert c.quorum == q


def test_invalid_node_count():
    with pytest.raises(ValueError):
        BFTConsensus(total_nodes=0)
    with pytest.raises(ValueError):
        tolerated_faults(0)


def test_consensus_reached_unanimous():
    c = BFTConsensus(total_nodes=4)  # quorum 3
    assert not c.consensus_reached
    c.vote("a", "H")
    c.vote("b", "H")
    assert not c.consensus_reached  # only 2 of needed 3
    reached = c.vote("c", "H")
    assert reached
    assert c.consensus_reached
    assert c.agreed_hash == "H"
    assert c.majority_count == 3


def test_no_consensus_on_split_votes():
    c = BFTConsensus(total_nodes=7)  # quorum 5
    for i, h in enumerate(["A", "A", "B", "B", "C", "C", "D"]):
        c.vote(f"n{i}", h)
    # best hash has only 2 votes; need 5
    assert not c.consensus_reached
    assert c.agreed_hash is None
    assert c.majority_count == 2


def test_byzantine_minority_outvoted():
    # n=7, f=2: two Byzantine nodes lie, five honest agree -> consensus holds.
    c = BFTConsensus(total_nodes=7)  # quorum 5
    for nid in ["h1", "h2", "h3", "h4", "h5"]:
        c.vote(nid, "GOOD")
    c.vote("byz1", "EVIL")
    c.vote("byz2", "OTHER")
    assert c.consensus_reached
    assert c.agreed_hash == "GOOD"
    assert c.majority_count == 5


def test_no_consensus_when_faults_exceed_f():
    # n=4, f=1, quorum 3: if 2 nodes are Byzantine, honest 2 cannot reach 3.
    c = BFTConsensus(total_nodes=4)
    c.vote("h1", "GOOD")
    c.vote("h2", "GOOD")
    c.vote("byz1", "EVIL")
    c.vote("byz2", "EVIL")
    assert not c.consensus_reached  # 2 vs 2, neither reaches quorum 3


def test_single_node_trivial_consensus():
    c = BFTConsensus(total_nodes=1)  # quorum 1
    assert c.vote("only", "X")
    assert c.consensus_reached
    assert c.agreed_hash == "X"


def test_last_vote_per_node_wins():
    c = BFTConsensus(total_nodes=3)  # quorum 1
    c.vote("a", "X")
    c.vote("a", "Y")  # revote
    assert c.votes["a"] == "Y"
    assert len(c.votes) == 1


def test_empty_round_has_no_majority():
    c = BFTConsensus(total_nodes=3)
    assert c.majority_hash is None
    assert c.majority_count == 0
    assert c.agreed_hash is None


def test_serialization_roundtrip():
    c = BFTConsensus(total_nodes=4)
    c.vote("a", "H")
    c.vote("b", "H")
    c.vote("c", "H")
    d = c.to_dict()
    assert d["quorum"] == 3
    assert d["f"] == 1
    assert d["consensus_reached"] is True
    assert d["agreed_hash"] == "H"
    import json
    assert json.loads(c.to_json())["agreed_hash"] == "H"


def test_ledger_keys_rounds_by_session():
    ledger = BFTLedger()
    ledger.cast_vote("sess-1", "a", "H", total_nodes=4)
    ledger.cast_vote("sess-1", "b", "H", total_nodes=4)
    ledger.cast_vote("sess-2", "a", "Z", total_nodes=4)
    r1 = ledger.status("sess-1")
    r2 = ledger.status("sess-2")
    assert len(r1.votes) == 2
    assert len(r2.votes) == 1
    assert ledger.status("missing") is None
    ledger.reset("sess-1")
    assert ledger.status("sess-1") is None
