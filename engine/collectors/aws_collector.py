"""AWS Collector for discovering EC2 instances, EBS volumes, and Security Groups."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from engine.models import Resource, ResourceType, ResourceState

logger = logging.getLogger(__name__)


import os

class AWSCollector:
    """Discovers AWS resources via live boto3 API or seed data fallback."""

    def __init__(self, region_name: Optional[str] = None, use_seed: Optional[bool] = None):
        self.region_name = region_name or os.getenv("AWS_REGION", "ap-south-1")
        # If use_seed is not explicitly passed, check APP_ENV or AWS credentials
        if use_seed is not None:
            self.use_seed = use_seed
        else:
            self.use_seed = (os.getenv("APP_ENV", "development").lower() != "production")
        self.seed_dir = Path(__file__).resolve().parent.parent.parent / "db" / "seed_data"

    def collect_all_resources(self) -> List[Resource]:
        """Collect all supported resources across EC2, EBS, and Security Groups."""
        resources: List[Resource] = []
        resources.extend(self.collect_ec2_instances())
        resources.extend(self.collect_ebs_volumes())
        resources.extend(self.collect_security_groups())
        return resources

    def collect_ec2_instances(self) -> List[Resource]:
        """Collect EC2 instances."""
        if not self.use_seed:
            try:
                ec2 = boto3.client("ec2", region_name=self.region_name)
                response = ec2.describe_instances()
                results = []
                for res in response.get("Reservations", []):
                    for inst in res.get("Instances", []):
                        tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                        name = tags.get("Name", inst["InstanceId"])
                        results.append(
                            Resource(
                                id=inst["InstanceId"],
                                name=name,
                                resource_type=ResourceType.EC2_INSTANCE,
                                region=self.region_name,
                                created_at=inst.get("LaunchTime"),
                                tags=tags,
                                state=ResourceState(inst["State"]["Name"].lower()) if inst.get("State") else ResourceState.RUNNING,
                                cost_per_month=150.0,
                                details={
                                    "instance_type": inst.get("InstanceType"),
                                    "private_ip": inst.get("PrivateIpAddress"),
                                },
                                dependencies=[sg["GroupId"] for sg in inst.get("SecurityGroups", [])]
                            )
                        )
                return results
            except (BotoCoreError, ClientError) as e:
                logger.warning(f"AWS EC2 describe failed ({e}). Falling back to seed data.")

        # Seed data fallback
        fpath = self.seed_dir / "ec2_instances.json"
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [Resource(**item) for item in data]
        return []

    def collect_ebs_volumes(self) -> List[Resource]:
        """Collect EBS volumes."""
        if not self.use_seed:
            try:
                ec2 = boto3.client("ec2", region_name=self.region_name)
                response = ec2.describe_volumes()
                results = []
                for vol in response.get("Volumes", []):
                    tags = {t["Key"]: t["Value"] for t in vol.get("Tags", [])}
                    name = tags.get("Name", vol["VolumeId"])
                    attached_to = [att["InstanceId"] for att in vol.get("Attachments", [])]
                    state = ResourceState.IN_USE if attached_to else ResourceState.AVAILABLE
                    results.append(
                        Resource(
                            id=vol["VolumeId"],
                            name=name,
                            resource_type=ResourceType.EBS_VOLUME,
                            region=self.region_name,
                            created_at=vol.get("CreateTime"),
                            tags=tags,
                            state=state,
                            cost_per_month=float(vol.get("Size", 10)) * 0.10,
                            details={
                                "size_gb": vol.get("Size"),
                                "volume_type": vol.get("VolumeType"),
                            },
                            attached_to=attached_to
                        )
                    )
                return results
            except (BotoCoreError, ClientError) as e:
                logger.warning(f"AWS EBS describe failed ({e}). Falling back to seed data.")

        # Seed data fallback
        fpath = self.seed_dir / "ebs_volumes.json"
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [Resource(**item) for item in data]
        return []

    def collect_security_groups(self) -> List[Resource]:
        """Collect VPC Security Groups."""
        if not self.use_seed:
            try:
                ec2 = boto3.client("ec2", region_name=self.region_name)
                response = ec2.describe_security_groups()
                results = []
                for sg in response.get("SecurityGroups", []):
                    tags = {t["Key"]: t["Value"] for t in sg.get("Tags", [])}
                    name = tags.get("Name", sg.get("GroupName", sg["GroupId"]))
                    results.append(
                        Resource(
                            id=sg["GroupId"],
                            name=name,
                            resource_type=ResourceType.SECURITY_GROUP,
                            region=self.region_name,
                            tags=tags,
                            state=ResourceState.IN_USE,
                            cost_per_month=0.0,
                            details={
                                "vpc_id": sg.get("VpcId"),
                                "description": sg.get("Description"),
                                "ingress_rules": sg.get("IpPermissions", [])
                            }
                        )
                    )
                return results
            except (BotoCoreError, ClientError) as e:
                logger.warning(f"AWS SG describe failed ({e}). Falling back to seed data.")

        # Seed data fallback
        fpath = self.seed_dir / "security_groups.json"
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [Resource(**item) for item in data]
        return []
