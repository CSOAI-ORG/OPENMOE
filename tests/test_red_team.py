"""Red-team orchestration backend (Expert #9). Hermetic — no clock, no RNG."""

import pytest

from openmoe_bft.red_team import (
    AttackStrategy,
    AttackResult,
    RedTeamOrchestrator,
    RedTeamReport,
    STRATEGIES,
    VALID_CATEGORIES,
    VALID_SEVERITIES,
    default_orchestrator,
)


# ── Deterministic heuristic probe factory ──────────────────────
#
# The target is a dict carrying a "defended" set of strategy ids. A probe
# succeeds (attack lands) iff the strategy id is NOT in the defended set. No
# randomness, no clock — the timestamp comes from the context.

def _probe_for(strategy):
    def probe(target, context):
        defended = set(target.get("defended", ()))
        succeeded = strategy.id not in defended
        return AttackResult(
            strategy_id=strategy.id,
            target_id=target.get("id", "tgt"),
            succeeded=succeeded,
            severity=strategy.severity_if_successful,
            evidence=("landed" if succeeded else "blocked") + f": {strategy.name}",
            timestamp=context.get("timestamp", 0),
        )
    return probe


def _orch():
    return default_orchestrator(probe_for=_probe_for)


# ── Registry integrity ─────────────────────────────────────────

def test_strategy_ids_unique():
    ids = [s.id for s in STRATEGIES]
    assert len(set(ids)) == len(ids)
    assert len(ids) >= 8


def test_categories_and_severities_valid():
    for s in STRATEGIES:
        assert s.category in VALID_CATEGORIES, s.id
        assert s.severity_if_successful in VALID_SEVERITIES, s.id


def test_at_least_one_strategy_per_category():
    present = {s.category for s in STRATEGIES}
    assert present == set(VALID_CATEGORIES)


def test_strategies_by_category():
    orch = _orch()
    apis = orch.strategies_by_category("api_abuse")
    assert apis, "expected at least one api_abuse strategy"
    assert all(s.category == "api_abuse" for s in apis)


def test_register_replaces_by_id():
    orch = RedTeamOrchestrator()
    s = AttackStrategy("X", "x", "jailbreak", "d", "low", probe=_probe_for)
    orch.register(s)
    orch.register(AttackStrategy("X", "x2", "jailbreak", "d2", "high", probe=_probe_for))
    assert len(orch.strategies) == 1
    assert orch.strategies[0].name == "x2"


# ── run() ───────────────────────────────────────────────────────

def test_run_executes_all_strategies_one_result_each():
    orch = _orch()
    target = {"id": "agent-1", "defended": set()}
    results = orch.run(target, context={"timestamp": 1000})
    assert len(results) == len(STRATEGIES)
    assert {r.strategy_id for r in results} == {s.id for s in STRATEGIES}
    assert all(isinstance(r, AttackResult) for r in results)
    assert all(r.timestamp == 1000 for r in results)


def test_run_is_deterministically_ordered():
    orch = _orch()
    target = {"id": "agent-1", "defended": set()}
    a = [r.strategy_id for r in orch.run(target)]
    b = [r.strategy_id for r in orch.run(target)]
    assert a == b == sorted(a)


def test_run_unbound_probe_raises():
    orch = RedTeamOrchestrator()
    orch.register(AttackStrategy("Y", "y", "jailbreak", "d", "low"))
    with pytest.raises(ValueError):
        orch.run({"id": "t"})


def test_run_explicit_strategy_subset():
    orch = _orch()
    subset = orch.strategies_by_category("multi_turn")
    results = orch.run({"id": "t", "defended": set()}, strategies=subset)
    assert len(results) == len(subset)


# ── report() risk_score ─────────────────────────────────────────

def test_risk_score_1_when_all_defended():
    orch = _orch()
    target = {"id": "fortress", "defended": {s.id for s in STRATEGIES}}
    report = orch.report(orch.run(target))
    assert report.risk_score == 1.0
    assert report.succeeded == 0
    assert report.defended == report.total


def test_risk_score_0_when_nothing_defended():
    orch = _orch()
    target = {"id": "sieve", "defended": set()}
    report = orch.report(orch.run(target))
    assert report.risk_score == 0.0
    assert report.succeeded == report.total


def test_critical_success_hurts_more_than_low():
    orch = RedTeamOrchestrator()
    low = AttackStrategy("LOW", "low", "jailbreak", "d", "low")
    crit = AttackStrategy("CRIT", "crit", "data_exfil", "d", "critical")
    orch.register(low.with_probe(_probe_for(low)))
    orch.register(crit.with_probe(_probe_for(crit)))

    # Defend the critical, let the low through.
    rep_low_lands = orch.report(orch.run({"id": "t", "defended": {"CRIT"}}))
    # Defend the low, let the critical through.
    rep_crit_lands = orch.report(orch.run({"id": "t", "defended": {"LOW"}}))

    # A landed critical must drop the score below a landed low.
    assert rep_crit_lands.risk_score < rep_low_lands.risk_score


def test_empty_results_score_is_one():
    orch = _orch()
    assert orch.report([]).risk_score == 1.0


# ── report() by_severity + critical_findings ────────────────────

def test_by_severity_and_critical_findings():
    orch = _orch()
    target = {"id": "agent-1", "defended": set()}  # everything lands
    report = orch.report(orch.run(target))

    # Every successful attack counted under its severity.
    assert sum(report.by_severity.values()) == report.succeeded
    # All severity keys present.
    assert set(report.by_severity) == set(VALID_SEVERITIES)

    crit_ids = {s.id for s in STRATEGIES if s.severity_if_successful == "critical"}
    assert {r.strategy_id for r in report.critical_findings} == crit_ids
    assert report.by_severity["critical"] == len(crit_ids)


def test_critical_findings_empty_when_criticals_defended():
    orch = _orch()
    crit_ids = {s.id for s in STRATEGIES if s.severity_if_successful == "critical"}
    report = orch.report(orch.run({"id": "t", "defended": crit_ids}))
    assert report.critical_findings == []
    assert report.by_severity["critical"] == 0


# ── to_a2a_evidence shape ───────────────────────────────────────

def test_to_a2a_evidence_shape():
    orch = _orch()
    report = orch.report(orch.run({"id": "agent-1", "defended": set()}))
    evidence = orch.to_a2a_evidence(report)

    assert "metadata" in evidence
    assert "redTeamReport" in evidence["metadata"]
    rt = evidence["metadata"]["redTeamReport"]
    assert rt["targetId"] == "agent-1"
    assert rt["total"] == report.total
    assert rt["succeeded"] == report.succeeded
    assert rt["riskScore"] == report.risk_score
    assert set(rt["bySeverity"]) == set(VALID_SEVERITIES)
    assert isinstance(rt["criticalFindings"], list)


def test_report_to_dict_roundtrips_keys():
    orch = _orch()
    report = orch.report(orch.run({"id": "agent-1", "defended": set()}))
    d = report.to_dict()
    assert set(d) >= {
        "target_id", "total", "succeeded", "defended",
        "by_severity", "critical_findings", "risk_score", "results",
    }
    assert len(d["results"]) == report.total
