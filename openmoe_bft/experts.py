"""The 14 OpenScore safety experts + MCP -> Expert registration protocol.

OpenMoE-BFT Empire, Layer 3 ("OpenScore Safety Experts").

The registry is *data-driven*: each expert is a frozen :class:`SafetyExpert`
record copied from the Empire spec (PART 1, Layer 3) and the AgentAudit
alignment doc. Routing and registration code reads this list — it never
hard-codes expert behaviour.

The registration protocol (:func:`register_expert`) is transport-agnostic: it
validates an MCP-server-shaped *expert candidate* card (name, tools, and
``a2a_field`` evidence) against the safety-expert contract. There is **no
network code here** — an MCP transport (optional ``[mcp]`` extra) feeds parsed
cards in; this module decides accept/reject.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, asdict
from typing import Any


class ExpertDomain(enum.Enum):
    COMPLIANCE = "compliance"
    SECURITY = "security"
    GOVERNANCE = "governance"
    MONETIZATION = "monetization"
    VERIFICATION = "verification"


@dataclass(frozen=True)
class SafetyExpert:
    """One of the 14 OpenScore safety experts."""

    expert_id: int          # 1-14
    name: str
    source_repo: str        # upstream project we fork / integrate
    domain: ExpertDomain
    regulation: str | None  # "eu_ai_act" | "dora" | None
    a2a_field: str          # A2A Agent Card field carrying evidence
    description: str = ""


# Canonical 14 experts — values copied from OPENMOE_BFT_ALIGNMENT.md /
# OPENMOE_BFT_EMPIRE_SPEC_v1.0.md (PART 1, Layer 3).
EXPERTS: tuple[SafetyExpert, ...] = (
    SafetyExpert(
        1, "EU AI Act Compliance", "AIR Blackbox (fork)",
        ExpertDomain.COMPLIANCE, "eu_ai_act", "metadata.riskAssessment",
        "Scans A2A Agent Cards against EU AI Act Annex III high-risk requirements",
    ),
    SafetyExpert(
        2, "NIST RMF Risk Scoring", "DeepTeam (integration)",
        ExpertDomain.COMPLIANCE, None, "metadata.nistRmfScore",
        "Continuous risk scoring using NIST AI Risk Management Framework",
    ),
    SafetyExpert(
        3, "DORA / NIS2 Incident Taxonomy", "DORA ROI Validator (fork)",
        ExpertDomain.COMPLIANCE, "dora", "metadata.ictRiskFramework",
        "Maps ICT incidents to DORA Art. 23 and NIS2 Art. 21 taxonomies",
    ),
    SafetyExpert(
        4, "Neurorights (GDPR Art 9)", "Custom (GDPR Art 9)",
        ExpertDomain.GOVERNANCE, None, "metadata.neurorightsPolicy",
        "Protects special-category biometric / neural data under GDPR Article 9",
    ),
    SafetyExpert(
        5, "x402 Payment Validation", "AgentMint + Signet (fork)",
        ExpertDomain.MONETIZATION, None, "metadata.x402Receipt",
        "Validates x402 micropayment tokens before gated tool execution",
    ),
    SafetyExpert(
        6, "MCP Tool Attestation", "Agent Security Harness",
        ExpertDomain.SECURITY, None, "metadata.mcpAttestation",
        "Attests that MCP tool descriptors match runtime behaviour",
    ),
    SafetyExpert(
        7, "Blockchain Verification", "liboqs (integration)",
        ExpertDomain.VERIFICATION, None, "metadata.blockchainAnchor",
        "Post-quantum ML-DSA-65 signatures for audit-trail anchoring",
    ),
    SafetyExpert(
        8, "Human-in-the-Loop Gate", "LangGraph Approval Hub (fork)",
        ExpertDomain.GOVERNANCE, None, "metadata.hitlContact",
        "Requires human approval for high-risk agent actions",
    ),
    SafetyExpert(
        9, "Red Team Automation", "RedAmon (fork) + PyRIT",
        ExpertDomain.SECURITY, None, "metadata.redTeamReport",
        "Autonomous adversarial testing of agent outputs",
    ),
    SafetyExpert(
        10, "Blue Team Defense", "Agent Security Harness",
        ExpertDomain.SECURITY, None, "metadata.blueTeamStatus",
        "Runtime defensive monitoring and anomaly detection",
    ),
    SafetyExpert(
        11, "Continuous Monitoring", "DeepTeam (integration)",
        ExpertDomain.SECURITY, None, "metadata.continuousMonitoring",
        "Ongoing evaluation of agent behaviour drift and policy violations",
    ),
    SafetyExpert(
        12, "Fuzzing / Mutation", "FuzzyAI (integration)",
        ExpertDomain.SECURITY, None, "metadata.fuzzingReport",
        "Generative fuzzing of agent inputs to surface edge-case failures",
    ),
    SafetyExpert(
        13, "Autonomous Auditor", "UI-TARS Desktop (ByteDance)",
        ExpertDomain.VERIFICATION, None, "metadata.autonomousAudit",
        "Vision-driven autonomous UI auditing and compliance screenshot verification",
    ),
    SafetyExpert(
        14, "Web Crawler / Extractor", "Firecrawl (integration)",
        ExpertDomain.VERIFICATION, None, "metadata.webExtractionPolicy",
        "Autonomous web extraction for regulatory document ingestion",
    ),
)


# ── Lookups ────────────────────────────────────────────────────

def by_id(expert_id: int) -> SafetyExpert | None:
    for e in EXPERTS:
        if e.expert_id == expert_id:
            return e
    return None


def by_domain(domain: ExpertDomain) -> list[SafetyExpert]:
    return [e for e in EXPERTS if e.domain == domain]


def by_regulation(regulation: str) -> list[SafetyExpert]:
    return [e for e in EXPERTS if e.regulation == regulation]


def expert_ids() -> list[int]:
    return [e.expert_id for e in EXPERTS]


def to_json() -> str:
    return json.dumps(
        [{**asdict(e), "domain": e.domain.value} for e in EXPERTS],
        indent=2,
    )


# ── MCP -> Expert registration protocol ────────────────────────

@dataclass
class RegistrationResult:
    """Outcome of validating an MCP expert candidate."""

    accepted: bool
    expert_id: int | None
    reasons: list[str]            # rejection reasons (empty if accepted)
    matched_tools: list[str]      # tool names found on the candidate card

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get_path(card: dict[str, Any], dotted: str) -> Any:
    node: Any = card
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def _has_evidence(card: dict[str, Any], dotted: str) -> bool:
    return _get_path(card, dotted) not in (None, "", [], {})


def register_expert(card: dict[str, Any]) -> RegistrationResult:
    """Validate an MCP-server-shaped expert candidate against the contract.

    A candidate is an A2A/MCP Agent Card shaped dict::

        {
          "expert_id": 1,                      # required: 1-14
          "name": "EU AI Act Compliance",      # required: must match the expert
          "tools": [{"name": "scan_card"}],    # required: >= 1 named tool
          "metadata": {"riskAssessment": ...}, # required: a2a_field evidence
        }

    Accept criteria (all must hold):
      1. ``expert_id`` is present and resolves to a known safety expert.
      2. ``name`` matches the registered expert name (case-insensitive).
      3. ``tools`` is a non-empty list, each entry exposing a ``name``.
      4. The expert's ``a2a_field`` evidence is present and non-empty.

    No network calls — the caller supplies an already-parsed card.
    """
    reasons: list[str] = []

    if not isinstance(card, dict):
        return RegistrationResult(False, None, ["candidate must be a dict"], [])

    expert_id = card.get("expert_id")
    expert = by_id(expert_id) if isinstance(expert_id, int) else None
    if expert is None:
        reasons.append(
            f"unknown or missing expert_id: {expert_id!r} (must be 1-14)"
        )

    # name match
    name = card.get("name")
    if expert is not None:
        if not isinstance(name, str) or name.strip().lower() != expert.name.lower():
            reasons.append(
                f"name {name!r} does not match expert {expert.expert_id} "
                f"({expert.name!r})"
            )

    # tools: non-empty list of named tools
    matched_tools: list[str] = []
    tools = card.get("tools")
    if not isinstance(tools, list) or not tools:
        reasons.append("tools must be a non-empty list")
    else:
        for t in tools:
            tname = t.get("name") if isinstance(t, dict) else None
            if isinstance(tname, str) and tname:
                matched_tools.append(tname)
        if not matched_tools:
            reasons.append("no tool in `tools` exposes a non-empty `name`")

    # a2a_field evidence
    if expert is not None and not _has_evidence(card, expert.a2a_field):
        reasons.append(
            f"missing evidence at a2a_field {expert.a2a_field!r}"
        )

    accepted = not reasons
    return RegistrationResult(
        accepted=accepted,
        expert_id=expert.expert_id if (accepted and expert) else None,
        reasons=reasons,
        matched_tools=matched_tools,
    )
