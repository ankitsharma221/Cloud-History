"""FastAPI Application exposing Cloud Resource Archaeologist REST endpoints."""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db, init_db, load_seed_data
from db.models_db import DBResource, DBEvent, DBOwner, DBRiskVerdict, DBQuarantine
from engine.models import (
    Resource,
    Timeline,
    Owner,
    RiskVerdict,
    ReadinessReport,
    QuarantineRecord,
    QuarantineStatus,
    ResourceState,
)
from engine.linker import Linker
from engine.timeline_builder import TimelineBuilder
from engine.owner_resolver import OwnerResolver
from engine.risk_engine import RiskEngine
from engine.readiness_checker import ReadinessChecker

# Initialize database schema and seed data on startup
init_db()
load_seed_data()

app = FastAPI(
    title="Cloud Resource Archaeologist API",
    description="Evidence-based cloud resource provenance, ownership resolution, risk evaluation, and reversible decommissioning.",
    version="1.0.0"
)

# Instantiate core engines
linker = Linker()
timeline_builder = TimelineBuilder()
owner_resolver = OwnerResolver()
risk_engine = RiskEngine()
readiness_checker = ReadinessChecker()


class OwnerConfirmRequest(BaseModel):
    """Ground truth confirmation or correction input."""
    confirmed: bool = Field(..., description="True if suggested owner is correct")
    corrected_owner: Optional[str] = Field(None, description="Actual owner name/team if correction is needed")


class QuarantineRequest(BaseModel):
    """Request to initiate safe reversible decommissioning."""
    approved_by: str = Field(..., description="Name or email of the approving engineer")
    watch_period_days: int = Field(14, ge=1, le=90, description="Duration of observation window")


class RollbackRequest(BaseModel):
    """Request to undo quarantine and restore resource."""
    reason: str = Field(..., description="Reason for rollback, e.g. dependency error or user report")


# ── Health & Readiness ─────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    """Health status endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/readiness", response_model=ReadinessReport, tags=["Observability"])
def get_readiness_report():
    """Evaluate audit signal availability and readiness."""
    return readiness_checker.check_readiness()


# ── Resources & Inventory ──────────────────────────────────────────────────────

@app.get("/resources", response_model=List[Resource], tags=["Inventory"])
def list_resources(db: Session = Depends(get_db)):
    """List all tracked cloud resources."""
    db_resources = db.query(DBResource).all()
    results: List[Resource] = []
    for r in db_resources:
        results.append(
            Resource(
                id=r.id,
                name=r.name,
                resource_type=r.resource_type,
                region=r.region,
                created_at=r.created_at,
                tags=r.tags,
                state=r.state,
                cost_per_month=r.cost_per_month,
                details=r.details,
                attached_to=r.attached_to,
                dependencies=r.dependencies
            )
        )
    return results


