"""Timeline Builder for compiling chronological provenance history for any cloud resource."""

from datetime import datetime
from typing import List, Optional

from engine.models import Event, EventSource, Timeline
from engine.linker import LinkedResource, Linker


class TimelineBuilder:
    """Builds a human-readable, chronological provenance story for a resource."""

    def build_timeline(self, linked: LinkedResource) -> Timeline:
        """Construct sorted timeline from linked resource evidence."""
        events: List[Event] = list(linked.events)

        # If creation date is present on resource but no explicit creation event in CloudTrail, synthesize creation entry
        has_creation_event = any(e.event_type.upper() in ["CREATED", "RUNINSTANCES", "CREATEVOLUME", "CREATESECURITYGROUP"] for e in events)
        if not has_creation_event and linked.resource.created_at:
            events.append(
                Event(
                    id=f"synth-created-{linked.resource.id}",
                    resource_id=linked.resource.id,
                    timestamp=linked.resource.created_at,
                    event_type="CREATED",
                    actor=linked.resource.tags.get("Owner", "Unknown (Pre-logs)"),
                    source=EventSource.AWS_API,
                    description=f"Resource {linked.resource.name or linked.resource.id} first recorded in AWS infrastructure",
                    metadata={"synthetic": True}
                )
            )

        # If GitHub PR exists and not already represented, add PR merge event
        if linked.github_pr:
            pr_already_present = any(e.metadata.get("prNumber") == linked.github_pr.pr_number for e in events)
            if not pr_already_present and linked.github_pr.merged_at:
                pr_time = datetime.fromisoformat(linked.github_pr.merged_at.replace("Z", "+00:00"))
                events.append(
                    Event(
                        id=f"gh-pr-{linked.github_pr.pr_number}",
                        resource_id=linked.resource.id,
                        timestamp=pr_time,
                        event_type="GITHUB_PR_MERGED",
                        actor=linked.github_pr.merged_by or linked.github_pr.author,
                        source=EventSource.GITHUB,
                        description=f"GitHub PR #{linked.github_pr.pr_number} ('{linked.github_pr.title}') merged into {linked.github_pr.repository}",
                        metadata={"pr": linked.github_pr.model_dump()}
                    )
                )

        # Sort all events strictly chronologically
        events.sort(key=lambda ev: ev.timestamp)

        return Timeline(
            resource_id=linked.resource.id,
            resource_name=linked.resource.name,
            events=events,
            total_events=len(events)
        )

    def format_story_summary(self, timeline: Timeline) -> List[str]:
        """Convert timeline events into plain-English storytelling bullets."""
        bullets = []
        for ev in timeline.events:
            date_str = ev.timestamp.strftime("%b %d, %Y")
            actor_str = ev.actor
            if "role/" in actor_str:
                actor_str = actor_str.split("role/")[-1]

            tag = ""
            if "MANUAL" in ev.event_type:
                tag = " ⚠️ [MANUAL CHANGE OUTSIDE PIPELINE]"

            bullets.append(f"• {date_str}: {ev.description} (Actor: {actor_str}){tag}")
        return bullets


if __name__ == "__main__":
    linker = Linker()
    lr = linker.get_linked_resource_by_id("i-0a1b2c3d4e5f67890")
    if lr:
        builder = TimelineBuilder()
        tl = builder.build_timeline(lr)
        print(f"Timeline for {tl.resource_id} ({tl.resource_name}):")
        for bullet in builder.format_story_summary(tl):
            print(" ", bullet)
