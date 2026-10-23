"""Tests for data ingestion collectors (AWS, CloudTrail, Terraform, GitHub)."""

import pytest
from engine.collectors.aws_collector import AWSCollector
from engine.collectors.cloudtrail_collector import CloudTrailCollector
from engine.collectors.terraform_collector import TerraformCollector
from engine.collectors.github_collector import GitHubCollector
from engine.models import ResourceType


def test_aws_collector_loads_all_types():
    collector = AWSCollector(use_seed=True)
    resources = collector.collect_all_resources()

    assert len(resources) >= 5
    types = {r.resource_type for r in resources}
    assert ResourceType.EC2_INSTANCE in types
    assert ResourceType.EBS_VOLUME in types
    assert ResourceType.SECURITY_GROUP in types


def test_cloudtrail_collector_events():
    collector = CloudTrailCollector(use_seed=True)
    events = collector.collect_all_events()

    assert len(events) >= 5
    resource_events = collector.get_events_for_resource("i-0a1b2c3d4e5f67890")
    assert len(resource_events) >= 1
    event_types = [e.event_type for e in resource_events]
    assert "CREATED" in event_types or "RESIZED" in event_types


def test_terraform_collector_mapping():
    collector = TerraformCollector()
    managed = collector.get_all_managed_resources()

    assert "i-0a1b2c3d4e5f67890" in managed
    info = managed["i-0a1b2c3d4e5f67890"]
    assert info.is_managed is True
    assert info.terraform_type == "aws_instance"
    assert info.module == "module.payment_api"


def test_github_collector_pr_lookup():
    collector = GitHubCollector()
    prs = collector.get_all_prs()

    assert len(prs) >= 1
    pr142 = collector.find_pr_for_commit("a1b2c3d4e5")
    assert pr142 is not None
    assert pr142.pr_number == 142
    assert "@payments-team" in pr142.codeowners
