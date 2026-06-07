"""Agent FICO + outcome-based billing (OpenMoE-BFT Empire, Layer 10/11).

These are **the differentiators that make MEOK more than a paywall** — the two
gaps the x402 strategy documents as *open* in the protocol itself:

1. **Agent identity / reputation.** x402 settles payments but has no notion of
   *which agents are trustworthy*. :func:`agent_fico` answers that with a
   FICO-style ``300..850`` score — an **"Agent FICO"** — blending behavioral
   pre-commitment adherence (covenants), settled on-chain payment history
   (receipts), and adversarial resilience (red-team risk).
2. **Outcome-based billing.** x402 charges per *call*; it cannot condition
   payment on the *result*. :class:`OutcomeBilling` escrows for a tool call and
   releases payment only if the **attested outcome** meets a caller-supplied
   predicate, else refunds — "pay for verified outcomes, not just calls" — and
   the whole settlement seals as a tamper-evident :class:`~openmoe_bft.receipts.Receipt`.

Both compose the **real** Empire modules — :mod:`openmoe_bft.covenants` (trust
score / web-of-trust), :mod:`openmoe_bft.receipts` (the hash-chained audit
trail used both to *count settled-payment history* and to *seal* an outcome
settlement), and :mod:`openmoe_bft.red_team` (:class:`RedTeamReport.risk_score`)
— so reputation and billing inherit the same tamper-evident, hermetic
foundations as the rest of the stack. Together they are the on-chain-trust and
revenue-quality signals that *defend* MEOK's #1 spot in the compliance niche:
buyers (and the Bazaar's trust ranking) prefer the compliance endpoint that can
prove who it serves and that it pays out only for verified work.

Hermeticity note: nothing here reads the clock or any randomness — every
``timestamp`` is caller-supplied and every signal is passed in or read from a
caller-built :class:`~openmoe_bft.receipts.AuditChain`. Deterministic and
reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .receipts import AuditChain, Receipt


__all__ = [
    "AgentScore",
    "FICO_MIN",
    "FICO_MAX",
    "FICO_WEIGHTS",
    "agent_fico",
    "web_of_trust_score",
    "OutcomeBilling",
    "OutcomeSettlement",
]


# FICO-style bounds — deliberately the consumer-credit 300..850 range so the
# number reads as a familiar creditworthiness signal for agents.
FICO_MIN = 300
FICO_MAX = 850

# Blend weights over three normalized [0,1] signals. They sum to 1.0; the score
# is FICO_MIN + (FICO_MAX - FICO_MIN) * weighted_signal.
#   covenant_trust  — behavioral pre-commitment adherence (covenants.py). Weighted
#                     highest: *honoring declared commitments* is the strongest
#                     predictor of future good behavior.
#   payment_history — settled on-chain payment depth/recency (receipts.py). The
#                     on-chain trust the Bazaar itself ranks on.
#   redteam         — adversarial resilience (red_team.py risk_score; higher
#                     risk_score == better-defended == higher reputation).
FICO_WEIGHTS: dict[str, float] = {
    "covenant_trust": 0.5,
    "payment_history": 0.3,
    "redteam": 0.2,
}


@dataclass(frozen=True)
class AgentScore:
    """An agent's reputation as a FICO-style score (``300..850``).

    Attributes
    ----------
    agent_id:
        The scored agent.
    score:
        Integer in ``[FICO_MIN, FICO_MAX]``. Higher == more trustworthy.
    factors:
        The normalized ``[0,1]`` sub-signals that produced ``score`` (for audit /
        explainability): ``covenant_trust``, ``payment_history``, ``redteam``,
        plus the blended ``signal``.
    computed_ts:
        Caller-supplied timestamp the score was computed at. Never from the clock.
    """

    agent_id: str
    score: int
    factors: dict[str, float]
    computed_ts: int | float


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _payment_history_signal(
    chain: AuditChain | None,
    agent_id: str,
    *,
    now_ts: int | float,
    recency_window: float,
    depth_target: int,
) -> float:
    """Settled-payment trust in ``[0,1]`` from the receipts audit chain.

    Reads ``chain`` for receipts that attest a *settled payment* for ``agent_id``
    — i.e. receipts whose ``payload`` is marked as a settled payment for this
    agent (``payload["kind"] == "settled_payment"`` and a matching ``agent_id`` /
    ``payee`` / ``payer``). Blends two on-chain signals:

    - **depth** — how many settlements, saturating at ``depth_target`` (a thick
      history is more trustworthy than a single payment), and
    - **recency** — how recent the most recent settlement is relative to
      ``now_ts`` over ``recency_window`` (stale history decays).

    Returns ``0.0`` when there is no chain or no settled-payment receipts for the
    agent — a brand-new / unpaid agent has no on-chain trust yet.
    """
    if chain is None:
        return 0.0

    settle_times: list[int | float] = []
    for r in chain.receipts:
        payload = r.payload or {}
        if payload.get("kind") != "settled_payment":
            continue
        if agent_id not in (
            payload.get("agent_id"),
            payload.get("payee"),
            payload.get("payer"),
        ):
            continue
        settle_times.append(r.timestamp)

    if not settle_times:
        return 0.0

    depth = len(settle_times)
    depth_signal = _clamp01(depth / depth_target) if depth_target > 0 else 1.0

    latest = max(settle_times)
    if recency_window <= 0:
        recency_signal = 1.0
    else:
        age = max(0.0, float(now_ts) - float(latest))
        recency_signal = _clamp01(1.0 - age / recency_window)

    # Depth weighted a bit more than recency: a deep history with some staleness
    # still signals a reliable counterparty.
    return _clamp01(0.6 * depth_signal + 0.4 * recency_signal)


def agent_fico(
    agent_id: str,
    *,
    computed_ts: int | float,
    covenant_trust: float | None = None,
    redteam_risk: float | None = None,
    payment_chain: AuditChain | None = None,
    payment_signal: float | None = None,
    now_ts: int | float | None = None,
    recency_window: float = 1.0,
    depth_target: int = 5,
) -> AgentScore:
    """Blend trust signals into a FICO-style ``300..850`` reputation. **Deterministic.**

    Composes the real Empire signals:

    - ``covenant_trust`` — an agent's ``[0,1]`` behavioral-adherence score, e.g.
      from :meth:`openmoe_bft.covenants.CovenantRegistry.trust_score`. Higher
      adherence -> higher FICO. Defaults to the covenants ``NO_ACTION_BASELINE``
      (``0.5``, "unproven") when not supplied.
    - ``payment_history`` — derived from ``payment_chain`` (a
      :class:`~openmoe_bft.receipts.AuditChain` of settled-payment receipts) via
      :func:`_payment_history_signal`, or passed directly as ``payment_signal``
      (which overrides the chain). The on-chain trust the Bazaar ranks on.
    - ``redteam_risk`` — a :attr:`openmoe_bft.red_team.RedTeamReport.risk_score`
      in ``[0,1]`` where **higher == better-defended**. Used as-is (more
      resilience -> higher FICO). Defaults to ``0.5`` (unknown) when not supplied.

    The three normalized signals are weighted by :data:`FICO_WEIGHTS`, mapped onto
    ``[FICO_MIN, FICO_MAX]`` and clamped. No clock / network / randomness:
    ``now_ts`` (for payment recency) defaults to ``computed_ts``.

    Returns an :class:`AgentScore` carrying the score and its sub-factors.
    """
    from .covenants import NO_ACTION_BASELINE

    ct = NO_ACTION_BASELINE if covenant_trust is None else _clamp01(float(covenant_trust))

    if payment_signal is not None:
        ph = _clamp01(float(payment_signal))
    else:
        ph = _payment_history_signal(
            payment_chain,
            agent_id,
            now_ts=computed_ts if now_ts is None else now_ts,
            recency_window=recency_window,
            depth_target=depth_target,
        )

    # red_team.risk_score is already "higher == better"; default 0.5 = unknown.
    rt = 0.5 if redteam_risk is None else _clamp01(float(redteam_risk))

    blended = (
        FICO_WEIGHTS["covenant_trust"] * ct
        + FICO_WEIGHTS["payment_history"] * ph
        + FICO_WEIGHTS["redteam"] * rt
    )
    blended = _clamp01(blended)
    score = int(round(FICO_MIN + (FICO_MAX - FICO_MIN) * blended))
    score = max(FICO_MIN, min(FICO_MAX, score))

    return AgentScore(
        agent_id=agent_id,
        score=score,
        factors={
            "covenant_trust": ct,
            "payment_history": ph,
            "redteam": rt,
            "signal": blended,
        },
        computed_ts=computed_ts,
    )


def web_of_trust_score(
    registry: Any,
    vouchers: dict[str, list[str]],
    *,
    alpha: float = 0.5,
) -> dict[str, float]:
    """Thin wrapper over :meth:`CovenantRegistry.web_of_trust`.

    Propagates covenant trust one hop across the vouching graph and returns
    ``{agent_id -> propagated_trust}``. Exposed here so reputation callers get the
    web-of-trust blend from the same surface as :func:`agent_fico` without
    reaching into :mod:`openmoe_bft.covenants` directly. Pass the propagated value
    in as ``covenant_trust`` to fold social vouching into an Agent FICO.
    """
    return registry.web_of_trust(vouchers, alpha=alpha)


@dataclass(frozen=True)
class OutcomeSettlement:
    """The result of settling an :class:`OutcomeBilling` escrow.

    Attributes
    ----------
    released:
        ``True`` if the outcome met the predicate and payment was released to the
        payee; ``False`` if it failed and the escrow was refunded to the payer.
    amount_atomic:
        The escrowed amount, in the network's atomic unit.
    payer / payee:
        The agents on each side of the escrow.
    outcome_ok:
        The boolean the caller-supplied predicate returned for the attested outcome.
    receipt:
        A tamper-evident :class:`~openmoe_bft.receipts.Receipt` sealing this
        settlement (always present — the settlement is itself auditable).
    """

    released: bool
    amount_atomic: int
    payer: str
    payee: str
    outcome_ok: bool
    receipt: Receipt


@dataclass
class OutcomeBilling:
    """Outcome-based billing: escrow now, pay only for a **verified** outcome.

    The x402 gap this fills: a normal x402 call pays on *invocation*. Here an
    agent escrows ``amount_atomic`` for a tool call; the tool's result is later
    **attested** (the attestation is sealed as a receipt); :meth:`settle` then
    releases the payment to the payee **only if** a caller-supplied predicate
    accepts the attested outcome, otherwise it refunds the payer. Pure and
    deterministic; every settlement is sealed into a
    :class:`~openmoe_bft.receipts.AuditChain` so it is independently verifiable.

    Construct with the escrow terms, then call :meth:`settle` with the attested
    outcome and the predicate. The instance is single-shot: a second
    :meth:`settle` raises (an escrow settles exactly once).
    """

    payer: str
    payee: str
    amount_atomic: int
    tool_call: str
    trace_id: str = "outcome-billing"
    chain: AuditChain = field(default_factory=AuditChain)
    _settled: bool = field(default=False, init=False, repr=False)

    def settle(
        self,
        outcome: dict[str, Any],
        predicate: Callable[[dict[str, Any]], bool],
        *,
        timestamp: int | float,
        signer_key: str | bytes | None = None,
    ) -> OutcomeSettlement:
        """Attest ``outcome``, apply ``predicate``, release or refund, seal a receipt.

        ``predicate(outcome) -> bool`` is the caller's acceptance test (e.g. "the
        compliance report says ``compliant is True``"). If it returns truthy the
        ``amount_atomic`` is released to ``payee``; otherwise it is refunded to
        ``payer``. Either way an attestation receipt is appended to :attr:`chain`
        (optionally HMAC-signed with ``signer_key``) and returned inside the
        :class:`OutcomeSettlement`. ``timestamp`` is caller-supplied (hermetic).

        Raises
        ------
        RuntimeError
            If this escrow has already been settled.
        """
        if self._settled:
            raise RuntimeError("escrow already settled (an escrow settles exactly once)")

        outcome_ok = bool(predicate(outcome))
        direction = "release" if outcome_ok else "refund"
        beneficiary = self.payee if outcome_ok else self.payer

        payload = {
            "kind": "settled_payment",
            "billing": "outcome_based",
            "tool_call": self.tool_call,
            "payer": self.payer,
            "payee": self.payee,
            # The agent credited by this settlement — so agent_fico's
            # payment-history reader counts a *released* payment toward the payee.
            "agent_id": beneficiary,
            "amount_atomic": self.amount_atomic,
            "direction": direction,
            "released": outcome_ok,
            "outcome": outcome,
        }
        receipt = self.chain.append(
            payload,
            trace_id=self.trace_id,
            timestamp=timestamp,
            signer_key=signer_key,
        )

        self._settled = True
        return OutcomeSettlement(
            released=outcome_ok,
            amount_atomic=self.amount_atomic,
            payer=self.payer,
            payee=self.payee,
            outcome_ok=outcome_ok,
            receipt=receipt,
        )
