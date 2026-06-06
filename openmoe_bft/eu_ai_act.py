"""EU AI Act high-risk compliance check registry — OpenScore Expert #1 backend.

OpenMoE-BFT Empire, Layer 3 ("OpenScore Safety Experts"). This module is the
embeddable *check core* behind Expert #1 ("EU AI Act Compliance", regulation
``eu_ai_act``) defined in :mod:`openmoe_bft.experts`. The live MEOK flagship
``eu-ai-act-compliance-mcp`` is the production MCP server; this registry is the
small, stdlib-only check engine it (and any other consumer) can embed.

The checks are a *cleanroom* reimplementation derived directly from the public
regulation text — Regulation (EU) 2024/1689 (the AI Act), Chapter III, Section 2,
Articles 9-15, which govern the requirements for **high-risk AI systems**:

- Art 9  — Risk management system
- Art 10 — Data and data governance
- Art 11 — Technical documentation
- Art 12 — Record-keeping (logging)
- Art 13 — Transparency and provision of information to deployers
- Art 14 — Human oversight
- Art 15 — Accuracy, robustness and cybersecurity

This is inspired by the structure of the open-source AIR Blackbox scanner
(github.com/airblackbox/gateway, Apache-2.0) but **no AIR Blackbox code was
fetched or copied** — every check is grounded in the article text itself and
cites the relevant article number.

Deadline context: the EU AI Act's obligations for high-risk systems reach full
enforcement on **2026-08-02**, which makes this the highest-priority expert in
the OpenScore fleet.

Each :class:`Check` names the A2A Agent Card metadata field
(``evidence_field``) that would carry proof for it, consistent with the
``a2a_field`` dotted convention used in :mod:`openmoe_bft.experts`. The check
core is evidence-driven: :func:`evaluate` takes a dict keyed by those fields and
returns a severity-weighted :class:`ComplianceReport` — it asserts nothing about
the *quality* of the evidence, only its presence (truthy value).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Article(enum.Enum):
    """The EU AI Act (Reg. (EU) 2024/1689) Chapter III, Section 2 articles."""

    ART_9 = "Article 9 — Risk management system"
    ART_10 = "Article 10 — Data and data governance"
    ART_11 = "Article 11 — Technical documentation"
    ART_12 = "Article 12 — Record-keeping"
    ART_13 = "Article 13 — Transparency and provision of information to deployers"
    ART_14 = "Article 14 — Human oversight"
    ART_15 = "Article 15 — Accuracy, robustness and cybersecurity"


# Severity vocabulary + weights. Blockers weigh most; a single failed blocker
# is meant to dominate the score relative to any number of minor gaps.
Severity = str  # "blocker" | "major" | "minor"

VALID_SEVERITIES: tuple[Severity, ...] = ("blocker", "major", "minor")

_SEVERITY_WEIGHT: dict[Severity, float] = {
    "blocker": 5.0,
    "major": 2.0,
    "minor": 1.0,
}


@dataclass(frozen=True)
class Check:
    """A single, article-grounded EU AI Act high-risk compliance check."""

    id: str               # e.g. "EUAIACT-ART9-001"
    article: Article      # the governing article
    title: str            # short human label
    requirement: str      # one-line plain-English of what must be demonstrated
    evidence_field: str   # A2A metadata field carrying proof (dotted, see experts.py)
    severity: Severity    # "blocker" | "major" | "minor"

    @property
    def weight(self) -> float:
        return _SEVERITY_WEIGHT[self.severity]


# ── The check registry ─────────────────────────────────────────
#
# ~18 checks spanning Art 9-15 (>= 2 per article), each grounded in the actual
# article requirement. Faithful to Regulation (EU) 2024/1689.

CHECKS: tuple[Check, ...] = (
    # ── Article 9 — Risk management system ──────────────────────
    Check(
        "EUAIACT-ART9-001", Article.ART_9,
        "Continuous, iterative risk management system",
        "A risk management system is established, implemented, documented and "
        "maintained as a continuous iterative process across the system's "
        "entire lifecycle (Art 9(1)-(2)).",
        "metadata.riskManagementSystem", "blocker",
    ),
    Check(
        "EUAIACT-ART9-002", Article.ART_9,
        "Identification and evaluation of foreseeable risks",
        "Known and reasonably foreseeable risks to health, safety and "
        "fundamental rights are identified and analysed (Art 9(2)(a)).",
        "metadata.riskAssessment", "blocker",
    ),
    Check(
        "EUAIACT-ART9-003", Article.ART_9,
        "Adoption of risk mitigation measures",
        "Appropriate and targeted risk management measures are adopted to "
        "address the identified risks (Art 9(2)(d), 9(5)).",
        "metadata.riskMitigationMeasures", "major",
    ),
    Check(
        "EUAIACT-ART9-004", Article.ART_9,
        "Testing to identify risk measures",
        "The system is tested to identify the most appropriate risk-management "
        "measures against defined, prior metrics (Art 9(6)-(8)).",
        "metadata.riskTesting", "major",
    ),

    # ── Article 10 — Data and data governance ───────────────────
    Check(
        "EUAIACT-ART10-001", Article.ART_10,
        "Training/validation/test data governance",
        "Training, validation and testing data sets are subject to data "
        "governance practices appropriate for the intended purpose (Art 10(1)-(2)).",
        "metadata.dataGovernance", "blocker",
    ),
    Check(
        "EUAIACT-ART10-002", Article.ART_10,
        "Examination for bias",
        "Data sets are examined in view of possible biases likely to affect "
        "health, safety or fundamental rights or cause discrimination (Art 10(2)(f)-(g)).",
        "metadata.biasExamination", "blocker",
    ),
    Check(
        "EUAIACT-ART10-003", Article.ART_10,
        "Relevant, representative, error-free data sets",
        "Data sets are relevant, sufficiently representative and, to the best "
        "extent possible, free of errors and complete (Art 10(3)).",
        "metadata.dataQuality", "major",
    ),

    # ── Article 11 — Technical documentation ────────────────────
    Check(
        "EUAIACT-ART11-001", Article.ART_11,
        "Technical documentation drawn up before placing on market",
        "Technical documentation is drawn up before the system is placed on the "
        "market and kept up to date, per the Annex IV content (Art 11(1)).",
        "metadata.technicalDocumentation", "blocker",
    ),
    Check(
        "EUAIACT-ART11-002", Article.ART_11,
        "Documentation demonstrates conformity",
        "The documentation demonstrates that the system complies with the "
        "high-risk requirements and gives authorities the information to assess "
        "conformity (Art 11(1)).",
        "metadata.conformityEvidence", "major",
    ),

    # ── Article 12 — Record-keeping (logging) ───────────────────
    Check(
        "EUAIACT-ART12-001", Article.ART_12,
        "Automatic logging of events over lifetime",
        "The system technically allows for the automatic recording of events "
        "(logs) over its lifetime (Art 12(1)-(2)).",
        "metadata.eventLogging", "blocker",
    ),
    Check(
        "EUAIACT-ART12-002", Article.ART_12,
        "Logs enable traceability and post-market monitoring",
        "Logging capabilities provide a level of traceability appropriate to "
        "the intended purpose and support post-market monitoring (Art 12(2)).",
        "metadata.logTraceability", "major",
    ),

    # ── Article 13 — Transparency to deployers ──────────────────
    Check(
        "EUAIACT-ART13-001", Article.ART_13,
        "Transparency enabling deployers to interpret output",
        "The system is designed and developed to be sufficiently transparent so "
        "that deployers can interpret and use its output appropriately (Art 13(1)).",
        "metadata.transparencyDesign", "blocker",
    ),
    Check(
        "EUAIACT-ART13-002", Article.ART_13,
        "Instructions for use provided to deployers",
        "The system is accompanied by instructions for use carrying concise, "
        "complete information for deployers (identity, characteristics, "
        "capabilities, limitations) (Art 13(2)-(3)).",
        "metadata.instructionsForUse", "major",
    ),

    # ── Article 14 — Human oversight ────────────────────────────
    Check(
        "EUAIACT-ART14-001", Article.ART_14,
        "Effective human oversight measures",
        "The system is designed with appropriate human-machine interface tools "
        "so it can be effectively overseen by natural persons during use "
        "(Art 14(1)-(3)).",
        "metadata.humanOversight", "blocker",
    ),
    Check(
        "EUAIACT-ART14-002", Article.ART_14,
        "Override / stop intervention capability",
        "Oversight persons can intervene on the operation, including the ability "
        "to disregard/override output or halt the system via a stop button or "
        "similar procedure (Art 14(4)(d)-(e)).",
        "metadata.overrideControl", "blocker",
    ),
    Check(
        "EUAIACT-ART14-003", Article.ART_14,
        "Mitigation of automation bias",
        "Oversight measures enable persons to remain aware of and counter "
        "automation bias (over-reliance on the system's output) (Art 14(4)(b)).",
        "metadata.automationBiasMitigation", "minor",
    ),

    # ── Article 15 — Accuracy, robustness, cybersecurity ────────
    Check(
        "EUAIACT-ART15-001", Article.ART_15,
        "Declared accuracy and metrics",
        "Appropriate levels of accuracy are achieved and the relevant accuracy "
        "metrics are declared in the instructions for use (Art 15(1)-(3)).",
        "metadata.accuracyMetrics", "major",
    ),
    Check(
        "EUAIACT-ART15-002", Article.ART_15,
        "Robustness and resilience to errors/faults",
        "The system is resilient to errors, faults and inconsistencies, and to "
        "feedback loops in continuously-learning systems (Art 15(1), 15(4)).",
        "metadata.robustnessTesting", "major",
    ),
    Check(
        "EUAIACT-ART15-003", Article.ART_15,
        "Cybersecurity against adversarial attacks",
        "The system is resilient against attempts to alter its use, behaviour or "
        "performance, including data/model poisoning and adversarial examples "
        "(Art 15(1), 15(5)).",
        "metadata.cybersecurityControls", "blocker",
    ),
)


# ── Report ──────────────────────────────────────────────────────

@dataclass
class ComplianceReport:
    """The outcome of evaluating evidence against the full :data:`CHECKS` set."""

    passed: list[Check] = field(default_factory=list)
    failed: list[Check] = field(default_factory=list)
    score: float = 0.0                       # 0.0-1.0, severity-weighted
    blocking_failures: list[Check] = field(default_factory=list)

    @property
    def compliant(self) -> bool:
        """No failed blockers and a perfect score."""
        return not self.blocking_failures and self.score >= 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": [c.id for c in self.passed],
            "failed": [c.id for c in self.failed],
            "score": self.score,
            "blocking_failures": [c.id for c in self.blocking_failures],
            "compliant": self.compliant,
        }


def evaluate(evidence: dict[str, Any]) -> ComplianceReport:
    """Run every check against provided ``evidence`` and return a report.

    ``evidence`` is keyed by :attr:`Check.evidence_field`; a *truthy* value
    means the proof for that check is present. Missing or falsy entries fail
    the check. The score is the fraction of total severity weight satisfied —
    so a failed ``blocker`` (weight 5) drops the score far more than a failed
    ``minor`` (weight 1). The score is 1.0 only when all checks pass and 0.0
    when none do.
    """
    evidence = evidence or {}
    passed: list[Check] = []
    failed: list[Check] = []
    blocking_failures: list[Check] = []

    earned = 0.0
    total = 0.0
    for check in CHECKS:
        total += check.weight
        if evidence.get(check.evidence_field):
            passed.append(check)
            earned += check.weight
        else:
            failed.append(check)
            if check.severity == "blocker":
                blocking_failures.append(check)

    score = (earned / total) if total else 0.0
    return ComplianceReport(
        passed=passed,
        failed=failed,
        score=score,
        blocking_failures=blocking_failures,
    )


# ── Lookups ─────────────────────────────────────────────────────

def checks_for_article(article: Article) -> list[Check]:
    """Every check governed by ``article``."""
    return [c for c in CHECKS if c.article == article]


def checks_by_severity(severity: Severity) -> list[Check]:
    """Every check at the given ``severity``."""
    return [c for c in CHECKS if c.severity == severity]
