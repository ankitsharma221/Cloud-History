"""CloudTrail Collector for extracting audit trails and historical lifecycle events."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from engine.models import Event, EventSource

logger = logging.getLogger(__name__)


import os

class CloudTrailCollector:
    """Collects historical events for resources from CloudTrail logs or seed data."""

    def __init__(self, region_name: Optional[str] = None, use_seed: Optional[bool] = None):
        self.region_name = region_name or os.getenv("AWS_REGION", "ap-south-1")
        if use_seed is not None:
            self.use_seed = use_seed
        else:
            self.use_seed = (os.getenv("APP_ENV", "development").lower() != "production")
        self.seed_dir = Path(__file__).resolve().parent.parent.parent / "db" / "seed_data"

    def collect_all_events(self) -> List[Event]:
        """Collect all historical audit events."""
        if not self.use_seed:
            try:
                ct = boto3.client("cloudtrail", region_name=self.region_name)
                response = ct.lookup_events(MaxResults=50)
                events = []
                for ev in response.get("Events", []):
                    res_list = ev.get("Resources", [])
                    res_id = res_list[0]["ResourceName"] if res_list else "unknown"
                    events.append(
                        Event(
                            id=ev["EventId"],
                            resource_id=res_id,
                            timestamp=ev["EventTime"],
                            event_type=ev.get("EventName", "API_CALL"),
                            actor=ev.get("Username", "Unknown"),
                            source=EventSource.CLOUDTRAIL,
                            description=f"Action {ev.get('EventName')} executed by {ev.get('Username')}",
                            metadata=ev
                        )
                    )
                return events
            except (BotoCoreError, ClientError) as e:
                logger.warning(f"CloudTrail lookup failed ({e}). Falling back to seed data.")

        # Seed data fallback
        fpath = self.seed_dir / "cloudtrail_events.json"
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [Event(**item) for item in data]
        return []

    def get_events_for_resource(self, resource_id: str) -> List[Event]:
        """Get all chronological events relating to a specific resource."""
        all_events = self.collect_all_events()
        return [e for e in all_events if e.resource_id == resource_id]
