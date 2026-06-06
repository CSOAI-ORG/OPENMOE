"""A2A compliance-validation layer — Layer 11 (interoperability) meets Layer 8.

OpenMoE-BFT Empire. This module is the **meok-a2a-compliance** capability living
in-package: it takes the **A2A (Agent-to-Agent) Protocol** wire shape — the
``AgentCard`` and a task payload — and validates it against the EU AI Act
*through the modules this package already ships*, rather than reinventing any
scoring or expert taxonomy.

Per the integration recon, we do **not** fork the A2A spec: we reproduce only
the ``AgentCard`` / task **data shape** from the public spec
(`a2aproject/A2A <https://github.com/a2aproject/A2A>`_, Apache-2.0) and build a
compliance layer on top. Compliance evidence rides in the card's permissive
``metadata`` dict — matching the ``a2a_field`` convention (dotted
``"metadata.<field>"``) used by :mod:`openmoe_bft.experts` and
:mod:`openmoe_bft.eu_ai_act`.

Composition (no reinvention)
----------------------------
- :func:`extract_evidence` flattens a card/task ``metadata`` dict into the
  dotted ``"metadata.<field>"`` evidence form that
  :func:`openmoe_bft.eu_ai_act.evaluate` consumes.
- :func:`validate_card` reuses :func:`~openmoe_bft.eu_ai_act.evaluate` for the
  severity-weighted :class:`~openmoe_bft.eu_ai_act.ComplianceReport`, **and**
  checks coverage of the 14 :data:`~openmoe_bft.experts.EXPERTS` via each
  expert's ``a2a_field``.
- :func:`validate_task` delegates to :func:`validate_card` on the task's agent
  card.
- :func:`seal_verdict` (optional) appends a verdict to an
  :class:`~openmoe_bft.receipts.AuditChain` so an A2A compliance decision becomes
  a tamper-evident :class:`~openmoe_bft.receipts.Receipt`.

Hermeticity: nothing here reads the clock or an RNG — the caller passes any
``timestamp`` (see :func:`seal_verdict`), mirroring the rest of the package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import eu_ai_act
from .eu_ai_act import ComplianceReport
from .experts import EXPERTS, SafetyExpert
from .receipts import AuditChain, Receipt


# ── A2A wire shapes (reproduced from a2aproject/A2A, Apache-2.0) ──
#
# Only the *data shape* of the core fields is reproduced — name/description/
# version/url/capabilities/skills — plus the permissive ``metadata`` extension
# bag where the Empire's compliance evidence lives. Both dataclasses are kept
# permissive: an ``extra`` bag absorbs any spec fields we do not model so a real
# A2A AgentCard round-trips without loss.


@dataclass
class AgentCard:
    """An A2A ``AgentCard`` (core fields + the compliance ``metadata`` bag).

    Mirrors the public A2A spec's AgentCard. Compliance evidence is carried in
    ``metadata`` keyed by the bare field name used in each expert's
    ``a2a_field`` (e.g. ``metadata["riskAssessment"]`` for Expert #1, whose
    ``a2a_field`` is ``"metadata.riskAssessment"``). A truthy nested value means
    the evidence is present. Permissive by design — unknown spec fields land in
    ``extra``.
    """

    name: str = ""
    description: str = ""
    version: str = ""
    url: str = ""
    capabilities: dict[str, Any] = field(default_factory=dict)
    skills: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentCard":
        """Build an :class:`AgentCard` from a raw A2A AgentCard dict.

        Known fields are mapped onto the dataclass; everything else is preserved
        in ``extra`` so nothing is dropped (permissive round-trip).
        """
        data = data or {}
        known = {"name", "description", "version", "url",
                 "capabilities", "skills", "metadata"}
        return cls(
            name=data.get("name", "") or "",
            description=data.get("description", "") or "",
            version=data.get("version", "") or "",
            url=data.get("url", "") or "",
            capabilities=dict(data.get("capabilities") or {}),
            skills=list(data.get("skills") or []),
            metadata=dict(data.get("metadata") or {}),
            extra={k: v for k, v in data.items() if k not in known},
        )

    @property
    def id(self) -> str:
        """A stable card identifier — ``url`` if set, else ``name``."""
        return self.url or self.name


@dataclass
class TaskEnvelope:
    """An A2A task payload referencing an agent + its compliance ``metadata``.

    ``agent`` may be a full :class:`AgentCard` or just its id string (the A2A
    spec lets a task reference an already-published card). ``input`` is the
    task's request payload; ``metadata`` carries per-task compliance evidence
    (same dotted convention as :class:`AgentCard`).
    """

    task_id: str = ""
    agent: "AgentCard | str | None" = None
    input: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskEnvelope":
        """Build a :class:`TaskEnvelope` from a raw A2A task dict."""
        data = data or {}
        agent_raw = data.get("agent")
        agent: AgentCard | str | None
        if isinstance(agent_raw, dict):
            agent = AgentCard.from_dict(agent_raw)
        else:
            agent = agent_raw
        return cls(
            task_id=data.get("task_id", "") or data.get("id", "") or "",
            agent=agent,
            input=dict(data.get("input") or {}),
            metadata=dict(data.get("metadata") or {}),
        )


# ── Evidence extraction ──────────────────────────────────────────


def _as_card(card_or_task: "AgentCard | TaskEnvelope | dict[str, Any]") -> AgentCard:
    """Coerce a card / task / raw dict into an :class:`AgentCard`."""
    if isinstance(card_or_task, AgentCard):
        return card_or_task
    if isinstance(card_or_task, TaskEnvelope):
        if isinstance(card_or_task.agent, AgentCard):
            return card_or_task.agent
        # task references its agent by id (or none) — synthesise an empty card
        # so coverage/evidence is computed over the task's own metadata.
        return AgentCard(name=card_or_task.agent or "", metadata={})
    if isinstance(card_or_task, dict):
        return AgentCard.from_dict(card_or_task)
    raise TypeError(
        "expected AgentCard, TaskEnvelope or dict, "
        f"got {type(card_or_task).__name__}"
    )


def extract_evidence(
    card_or_task: "AgentCard | TaskEnvelope | dict[str, Any]",
) -> dict[str, bool]:
    """Flatten a ``metadata`` dict into dotted ``"metadata.<field>"`` evidence.

    A *truthy* nested value becomes ``{"metadata.<field>": True}`` — the exact
    shape :func:`openmoe_bft.eu_ai_act.evaluate` consumes. Only one level of
    nesting under ``metadata`` is flattened (e.g.
    ``{"riskAssessment": {...}} -> {"metadata.riskAssessment": True}``); falsy
    nested values are dropped entirely (evidence absent). For a
    :class:`TaskEnvelope` whose ``agent`` is a full card, the card's metadata is
    merged with the task's metadata (task metadata wins on conflict).
    """
    metadata: dict[str, Any] = {}

    if isinstance(card_or_task, TaskEnvelope):
        if isinstance(card_or_task.agent, AgentCard):
            metadata.update(card_or_task.agent.metadata or {})
        metadata.update(card_or_task.metadata or {})
    else:
        metadata.update(_as_card(card_or_task).metadata or {})

    evidence: dict[str, bool] = {}
    for key, value in metadata.items():
        if value:  # truthy nested value == evidence present
            evidence[f"metadata.{key}"] = True
    return evidence


# ── Verdict ──────────────────────────────────────────────────────


@dataclass
class A2AComplianceVerdict:
    """The outcome of validating an A2A card/task against the Empire compliance layer.

    Composes the reused EU AI Act :class:`~openmoe_bft.eu_ai_act.ComplianceReport`
    with 14-expert coverage. ``compliant`` is ``True`` only when the EU AI Act
    report is compliant **and** there are no blocking gaps (no failed EU AI Act
    blocker checks). ``advisory`` lists, in human-readable form, what to add to
    the card's ``metadata`` to close the gaps.
    """

    eu_ai_act_report: ComplianceReport
    experts_covered: list[int] = field(default_factory=list)
    experts_missing: list[int] = field(default_factory=list)
    compliant: bool = False
    advisory: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Convenience passthrough to the EU AI Act severity-weighted score."""
        return self.eu_ai_act_report.score

    def to_dict(self) -> dict[str, Any]:
        return {
            "eu_ai_act": self.eu_ai_act_report.to_dict(),
            "experts_covered": list(self.experts_covered),
            "experts_missing": list(self.experts_missing),
            "compliant": self.compliant,
            "advisory": list(self.advisory),
        }


