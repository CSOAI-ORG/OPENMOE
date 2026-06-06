"""Agent covenant protocol + web-of-trust reputation (OpenMoE-BFT Empire).

Layer-9-adjacent. This module backs the **OpenScore TRUST SCORE**: an agent
*pre-commits* to what it is allowed to do (a **covenant**) **before** it acts;
every subsequent action is audited against that covenant; breaches degrade a
web-of-trust reputation that propagates one hop across vouchers.

Protocol (cleanroom)
--------------------
1. **Covenant inscription** — an agent files a :class:`Covenant` declaring its
   ``allowed_actions`` and optional structured ``constraints`` *before* acting.
   The covenant is content-addressed (deterministic ``inscription_hash`` /
   ``covenant_id``): same content + timestamp -> same id.
2. **Action log** — every :class:`Action` the agent takes is appended to an
   append-only log via :meth:`CovenantRegistry.record`.
3. **Breach detection** — :meth:`CovenantRegistry.check` audits one action
   against the agent's inscribed covenant, deterministically.
4. **Breach propagation** — breaches accumulate and degrade the agent's
   :meth:`CovenantRegistry.trust_score`; :meth:`CovenantRegistry.web_of_trust`
   blends that with the trust of vouching agents (one hop).
5. **Reputation** — the resulting score feeds the OpenScore trust score.

Composition with the rest of the Empire
---------------------------------------
- **receipts.py (Layer 9):** a covenant inscription and each :class:`Breach` can
  be SEALED as a tamper-evident :class:`~openmoe_bft.receipts.Receipt` — the
  ``inscription_hash`` / breach record is exactly the kind of decision a
  :class:`~openmoe_bft.receipts.AuditChain` is built to attest. This module does
  **not** import receipts (no coupling); it reuses the *canonical-serialization
  idea* via a small local :func:`_canonical`, kept consistent with receipts.py.
- **experts.py (Layer 3):** :func:`expert_covenants` maps each of the 14
  OpenScore :data:`~openmoe_bft.experts.EXPERTS` to a covenant declaring the one
  action that expert is allowed to take (``"audit:<a2a_field>"``), so the same
  breach machinery governs the safety experts themselves.

Absorbs **Nobulex** (https://github.com/arian-gogani/nobulex, MIT — permissive;
attribution preserved here). The covenant protocol concept (covenant inscription
-> action log -> breach detection -> breach propagation -> reputation) is
reimplemented cleanroom in pure stdlib Python; no upstream code was fetched or
copied. Zero hard dependencies.

Hermeticity note: this module never reads the clock or any randomness — the
caller supplies every ``timestamp`` explicitly, keeping construction
deterministic and tests reproducible.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


__all__ = [
    "Covenant",
    "Action",
    "Breach",
    "CovenantRegistry",
    "SEVERITY_PENALTY",
    "NO_ACTION_BASELINE",
    "expert_covenants",
]


# Trust penalty weights, subtracted from a starting score of 1.0 per breach.
# critical > major > minor: a forbidden/uncommitted action costs far more than a
# soft constraint overshoot.
SEVERITY_PENALTY: dict[str, float] = {
    "critical": 0.5,
    "major": 0.2,
    "minor": 0.05,
}

# An agent that has taken no actions at all is "unproven", not trusted and not
# distrusted: a neutral baseline rather than a perfect 1.0 (which would let a
# brand-new agent inherit full trust before doing anything).
NO_ACTION_BASELINE: float = 0.5


def _canonical(obj: Any) -> str:
    """Canonical JSON serialization: stable, order-independent, compact.

    Mirrors the canonicalization idea in ``receipts.py`` (kept consistent so the
    two content-addressing schemes behave identically) without importing its
    private helper. ``sort_keys=True`` makes dict ordering irrelevant and
    ``separators`` strips incidental whitespace, so the same logical content
    always hashes identically.
    """
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _inscription_hash(
    agent_id: str,
    allowed_actions: frozenset[str],
    constraints: dict[str, Any],
    timestamp: int | float,
) -> str:
    """SHA-256 content-address over a covenant's declared content.

    ``allowed_actions`` is sorted so the frozenset's iteration order is
    irrelevant; the result is deterministic for identical declared content.
    """
    material = _canonical(
        {
            "agent_id": agent_id,
            "allowed_actions": sorted(allowed_actions),
            "constraints": constraints,
            "timestamp": timestamp,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Covenant:
    """A pre-commitment: what an agent declares it is allowed to do, before acting.

    Attributes
    ----------
    covenant_id:
        Deterministic content hash (== ``inscription_hash``). Same declared
        content + timestamp always yields the same id.
    agent_id:
        The agent bound by this covenant.
    allowed_actions:
        The action *names* the agent pre-commits to. Any action whose
        ``action_name`` is not in this set is a **critical** breach.
    constraints:
        Optional structured limits. Numeric ``"max_*"`` keys are enforced against
        the matching payload key (e.g. ``{"max_cost_usd": 1.0}`` is checked
        against ``payload["cost_usd"]``); overshoot is a **major** breach.
    timestamp:
        Caller-supplied (``int``/``float``). Never read from the clock.
    inscription_hash:
        SHA-256 content-address of the covenant (same value as ``covenant_id``).
    """

    covenant_id: str
    agent_id: str
    allowed_actions: frozenset[str]
    constraints: dict[str, Any]
    timestamp: int | float
    inscription_hash: str

    @classmethod
    def inscribe(
        cls,
        *,
        agent_id: str,
        allowed_actions: frozenset[str] | set[str] | list[str] | tuple[str, ...],
        timestamp: int | float,
        constraints: dict[str, Any] | None = None,
    ) -> "Covenant":
        """Build a content-addressed covenant from declared content."""
        allowed = frozenset(allowed_actions)
        cons = dict(constraints or {})
        h = _inscription_hash(agent_id, allowed, cons, timestamp)
        return cls(
            covenant_id=h,
            agent_id=agent_id,
            allowed_actions=allowed,
            constraints=cons,
            timestamp=timestamp,
            inscription_hash=h,
        )


@dataclass(frozen=True)
class Action:
    """A single action an agent takes, to be audited against its covenant."""

    action_id: str
    agent_id: str
    action_name: str
    payload: dict[str, Any]
    timestamp: int | float


@dataclass(frozen=True)
class Breach:
    """A detected covenant violation. ``severity`` drives the trust penalty.

    severity is one of ``"minor"`` | ``"major"`` | ``"critical"``.
    """

    action_id: str
    agent_id: str
    covenant_id: str | None
    reason: str
    severity: str
    timestamp: int | float


class CovenantRegistry:
    """Stores covenants, audits actions, and computes web-of-trust reputation.

    An agent's *latest* inscribed covenant governs it (re-inscribing replaces the
    prior one). :meth:`record` is the append-only entry point: it checks an
    action, logs it, and logs any breach. :meth:`check` is the pure, side-effect
    free audit used internally and exposed for callers who only want to evaluate.
    """

    def __init__(self) -> None:
        self._covenants: dict[str, Covenant] = {}
        self._actions: list[Action] = []
        self._breaches: list[Breach] = []

    # ── Inscription ────────────────────────────────────────────

    def inscribe(self, covenant: Covenant) -> Covenant:
        """Store an agent's covenant (latest wins). Return the covenant."""
        self._covenants[covenant.agent_id] = covenant
        return covenant

    def covenant_for(self, agent_id: str) -> Covenant | None:
        """The covenant currently governing ``agent_id``, or ``None``."""
        return self._covenants.get(agent_id)

    # ── Detection (pure) ───────────────────────────────────────

    def check(self, action: Action) -> Breach | None:
        """Audit one action against the agent's covenant. Pure / deterministic.

        Returns ``None`` if compliant, else a :class:`Breach`:

        - no covenant on file for the agent -> **critical** ("no covenant inscribed");
        - ``action_name`` not in ``allowed_actions`` -> **critical** ("unknown action");
        - a numeric ``"max_*"`` constraint exceeded by the matching payload key
          -> **major**.

        The first violation found is returned (covenant presence, then allowed
        action, then constraints).
        """
        covenant = self._covenants.get(action.agent_id)

        if covenant is None:
            return Breach(
                action_id=action.action_id,
                agent_id=action.agent_id,
                covenant_id=None,
                reason="no covenant inscribed",
                severity="critical",
                timestamp=action.timestamp,
            )

        if action.action_name not in covenant.allowed_actions:
            return Breach(
                action_id=action.action_id,
                agent_id=action.agent_id,
                covenant_id=covenant.covenant_id,
                reason=(
                    f"unknown action {action.action_name!r}: not in "
                    f"allowed_actions {sorted(covenant.allowed_actions)!r}"
                ),
                severity="critical",
                timestamp=action.timestamp,
            )

        breach = self._check_constraints(action, covenant)
        if breach is not None:
            return breach

        return None

    def _check_constraints(self, action: Action, covenant: Covenant) -> Breach | None:
        """Numeric ``max_*`` constraint check against matching payload keys.

        ``{"max_cost_usd": 1.0}`` is enforced against ``payload["cost_usd"]``:
        if the payload value is numeric and strictly greater than the limit it is
        a **major** breach. Non-``max_*`` constraints and absent payload keys are
        ignored here (the action remains compliant on them).
        """
        for key, limit in covenant.constraints.items():
            if not key.startswith("max_"):
                continue
            if not isinstance(limit, (int, float)) or isinstance(limit, bool):
                continue
            payload_key = key[len("max_") :]
            value = action.payload.get(payload_key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if value > limit:
                return Breach(
                    action_id=action.action_id,
                    agent_id=action.agent_id,
                    covenant_id=covenant.covenant_id,
                    reason=(
                        f"constraint {key}={limit} violated: "
                        f"payload[{payload_key!r}]={value} exceeds limit"
                    ),
                    severity="major",
                    timestamp=action.timestamp,
                )
        return None

    # ── Recording (append-only) ────────────────────────────────

    def record(self, action: Action) -> Breach | None:
        """Check ``action``, append it to the action log, log any breach.

        Returns the :class:`Breach` if one was detected, else ``None``. Both logs
        are append-only — nothing is ever mutated or removed.
        """
        breach = self.check(action)
        self._actions.append(action)
        if breach is not None:
            self._breaches.append(breach)
        return breach

    # ── Log helpers ────────────────────────────────────────────

    def actions_for(self, agent_id: str) -> list[Action]:
        """All recorded actions for ``agent_id`` (in record order)."""
        return [a for a in self._actions if a.agent_id == agent_id]

    def breaches_for(self, agent_id: str) -> list[Breach]:
        """All recorded breaches for ``agent_id`` (in record order)."""
        return [b for b in self._breaches if b.agent_id == agent_id]

    # ── Trust scoring / reputation ─────────────────────────────

    def trust_score(self, agent_id: str) -> float:
        """Reputation in ``[0.0, 1.0]`` from this agent's own breach history.

        - No recorded actions at all -> :data:`NO_ACTION_BASELINE` (``0.5``,
          "unproven": neither trusted nor distrusted).
        - Otherwise start at ``1.0`` and subtract :data:`SEVERITY_PENALTY` per
          breach (critical ``0.5`` > major ``0.2`` > minor ``0.05``), clamped to
          ``[0.0, 1.0]``. An agent with >= 1 action and no breaches scores
          ``1.0``.
        """
        if not self.actions_for(agent_id):
            return NO_ACTION_BASELINE

        score = 1.0
        for breach in self.breaches_for(agent_id):
            score -= SEVERITY_PENALTY.get(breach.severity, 0.0)
        return _clamp(score)

    def web_of_trust(
        self,
        vouchers: dict[str, list[str]],
        *,
        alpha: float = 0.5,
    ) -> dict[str, float]:
        """Propagate trust one hop across a vouching graph (reputation blend).

        ``vouchers`` maps ``agent_id -> [voucher_agent_id, ...]``. The propagated
        score blends the agent's own :meth:`trust_score` with the **mean own
        trust of its vouchers** (one hop only — vouchers' own scores are *not*
        re-propagated, so there is no recursion and no cycles to resolve)::

            propagated = alpha * own + (1 - alpha) * mean(voucher own-trust)

        With the default ``alpha = 0.5`` a high-trust voucher lifts a mid-trust
        agent toward the voucher, while low-trust vouchers pull the blend *down*
        (they cannot inflate it above the agent's own score). An agent with no
        listed vouchers keeps its own score unchanged. The result is clamped to
        ``[0.0, 1.0]``.
        """
        own = {aid: self.trust_score(aid) for aid in vouchers}

        # Include any agent that only appears as a voucher, so its own trust is
        # available for the mean.
        for voucher_list in vouchers.values():
            for v in voucher_list:
                if v not in own:
                    own[v] = self.trust_score(v)

        propagated: dict[str, float] = {}
        for aid, voucher_list in vouchers.items():
            if not voucher_list:
                propagated[aid] = own[aid]
                continue
            voucher_mean = sum(own[v] for v in voucher_list) / len(voucher_list)
            blended = alpha * own[aid] + (1.0 - alpha) * voucher_mean
            propagated[aid] = _clamp(blended)
        return propagated


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp ``x`` into ``[lo, hi]``."""
    return max(lo, min(hi, x))


def expert_covenants(timestamp: int | float) -> dict[int, Covenant]:
    """A covenant per OpenScore safety expert (Layer 3 composition).

    Maps each of the 14 :data:`~openmoe_bft.experts.EXPERTS` to a covenant whose
    single allowed action is ``"audit:<a2a_field>"`` — the one thing that expert
    pre-commits to doing — so the same breach machinery governs the experts
    themselves. ``timestamp`` is caller-supplied (hermetic). Returns
    ``{expert_id: Covenant}``.
    """
    from .experts import EXPERTS

    covenants: dict[int, Covenant] = {}
    for expert in EXPERTS:
        covenants[expert.expert_id] = Covenant.inscribe(
            agent_id=f"expert:{expert.expert_id}",
            allowed_actions={f"audit:{expert.a2a_field}"},
            timestamp=timestamp,
        )
    return covenants
