"""Terraform Collector for mapping cloud resources to IaC state and configuration."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TerraformResourceInfo(BaseModel):
    """Metadata associating a cloud resource with Terraform state."""
    resource_id: str
    terraform_type: str
    terraform_name: str
    module: Optional[str] = None
    source_file: Optional[str] = None
    repository: Optional[str] = None
    is_managed: bool = True
    attributes: Dict[str, Any] = {}


class TerraformCollector:
    """Parses Terraform state files to discover infrastructure-as-code provenance."""

    def __init__(self, state_file_path: Optional[str] = None):
        if state_file_path:
            self.state_file_path = Path(state_file_path)
        else:
            self.state_file_path = Path(__file__).resolve().parent.parent.parent / "db" / "seed_data" / "terraform_state.json"

    def get_all_managed_resources(self) -> Dict[str, TerraformResourceInfo]:
        """Returns mapping of cloud resource_id -> TerraformResourceInfo."""
        mapping: Dict[str, TerraformResourceInfo] = {}

        if not self.state_file_path.exists():
            return mapping

        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            resources = state_data.get("resources", [])
            for res in resources:
                res_type = res.get("type")
                res_name = res.get("name")
                module = res.get("module")
                source_file = res.get("source_file", "main.tf")
                repo = res.get("repository", "infrastructure")

                for instance in res.get("instances", []):
                    attrs = instance.get("attributes", {})
                    res_id = attrs.get("id")
                    if res_id:
                        mapping[res_id] = TerraformResourceInfo(
                            resource_id=res_id,
                            terraform_type=res_type,
                            terraform_name=res_name,
                            module=module,
                            source_file=source_file,
                            repository=repo,
                            is_managed=True,
                            attributes=attrs
                        )
        except Exception as e:
            logger.error(f"Error parsing Terraform state file: {e}")

        return mapping

    def get_resource_terraform_info(self, resource_id: str) -> Optional[TerraformResourceInfo]:
        """Look up Terraform state info for a specific resource ID."""
        all_info = self.get_all_managed_resources()
        return all_info.get(resource_id)