def _expert_field_name(expert: SafetyExpert) -> str:
    """The bare ``metadata`` key for an expert (strip the ``metadata.`` prefix)."""
    return expert.a2a_field.split(".", 1)[-1]


def _build_verdict(card: AgentCard, evidence: dict[str, bool]) -> A2AComplianceVerdict:
    """Run EU AI Act evaluation + 14-expert coverage and assemble the verdict."""
    report = eu_ai_act.evaluate(evidence)

    metadata = card.metadata or {}
    covered: list[int] = []
    missing: list[int] = []
    for expert in EXPERTS:
        if metadata.get(_expert_field_name(expert)):
            covered.append(expert.expert_id)
        else:
            missing.append(expert.expert_id)

    advisory: list[str] = []
    for check in report.blocking_failures:
        advisory.append(
            f"add EU AI Act evidence at {check.evidence_field!r} "
            f"({check.id}: {check.title})"
        )
    for expert in EXPERTS:
        if expert.expert_id in missing:
            advisory.append(
                f"add Expert #{expert.expert_id} ({expert.name}) evidence at "
                f"{expert.a2a_field!r}"
            )

    # Compliant only when EU AI Act passes AND there are no blocking gaps.
    compliant = report.compliant and not report.blocking_failures

    return A2AComplianceVerdict(
        eu_ai_act_report=report,
        experts_covered=covered,
        experts_missing=missing,
        compliant=compliant,
        advisory=advisory,
    )


