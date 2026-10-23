"""Owner Resolver implementing a 5-tier fallback chain for robust resource ownership attribution."""

from typing import List, Optional, Set
from engine.models import Owner, OwnerSource, ConfidenceLevel
from engine.linker import LinkedResource, Linker

# Simulated company directory of active team members
ACTIVE_EMPLOYEES: Set[str] = {
    "alice@company.com",
    "alice",
    "bob@company.com",
    "bob",
    "charlie@company.com",
    "charlie",
    "payment-ci-role",
    "payments-team@company.com",
}

# Known inactive / departed employees
INACTIVE_EMPLOYEES: Set[str] = {
    "dan@company.com",
    "dan",
    "admin-temp",
}

DEFAULT_ACCOUNT_OWNER = "cloud-platform-ops@company.com"


class OwnerResolver:
    """Resolves true current resource owner using strict fallback rules and confidence tiers."""

    def __init__(self, active_directory: Optional[Set[str]] = None):
        self.active_directory = active_directory or ACTIVE_EMPLOYEES

    def resolve_owner(self, linked: LinkedResource) -> Owner:
        """Execute 5-step fallback chain to identify resource owner."""
        res = linked.resource

        # Tier 1: Explicit 'Owner' or 'Team' Tag
        for tag_key in ["Owner", "owner", "Team", "team", "Contact"]:
            if tag_key in res.tags and res.tags[tag_key].strip():
                tag_val = res.tags[tag_key].strip()
                return Owner(
                    resource_id=res.id,
                    name=tag_val,
                    team=res.tags.get("Team", tag_val),
                    email=tag_val if "@" in tag_val else None,
                    confidence=ConfidenceLevel.HIGH,
                    source=OwnerSource.OWNER_TAG,
                    explanation=f"Directly attributed from resource tag '{tag_key}: {tag_val}'"
                )

        # Tier 2: CODEOWNERS from IaC / Git repository
        if linked.codeowners:
            primary_codeowner = linked.codeowners[0].lstrip("@")
            return Owner(
                resource_id=res.id,
                name=primary_codeowner,
                team=primary_codeowner,
                confidence=ConfidenceLevel.HIGH,
                source=OwnerSource.CODEOWNERS,
                explanation=f"Attributed from repository CODEOWNERS configuration ({', '.join(linked.codeowners)})"
            )

        # Tier 3: Find creator from CloudTrail events and check if still active
        creator_actor = None
        for ev in linked.events:
            if ev.event_type.upper() in ["CREATED", "RUNINSTANCES", "CREATEVOLUME", "CREATESECURITYGROUP"]:
                creator_actor = ev.actor
                break

        if creator_actor:
            actor_clean = creator_actor.split("/")[-1].lower()
            if actor_clean in self.active_directory:
                return Owner(
                    resource_id=res.id,
                    name=creator_actor,
                    email=creator_actor if "@" in creator_actor else None,
                    confidence=ConfidenceLevel.MEDIUM,
                    source=OwnerSource.CREATOR,
                    explanation=f"Attributed to active creator '{creator_actor}' found in CloudTrail origin event"
                )
            else:
                # Creator is inactive or departed
                pass

        # Tier 4: Account Owner / Platform Ops fallback if resource has active environment tags
        if "Environment" in res.tags or res.region:
            return Owner(
                resource_id=res.id,
                name=DEFAULT_ACCOUNT_OWNER,
                team="Cloud Platform Ops",
                email=DEFAULT_ACCOUNT_OWNER,
                confidence=ConfidenceLevel.MEDIUM,
                source=OwnerSource.ACCOUNT_OWNER,
                explanation=f"Defaulted to AWS Account Owner / Platform Ops because creator is departed or unlisted"
            )

        # Tier 5: Review Queue / Unknown Origin
        return Owner(
            resource_id=res.id,
            name="Unassigned (Review Queue)",
            team="Unassigned",
            confidence=ConfidenceLevel.LOW,
            source=OwnerSource.REVIEW_QUEUE,
            explanation="Insufficient evidence to attribute ownership. Escalated to triage review queue."
        )


if __name__ == "__main__":
    linker = Linker()
    resolver = OwnerResolver()
    for rid, lr in linker.link_all().items():
        owner = resolver.resolve_owner(lr)
        print(f"[{owner.confidence.value}] {rid} ({lr.resource.name}) -> {owner.name} (Source: {owner.source.value})")
