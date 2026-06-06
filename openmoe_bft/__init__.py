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
- MoE base routing:  softmax, top_k_gating, noisy_top_k_gating,
                     load_balancing_loss, SparseMoERouter, RoutingResult
- EU AI Act checks:  Article, Check, CHECKS, ComplianceReport, evaluate,
                     checks_for_article, checks_by_severity
- Receipts (Layer 9): Receipt, AuditChain, VerifyResult, sign_hmac, verify_hmac,
                     sign_ed25519, verify_ed25519
- Memory (Layer 4):  MemoryPyramid, MemoryEvent, Atom, Scenario, PersonaTrait,
                     RecallHit, DreamStats, L0, L1, L2, L3, ALL_TIERS
- Covenants/trust:   Covenant, Action, Breach, CovenantRegistry,
                     expert_covenants, SEVERITY_PENALTY, NO_ACTION_BASELINE
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
from .moe import (
    softmax,
    top_k_gating,
    noisy_top_k_gating,
    load_balancing_loss,
    SparseMoERouter,
    RoutingResult,
)
from .eu_ai_act import (
    Article,
    Check,
    CHECKS,
    ComplianceReport,
    evaluate,
    checks_for_article,
    checks_by_severity,
)
from .receipts import (
    Receipt,
    AuditChain,
    VerifyResult,
    sign_hmac,
    verify_hmac,
    sign_ed25519,
    verify_ed25519,
)
from .memory import (
    MemoryPyramid,
    MemoryEvent,
    Atom,
    Scenario,
    PersonaTrait,
    RecallHit,
    DreamStats,
    tokenize,
    overlap_score,
    L0,
    L1,
    L2,
    L3,
    ALL_TIERS,
)
from .covenants import (
    Covenant,
    Action,
    Breach,
    CovenantRegistry,
    expert_covenants,
    SEVERITY_PENALTY,
    NO_ACTION_BASELINE,
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
    # moe (base-model routing, Layer 1)
    "softmax",
    "top_k_gating",
    "noisy_top_k_gating",
    "load_balancing_loss",
    "SparseMoERouter",
    "RoutingResult",
    # eu_ai_act (Expert #1 check backend)
    "Article",
    "Check",
    "CHECKS",
    "ComplianceReport",
    "evaluate",
    "checks_for_article",
    "checks_by_severity",
    # receipts (Layer 9, audit & receipts)
    "Receipt",
    "AuditChain",
    "VerifyResult",
    "sign_hmac",
    "verify_hmac",
    "sign_ed25519",
    "verify_ed25519",
    # memory (Layer 4, SOV3 pyramid)
    "MemoryPyramid",
    "MemoryEvent",
    "Atom",
    "Scenario",
    "PersonaTrait",
    "RecallHit",
    "DreamStats",
    "tokenize",
    "overlap_score",
    "L0",
    "L1",
    "L2",
    "L3",
    "ALL_TIERS",
    # covenants (pre-commitment + web-of-trust score)
    "Covenant",
    "Action",
    "Breach",
    "CovenantRegistry",
    "expert_covenants",
    "SEVERITY_PENALTY",
    "NO_ACTION_BASELINE",
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
