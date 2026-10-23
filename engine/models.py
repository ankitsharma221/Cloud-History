"""Pydantic data models for Cloud Resource Archaeologist.

Defines the structure for cloud resources, provenance events, ownership resolution,
risk verdicts, timeline history, and quarantine workflows.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    """Supported cloud resource types."""
    EC2_INSTANCE = "ec2_instance"
    EBS_VOLUME = "ebs_volume"
    SECURITY_GROUP = "security_group"
    RDS_INSTANCE = "rds_instance"
    S3_BUCKET = "s3_bucket"


class ResourceState(str, Enum):
    """Lifecycle and operation states of cloud resources."""
    RUNNING = "running"
    STOPPED = "stopped"
    AVAILABLE = "available"
    IN_USE = "in_use"
    ATTACHED = "attached"
    UNATTACHED = "unattached"
    QUARANTINED = "quarantined"
    TERMINATED = "terminated"
    DELETED = "deleted"


class ConfidenceLevel(str, Enum):
    """Confidence tier for conclusions based on hard evidence."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, Enum):
    """Deletion risk levels."""
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    BLOCKED = "BLOCKED"


class QuarantineStatus(str, Enum):
    """State of reversible decommissioning."""
    NONE = "none"
    PENDING_APPROVAL = "pending_approval"
    QUARANTINED = "quarantined"
    WATCHING = "watching"
    ROLLED_BACK = "rolled_back"
    DECOMMISSIONED = "decommissioned"


class EventSource(str, Enum):
    """Source system where an event or clue was discovered."""
    AWS_API = "aws_api"
    CLOUDTRAIL = "cloudtrail"
    TERRAFORM = "terraform"
    GITHUB = "github"
    CLOUDWATCH = "cloudwatch"
    MANUAL = "manual"


class OwnerSource(str, Enum):
    """Fallback step from which the owner was identified."""
    OWNER_TAG = "owner_tag"
    CODEOWNERS = "codeowners"
    ACCOUNT_OWNER = "account_owner"
    CREATOR = "creator"
    REVIEW_QUEUE = "review_queue"


class Resource(BaseModel):
    """Represents a discovered cloud resource."""
    id: str = Field(..., description="Unique AWS resource identifier, e.g. i-0a1b2c3d4e5f67890")
    name: Optional[str] = Field(None, description="Human-readable resource name from tags or code")
    resource_type: ResourceType = Field(..., description="Category of resource")
    region: str = Field("us-east-1", description="AWS region")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp if known")
    tags: Dict[str, str] = Field(default_factory=dict, description="Resource tags key-value pairs")
    state: ResourceState = Field(ResourceState.RUNNING, description="Current operational state")
    cost_per_month: float = Field(0.0, description="Estimated monthly run cost in USD")
    details: Dict[str, Any] = Field(default_factory=dict, description="Type-specific technical details")
    attached_to: List[str] = Field(default_factory=list, description="IDs of resources this item is attached to")
    dependencies: List[str] = Field(default_factory=list, description="IDs or ARNs of connected dependencies")


class Event(BaseModel):
    """Represents an audit, pipeline, or lifecycle event on a resource."""
    id: str = Field(..., description="Unique event identifier")
    resource_id: str = Field(..., description="Target resource ID")
    timestamp: datetime = Field(..., description="When the event occurred")
    event_type: str = Field(..., description="Category, e.g., CREATED, RESIZED, MODIFIED, ATTACHED")
    actor: str = Field(..., description="User, service, or pipeline that triggered the event")
    source: EventSource = Field(..., description="Source system generating the event")
    description: str = Field(..., description="Plain-English explanation of what happened")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extra context like commit SHA, PR #, or API event")


class Owner(BaseModel):
    """Resolved ownership details with confidence and provenance."""
    resource_id: str = Field(..., description="Resource ID")
    name: str = Field(..., description="Owner name or team name")
    team: Optional[str] = Field(None, description="Team or division responsible")
    email: Optional[str] = Field(None, description="Contact email if found")
    confidence: ConfidenceLevel = Field(..., description="Confidence rating based on evidence")
    source: OwnerSource = Field(..., description="Which step in fallback resolved the owner")
    explanation: str = Field(..., description="Explanation of why this owner was identified")


class RiskVerdict(BaseModel):
    """Rule-based deletion risk assessment."""
    resource_id: str = Field(..., description="Resource ID")
    risk_level: RiskLevel = Field(..., description="Calculated deletion risk")
    monthly_savings: float = Field(0.0, description="Potential cost savings if retired")
    evidence_for: List[str] = Field(default_factory=list, description="Clues supporting deletion")
    evidence_against: List[str] = Field(default_factory=list, description="Clues indicating danger in deletion")
    missing_evidence: List[str] = Field(default_factory=list, description="Expected signals not found or unavailable")
    verdict_blocked: bool = Field(False, description="True if evidence is too thin to make a safe determination")
    block_reason: Optional[str] = Field(None, description="Why the verdict is blocked")
    required_actions: List[str] = Field(default_factory=list, description="Actions required before deletion")


class Timeline(BaseModel):
    """Chronological history of a resource."""
    resource_id: str = Field(..., description="Resource ID")
    resource_name: Optional[str] = Field(None, description="Resource name")
    events: List[Event] = Field(default_factory=list, description="List of events ordered by timestamp")
    total_events: int = Field(0, description="Total count of historical events found")


class ReadinessReport(BaseModel):
    """Status report on available data sources and signals."""
    signals_available: Dict[str, bool] = Field(default_factory=dict, description="Map of signal name to availability")
    coverage_score: float = Field(..., description="Ratio of available signals (0.0 to 1.0)")
    missing_signals: List[str] = Field(default_factory=list, description="List of signals that are missing")
    summary: str = Field(..., description="Plain-English summary of signal readiness")


class QuarantineRecord(BaseModel):
    """Audit record for safe, reversible decommissioning."""
    id: str = Field(..., description="Unique quarantine workflow ID")
    resource_id: str = Field(..., description="Resource being quarantined")
    status: QuarantineStatus = Field(QuarantineStatus.NONE, description="Current workflow status")
    initiated_at: datetime = Field(default_factory=datetime.utcnow, description="When quarantine was initiated")
    approved_by: str = Field(..., description="Owner or admin who authorized quarantine")
    snapshot_id: Optional[str] = Field(None, description="Backup snapshot ID created prior to quarantine")
    previous_state: Dict[str, Any] = Field(default_factory=dict, description="State properties before quarantine for rollback")
    watch_period_days: int = Field(14, description="Quarantine observation window in days")
    watch_until: Optional[datetime] = Field(None, description="Expiration timestamp of watch window")
    problem_detected: bool = Field(False, description="Whether an alert or connection rejection was triggered")
    problem_details: Optional[str] = Field(None, description="Details of any incident during observation")
    logs: List[str] = Field(default_factory=list, description="Step-by-step audit log entries")