@app.get("/resources/{resource_id}", response_model=Resource, tags=["Inventory"])
def get_resource(resource_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a single resource by ID."""
    r = db.query(DBResource).filter(DBResource.id == resource_id).first()
    if not r:
        raise HTTPException(status_code=404, detail=f"Resource '{resource_id}' not found")
    return Resource(
        id=r.id,
        name=r.name,
        resource_type=r.resource_type,
        region=r.region,
        created_at=r.created_at,
        tags=r.tags,
        state=r.state,
        cost_per_month=r.cost_per_month,
        details=r.details,
        attached_to=r.attached_to,
        dependencies=r.dependencies
    )


# ── Provenance & History ───────────────────────────────────────────────────────

@app.get("/resources/{resource_id}/provenance", response_model=Dict[str, Any], tags=["Provenance"])
def get_resource_provenance(resource_id: str):
    """Generate the full chronological provenance timeline and story summary."""
    linked = linker.get_linked_resource_by_id(resource_id)
    if not linked:
        raise HTTPException(status_code=404, detail=f"Resource '{resource_id}' not found")

    timeline = timeline_builder.build_timeline(linked)
    story = timeline_builder.format_story_summary(timeline)

    return {
        "timeline": timeline,
        "story": story,
        "clues_found": linked.clues_found,
        "clues_missing": linked.clues_missing,
        "evidence_coverage": f"{linked.evidence_coverage_ratio:.1%}",
        "in_terraform": linked.in_terraform,
        "codeowners": linked.codeowners
    }


# ── Ownership & Ground Truth ──────────────────────────────────────────────────

@app.get("/resources/{resource_id}/owner", response_model=Owner, tags=["Ownership"])
def get_resource_owner(resource_id: str, db: Session = Depends(get_db)):
    """Resolve resource owner using the 5-step fallback chain."""
    # Check if ground truth was already stored in DB
    existing_owner = db.query(DBOwner).filter(DBOwner.resource_id == resource_id).first()
    if existing_owner and existing_owner.confirmed_by_user and existing_owner.user_correction:
        return Owner(
            resource_id=resource_id,
            name=existing_owner.user_correction,
            team=existing_owner.team,
            email=existing_owner.email,
            confidence="HIGH",
            source="owner_tag",
            explanation="Ground truth verified and confirmed by human administrator"
        )

    linked = linker.get_linked_resource_by_id(resource_id)
    if not linked:
        raise HTTPException(status_code=404, detail=f"Resource '{resource_id}' not found")

    return owner_resolver.resolve_owner(linked)


@app.post("/resources/{resource_id}/owner/confirm", tags=["Ownership"])
def confirm_or_correct_owner(
    resource_id: str,
    payload: OwnerConfirmRequest,
    db: Session = Depends(get_db)
):
    """Confirm or correct the suggested owner, recording ground truth."""
    linked = linker.get_linked_resource_by_id(resource_id)
    if not linked:
        raise HTTPException(status_code=404, detail=f"Resource '{resource_id}' not found")

    owner_guess = owner_resolver.resolve_owner(linked)

    db_owner = db.query(DBOwner).filter(DBOwner.resource_id == resource_id).first()
    if not db_owner:
        db_owner = DBOwner(
            resource_id=resource_id,
            name=owner_guess.name,
            team=owner_guess.team,
            email=owner_guess.email,
            confidence=owner_guess.confidence.value,
            source=owner_guess.source.value,
            explanation=owner_guess.explanation
        )
        db.add(db_owner)

    db_owner.confirmed_by_user = payload.confirmed
    if payload.corrected_owner:
        db_owner.user_correction = payload.corrected_owner

    db.commit()

    return {
        "status": "success",
        "resource_id": resource_id,
        "confirmed": payload.confirmed,
        "recorded_owner": payload.corrected_owner or owner_guess.name,
        "message": "Ground truth ownership feedback stored successfully."
    }


# ── Risk Assessment ───────────────────────────────────────────────────────────

@app.get("/resources/{resource_id}/verdict", response_model=RiskVerdict, tags=["Risk"])
def get_resource_verdict(resource_id: str, db: Session = Depends(get_db)):
    """Evaluate deletion risk verdict with evidence."""
    linked = linker.get_linked_resource_by_id(resource_id)
    if not linked:
        raise HTTPException(status_code=404, detail=f"Resource '{resource_id}' not found")

    verdict = risk_engine.evaluate_risk(linked)

    # Persist verdict record in database
    db_verdict = DBRiskVerdict(
        resource_id=resource_id,
        risk_level=verdict.risk_level.value,
        monthly_savings=verdict.monthly_savings,
        evidence_for_json=str(verdict.evidence_for),
        evidence_against_json=str(verdict.evidence_against),
        missing_evidence_json=str(verdict.missing_evidence),
        verdict_blocked=verdict.verdict_blocked,
        block_reason=verdict.block_reason,
        required_actions_json=str(verdict.required_actions)
    )
    db.add(db_verdict)
    db.commit()

    return verdict


# ── Reversible Decommissioning & Quarantine ──────────────────────────────────

@app.post("/resources/{resource_id}/quarantine", response_model=Dict[str, Any], tags=["Decommissioning"])
def start_quarantine(
    resource_id: str,
    payload: QuarantineRequest,
    db: Session = Depends(get_db)
):
    """Start reversible quarantine: create backup snapshot, isolate resource, and start watch period."""
    db_res = db.query(DBResource).filter(DBResource.id == resource_id).first()
    if not db_res:
        raise HTTPException(status_code=404, detail=f"Resource '{resource_id}' not found")

    # Generate synthetic backup snapshot
    snapshot_id = f"snap-auto-{uuid.uuid4().hex[:8]}"
    quarantine_id = f"quar-{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow()
    watch_until = now + timedelta(days=payload.watch_period_days)

    prev_state = {
        "state": db_res.state,
        "tags": db_res.tags,
        "details": db_res.details
    }

    # Record quarantine in database
    quarantine_rec = DBQuarantine(
        id=quarantine_id,
        resource_id=resource_id,
        status="watching",
        initiated_at=now,
        approved_by=payload.approved_by,
        snapshot_id=snapshot_id,
        watch_period_days=payload.watch_period_days,
        watch_until=watch_until,
        problem_detected=False
    )
    quarantine_rec.previous_state = prev_state
    quarantine_rec.logs = [
        f"[{now.isoformat()}] Quarantine initiated by {payload.approved_by}",
        f"[{now.isoformat()}] Pre-quarantine snapshot created: {snapshot_id}",
        f"[{now.isoformat()}] Resource state transitioned to 'quarantined' / stopped",
        f"[{now.isoformat()}] Observation watch window active until {watch_until.isoformat()} ({payload.watch_period_days} days)"
    ]

    # Update resource state
    db_res.state = "quarantined"

    db.add(quarantine_rec)
    db.commit()

    return {
        "quarantine_id": quarantine_id,
        "resource_id": resource_id,
        "status": "watching",
        "snapshot_id": snapshot_id,
        "watch_until": watch_until.isoformat(),
        "monthly_savings_pending": db_res.cost_per_month,
        "message": f"Resource {resource_id} successfully isolated and placed under observation. Fully reversible."
    }


@app.post("/resources/{resource_id}/rollback", response_model=Dict[str, Any], tags=["Decommissioning"])
def rollback_quarantine(
    resource_id: str,
    payload: RollbackRequest,
    db: Session = Depends(get_db)
):
    """Roll back quarantine immediately, restoring the resource to its previous operational state."""
    db_res = db.query(DBResource).filter(DBResource.id == resource_id).first()
    if not db_res:
        raise HTTPException(status_code=404, detail=f"Resource '{resource_id}' not found")

    active_quarantine = (
        db.query(DBQuarantine)
        .filter(DBQuarantine.resource_id == resource_id)
        .order_by(DBQuarantine.initiated_at.desc())
        .first()
    )

    if not active_quarantine:
        raise HTTPException(status_code=400, detail=f"No active quarantine record found for {resource_id}")

    now = datetime.utcnow()
    logs = active_quarantine.logs
    logs.append(f"[{now.isoformat()}] ROLLBACK TRIGGERED: {payload.reason}")
    logs.append(f"[{now.isoformat()}] Restoring previous state from snapshot {active_quarantine.snapshot_id}")

    # Restore previous operational state
    prev = active_quarantine.previous_state
    db_res.state = prev.get("state", "running")

    active_quarantine.status = "rolled_back"
    active_quarantine.problem_detected = True
    active_quarantine.problem_details = payload.reason
    active_quarantine.logs = logs

    db.commit()

    return {
        "status": "rolled_back",
        "resource_id": resource_id,
        "restored_state": db_res.state,
        "rollback_reason": payload.reason,
        "message": f"Quarantine successfully rolled back for {resource_id}. Resource restored to active operation."
    }


@app.get("/resources/{resource_id}/audit", tags=["Decommissioning"])
def get_audit_trail(resource_id: str, db: Session = Depends(get_db)):
    """Retrieve full audit log history for a resource."""
    events = db.query(DBEvent).filter(DBEvent.resource_id == resource_id).order_by(DBEvent.timestamp.asc()).all()
    quarantines = db.query(DBQuarantine).filter(DBQuarantine.resource_id == resource_id).order_by(DBQuarantine.initiated_at.desc()).all()

    return {
        "resource_id": resource_id,
        "lifecycle_events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "actor": e.actor,
                "source": e.source,
                "description": e.description
            }
            for e in events
        ],
        "quarantine_workflows": [
            {
                "id": q.id,
                "status": q.status,
                "initiated_at": q.initiated_at.isoformat(),
                "approved_by": q.approved_by,
                "snapshot_id": q.snapshot_id,
                "watch_until": q.watch_until.isoformat() if q.watch_until else None,
                "problem_detected": q.problem_detected,
                "problem_details": q.problem_details,
                "logs": q.logs
            }
            for q in quarantines
        ]
    }
