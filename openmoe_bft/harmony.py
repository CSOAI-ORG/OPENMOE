"""Harmony Arena — quantified evolutionary A/B selection (OpenMoE-BFT Empire).

Layer 3-adjacent "evolutionary harmony": spawn variants of an agent/expert,
**shadow-mirror** them on the *same* inputs, score each on a weighted basket of
metrics (a single ``[0,1]`` *harmony score*), then **promote** the winner,
**kill** the loser, or **ensemble** on a statistical tie. Selection is where the
weak provably die — but they must die on *evidence*, not on small-sample noise.

Why a significance gate (the real fix)
--------------------------------------
The naive brief rule — *"promote the challenger if its score beats the champion
by > 5%"* — is statistically wrong. On a handful of shadow trials a *better*
variant routinely loses (and a *worse* one routinely wins) by more than 5% from
pure sampling noise. Promoting / killing on that noise throws away good variants
and ships bad ones. So :meth:`ShadowArena.select` gates every promotion on a real
**two-proportion z-test** on the primary metric: the challenger is promoted only
when

1. its **harmony score beats** the champion's, **and**
2. the primary-metric difference is **statistically significant** at ``alpha``
   (``|z|`` past the critical value, ~1.96 for ``alpha=0.05``), **and**
3. it clears a caller-supplied ``min_uplift`` floor on the primary metric.

If the lead is real but the sample is too small to be significant, the verdict is
``KEEP_BOTH`` (ensemble — don't kill on noise) or ``INSUFFICIENT_DATA`` when even
detecting a moderate effect is underpowered. This is the genuine "quantify A/B
with harmony" answer.

The guard-bee gate (hard compliance floor)
------------------------------------------
Compliance is **not** a tradeable metric. Any variant whose ``compliance`` is
below ``compliance_floor`` (default ``0.90``) is auto-**KILLed** regardless of how
good it looks elsewhere — the "guard bee" rule: a single non-compliant forager
never enters the hive, however much nectar it carries.

Composition
-----------
Every promotion / kill is sealable as a tamper-evident
:class:`~openmoe_bft.receipts.Receipt` via :func:`seal_verdict`, mirroring
:mod:`openmoe_bft.a2a` / :mod:`openmoe_bft.reputation` — so an evolutionary
decision is auditable end-to-end. A :class:`VariantResult` may optionally carry a
:func:`~openmoe_bft.reputation.agent_fico` score or a
:attr:`~openmoe_bft.red_team.RedTeamReport.risk_score` folded in as a metric
value (kept optional — the module is transport- and signal-agnostic).

Hermeticity note: nothing here reads the clock or any randomness. ``timestamp``
is caller-supplied; all scoring is pure and deterministic. Stdlib only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .receipts import AuditChain, Receipt


__all__ = [
    "HarmonyMetric",
    "DEFAULT_METRICS",
    "DEFAULT_COMPLIANCE_FLOOR",
    "VariantResult",
    "SelectionVerdict",
    "ShadowArena",
    "harmony_score",
    "seal_verdict",
]


# Default compliance floor — the guard-bee threshold. A variant below this on the
# ``compliance`` metric is auto-killed regardless of everything else.
DEFAULT_COMPLIANCE_FLOOR = 0.90

# Minimum per-arm sample size below which a non-significant result is reported as
# INSUFFICIENT_DATA (underpowered) rather than KEEP_BOTH. ~30 successes/arm is the
# usual rule-of-thumb floor for the normal approximation of a proportion to hold.
_MIN_POWER_N = 30


# ── Metrics ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HarmonyMetric:
    """One weighted axis of the harmony score.

    Attributes
    ----------
    name:
        The metric key looked up in :attr:`VariantResult.per_metric_values`.
    weight:
        Its share of the harmony score, in ``[0,1]``. The active metric set's
        weights must sum to ~1.0 (validated in :func:`harmony_score`).
    higher_is_better:
        ``True`` if a larger raw value is better (e.g. accuracy); ``False`` if a
        smaller raw value is better (e.g. token cost), which is inverted during
        min-max normalization so "better" always maps toward ``1.0``.
    """

    name: str
    weight: float
    higher_is_better: bool = True


# The default basket mirrors the brief. token_efficiency is lower-is-better
# (fewer tokens == cheaper == better); everything else is higher-is-better.
# Weights sum to 1.0.
DEFAULT_METRICS: tuple[HarmonyMetric, ...] = (
    HarmonyMetric("accuracy", 0.30, higher_is_better=True),
    HarmonyMetric("token_efficiency", 0.20, higher_is_better=False),
    HarmonyMetric("user_satisfaction", 0.25, higher_is_better=True),
    HarmonyMetric("revenue_impact", 0.15, higher_is_better=True),
    HarmonyMetric("compliance", 0.10, higher_is_better=True),
)


# ── Variant results (fed in from shadow mirroring) ──────────────────


@dataclass(frozen=True)
class VariantResult:
    """A variant's measured metrics from shadow mirroring.

    The module is transport-agnostic: results are *fed in* — there is no real
    traffic here. ``per_metric_values`` maps each :class:`HarmonyMetric` name to
    a raw measured value (any scale; min-max normalized at scoring time).

    Attributes
    ----------
    variant_id:
        Identifier of the variant (champion or challenger).
    per_metric_values:
        ``{metric_name -> raw value}``. A value may be a proportion in ``[0,1]``
        (accuracy, compliance, user_satisfaction) or any scale (token counts,
        revenue). Missing metrics are treated as the worst observed value.
    n_trials:
        Number of shadow trials behind these measurements — the sample size the
        significance gate uses. More trials -> tighter confidence.
    """

    variant_id: str
    per_metric_values: dict[str, float]
    n_trials: int = 0

    def value(self, metric_name: str, default: float = 0.0) -> float:
        return float(self.per_metric_values.get(metric_name, default))


# ── Harmony score ───────────────────────────────────────────────────


def _validate_weights(metrics: "tuple[HarmonyMetric, ...] | list[HarmonyMetric]") -> None:
    total = sum(m.weight for m in metrics)
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(
            f"harmony metric weights must sum to 1.0, got {total!r}"
        )


def harmony_score(
    result: VariantResult,
    metrics: "tuple[HarmonyMetric, ...] | list[HarmonyMetric]" = DEFAULT_METRICS,
    *,
    peers: "list[VariantResult] | None" = None,
) -> float:
    """Weighted harmony score in ``[0,1]`` for ``result``. **Pure / deterministic.**

    Each metric is min-max normalized to ``[0,1]`` *across the variants being
    compared* (``peers``, which must include ``result`` — defaults to just
    ``result`` itself), respecting :attr:`HarmonyMetric.higher_is_better` (a
    lower-is-better metric is inverted so "better" maps toward ``1.0``). When all
    peers share a value on a metric (zero spread) that metric contributes the
    neutral ``0.5`` (it carries no discriminating signal). The normalized values
    are weighted by :attr:`HarmonyMetric.weight` and summed.

    With a single variant (no peers) every metric has zero spread, so the score
    is ``0.5`` — by design: a harmony score is *comparative*, only meaningful
    relative to the cohort being selected over (see :meth:`ShadowArena.score_all`).
    """
    _validate_weights(metrics)
    cohort = list(peers) if peers is not None else [result]
    if result not in cohort:
        cohort = cohort + [result]

    score = 0.0
    for m in metrics:
        vals = [r.value(m.name) for r in cohort]
        lo, hi = min(vals), max(vals)
        spread = hi - lo
        if spread <= 0:
            norm = 0.5  # no discriminating signal across the cohort
        else:
            raw = result.value(m.name)
            norm = (raw - lo) / spread
            if not m.higher_is_better:
                norm = 1.0 - norm
        score += m.weight * norm
    return score


# ── Two-proportion z-test (stdlib only) ─────────────────────────────


def _z_crit(alpha: float) -> float:
    """Two-sided critical z value for ``alpha``.

    Common alphas are hardcoded (no scipy): ``.10 -> 1.645``, ``.05 -> 1.96``,
    ``.01 -> 2.576``. Any other alpha raises — callers should pick a standard one
    so the test stays stdlib-only and transparent.
    """
    table = {0.10: 1.645, 0.05: 1.96, 0.01: 2.576}
    for a, z in table.items():
        if math.isclose(alpha, a, abs_tol=1e-9):
            return z
    raise ValueError(
        f"unsupported alpha {alpha!r}; use one of {sorted(table)} "
        "(stdlib-only critical-value table)"
    )


def _two_proportion_z(p1: float, n1: int, p2: float, n2: int) -> float:
    """Two-proportion z statistic ``(p2 - p1) / sqrt(p*(1-p)*(1/n1 + 1/n2))``.

    ``p`` is the pooled proportion ``(x1 + x2) / (n1 + n2)`` with
    ``x_i = round(p_i * n_i)``. Returns ``0.0`` when the standard error is zero
    (degenerate: empty samples or a pooled proportion of 0 or 1) — i.e. no
    detectable difference. A positive z means the *challenger* (``p2``) leads.
    """
    if n1 <= 0 or n2 <= 0:
        return 0.0
    x1 = round(p1 * n1)
    x2 = round(p2 * n2)
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2))
    if se == 0.0:
        return 0.0
    return (p2 - p1) / se


# ── Selection verdict ───────────────────────────────────────────────


# Decision constants.
PROMOTE = "PROMOTE"            # challenger provably better -> it replaces champion
KILL = "KILL"                  # a variant violated the compliance floor -> removed
KEEP_BOTH = "KEEP_BOTH"        # real-but-not-significant lead -> ensemble both
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # too few trials to decide -> gather more


@dataclass(frozen=True)
class SelectionVerdict:
    """The outcome of a champion-vs-challenger selection.

    Attributes
    ----------
    decision:
        One of :data:`PROMOTE`, :data:`KILL`, :data:`KEEP_BOTH`,
        :data:`INSUFFICIENT_DATA`.
    champion_id / challenger_id:
        The two variants compared.
    winner_id:
        The promoted variant on :data:`PROMOTE`; the *surviving* variant on
        :data:`KILL`; ``None`` for :data:`KEEP_BOTH` / :data:`INSUFFICIENT_DATA`.
    killed_id:
        The removed variant on :data:`KILL` (compliance guard-bee), else ``None``.
    primary_metric:
        The metric the significance test ran on.
    champion_harmony / challenger_harmony:
        The two harmony scores compared.
    z / z_crit:
        The two-proportion z statistic and the critical value for ``alpha``.
    significant:
        Whether ``|z| >= z_crit`` on the primary metric.
    reason:
        Human-readable explanation of the decision (every rule is documented here).
    """

    decision: str
    champion_id: str
    challenger_id: str
    winner_id: str | None
    killed_id: str | None
    primary_metric: str
    champion_harmony: float
    challenger_harmony: float
    z: float
    z_crit: float
    significant: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "champion_id": self.champion_id,
            "challenger_id": self.challenger_id,
            "winner_id": self.winner_id,
            "killed_id": self.killed_id,
            "primary_metric": self.primary_metric,
            "champion_harmony": self.champion_harmony,
            "challenger_harmony": self.challenger_harmony,
            "z": self.z,
            "z_crit": self.z_crit,
            "significant": self.significant,
            "reason": self.reason,
        }


# ── The arena ───────────────────────────────────────────────────────


class ShadowArena:
    """Register shadow-mirrored variants and select among them with significance.

    Variants and their :class:`VariantResult` measurements are *fed in* (the
    arena does not generate traffic). :meth:`score_all` ranks the cohort by
    :func:`harmony_score`; :meth:`select` runs the significance-gated,
    compliance-guarded champion-vs-challenger decision.
    """

    def __init__(
        self,
        metrics: "tuple[HarmonyMetric, ...] | list[HarmonyMetric]" = DEFAULT_METRICS,
        *,
        compliance_floor: float = DEFAULT_COMPLIANCE_FLOOR,
        compliance_metric: str = "compliance",
    ) -> None:
        _validate_weights(metrics)
        self.metrics = tuple(metrics)
        self.compliance_floor = compliance_floor
        self.compliance_metric = compliance_metric
        self._variants: dict[str, VariantResult] = {}

    def register(self, result: VariantResult) -> None:
        """Add (or replace) a variant's shadow result by ``variant_id``."""
        self._variants[result.variant_id] = result

    @property
    def variants(self) -> list[VariantResult]:
        """All registered results, id-sorted (deterministic ordering)."""
        return [self._variants[k] for k in sorted(self._variants)]

    def score_all(self) -> list[tuple[str, float]]:
        """Rank every registered variant by harmony score, best first.

        Each variant is scored against the *whole* registered cohort (min-max
        normalized across all peers), so the ranking is comparative. Ties break
        on ``variant_id`` for determinism.
        """
        cohort = self.variants
        scored = [
            (r.variant_id, harmony_score(r, self.metrics, peers=cohort))
            for r in cohort
        ]
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return scored

    def _compliance_of(self, result: VariantResult) -> float:
        return result.value(self.compliance_metric, default=0.0)

    def select(
        self,
        champion_id: str,
        challenger_id: str,
        *,
        primary_metric: str = "accuracy",
        alpha: float = 0.05,
        min_uplift: float = 0.0,
    ) -> SelectionVerdict:
        """Decide champion vs challenger with a significance gate + compliance guard.

        The decision rules, in order:

        1. **Guard-bee compliance gate (hard).** If the *challenger* is below
           :attr:`compliance_floor` on the compliance metric it is **KILLed**
           (winner = champion) regardless of every other metric. Else if the
           *champion* is below the floor and the challenger is compliant, the
           challenger is **PROMOTEd** (the incumbent is the non-compliant one and
           must go — the challenger is the surviving compliant forager). If both
           are below the floor, the challenger is still **KILLed** (a
           champion-vs-challenger call removes the challenger; the incumbent
           non-compliant champion is flagged in ``reason`` for a separate sweep).
        2. **Power check.** If either arm has fewer than ``_MIN_POWER_N`` trials
           the comparison is underpowered -> **INSUFFICIENT_DATA** (gather more;
           never kill on a handful of trials).
        3. **Significance + harmony + uplift (PROMOTE gate).** Compute the
           two-proportion z on ``primary_metric``. PROMOTE the challenger **only
           if** (a) its harmony score beats the champion's, **and** (b)
           ``z >= z_crit(alpha)`` (the lead is statistically significant and in
           the challenger's favour), **and** (c) the primary-metric uplift
           ``p_challenger - p_champion >= min_uplift``.
        4. **Otherwise KEEP_BOTH** — a real-looking but not-significant (or
           sub-uplift, or harmony-losing) lead is *ensembled*, not killed. This is
           exactly the case the naive "+5%" rule gets wrong.

        Raises
        ------
        KeyError
            If either id is not registered.
        """
        champ = self._variants[champion_id]
        chall = self._variants[challenger_id]
        cohort = [champ, chall]

        z_crit = _z_crit(alpha)
        h_champ = harmony_score(champ, self.metrics, peers=cohort)
        h_chall = harmony_score(chall, self.metrics, peers=cohort)

        p_champ = champ.value(primary_metric)
        p_chall = chall.value(primary_metric)
        z = _two_proportion_z(p_champ, champ.n_trials, p_chall, chall.n_trials)
        significant = abs(z) >= z_crit

        def verdict(decision, winner, killed, reason) -> SelectionVerdict:
            return SelectionVerdict(
                decision=decision,
                champion_id=champion_id,
                challenger_id=challenger_id,
                winner_id=winner,
                killed_id=killed,
                primary_metric=primary_metric,
                champion_harmony=h_champ,
                challenger_harmony=h_chall,
                z=z,
                z_crit=z_crit,
                significant=significant,
                reason=reason,
            )

        # ── Rule 1: guard-bee compliance gate (hard, overrides everything) ──
        champ_ok = self._compliance_of(champ) >= self.compliance_floor
        chall_ok = self._compliance_of(chall) >= self.compliance_floor
        if not chall_ok:
            return verdict(
                KILL,
                winner=champion_id,
                killed=challenger_id,
                reason=(
                    f"challenger {challenger_id!r} compliance "
                    f"{self._compliance_of(chall):.3f} < floor "
                    f"{self.compliance_floor:.2f} (guard-bee gate): KILLed "
                    "regardless of other metrics"
                    + ("" if champ_ok else
                       f"; NOTE champion {champion_id!r} is ALSO sub-floor "
                       "and should be swept separately")
                ),
            )
        if not champ_ok:  # challenger compliant, champion is not -> challenger wins
            return verdict(
                PROMOTE,
                winner=challenger_id,
                killed=None,
                reason=(
                    f"champion {champion_id!r} compliance "
                    f"{self._compliance_of(champ):.3f} < floor "
                    f"{self.compliance_floor:.2f} while challenger is compliant: "
                    "PROMOTE the compliant challenger (guard-bee gate)"
                ),
            )

        # ── Rule 2: power check ──
        if champ.n_trials < _MIN_POWER_N or chall.n_trials < _MIN_POWER_N:
            return verdict(
                INSUFFICIENT_DATA,
                winner=None,
                killed=None,
                reason=(
                    f"under-powered: need >= {_MIN_POWER_N} trials/arm, have "
                    f"champion={champ.n_trials}, challenger={chall.n_trials}; "
                    "NOT killing a variant on small-sample noise — gather more"
                ),
            )

        # ── Rule 3: PROMOTE gate (harmony AND significance AND uplift) ──
        uplift = p_chall - p_champ
        harmony_wins = h_chall > h_champ
        clears_uplift = uplift >= min_uplift
        if harmony_wins and significant and z > 0 and clears_uplift:
            return verdict(
                PROMOTE,
                winner=challenger_id,
                killed=None,
                reason=(
                    f"challenger PROMOTEd: harmony {h_chall:.3f} > {h_champ:.3f}, "
                    f"primary-metric z={z:.3f} >= z_crit={z_crit} (significant at "
                    f"alpha={alpha}), uplift {uplift:+.3f} >= min_uplift "
                    f"{min_uplift:.3f}"
                ),
            )

        # ── Rule 4: KEEP_BOTH (ensemble) — the anti-noise default ──
        why: list[str] = []
        if not harmony_wins:
            why.append(
                f"harmony {h_chall:.3f} !> champion {h_champ:.3f}"
            )
        if not significant:
            why.append(
                f"primary-metric |z|={abs(z):.3f} < z_crit={z_crit} "
                f"(NOT significant at alpha={alpha} — lead may be noise)"
            )
        elif z <= 0:
            why.append("significant difference favours the champion")
        if not clears_uplift:
            why.append(f"uplift {uplift:+.3f} < min_uplift {min_uplift:.3f}")
        return verdict(
            KEEP_BOTH,
            winner=None,
            killed=None,
            reason="ensemble (KEEP_BOTH): " + "; ".join(why),
        )


# ── Optional composition: seal a verdict as a tamper-evident receipt ──


def seal_verdict(
    verdict: SelectionVerdict,
    chain: AuditChain,
    timestamp: int | float,
    trace_id: str = "harmony-selection",
    signer_key: "str | bytes | None" = None,
) -> Receipt:
    """Append ``verdict`` to ``chain`` as a receipt; return that :class:`Receipt`.

    Makes an evolutionary promotion / kill tamper-evident: the verdict's
    ``to_dict`` becomes the sealed receipt payload, hash-chained to its
    predecessor (mirrors :func:`openmoe_bft.a2a.seal_verdict` /
    :class:`openmoe_bft.reputation.OutcomeBilling`). ``timestamp`` is
    caller-supplied (hermetic); pass ``signer_key`` to HMAC-sign. After this call
    ``chain.verify().ok`` holds.
    """
    return chain.append(
        payload={"harmony_verdict": verdict.to_dict()},
        trace_id=trace_id,
        timestamp=timestamp,
        signer_key=signer_key,
    )
