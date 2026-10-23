"""Readiness Checker for validating observability signals and audit sources."""

from pathlib import Path
from typing import Dict, List
from engine.models import ReadinessReport
from engine.collectors.aws_collector import AWSCollector
from engine.collectors.cloudtrail_collector import CloudTrailCollector
from engine.collectors.terraform_collector import TerraformCollector
from engine.collectors.github_collector import GitHubCollector


class ReadinessChecker:
    """Verifies that all required audit and log signals are configured before assessments."""

    def __init__(
        self,
        aws_collector: AWSCollector = None,
        cloudtrail_collector: CloudTrailCollector = None,
        terraform_collector: TerraformCollector = None,
        github_collector: GitHubCollector = None,
    ):
        self.aws = aws_collector or AWSCollector()
        self.cloudtrail = cloudtrail_collector or CloudTrailCollector()
        self.terraform = terraform_collector or TerraformCollector()
        self.github = github_collector or GitHubCollector()

    def check_readiness(self) -> ReadinessReport:
        """Evaluate availability of all 5 critical enterprise audit signals."""
        signals: Dict[str, bool] = {}

        # 1. AWS API
        try:
            resources = self.aws.collect_all_resources()
            signals["AWS Inventory API"] = len(resources) > 0
        except Exception:
            signals["AWS Inventory API"] = False

        # 2. CloudTrail Logging
        try:
            events = self.cloudtrail.collect_all_events()
            signals["CloudTrail Audit Trail"] = len(events) > 0
        except Exception:
            signals["CloudTrail Audit Trail"] = False

        # 3. Terraform State
        try:
            tf_resources = self.terraform.get_all_managed_resources()
            signals["Terraform State"] = len(tf_resources) > 0
        except Exception:
            signals["Terraform State"] = False

        # 4. GitHub PR & CODEOWNERS
        try:
            prs = self.github.get_all_prs()
            signals["GitHub Repository & PRs"] = len(prs) > 0
        except Exception:
            signals["GitHub Repository & PRs"] = False

        # 5. CloudWatch Metrics & Flow Logs
        # In seed/demo mode, metrics are embedded in resource details
        has_metrics = False
        try:
            for r in self.aws.collect_all_resources():
                if "cpu_utilization_avg_pct" in r.details or "network_req_per_sec" in r.details:
                    has_metrics = True
                    break
            signals["CloudWatch & Flow Logs"] = has_metrics
        except Exception:
            signals["CloudWatch & Flow Logs"] = False

        available_count = sum(1 for v in signals.values() if v)
        total_count = len(signals)
        coverage_score = available_count / float(total_count) if total_count > 0 else 0.0

        missing_signals = [name for name, is_avail in signals.items() if not is_avail]

        if coverage_score >= 1.0:
            summary = "All 5 core audit signals are active and verified. High confidence verdicts enabled."
        elif coverage_score >= 0.6:
            summary = f"Partial signal coverage ({available_count}/{total_count} active). Missing: {', '.join(missing_signals)}. Verdicts on missing metrics will be blocked."
        else:
            summary = f"Critical signals missing ({available_count}/{total_count} active). Decommissioning actions blocked until audit sources are enabled."

        return ReadinessReport(
            signals_available=signals,
            coverage_score=coverage_score,
            missing_signals=missing_signals,
            summary=summary
        )


if __name__ == "__main__":
    checker = ReadinessChecker()
    report = checker.check_readiness()
    print(f"Readiness Score: {report.coverage_score:.1%}")
    for sig, avail in report.signals_available.items():
        print(f"  [{'PASS' if avail else 'FAIL'}] {sig}")
    print(f"Summary: {report.summary}")
