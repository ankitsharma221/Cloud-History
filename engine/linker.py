"""Linker Engine for correlating cloud inventory, audit logs, IaC, and Git PRs."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from engine.models import Resource, Event
from engine.collectors.aws_collector import AWSCollector
from engine.collectors.cloudtrail_collector import CloudTrailCollector
from engine.collectors.terraform_collector import TerraformCollector, TerraformResourceInfo
from engine.collectors.github_collector import GitHubCollector, GitHubPRInfo


class LinkedResource(BaseModel):
    """Unified composite representation containing all gathered evidence for a resource."""
    resource: Resource
    events: List[Event] = Field(default_factory=list)
    terraform_info: Optional[TerraformResourceInfo] = None
    github_pr: Optional[GitHubPRInfo] = None
    in_terraform: bool = False
    codeowners: List[str] = Field(default_factory=list)
    clues_found: List[str] = Field(default_factory=list)
    clues_missing: List[str] = Field(default_factory=list)
    total_clues_count: int = 6
    evidence_coverage_ratio: float = 0.0


class Linker:
    """Joins evidence across AWS, CloudTrail, Terraform, and GitHub by resource ID."""

    def __init__(
        self,
        aws_collector: Optional[AWSCollector] = None,
        cloudtrail_collector: Optional[CloudTrailCollector] = None,
        terraform_collector: Optional[TerraformCollector] = None,
        github_collector: Optional[GitHubCollector] = None,
    ):
        self.aws = aws_collector or AWSCollector()
        self.cloudtrail = cloudtrail_collector or CloudTrailCollector()
        self.terraform = terraform_collector or TerraformCollector()
        self.github = github_collector or GitHubCollector()

    def link_resource(self, resource: Resource) -> LinkedResource:
        """Link all evidence for a single resource."""
        events = self.cloudtrail.get_events_for_resource(resource.id)
        tf_info = self.terraform.get_resource_terraform_info(resource.id)

        # Look for Git/PR info via commit in CloudTrail or Terraform source
        gh_pr: Optional[GitHubPRInfo] = None
        codeowners: List[str] = []

        # Check commit SHA in CloudTrail events
        for ev in events:
            commit_sha = ev.metadata.get("commitSha")
            if commit_sha:
                gh_pr = self.github.find_pr_for_commit(commit_sha)
                if gh_pr:
                    break

        # Check source file in Terraform info
        if tf_info and tf_info.source_file:
            codeowners = self.github.find_codeowners_for_file(tf_info.source_file)
            if not gh_pr:
                # Search PR by source file
                for pr in self.github.get_all_prs():
                    if pr.source_file == tf_info.source_file:
                        gh_pr = pr
                        break

        # Calculate clue coverage (out of 6 core clues: AWS API, CloudTrail creation, CloudTrail change history, Terraform, GitHub PR, Usage Metrics)
        clues_found: List[str] = ["AWS API state & metadata"]
        clues_missing: List[str] = []

        # CloudTrail creation clue
        has_creation_event = any(e.event_type.upper() in ["CREATED", "RUNINSTANCES", "CREATEVOLUME", "CREATESECURITYGROUP"] for e in events)
        if has_creation_event:
            clues_found.append("CloudTrail origin event")
        else:
            clues_missing.append("CloudTrail origin event")

        # CloudTrail modification history
        has_mod_event = any(e.event_type.upper() not in ["CREATED", "RUNINSTANCES", "CREATEVOLUME", "CREATESECURITYGROUP"] for e in events)
        if has_mod_event:
            clues_found.append("CloudTrail modification logs")
        else:
            clues_missing.append("CloudTrail modification logs")

        # Terraform state
        if tf_info and tf_info.is_managed:
            clues_found.append("Terraform state definition")
        else:
            clues_missing.append("Terraform state definition")

        # GitHub PR / Commit provenance
        if gh_pr:
            clues_found.append(f"GitHub PR #{gh_pr.pr_number} / commit {gh_pr.commit_sha}")
        else:
            clues_missing.append("GitHub PR / commit link")

        # Usage metrics
        if "cpu_utilization_avg_pct" in resource.details or "network_req_per_sec" in resource.details or "unattached_duration_days" in resource.details:
            clues_found.append("CloudWatch usage metrics")
        else:
            clues_missing.append("CloudWatch usage metrics")

        coverage_ratio = len(clues_found) / 6.0

        return LinkedResource(
            resource=resource,
            events=events,
            terraform_info=tf_info,
            github_pr=gh_pr,
            in_terraform=(tf_info is not None and tf_info.is_managed),
            codeowners=codeowners or (gh_pr.codeowners if gh_pr else []),
            clues_found=clues_found,
            clues_missing=clues_missing,
            total_clues_count=6,
            evidence_coverage_ratio=coverage_ratio
        )

    def link_all(self) -> Dict[str, LinkedResource]:
        """Link all discovered resources across the account."""
        resources = self.aws.collect_all_resources()
        return {r.id: self.link_resource(r) for r in resources}

    def get_linked_resource_by_id(self, resource_id: str) -> Optional[LinkedResource]:
        """Find and link a specific resource by ID."""
        resources = self.aws.collect_all_resources()
        target = next((r for r in resources if r.id == resource_id), None)
        if not target:
            return None
        return self.link_resource(target)
