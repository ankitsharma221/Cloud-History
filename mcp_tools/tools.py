"""MCP Tools layer for exposing Cloud Resource Archaeologist engine to AI agents."""

import json
from typing import Any, Dict, List, Optional
from engine.linker import Linker
from engine.timeline_builder import TimelineBuilder
from engine.owner_resolver import OwnerResolver
from engine.risk_engine import RiskEngine
from engine.readiness_checker import ReadinessChecker
from db.database import SessionLocal, init_db, load_seed_data
from db.models_db import DBResource, DBQuarantine

# Ensure DB is ready
init_db()
load_seed_data()

_linker = Linker()
_timeline_builder = TimelineBuilder()
_owner_resolver = OwnerResolver()
_risk_engine = RiskEngine()
_readiness_checker = ReadinessChecker()


def get_readiness_report() -> Dict[str, Any]:
    """Check availability of audit sources (CloudTrail, VPC Flow Logs, Terraform, GitHub) and overall readiness score."""
    report = _readiness_checker.check_readiness()
    return report.model_dump()


def list_cloud_resources() -> List[Dict[str, Any]]:
    """List all discovered cloud resources across EC2 instances, EBS volumes, and Security Groups."""
    db = SessionLocal()
    try:
        resources = db.query(DBResource).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "type": r.resource_type,
                "region": r.region,
                "state": r.state,
                "cost_per_month": r.cost_per_month,
                "tags": r.tags,
                "details": r.details,
                "attached_to": r.attached_to,
                "dependencies": r.dependencies
            }
            for r in resources
        ]
    finally:
        db.close()


def get_resource_provenance(resource_id: str) -> Dict[str, Any]:
    """Retrieve full chronological provenance timeline and plain-English story for a cloud resource.

    Args:
        resource_id: AWS resource identifier (e.g. 'i-0a1b2c3d4e5f67890' or 'vol-04d5e6f7a8b9c0d1e')
    """
    linked = _linker.get_linked_resource_by_id(resource_id)
    if not linked:
        return {"error": f"Resource '{resource_id}' not found in inventory."}

    timeline = _timeline_builder.build_timeline(linked)
    story = _timeline_builder.format_story_summary(timeline)

    return {
        "resource_id": resource_id,
        "resource_name": linked.resource.name,
        "type": linked.resource.resource_type.value,
        "cost_per_month": linked.resource.cost_per_month,
        "evidence_coverage": f"{linked.evidence_coverage_ratio:.1%}",
        "clues_found": linked.clues_found,
        "clues_missing": linked.clues_missing,
        "in_terraform": linked.in_terraform,
        "codeowners": linked.codeowners,
        "story": story,
        "events": [e.model_dump() for e in timeline.events]
    }


def get_resource_owner(resource_id: str) -> Dict[str, Any]:
    """Identify the current responsible team or owner using a 5-step fallback chain with confidence rating.

    Args:
        resource_id: AWS resource identifier
    """
    linked = _linker.get_linked_resource_by_id(resource_id)
    if not linked:
        return {"error": f"Resource '{resource_id}' not found in inventory."}

    owner = _owner_resolver.resolve_owner(linked)
    return owner.model_dump()


def get_deletion_risk_verdict(resource_id: str) -> Dict[str, Any]:
    """Assess whether a resource is safe to retire based on usage, dependencies, and IaC status.

    Args:
        resource_id: AWS resource identifier
    """
    linked = _linker.get_linked_resource_by_id(resource_id)
    if not linked:
        return {"error": f"Resource '{resource_id}' not found in inventory."}

    verdict = _risk_engine.evaluate_risk(linked)
    return verdict.model_dump()


def start_safe_quarantine(resource_id: str, approved_by: str, watch_period_days: int = 14) -> Dict[str, Any]:
    """Initiate reversible decommissioning: creates backup snapshot, isolates resource, and starts observation window.

    Args:
        resource_id: AWS resource identifier
        approved_by: Engineer email/name approving quarantine
        watch_period_days: Observation duration before final deletion (default: 14 days)
    """
    import requests
    from api.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.post(
        f"/resources/{resource_id}/quarantine",
        json={"approved_by": approved_by, "watch_period_days": watch_period_days}
    )
    return response.json()


def rollback_quarantine(resource_id: str, reason: str) -> Dict[str, Any]:
    """Immediately undo quarantine and restore resource to previous active state.

    Args:
        resource_id: AWS resource identifier
        reason: Explanation for rollback (e.g. dependency alert or unexpected traffic)
    """
    from api.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.post(
        f"/resources/{resource_id}/rollback",
        json={"reason": reason}
    )
    return response.json()


def get_resource_audit_trail(resource_id: str) -> Dict[str, Any]:
    """Retrieve full audit trail of lifecycle events and quarantine actions for a resource.

    Args:
        resource_id: AWS resource identifier
    """
    from api.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get(f"/resources/{resource_id}/audit")
    return response.json()
