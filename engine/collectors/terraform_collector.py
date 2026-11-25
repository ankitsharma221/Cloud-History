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
        self.custom_path = Path(state_file_path) if state_file_path else None
        self.live_state_path = Path(__file__).resolve().parent.parent.parent / "terraform" / "terraform.tfstate"
        self.seed_state_path = Path(__file__).resolve().parent.parent.parent / "db" / "seed_data" / "terraform_state.json"

    def _parse_file(self, fpath: Path) -> Dict[str, TerraformResourceInfo]:
        """Helper to parse a single Terraform state JSON file."""
        mapping: Dict[str, TerraformResourceInfo] = {}
        if not fpath.exists():
            return mapping

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            resources = state_data.get("resources", [])
            for res in resources:
                res_type = res.get("type", "unknown")
                res_name = res.get("name", "unknown")
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
            logger.error(f"Error parsing Terraform state file at {fpath}: {e}")

        return mapping

    def get_all_managed_resources(self) -> Dict[str, TerraformResourceInfo]:
        """Returns mapping of cloud resource_id -> TerraformResourceInfo.
        
        Merges seed data with live Terraform state if present.
        """
        if self.custom_path:
            return self._parse_file(self.custom_path)

        # Merge seed state and live state so both test suites and live resources work seamlessly
        results: Dict[str, TerraformResourceInfo] = {}
        results.update(self._parse_file(self.seed_state_path))
        results.update(self._parse_file(self.live_state_path))
        return results

    def get_resource_terraform_info(self, resource_id: str) -> Optional[TerraformResourceInfo]:
        """Look up Terraform state info for a specific resource ID."""
        all_info = self.get_all_managed_resources()
        return all_info.get(resource_id)
