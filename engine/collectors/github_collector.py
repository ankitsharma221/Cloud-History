"""GitHub Collector for retrieving PRs, commit history, and CODEOWNERS attribution."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class GitHubPRInfo(BaseModel):
    """Metadata for pull requests creating or updating cloud infrastructure."""
    pr_number: int
    repository: str
    title: str
    author: str
    merged_by: Optional[str] = None
    merged_at: Optional[str] = None
    commit_sha: str
    codeowners: List[str] = []
    source_file: Optional[str] = None
    description: Optional[str] = None


class GitHubCollector:
    """Collects Git and PR provenance from GitHub API or seed data."""

    def __init__(self, token: Optional[str] = None, seed_file: Optional[str] = None):
        self.token = token
        if seed_file:
            self.seed_file = Path(seed_file)
        else:
            self.seed_file = Path(__file__).resolve().parent.parent.parent / "db" / "seed_data" / "github_prs.json"

    def get_all_prs(self) -> List[GitHubPRInfo]:
        """Load all tracked pull requests."""
        if not self.seed_file.exists():
            return []

        try:
            with open(self.seed_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [GitHubPRInfo(**item) for item in data]
        except Exception as e:
            logger.error(f"Error reading GitHub seed data: {e}")
            return []

    def find_pr_for_commit(self, commit_sha: str) -> Optional[GitHubPRInfo]:
        """Find PR associated with a specific commit SHA."""
        prs = self.get_all_prs()
        for pr in prs:
            if commit_sha.startswith(pr.commit_sha) or pr.commit_sha.startswith(commit_sha):
                return pr
        return None

    def find_codeowners_for_file(self, source_file: str) -> List[str]:
        """Determine CODEOWNERS assigned to a given infrastructure file path."""
        prs = self.get_all_prs()
        for pr in prs:
            if pr.source_file == source_file:
                return pr.codeowners
        return []
