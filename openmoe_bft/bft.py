"""Byzantine-fault-tolerant consensus engine (OpenMoE-BFT Empire, Layer 2).

Standalone, stdlib-only. No agentaudit dependency.

A consensus *round* collects votes from a set of nodes. Each vote is a
``vote_hash`` (an opaque string — typically a hash of the proposed decision).
Consensus is reached when at least ``quorum`` nodes vote for the same hash,
where::

    f      = floor((n - 1) / 3)      # tolerated Byzantine (faulty) nodes
    quorum = 2f + 1                  # agreeing nodes required

This is the classic BFT safety bound: with ``n`` total nodes the protocol
tolerates up to ``f`` arbitrary (Byzantine) faults and still guarantees a
single agreed value.

The :class:`BFTLedger` keys rounds by ``session_id`` so a single engine can
arbitrate many concurrent routing decisions. Production deployments replace the
in-memory ledger with a distributed consensus log (Mysticeti, Lachesis, or a
ByzFL aggregator).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Any


def tolerated_faults(total_nodes: int) -> int:
    """f = floor((n - 1) / 3): the number of Byzantine faults tolerated."""
    if total_nodes < 1:
        raise ValueError("total_nodes must be >= 1")
    return (total_nodes - 1) // 3


def quorum_size(total_nodes: int) -> int:
    """2f + 1: the number of agreeing votes required for consensus."""
    return 2 * tolerated_faults(total_nodes) + 1


@dataclass
class BFTConsensus:
    """Consensus state for a single round (keyed externally by session_id)."""

    total_nodes: int
    round_id: int = 0
    votes: dict[str, str] = field(default_factory=dict)  # node_id -> vote_hash
    leader_id: str | None = None
    ai_enhanced_selection: bool = False  # AI-enhanced leader election (reserved)

    def __post_init__(self) -> None:
        if self.total_nodes < 1:
            raise ValueError("total_nodes must be >= 1")

    @property
    def f(self) -> int:
        """Tolerated Byzantine faults: floor((n - 1) / 3)."""
        return tolerated_faults(self.total_nodes)

    @property
    def quorum(self) -> int:
        """2f + 1 — agreeing votes required for consensus."""
        return quorum_size(self.total_nodes)

    @property
    def majority_hash(self) -> str | None:
        """The most-voted hash, or None if no votes have been cast."""
        if not self.votes:
            return None
        return Counter(self.votes.values()).most_common(1)[0][0]

    @property
    def majority_count(self) -> int:
        """Vote count for the most-voted hash (0 if no votes)."""
        if not self.votes:
            return 0
        return Counter(self.votes.values()).most_common(1)[0][1]

    @property
    def consensus_reached(self) -> bool:
        """True when at least ``quorum`` nodes agree on one hash."""
        return self.majority_count >= self.quorum

    @property
    def agreed_hash(self) -> str | None:
        """The agreed hash if (and only if) consensus is reached, else None."""
        return self.majority_hash if self.consensus_reached else None

    def vote(self, node_id: str, vote_hash: str) -> bool:
        """Record a vote (last vote per node wins). Returns consensus status."""
        self.votes[node_id] = vote_hash
        return self.consensus_reached

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["f"] = self.f
        d["quorum"] = self.quorum
        d["consensus_reached"] = self.consensus_reached
        d["agreed_hash"] = self.agreed_hash
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class BFTLedger:
    """In-memory registry of consensus rounds keyed by ``session_id``."""

    def __init__(self) -> None:
        self._rounds: dict[str, BFTConsensus] = {}

    def round_for(self, session_id: str, total_nodes: int) -> BFTConsensus:
        """Get (or create) the consensus round for a session."""
        rnd = self._rounds.get(session_id)
        if rnd is None:
            rnd = BFTConsensus(total_nodes=total_nodes)
            self._rounds[session_id] = rnd
        return rnd

    def cast_vote(
        self,
        session_id: str,
        node_id: str,
        vote_hash: str,
        total_nodes: int,
    ) -> BFTConsensus:
        """Cast one vote into a session's round, creating it on first use."""
        rnd = self.round_for(session_id, total_nodes)
        rnd.vote(node_id, vote_hash)
        return rnd

    def status(self, session_id: str) -> BFTConsensus | None:
        return self._rounds.get(session_id)

    def reset(self, session_id: str) -> None:
        self._rounds.pop(session_id, None)
