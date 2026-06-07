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
- Red team (Exp #9): AttackStrategy, AttackResult, RedTeamReport,
                     RedTeamOrchestrator, STRATEGIES, default_orchestrator
- A2A compliance:    AgentCard, TaskEnvelope, A2AComplianceVerdict,
                     extract_evidence, validate_card, validate_task, seal_verdict
- x402 Bazaar (L10): BazaarResource, BazaarClient, rank_in_niche,
                     listing_readiness, NICHE_KEYWORDS
- Agent reputation:  AgentScore, agent_fico, web_of_trust_score, OutcomeBilling,
                     OutcomeSettlement (Agent-FICO + outcome-based billing)
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
from .red_team import (
    AttackStrategy,
    AttackResult,
    RedTeamReport,
    RedTeamOrchestrator,
    STRATEGIES,
    default_orchestrator,
)
from .a2a import (
    AgentCard,
    TaskEnvelope,
    A2AComplianceVerdict,
    extract_evidence,
    validate_card,
    validate_task,
    seal_verdict,
)
from .bazaar import (
    BazaarResource,
    BazaarClient,
    NICHE_KEYWORDS,
    rank_in_niche,
    listing_readiness,
)
from .reputation import (
    AgentScore,
    agent_fico,
    web_of_trust_score,
    OutcomeBilling,
    OutcomeSettlement,
    FICO_MIN,
    FICO_MAX,
    FICO_WEIGHTS,
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
    # red team (Expert #9)
    "AttackStrategy",
    "AttackResult",
    "RedTeamReport",
    "RedTeamOrchestrator",
    "STRATEGIES",
    "default_orchestrator",
    # a2a (compliance capstone: Layer 11 ∩ Layer 8)
    "AgentCard",
    "TaskEnvelope",
    "A2AComplianceVerdict",
    "extract_evidence",
    "validate_card",
    "validate_task",
    "seal_verdict",
    # x402 Bazaar discovery (Layer 10 — #1-position tooling)
    "BazaarResource",
    "BazaarClient",
    "NICHE_KEYWORDS",
    "rank_in_niche",
    "listing_readiness",
    # agent reputation (Agent FICO + outcome-based billing)
    "AgentScore",
    "agent_fico",
    "web_of_trust_score",
    "OutcomeBilling",
    "OutcomeSettlement",
    "FICO_MIN",
    "FICO_MAX",
    "FICO_WEIGHTS",
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
