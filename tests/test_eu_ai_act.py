"""EU AI Act check-registry integrity + evaluate() scoring. Hermetic."""

import pytest

from openmoe_bft.eu_ai_act import (
    Article,
    Check,
    CHECKS,
    ComplianceReport,
    VALID_SEVERITIES,
    evaluate,
    checks_for_article,
    checks_by_severity,
)


# ── Registry integrity ──────────────────────────────────────────

def test_ids_unique():
    ids = [c.id for c in CHECKS]
    assert len(set(ids)) == len(ids)


def test_at_least_fifteen_checks():
    assert len(CHECKS) >= 15


def test_every_article_represented_with_at_least_two_checks():
    for article in Article:
        article_checks = checks_for_article(article)
        assert len(article_checks) >= 2, f"{article} has < 2 checks"


def test_all_seven_articles_used():
    used = {c.article for c in CHECKS}
    assert used == set(Article)
    assert len(Article) == 7


def test_severities_valid():
    for c in CHECKS:
        assert c.severity in VALID_SEVERITIES


def test_evidence_fields_follow_metadata_convention():
    for c in CHECKS:
        assert c.evidence_field.startswith("metadata.")
        assert "." in c.evidence_field


def test_id_naming_convention():
    for c in CHECKS:
        assert c.id.startswith("EUAIACT-ART")


def test_at_least_one_blocker_per_lifecycle_critical_article():
    # Art 9, 10, 14 each carry hard high-risk obligations -> must have a blocker.
    for article in (Article.ART_9, Article.ART_10, Article.ART_14):
        sevs = {c.severity for c in checks_for_article(article)}
        assert "blocker" in sevs


# ── evaluate(): full / empty / partial ──────────────────────────

def _full_evidence():
    return {c.evidence_field: "present" for c in CHECKS}


def test_full_evidence_scores_one_no_failures():
    report = evaluate(_full_evidence())
    assert isinstance(report, ComplianceReport)
    assert report.score == 1.0
    assert report.failed == []
    assert report.blocking_failures == []
    assert len(report.passed) == len(CHECKS)
    assert report.compliant


def test_empty_evidence_scores_zero_all_blockers_blocking():
    report = evaluate({})
    assert report.score == 0.0
    assert report.passed == []
    assert len(report.failed) == len(CHECKS)
    expected_blockers = [c for c in CHECKS if c.severity == "blocker"]
    assert set(report.blocking_failures) == set(expected_blockers)
    assert not report.compliant


def test_none_evidence_handled():
    report = evaluate(None)
    assert report.score == 0.0
    assert len(report.failed) == len(CHECKS)


def test_partial_evidence_strictly_between():
    # Provide evidence for exactly half the checks.
    half = list(CHECKS)[: len(CHECKS) // 2]
    evidence = {c.evidence_field: True for c in half}
    report = evaluate(evidence)
    assert 0.0 < report.score < 1.0
    passed_ids = {c.id for c in report.passed}
    failed_ids = {c.id for c in report.failed}
    assert passed_ids == {c.id for c in half}
    assert passed_ids.isdisjoint(failed_ids)
    assert passed_ids | failed_ids == {c.id for c in CHECKS}


def test_falsy_evidence_value_fails_check():
    c = CHECKS[0]
    report = evaluate({c.evidence_field: ""})  # empty string is falsy -> fail
    assert c in report.failed
    assert c not in report.passed


# ── Severity weighting ──────────────────────────────────────────

def test_blocker_failure_drops_score_more_than_minor():
    blocker = next(c for c in CHECKS if c.severity == "blocker")
    minor = next(c for c in CHECKS if c.severity == "minor")

    full = _full_evidence()

    drop_blocker = dict(full)
    del drop_blocker[blocker.evidence_field]
    drop_minor = dict(full)
    del drop_minor[minor.evidence_field]

    report_blocker = evaluate(drop_blocker)
    report_minor = evaluate(drop_minor)

    # Dropping a blocker must hurt the score strictly more than a minor.
    assert report_blocker.score < report_minor.score < 1.0
    assert blocker in report_blocker.blocking_failures
    assert report_minor.blocking_failures == []


def test_weight_ordering():
    blocker = next(c for c in CHECKS if c.severity == "blocker")
    major = next(c for c in CHECKS if c.severity == "major")
    minor = next(c for c in CHECKS if c.severity == "minor")
    assert blocker.weight > major.weight > minor.weight


# ── Helpers ──────────────────────────────────────────────────────

def test_checks_for_article_subset():
    art9 = checks_for_article(Article.ART_9)
    assert art9
    assert all(c.article == Article.ART_9 for c in art9)
    assert set(art9).issubset(set(CHECKS))


def test_checks_by_severity_subset_and_partition():
    buckets = {sev: checks_by_severity(sev) for sev in VALID_SEVERITIES}
    for sev, bucket in buckets.items():
        assert all(c.severity == sev for c in bucket)
    total = sum(len(b) for b in buckets.values())
    assert total == len(CHECKS)


def test_checks_by_severity_unknown_returns_empty():
    assert checks_by_severity("catastrophic") == []
