"""Harmony Arena — quantified evolutionary A/B selection.

Hermetic: stdlib only, no clock, no network, no randomness. Timestamps are
passed explicitly; all scoring is pure/deterministic.
"""

import math

import pytest

from openmoe_bft.harmony import (
    DEFAULT_METRICS,
    DEFAULT_COMPLIANCE_FLOOR,
    HarmonyMetric,
    INSUFFICIENT_DATA,
    KEEP_BOTH,
    KILL,
    PROMOTE,
    SelectionVerdict,
    ShadowArena,
    VariantResult,
    _two_proportion_z,
    _z_crit,
    harmony_score,
    seal_verdict,
)
from openmoe_bft.receipts import AuditChain


# A high-compliance baseline so the guard-bee gate doesn't fire unless we want it.
def _vr(vid, *, accuracy, n, tok=100.0, sat=0.8, rev=0.5, compliance=0.99):
    return VariantResult(
        variant_id=vid,
        per_metric_values={
            "accuracy": accuracy,
            "token_efficiency": tok,
            "user_satisfaction": sat,
            "revenue_impact": rev,
            "compliance": compliance,
        },
        n_trials=n,
    )


# ── harmony_score ───────────────────────────────────────────────────


def test_default_metrics_weights_sum_to_one():
    assert math.isclose(sum(m.weight for m in DEFAULT_METRICS), 1.0)


def test_bad_weights_raise():
    bad = (HarmonyMetric("a", 0.4), HarmonyMetric("b", 0.4))
    with pytest.raises(ValueError):
        harmony_score(VariantResult("x", {"a": 1, "b": 1}), bad)


def test_harmony_score_normalizes_and_weights():
    # Two variants; min-max normalization across the cohort.
    best = _vr("best", accuracy=1.0, n=0, tok=50.0, sat=1.0, rev=1.0, compliance=1.0)
    worst = _vr("worst", accuracy=0.0, n=0, tok=150.0, sat=0.0, rev=0.0, compliance=0.0)
    cohort = [best, worst]
    # best is the max on every higher-is-better metric and the min token cost ->
    # normalizes to 1.0 on every axis -> weighted sum == 1.0.
    assert math.isclose(harmony_score(best, peers=cohort), 1.0, abs_tol=1e-9)
    # worst is the opposite extreme on every axis -> 0.0.
    assert math.isclose(harmony_score(worst, peers=cohort), 0.0, abs_tol=1e-9)


def test_token_efficiency_is_lower_is_better():
    # Same on everything except tokens; the cheaper-token variant must score higher.
    cheap = _vr("cheap", accuracy=0.8, n=0, tok=50.0)
    pricey = _vr("pricey", accuracy=0.8, n=0, tok=200.0)
    cohort = [cheap, pricey]
    assert harmony_score(cheap, peers=cohort) > harmony_score(pricey, peers=cohort)


def test_single_variant_scores_neutral_half():
    # No cohort spread -> every metric is the neutral 0.5 -> score 0.5.
    assert math.isclose(harmony_score(_vr("solo", accuracy=0.9, n=0)), 0.5)


# ── two-proportion z math (hand-computed) ──────────────────────────


def test_two_proportion_z_against_hand_value():
    # p1=.50 n1=100, p2=.70 n2=100 -> pooled .60, se=sqrt(.6*.4*.02)=.069282,
    # z=(.70-.50)/.069282 = 2.8868 (hand-computed).
    z = _two_proportion_z(0.50, 100, 0.70, 100)
    assert math.isclose(z, 2.8868, abs_tol=1e-3)


def test_z_crit_table():
    assert _z_crit(0.05) == 1.96
    assert _z_crit(0.10) == 1.645
    assert _z_crit(0.01) == 2.576
    with pytest.raises(ValueError):
        _z_crit(0.042)


def test_two_proportion_z_zero_when_degenerate():
    assert _two_proportion_z(0.5, 0, 0.5, 100) == 0.0  # empty arm
    assert _two_proportion_z(1.0, 100, 1.0, 100) == 0.0  # pooled==1 -> se 0


# ── selection: PROMOTE on a clear, large-sample win ─────────────────


