"""Debate-rounds-as-consensus: convergence, split, transcript, ledger. Hermetic."""

import pytest

from openmoe_bft import BFTLedger, run_debate
from openmoe_bft.debate import DebateRound


def _fixed(claim_hash, prefix="says"):
    """A proposer that always holds the same position, ignoring the transcript."""
    return lambda transcript: (claim_hash, f"{prefix}-{claim_hash}-r{len(transcript)}")


def test_convergent_debate_reaches_consensus():
    # 4 participants, quorum 3; three hold "A", one holds "B".
    proposers = {
        "p1": _fixed("A"),
        "p2": _fixed("A"),
        "p3": _fixed("A"),
        "p4": _fixed("B"),
    }
    ledger = BFTLedger()
    res = run_debate("deb-1", proposers, rounds=2, ledger=ledger)
    assert res.consensus
    assert res.agreed_hash == "A"
    assert res.quorum == 3
    assert res.f == 1
    assert res.total_participants == 4


def test_persistent_split_no_consensus():
    # 4 participants, quorum 3; 2 vs 2 -> never reaches quorum.
    proposers = {
        "p1": _fixed("A"),
        "p2": _fixed("A"),
        "p3": _fixed("B"),
        "p4": _fixed("B"),
    }
    ledger = BFTLedger()
    res = run_debate("deb-2", proposers, rounds=3, ledger=ledger)
    assert not res.consensus
    assert res.agreed_hash is None


def test_debate_converges_after_seeing_transcript():
    # A "follower" adopts the first transcript message's stance once it appears.
    def stubborn(transcript):
        return ("WIN", "I hold WIN")

    def follower(transcript):
        # round 0: no transcript yet -> proposes LOSE; later rounds -> WIN.
        if transcript:
            return ("WIN", "I now agree: WIN")
        return ("LOSE", "initially LOSE")

    proposers = {"a": stubborn, "b": stubborn, "c": follower}
    ledger = BFTLedger()
    # quorum for n=3 is 1; but to show real convergence run 2 rounds so the
    # follower's *final* position is WIN, giving a clean 3/3.
    res = run_debate("deb-3", proposers, rounds=2, ledger=ledger)
    assert res.consensus
    assert res.agreed_hash == "WIN"
    # final positions all WIN
    assert res.debate.positions == {"a": "WIN", "b": "WIN", "c": "WIN"}


def test_transcript_accumulates_across_rounds():
    proposers = {"p1": _fixed("A"), "p2": _fixed("A"), "p3": _fixed("A")}
    ledger = BFTLedger()
    res = run_debate("deb-4", proposers, rounds=3, ledger=ledger)
    # 3 participants x 3 rounds = 9 transcript entries.
    assert len(res.debate.transcript) == 9
    assert res.debate.participants == ["p1", "p2", "p3"]
    # entries are (id, message) tuples.
    ids = {pid for pid, _msg in res.debate.transcript}
    assert ids == {"p1", "p2", "p3"}


def test_proposer_sees_growing_transcript():
    seen_lengths = []

    def recorder(transcript):
        seen_lengths.append(len(transcript))
        return ("X", "msg")

    proposers = {"only": recorder}
    ledger = BFTLedger()
    run_debate("deb-5", proposers, rounds=3, ledger=ledger)
    # one proposer, 3 rounds: transcript length grows 0,1,2 as it calls.
    assert seen_lengths == [0, 1, 2]


def test_votes_land_in_ledger_via_public_api():
    proposers = {"p1": _fixed("A"), "p2": _fixed("A"), "p3": _fixed("A")}
    ledger = BFTLedger()
    res = run_debate("deb-6", proposers, rounds=1, ledger=ledger)
    # The vote round is retrievable through the existing ledger public API.
    rnd = ledger.status("deb-6")
    assert rnd is not None
    assert rnd.consensus_reached
    assert rnd.agreed_hash == "A"
    assert len(rnd.votes) == 3
    # node ids are the stringified participant ids.
    assert set(rnd.votes) == {"p1", "p2", "p3"}
    assert res.round is rnd


def test_validation_errors():
    ledger = BFTLedger()
    with pytest.raises(ValueError):
        run_debate("x", {}, rounds=1, ledger=ledger)
    with pytest.raises(ValueError):
        run_debate("x", {"p1": _fixed("A")}, rounds=0, ledger=ledger)


def test_debate_round_record_helper():
    dr = DebateRound()
    dr.record("a", "H1", "hello")
    dr.record("b", "H2", "world")
    dr.record("a", "H3", "revised")  # a revises position
    assert dr.participants == ["a", "b"]  # no dup for a
    assert dr.positions == {"a": "H3", "b": "H2"}
    assert dr.transcript == [("a", "hello"), ("b", "world"), ("a", "revised")]
