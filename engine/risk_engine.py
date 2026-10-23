"""Risk Engine for rule-based cloud resource deletion safety evaluation."""

from typing import List, Optional
from engine.models import RiskLevel, RiskVerdict, ResourceState, ResourceType
from engine.linker import LinkedResource, Linker


class RiskEngine:
    """Evaluates whether a resource is safe to retire based on hard evidence."""

    def evaluate_risk(self, linked: LinkedResource) -> RiskVerdict:
        """Calculate deletion risk verdict with evidence and required actions."""
        res = linked.resource
        evidence_for: List[str] = []
        evidence_against: List[str] = []
        missing_evidence: List[str] = list(linked.clues_missing)
        required_actions: List[str] = []

        # 1. Check Evidence Coverage (Safety Block)
        # Minimum threshold: at least 2 clues found. If only 1 clue found, block verdict
        if len(linked.clues_found) < 2:
            return RiskVerdict(
                resource_id=res.id,
                risk_level=RiskLevel.BLOCKED,
                monthly_savings=res.cost_per_month,
                evidence_for=[],
                evidence_against=[],
                missing_evidence=missing_evidence,
                verdict_blocked=True,
                block_reason=f"Insufficient evidence: Only {len(linked.clues_found)} of 6 signals found. Deletion assessment blocked for safety.",
                required_actions=["Enable VPC Flow Logs and CloudTrail retention", "Run discovery scan before reassessing"]
            )

        # 2. Terraform / IaC Check
        if linked.in_terraform:
            module_name = linked.terraform_info.module if linked.terraform_info else "root"
            evidence_against.append(f"Actively managed in Terraform module '{module_name}' in repository '{linked.terraform_info.repository if linked.terraform_info else 'repo'}'")
        else:
            evidence_for.append("Not managed by Terraform (manual or orphaned resource)")

        # 3. Environment & Tagging Check
        env = res.tags.get("Environment", "").lower()
        if env in ["production", "prod"]:
            evidence_against.append("Tagged as 'production' environment")
        elif env in ["dev", "development", "test", "stage"]:
            evidence_for.append(f"Non-production environment tag ('{env}')")

        # 4. Usage & Traffic Checks
        details = res.details

        # Check traffic / request rate
        if "network_req_per_sec" in details:
            req_rate = details["network_req_per_sec"]
            if req_rate > 0.1:
                evidence_against.append(f"Active incoming network traffic ({req_rate} req/s)")
            elif req_rate == 0.0:
                traffic_days = details.get("traffic_last_seen_days", 0)
                if traffic_days >= 21:
                    evidence_for.append(f"Zero network traffic for {traffic_days} consecutive days")

        # Check CPU utilization
        if "cpu_utilization_avg_pct" in details:
            cpu = details["cpu_utilization_avg_pct"]
            if cpu > 5.0:
                evidence_against.append(f"CPU utilization active ({cpu:.1f}% avg)")
            elif cpu < 1.0:
                evidence_for.append(f"Negligible CPU utilization ({cpu:.1f}% avg)")

        # Check unattached duration (EBS)
        if "unattached_duration_days" in details:
            unattached_days = details["unattached_duration_days"]
            if unattached_days >= 30:
                evidence_for.append(f"Volume has remained unattached and idle for {unattached_days} days")

        # 5. Attachment & Dependency Checks
        if res.resource_type == ResourceType.EBS_VOLUME:
            if res.attached_to:
                evidence_against.append(f"Attached to active EC2 instance ({', '.join(res.attached_to)})")
            elif res.state == ResourceState.AVAILABLE:
                evidence_for.append("Volume is unattached (available)")

        if res.dependencies:
            evidence_against.append(f"Has {len(res.dependencies)} active dependencies ({', '.join(res.dependencies[:3])})")

        if res.state == ResourceState.STOPPED:
            evidence_for.append("Instance is currently in stopped state")

        # 6. Determine Risk Level
        if len(evidence_against) == 0 and len(evidence_for) >= 2:
            risk_level = RiskLevel.LOW_RISK
            required_actions = [
                "1. Notify resolved owner with evidence report",
                "2. Create backup snapshot prior to decommission",
                "3. Place in 7-day watch period before permanent deletion",
                "4. Record full action in audit log"
            ]
        elif len(evidence_against) > 0 and len(evidence_for) > 0:
            risk_level = RiskLevel.MEDIUM_RISK
            required_actions = [
                "1. Mandatory explicit approval from resource owner",
                "2. Create backup snapshot prior to quarantine",
                "3. Swap security group to deny-all or stop instance",
                "4. Observe 14-day watch period for connection failures or alert triggers",
                "5. Roll back immediately if any dependent system reports errors"
            ]
        else:
            risk_level = RiskLevel.HIGH_RISK
            required_actions = [
                "1. High deletion risk: active production dependencies detected",
                "2. Deletion NOT recommended unless decommissioning entire service",
                "3. Architecture team sign-off required"
            ]

        return RiskVerdict(
            resource_id=res.id,
            risk_level=risk_level,
            monthly_savings=res.cost_per_month,
            evidence_for=evidence_for,
            evidence_against=evidence_against,
            missing_evidence=missing_evidence,
            verdict_blocked=False,
            block_reason=None,
            required_actions=required_actions
        )


if __name__ == "__main__":
    linker = Linker()
    engine = RiskEngine()
    for rid, lr in linker.link_all().items():
        verdict = engine.evaluate_risk(lr)
        print(f"[{verdict.risk_level.value}] {rid} ({lr.resource.name}) - Saving: ${verdict.monthly_savings}/mo")
        for f in verdict.evidence_for:
            print(f"   + FOR: {f}")
        for a in verdict.evidence_against:
            print(f"   - AGAINST: {a}")
        if verdict.verdict_blocked:
            print(f"   BLOCKED: {verdict.block_reason}")
