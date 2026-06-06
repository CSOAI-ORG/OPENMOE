"""BFT consensus wrapper for Mixture-of-Experts routing (Empire Layer 2 -> 3).

The novel piece. Standard MoE gating picks an expert with a single (trainable)
router; a compromised or buggy router can silently misroute a token to an unsafe
expert. :class:`BFTRouter` instead fans the routing decision out to N *router
replicas*, each of which independently proposes an expert assignment. The
proposals are hashed and run through the BFT consensus engine
(:mod:`openmoe_bft.bft`). The token is dispatched to the chosen expert **only**
when ``2f+1`` replicas agree; otherwise a clear no-consensus result is returned
and nothing is dispatched.

"Every expert is a safety expert" — the experts being routed to are, by default,
the 14 OpenScore safety experts, but expert definitions are fully data-driven:
any callable or id can be an expert.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .bft import BFTConsensus, BFTLedger


# A router replica inspects the input and proposes an expert key (id or name).
RouterReplica = Callable[[Any], Any]


def assignment_hash(expert_key: Any) -> str:
    """Deterministic hash of a proposed expert assignment."""
    payload = json.dumps(expert_key, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class RoutingDecision:
    """Result of a BFT-gated routing attempt."""

    session_id: str
    consensus: bool
    expert_key: Any | None          # agreed expert key, or None
    agreed_hash: str | None
    quorum: int
    f: int
    total_replicas: int
    votes: dict[str, str]           # replica_id -> assignment_hash
    proposals: dict[str, Any]       # replica_id -> proposed expert_key
    dispatched: bool = False
    result: Any = None              # expert return value if dispatched

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "consensus": self.consensus,
            "expert_key": self.expert_key,
            "agreed_hash": self.agreed_hash,
            "quorum": self.quorum,
            "f": self.f,
            "total_replicas": self.total_replicas,
            "votes": self.votes,
            "proposals": {k: str(v) for k, v in self.proposals.items()},
            "dispatched": self.dispatched,
        }


class NoConsensusError(RuntimeError):
    """Raised by :meth:`BFTRouter.route` (strict mode) when no quorum agrees."""

    def __init__(self, decision: "RoutingDecision") -> None:
        self.decision = decision
        super().__init__(
            f"no BFT consensus: best hash had "
            f"{max(_tally(decision.votes).values(), default=0)} votes, "
            f"need {decision.quorum} of {decision.total_replicas} replicas"
        )


def _tally(votes: Mapping[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for h in votes.values():
        out[h] = out.get(h, 0) + 1
    return out


class BFTRouter:
    """Route MoE inputs to experts only on Byzantine-fault-tolerant agreement.

    Parameters
    ----------
    experts:
        Mapping of ``expert_key -> expert_callable``. Keys are typically the
        14 safety-expert ids (ints) or names (str); values are callables taking
        the routed input. Keys may also be supplied with no callables (pure
        decision mode) — then :meth:`route` returns the agreed key but does not
        dispatch.
    replicas:
        Sequence of router-replica callables. Each takes the input and returns a
        proposed ``expert_key``. ``len(replicas)`` is the node count ``n`` used
        for the ``2f+1`` quorum.
    """

    def __init__(
        self,
        experts: Mapping[Any, Callable[[Any], Any]] | Sequence[Any],
        replicas: Sequence[RouterReplica],
    ) -> None:
        if not replicas:
            raise ValueError("BFTRouter needs at least one router replica")
        # Allow experts as a bare sequence of keys (decision-only mode).
        if isinstance(experts, Mapping):
            self.experts: dict[Any, Callable[[Any], Any] | None] = dict(experts)
        else:
            self.experts = {k: None for k in experts}
        if not self.experts:
            raise ValueError("BFTRouter needs at least one expert")
        self.replicas = list(replicas)
        self.ledger = BFTLedger()

    @property
    def total_replicas(self) -> int:
        return len(self.replicas)

    def decide(self, x: Any, session_id: str) -> RoutingDecision:
        """Run replicas through consensus WITHOUT dispatching to the expert."""
        n = self.total_replicas
        consensus = BFTConsensus(total_nodes=n)
        proposals: dict[str, Any] = {}

        for i, replica in enumerate(self.replicas):
            node_id = f"replica-{i}"
            proposed = replica(x)
            proposals[node_id] = proposed
            consensus.vote(node_id, assignment_hash(proposed))

        # Park the round in the ledger for later inspection / status tools.
        self.ledger._rounds[session_id] = consensus  # noqa: SLF001 (internal)

        agreed_hash = consensus.agreed_hash
        expert_key: Any | None = None
        if agreed_hash is not None:
            # Recover the human-readable key whose hash won.
            for nid, proposed in proposals.items():
                if consensus.votes[nid] == agreed_hash:
                    expert_key = proposed
                    break

        return RoutingDecision(
            session_id=session_id,
            consensus=consensus.consensus_reached,
            expert_key=expert_key,
            agreed_hash=agreed_hash,
            quorum=consensus.quorum,
            f=consensus.f,
            total_replicas=n,
            votes=dict(consensus.votes),
            proposals=proposals,
        )

    def route(
        self,
        x: Any,
        session_id: str,
        *,
        strict: bool = False,
    ) -> RoutingDecision:
        """Decide via consensus, then dispatch to the agreed expert.

        On consensus: if the agreed expert key maps to a callable, the expert is
        invoked with ``x`` and the return value is stored on
        ``decision.result`` (``dispatched=True``).

        On no consensus: nothing is dispatched. ``strict=True`` raises
        :class:`NoConsensusError`; otherwise the decision is returned with
        ``consensus=False`` and ``dispatched=False``.
        """
        decision = self.decide(x, session_id)

        if not decision.consensus:
            if strict:
                raise NoConsensusError(decision)
            return decision

        if decision.expert_key not in self.experts:
            raise KeyError(
                f"consensus chose unknown expert key {decision.expert_key!r}; "
                f"known experts: {list(self.experts)}"
            )

        expert_fn = self.experts[decision.expert_key]
        if expert_fn is not None:
            decision.result = expert_fn(x)
            decision.dispatched = True
        return decision
