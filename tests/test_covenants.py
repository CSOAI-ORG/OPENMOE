"""Agent covenant protocol + web-of-trust trust scoring (OpenMoE-BFT Empire).

Hermetic: stdlib only, no clock, no randomness, no HOME I/O. Timestamps are
passed explicitly (1000, 1001, ...) — never read from the clock.
"""

import pytest

from openmoe_bft.covenants import (
    Action,
    Breach,
    Covenant,
    CovenantRegistry,
    NO_ACTION_BASELINE,
    SEVERITY_PENALTY,
    expert_covenants,
)


def _act(agent_id, name, payload=None, *, action_id="a", timestamp=1000):
    return Action(
        action_id=action_id,
        agent_id=agent_id,
        action_name=name,
        payload=payload or {},
        timestamp=timestamp,
    )


# ── Inscription + deterministic content address ───────────────────

def test_inscribe_returns_covenant_and_stores_latest():
    reg = CovenantRegistry()
    cov = Covenant.inscribe(
        agent_id="agent-1", allowed_actions={"read", "write"}, timestamp=1000
    )
    assert reg.inscribe(cov) is cov
    assert reg.covenant_for("agent-1") is cov


def test_deterministic_covenant_id_same_content():
    # Same declared content + timestamp -> identical id, regardless of the
    # iteration order of the allowed_actions collection.
    a = Covenant.inscribe(
        agent_id="x", allowed_actions=["read", "write"], timestamp=1000
    )
    b = Covenant.inscribe(
        agent_id="x", allowed_actions=["write", "read"], timestamp=1000
    )
    assert a.covenant_id == b.covenant_id
    assert a.inscription_hash == a.covenant_id
    assert len(a.covenant_id) == 64  # SHA-256 hex
    # Changing any field changes the id.
    c = Covenant.inscribe(
        agent_id="x", allowed_actions=["read", "write"], timestamp=1001
    )
    assert c.covenant_id != a.covenant_id


def test_latest_covenant_replaces_prior():
    reg = CovenantRegistry()
    reg.inscribe(Covenant.inscribe(agent_id="a", allowed_actions={"read"}, timestamp=1000))
    reg.inscribe(Covenant.inscribe(agent_id="a", allowed_actions={"write"}, timestamp=1001))
    assert reg.covenant_for("a").allowed_actions == frozenset({"write"})


# ── check(): compliant / breaches ─────────────────────────────────

def test_compliant_action_returns_none():
    reg = CovenantRegistry()
    reg.inscribe(
        Covenant.inscribe(agent_id="a", allowed_actions={"read"}, timestamp=1000)
    )
    assert reg.check(_act("a", "read")) is None


def test_disallowed_action_is_critical_breach():
    reg = CovenantRegistry()
    reg.inscribe(
        Covenant.inscribe(agent_id="a", allowed_actions={"read"}, timestamp=1000)
    )
    breach = reg.check(_act("a", "delete"))
    assert isinstance(breach, Breach)
    assert breach.severity == "critical"
    assert "delete" in breach.reason


def test_constraint_violation_is_major_breach():
    reg = CovenantRegistry()
    reg.inscribe(
        Covenant.inscribe(
            agent_id="a",
            allowed_actions={"spend"},
            constraints={"max_cost_usd": 1.0},
            timestamp=1000,
        )
    )
    over = reg.check(_act("a", "spend", {"cost_usd": 2.5}))
    assert over is not None and over.severity == "major"
    # At/under the limit is compliant.
    assert reg.check(_act("a", "spend", {"cost_usd": 1.0})) is None
    assert reg.check(_act("a", "spend", {"cost_usd": 0.5})) is None


def test_no_covenant_on_file_is_critical_breach():
    reg = CovenantRegistry()
    breach = reg.check(_act("ghost", "read"))
    assert breach is not None
    assert breach.severity == "critical"
    assert breach.reason == "no covenant inscribed"
    assert breach.covenant_id is None


# ── record(): append-only logs + trust degradation ────────────────

def test_record_appends_to_both_logs():
    reg = CovenantRegistry()
    reg.inscribe(
        Covenant.inscribe(agent_id="a", allowed_actions={"read"}, timestamp=1000)
    )
    reg.record(_act("a", "read", action_id="ok", timestamp=1000))      # compliant
    reg.record(_act("a", "nuke", action_id="bad", timestamp=1001))     # breach
    assert len(reg.actions_for("a")) == 2
    breaches = reg.breaches_for("a")
    assert len(breaches) == 1
    assert breaches[0].action_id == "bad"


def test_trust_score_drops_with_breach_severity():
    # A critical breach drops trust more than a minor one.
    reg_crit = CovenantRegistry()
    reg_crit.inscribe(
        Covenant.inscribe(agent_id="a", allowed_actions={"read"}, timestamp=1000)
    )
    reg_crit.record(_act("a", "delete"))  # critical (not allowed)
    crit_score = reg_crit.trust_score("a")

    reg_minor = CovenantRegistry()
    reg_minor.inscribe(
        Covenant.inscribe(agent_id="b", allowed_actions={"read"}, timestamp=1000)
    )
    # Manually fabricate a minor breach via record path is not possible (no
    # minor rule), so assert the penalty ordering directly and via critical math.
    assert SEVERITY_PENALTY["critical"] > SEVERITY_PENALTY["major"] > SEVERITY_PENALTY["minor"]
    assert crit_score == pytest.approx(1.0 - SEVERITY_PENALTY["critical"])

    # A major breach drops less than a critical one.
    reg_major = CovenantRegistry()
    reg_major.inscribe(
        Covenant.inscribe(
            agent_id="c",
            allowed_actions={"spend"},
            constraints={"max_cost_usd": 1.0},
            timestamp=1000,
        )
    )
    reg_major.record(_act("c", "spend", {"cost_usd": 99.0}))  # major
    major_score = reg_major.trust_score("c")
    assert crit_score < major_score < 1.0


