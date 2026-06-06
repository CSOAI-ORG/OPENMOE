"""Debate-rounds-as-consensus (OpenMoE-BFT Empire, Layer 2).

The Agent4Debate absorption (Empire spec PART 1, TIER 1 #2:
"Fork Agent4Debate, replace debate stages with BFT consensus rounds").

The design point from the spec is exact: **debate refines positions, BFT
decides.** Participants ("proposers") argue over several rounds — each round
they see the accumulated transcript and may revise their position — and then,
*after the final round*, each participant's final position is cast as a vote
into the existing :mod:`openmoe_bft.bft` ledger. Consensus is decided by the
unchanged ``2f+1`` quorum engine, not by any debate-specific tallying.

There are **no LLM calls** here. Proposers are plain callables so any backend
(an LLM agent, a heuristic, a fixed stance) plugs in later without touching this
module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .bft import BFTConsensus, BFTLedger


# A proposer is given the current transcript and returns (claim_hash, argument).
# - claim_hash: an opaque string identifying the participant's *position* (the
#   thing that gets BFT-voted; typically a hash of the proposed claim).
# - argument:   the free-text message added to the transcript for this round.
Proposer = Callable[["list[tuple[Any, str]]"], "tuple[str, str]"]


@dataclass
class DebateRound:
    """Accumulated state of a multi-round debate.

    Attributes
    ----------
    participants:
        Ordered list of participant ids.
    positions:
        ``id -> claim_hash`` — each participant's *current* (latest) position.
    transcript:
        Ordered ``(id, message)`` tuples across all rounds.
    """

    participants: list[Any] = field(default_factory=list)
    positions: dict[Any, str] = field(default_factory=dict)
    transcript: list[tuple[Any, str]] = field(default_factory=list)

    def record(self, participant: Any, claim_hash: str, argument: str) -> None:
        """Append one participant's turn: update position, extend transcript."""
        if participant not in self.positions:
            self.participants.append(participant)
        self.positions[participant] = claim_hash
        self.transcript.append((participant, argument))


@dataclass
class DebateResult:
    """Outcome of :func:`run_debate`.

    ``consensus`` mirrors the BFT engine's decision; ``agreed_hash`` is the
    winning claim hash (or ``None`` on no quorum). ``debate`` carries the full
    :class:`DebateRound` for inspection, and ``round`` is the underlying
    :class:`~openmoe_bft.bft.BFTConsensus` for this session.
    """

    session_id: str
    consensus: bool
    agreed_hash: str | None
    quorum: int
    f: int
    total_participants: int
    rounds: int
    debate: DebateRound
    round: BFTConsensus


def run_debate(
    session_id: str,
    proposers: dict[Any, Proposer],
    rounds: int,
    ledger: BFTLedger,
) -> DebateResult:
    """Run an N-round debate, then settle it with one BFT consensus round.

    Each of ``rounds`` iterations, every proposer callable is given the current
    transcript (a list of ``(id, message)`` tuples) and returns
    ``(claim_hash, argument)``. The argument is appended to the transcript and
    the claim_hash becomes that participant's current position. After the final
    round, each participant's *final* claim_hash is cast as a BFT vote into
    ``ledger`` under ``session_id``, and the result is read back through the
    existing consensus API.

    Parameters
    ----------
    session_id:
        Ledger key for this debate's consensus round.
    proposers:
        ``id -> proposer_callable``. ``len(proposers)`` is the node count ``n``
        used for the ``2f+1`` quorum.
    rounds:
        Number of debate rounds (``>= 1``).
    ledger:
        An :class:`openmoe_bft.bft.BFTLedger` to record votes into.

    Returns
    -------
    DebateResult
        With ``consensus`` / ``agreed_hash`` taken from the BFT engine.

    Raises
    ------
    ValueError
        If ``proposers`` is empty or ``rounds < 1``.
    """
    if not proposers:
        raise ValueError("run_debate needs at least one proposer")
    if rounds < 1:
        raise ValueError("rounds must be >= 1")

    debate = DebateRound()
    n = len(proposers)

    for _ in range(rounds):
        for pid, propose in proposers.items():
            # Each proposer sees the transcript as it stands so far.
            claim_hash, argument = propose(list(debate.transcript))
            debate.record(pid, claim_hash, argument)

    # Debate refined positions; BFT decides. Cast each participant's final
    # position as a vote into the existing ledger for this session.
    for pid in debate.participants:
        ledger.cast_vote(
            session_id=session_id,
            node_id=str(pid),
            vote_hash=debate.positions[pid],
            total_nodes=n,
        )

    rnd = ledger.status(session_id)
    assert rnd is not None  # we just cast at least one vote

    return DebateResult(
        session_id=session_id,
        consensus=rnd.consensus_reached,
        agreed_hash=rnd.agreed_hash,
        quorum=rnd.quorum,
        f=rnd.f,
        total_participants=n,
        rounds=rounds,
        debate=debate,
        round=rnd,
    )
