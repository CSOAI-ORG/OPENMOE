"""openmoe-bft — Byzantine-fault-tolerant consensus for MoE routing.

OpenMoE-BFT Empire (Layer 2 BFT consensus + Layer 3 OpenScore safety experts).
"Every expert is a safety expert."

Public API
----------
- BFT engine:        BFTConsensus, BFTLedger, quorum_size, tolerated_faults
- BFT MoE routing:   BFTRouter, RoutingDecision, NoConsensusError, assignment_hash
- Robust aggregation: coordinate_wise_median, trimmed_mean, krum, multi_krum,
                     robust_route
- Debate consensus:  DebateRound, DebateResult, run_debate
- Safety experts:    EXPERTS, SafetyExpert, ExpertDomain, by_id, by_domain,
                     by_regulation, expert_ids
- Registration:      register_expert, RegistrationResult
"""

from __future__ import annotations

from .bft import (
    BFTConsensus,
    BFTLedger,
    quorum_size,
    tolerated_faults,
)
from .routing import (
    BFTRouter,
    RoutingDecision,
    NoConsensusError,
    assignment_hash,
)
from .aggregators import (
    coordinate_wise_median,
    trimmed_mean,
    krum,
    multi_krum,
    robust_route,
)
from .debate import (
    DebateRound,
    DebateResult,
    run_debate,
)
from .experts import (
    EXPERTS,
    SafetyExpert,
    ExpertDomain,
    RegistrationResult,
    register_expert,
    by_id,
    by_domain,
    by_regulation,
    expert_ids,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # bft
    "BFTConsensus",
    "BFTLedger",
    "quorum_size",
    "tolerated_faults",
    # routing
    "BFTRouter",
    "RoutingDecision",
    "NoConsensusError",
    "assignment_hash",
    # aggregators
    "coordinate_wise_median",
    "trimmed_mean",
    "krum",
    "multi_krum",
    "robust_route",
    # debate
    "DebateRound",
    "DebateResult",
    "run_debate",
    # experts
    "EXPERTS",
    "SafetyExpert",
    "ExpertDomain",
    "RegistrationResult",
    "register_expert",
    "by_id",
    "by_domain",
    "by_regulation",
    "expert_ids",
]