def validate_card(
    card: "AgentCard | dict[str, Any]",
) -> A2AComplianceVerdict:
    """Validate an A2A ``AgentCard`` against the Empire compliance layer.

    Runs :func:`openmoe_bft.eu_ai_act.evaluate` over the card's flattened
    evidence (reusing its severity-weighted scoring), and checks whether each of
    the 14 :data:`~openmoe_bft.experts.EXPERTS` has its ``a2a_field`` present in
    ``metadata``. Returns an :class:`A2AComplianceVerdict`.
    """
    agent_card = _as_card(card)
    evidence = extract_evidence(agent_card)
    return _build_verdict(agent_card, evidence)


def validate_task(
    task: "TaskEnvelope | dict[str, Any]",
) -> A2AComplianceVerdict:
    """Validate an A2A task: its agent card + the task's own metadata.

    Delegates to :func:`validate_card` on the task's agent card, but evaluates
    over the **merged** evidence (card metadata + task metadata, task winning)
    so per-task evidence counts. Coverage is reported against the agent card's
    metadata as the system-of-record.
    """
    envelope = task if isinstance(task, TaskEnvelope) else TaskEnvelope.from_dict(task)
    agent_card = _as_card(envelope)
    evidence = extract_evidence(envelope)
    return _build_verdict(agent_card, evidence)


# ── Optional composition: seal a verdict as a tamper-evident receipt ──


def seal_verdict(
    verdict: A2AComplianceVerdict,
    chain: AuditChain,
    timestamp: int | float,
    trace_id: str = "a2a-compliance",
    signer_key: "str | bytes | None" = None,
) -> Receipt:
    """Append ``verdict`` to ``chain`` as a receipt; return that :class:`Receipt`.

    Makes an A2A compliance decision tamper-evident: the verdict's ``to_dict``
    becomes the sealed receipt payload, hash-chained to its predecessor. The
    caller supplies ``timestamp`` (hermetic — never read from the clock) and may
    pass ``signer_key`` to HMAC-sign the receipt. After this call
    ``chain.verify().ok`` holds.
    """
    return chain.append(
        payload={"a2a_compliance_verdict": verdict.to_dict()},
        trace_id=trace_id,
        timestamp=timestamp,
        signer_key=signer_key,
    )
