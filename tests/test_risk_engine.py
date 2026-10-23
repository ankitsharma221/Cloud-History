"""Tests for deletion risk evaluation rules and safety thresholds."""

import pytest
from engine.linker import Linker
from engine.risk_engine import RiskEngine
from engine.models import RiskLevel


def test_production_active_ec2_is_high_risk():
    linker = Linker()
    engine = RiskEngine()

    linked = linker.get_linked_resource_by_id("i-0a1b2c3d4e5f67890")
    verdict = engine.evaluate_risk(linked)

    assert verdict.risk_level == RiskLevel.HIGH_RISK
    assert verdict.verdict_blocked is False
    assert any("Terraform" in r for r in verdict.evidence_against)
    assert any("production" in r for r in verdict.evidence_against)


def test_orphaned_unattached_ebs_is_low_risk():
    linker = Linker()
    engine = RiskEngine()

    linked = linker.get_linked_resource_by_id("vol-04d5e6f7a8b9c0d1e")
    verdict = engine.evaluate_risk(linked)

    assert verdict.risk_level == RiskLevel.LOW_RISK
    assert verdict.verdict_blocked is False
    assert verdict.monthly_savings == 20.00
    assert any("unattached" in r.lower() for r in verdict.evidence_for)


def test_idle_server_with_dependencies_is_medium_risk():
    linker = Linker()
    engine = RiskEngine()

    linked = linker.get_linked_resource_by_id("i-0b2c3d4e5f6a7b8c9")
    verdict = engine.evaluate_risk(linked)

    assert verdict.risk_level == RiskLevel.MEDIUM_RISK
    assert verdict.monthly_savings == 245.00
    assert any("Zero network traffic" in r for r in verdict.evidence_for)
    assert any("dependencies" in r.lower() for r in verdict.evidence_against)


def test_thin_evidence_safeguard_blocks_verdict():
    linker = Linker()
    engine = RiskEngine()

    # vol-analytics-root has only 1 clue (AWS API only)
    linked = linker.get_linked_resource_by_id("vol-02b3c4d5e6f7a8b9c")
    verdict = engine.evaluate_risk(linked)

    assert verdict.risk_level == RiskLevel.BLOCKED
    assert verdict.verdict_blocked is True
    assert "Insufficient evidence" in verdict.block_reason