def test_trust_score_clamps_to_zero():
    reg = CovenantRegistry()
    reg.inscribe(
        Covenant.inscribe(agent_id="a", allowed_actions={"read"}, timestamp=1000)
    )
    for i in range(5):  # 5 criticals -> 1.0 - 2.5, clamped to 0.0
        reg.record(_act("a", "delete", action_id=f"x{i}", timestamp=1000 + i))
    assert reg.trust_score("a") == 0.0


def test_clean_agent_with_compliant_action_scores_one():
    reg = CovenantRegistry()
    reg.inscribe(
        Covenant.inscribe(agent_id="a", allowed_actions={"read"}, timestamp=1000)
    )
    reg.record(_act("a", "read"))
    assert reg.trust_score("a") == 1.0


def test_no_action_agent_scores_neutral_baseline():
    reg = CovenantRegistry()
    reg.inscribe(
        Covenant.inscribe(agent_id="a", allowed_actions={"read"}, timestamp=1000)
    )
    # Inscribed but never acted -> unproven baseline, not 1.0.
    assert reg.trust_score("a") == NO_ACTION_BASELINE
    assert NO_ACTION_BASELINE == 0.5


# ── web_of_trust: one-hop blend / propagation ─────────────────────

def test_web_of_trust_high_voucher_raises_mid_trust_agent():
    reg = CovenantRegistry()
    # mid-trust agent: one major breach -> 0.8
    reg.inscribe(
        Covenant.inscribe(
            agent_id="mid",
            allowed_actions={"spend"},
            constraints={"max_cost_usd": 1.0},
            timestamp=1000,
        )
    )
    reg.record(_act("mid", "spend", {"cost_usd": 5.0}))
    assert reg.trust_score("mid") == pytest.approx(0.8)

    # high-trust voucher: a clean compliant agent -> 1.0
    reg.inscribe(
        Covenant.inscribe(agent_id="high", allowed_actions={"read"}, timestamp=1000)
    )
    reg.record(_act("high", "read"))
    assert reg.trust_score("high") == 1.0

    wot = reg.web_of_trust({"mid": ["high"]})
    # 0.5 * 0.8 + 0.5 * 1.0 = 0.9 -> a high voucher lifts the mid agent.
    assert wot["mid"] == pytest.approx(0.9)
    assert wot["mid"] > reg.trust_score("mid")


def test_web_of_trust_low_voucher_does_not_inflate():
    reg = CovenantRegistry()
    # mid agent -> 0.8
    reg.inscribe(
        Covenant.inscribe(
            agent_id="mid",
            allowed_actions={"spend"},
            constraints={"max_cost_usd": 1.0},
            timestamp=1000,
        )
    )
    reg.record(_act("mid", "spend", {"cost_usd": 5.0}))

    # low-trust voucher: a critical-breach agent -> 0.5
    reg.inscribe(
        Covenant.inscribe(agent_id="low", allowed_actions={"read"}, timestamp=1000)
    )
    reg.record(_act("low", "delete"))
    assert reg.trust_score("low") == pytest.approx(0.5)

    wot = reg.web_of_trust({"mid": ["low"]})
    # 0.5 * 0.8 + 0.5 * 0.5 = 0.65 -> a low voucher pulls the blend DOWN,
    # never above the agent's own score.
    assert wot["mid"] == pytest.approx(0.65)
    assert wot["mid"] < reg.trust_score("mid")


def test_web_of_trust_no_vouchers_keeps_own_score():
    reg = CovenantRegistry()
    reg.inscribe(
        Covenant.inscribe(agent_id="a", allowed_actions={"read"}, timestamp=1000)
    )
    reg.record(_act("a", "read"))
    wot = reg.web_of_trust({"a": []})
    assert wot["a"] == reg.trust_score("a") == 1.0


# ── Layer-3 composition: experts -> covenants ─────────────────────

def test_expert_covenants_cover_all_14_with_audit_actions():
    covs = expert_covenants(timestamp=1000)
    assert len(covs) == 14
    cov1 = covs[1]
    assert cov1.agent_id == "expert:1"
    # Expert #1's a2a_field is metadata.riskAssessment.
    assert cov1.allowed_actions == frozenset({"audit:metadata.riskAssessment"})

    # The same expert covenant governs the same breach machinery.
    reg = CovenantRegistry()
    reg.inscribe(cov1)
    assert reg.check(_act("expert:1", "audit:metadata.riskAssessment")) is None
    bad = reg.check(_act("expert:1", "audit:something.else"))
    assert bad is not None and bad.severity == "critical"
