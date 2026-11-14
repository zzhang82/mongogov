import pytest

from govmem import config, policy


def test_veto_evidence_boundary():
    assert policy.decide(0.90, 0.49) == "veto"
    assert policy.decide(0.90, 0.50) != "veto"


def test_veto_similarity_boundary():
    assert policy.decide(0.29, 0.26) == "none"
    assert policy.decide(0.30, 0.26) == "veto"


def test_fast_boundary():
    assert policy.decide(0.76, 0.85) == "trusted"
    assert policy.decide(0.77, 0.85) == "fast"


def test_fast_evidence_boundary():
    assert policy.decide(0.90, 0.79) == "trusted"
    assert policy.decide(0.90, 0.80) == "fast"


def test_trusted_boundary():
    assert policy.decide(0.54, 0.85) == "none"
    assert policy.decide(0.55, 0.60) == "trusted"
    assert policy.decide(0.55, 0.59) == "none"


def test_veto_wins_over_fast():
    assert policy.decide(0.99, 0.49) == "veto"


@pytest.mark.parametrize("path", ["fast", "trusted", "catalog", "none", "veto"])
def test_confidence_unverified(path):
    assert policy.confidence(path, similarity=0.95, evidence=0.95, verified=False) == 0.0


def test_confidence_verified():
    assert policy.confidence("fast", similarity=0.85, evidence=0.90, verified=True) == 0.85
    assert policy.confidence("catalog", verified=True) == policy.CATALOG_CONFIDENCE


def test_must_hold():
    assert policy.must_hold(0.69) is True
    assert policy.must_hold(0.70) is False


def test_config_thresholds():
    assert config.FAST_SIM == 0.77
    assert config.FAST_EVIDENCE == 0.80
    assert config.TRUST_SIM == 0.55
    assert config.TRUST_EVIDENCE == 0.60
    assert config.VETO_SIM == 0.30
    assert config.VETO_EVIDENCE == 0.50
    assert config.HOLD_CONFIDENCE == 0.70
    assert config.PROBE_ABORT_SIM == 0.75
