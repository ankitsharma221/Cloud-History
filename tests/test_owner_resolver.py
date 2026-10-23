"""Tests for 5-tier ownership resolution fallback chain."""

import pytest
from engine.linker import Linker
from engine.owner_resolver import OwnerResolver
from engine.models import ConfidenceLevel, OwnerSource


def test_owner_tag_high_confidence():
    linker = Linker()
    resolver = OwnerResolver()

    # payment-api-prod has explicit Owner tag
    linked = linker.get_linked_resource_by_id("i-0a1b2c3d4e5f67890")
    assert linked is not None

    owner = resolver.resolve_owner(linked)
    assert owner.confidence == ConfidenceLevel.HIGH
    assert owner.source == OwnerSource.OWNER_TAG
    assert "payments-team@company.com" in owner.name


def test_codeowners_high_confidence():
    linker = Linker()
    resolver = OwnerResolver()

    # vol-01a2b3c4d5e6f7a8b has no Owner tag directly on disk, but has CODEOWNERS in IaC
    linked = linker.get_linked_resource_by_id("vol-01a2b3c4d5e6f7a8b")
    assert linked is not None

    owner = resolver.resolve_owner(linked)
    assert owner.confidence == ConfidenceLevel.HIGH
    assert owner.source == OwnerSource.CODEOWNERS
    assert "payments-team" in owner.name


def test_creator_departed_fallback_to_account_owner():
    linker = Linker()
    # Dan is marked inactive in company directory
    resolver = OwnerResolver()

    linked = linker.get_linked_resource_by_id("i-0b2c3d4e5f6a7b8c9")
    assert linked is not None

    owner = resolver.resolve_owner(linked)
    # Since creator Dan is inactive, fallback step resolves to account owner
    assert owner.source == OwnerSource.ACCOUNT_OWNER
    assert owner.confidence == ConfidenceLevel.MEDIUM


def test_active_creator_attribution():
    linker = Linker()
    # Charlie is an active employee
    resolver = OwnerResolver()

    linked = linker.get_linked_resource_by_id("i-0c3d4e5f6a7b8c9d0")
    assert linked is not None

    owner = resolver.resolve_owner(linked)
    assert owner.source == OwnerSource.CREATOR
    assert "charlie" in owner.name
    assert owner.confidence == ConfidenceLevel.MEDIUM