def test_large_sample_clear_winner_promotes():
    arena = ShadowArena()
    arena.register(_vr("champ", accuracy=0.50, n=400))
    arena.register(_vr("chall", accuracy=0.70, n=400))
    v = arena.select("champ", "chall", primary_metric="accuracy", alpha=0.05)
    assert v.decision == PROMOTE
    assert v.winner_id == "chall"
    assert v.significant is True
    assert v.z > v.z_crit


# ── THE key test: a tiny-sample lead must NOT kill (no noise kills) ─


def test_tiny_sample_lead_is_insufficient_data_not_kill():
    # Same 20-point accuracy lead as above, but only a handful of trials/arm.
    arena = ShadowArena()
    arena.register(_vr("champ", accuracy=0.50, n=8))
    arena.register(_vr("chall", accuracy=0.70, n=8))
    v = arena.select("champ", "chall", primary_metric="accuracy", alpha=0.05)
    assert v.decision == INSUFFICIENT_DATA
    assert v.winner_id is None
    assert v.killed_id is None  # we did NOT kill a possibly-good variant on noise


def test_real_but_not_significant_lead_keeps_both():
    # Enough trials to be powered, but the accuracy gap is small enough that the
    # z-test is not significant -> ensemble, do not promote, do not kill.
    arena = ShadowArena()
    arena.register(_vr("champ", accuracy=0.50, n=40))
    arena.register(_vr("chall", accuracy=0.55, n=40))
    v = arena.select("champ", "chall", primary_metric="accuracy", alpha=0.05)
    assert v.decision == KEEP_BOTH
    assert v.significant is False
    assert v.killed_id is None


# ── guard-bee compliance gate (hard) ────────────────────────────────


def test_subfloor_compliance_challenger_is_killed_regardless():
    # Challenger is wildly better on accuracy with a huge sample, BUT below the
    # compliance floor -> KILL, no matter what.
    arena = ShadowArena()
    arena.register(_vr("champ", accuracy=0.50, n=1000, compliance=0.99))
    arena.register(_vr("chall", accuracy=0.99, n=1000, compliance=0.80))
    v = arena.select("champ", "chall", primary_metric="accuracy", alpha=0.05)
    assert v.decision == KILL
    assert v.killed_id == "chall"
    assert v.winner_id == "champ"
    assert "guard-bee" in v.reason


def test_subfloor_compliance_champion_promotes_compliant_challenger():
    arena = ShadowArena()
    arena.register(_vr("champ", accuracy=0.90, n=1000, compliance=0.50))
    arena.register(_vr("chall", accuracy=0.60, n=1000, compliance=0.99))
    v = arena.select("champ", "chall", primary_metric="accuracy", alpha=0.05)
    assert v.decision == PROMOTE
    assert v.winner_id == "chall"


def test_compliance_floor_default_is_090():
    assert DEFAULT_COMPLIANCE_FLOOR == 0.90


# ── score_all ranking ───────────────────────────────────────────────


def test_score_all_ranks_best_first():
    arena = ShadowArena()
    arena.register(_vr("low", accuracy=0.4, n=0))
    arena.register(_vr("high", accuracy=0.9, n=0))
    ranked = arena.score_all()
    assert ranked[0][0] == "high"
    assert ranked[-1][0] == "low"
    assert ranked[0][1] >= ranked[-1][1]


# ── seal_verdict appends a verifiable receipt ───────────────────────


def test_seal_verdict_appends_verifiable_receipt():
    arena = ShadowArena()
    arena.register(_vr("champ", accuracy=0.50, n=400))
    arena.register(_vr("chall", accuracy=0.70, n=400))
    v = arena.select("champ", "chall")
    assert isinstance(v, SelectionVerdict)

    chain = AuditChain()
    r = seal_verdict(v, chain, timestamp=1000, signer_key="k")
    assert chain.verify().ok
    assert r.payload["harmony_verdict"]["decision"] == PROMOTE
    assert chain.verify_signatures({0: "k"}).ok


def test_seal_verdict_detects_tamper():
    arena = ShadowArena()
    arena.register(_vr("champ", accuracy=0.50, n=400))
    arena.register(_vr("chall", accuracy=0.70, n=400))
    chain = AuditChain()
    seal_verdict(arena.select("champ", "chall"), chain, timestamp=1)
    # Mutate the sealed payload -> chain must detect it.
    chain.receipts[0].payload["harmony_verdict"]["decision"] = KILL
    assert not chain.verify().ok
