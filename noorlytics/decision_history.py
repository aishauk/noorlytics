"""Decision History - Track and compare decision versions.

Tracks decision evolution across multiple assessments and generates diff reports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Optional

from .assessment import Decision, Priority, DecisionCategory
from .decision_store import DecisionStore

logger = logging.getLogger(__name__)


@dataclass
class AssessmentSnapshot:
    """Snapshot of decisions at a point in time."""

    manifest_path: str
    assessment_version: int
    created_at: str
    decisions: List[Decision]
    decision_count: int
    by_priority: dict[str, int]


@dataclass
class DecisionDiff:
    """Difference between two assessments."""

    added: List[Decision]
    removed: List[Decision]
    modified: List[Tuple[Decision, Decision]]  # (old, new)
    priority_changed: List[Tuple[str, Priority, Priority]]  # (decision_id, old_priority, new_priority)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.added or self.removed or self.modified or self.priority_changed)

    @property
    def summary(self) -> str:
        """Get summary of changes."""
        parts = []
        if self.added:
            parts.append(f"✅ {len(self.added)} added")
        if self.removed:
            parts.append(f"❌ {len(self.removed)} removed")
        if self.priority_changed:
            parts.append(f"📊 {len(self.priority_changed)} priority changed")
        return ", ".join(parts) if parts else "No changes"


class DecisionHistory:
    """Tracks decision evolution across assessments."""

    def __init__(self, store: DecisionStore):
        """Initialize history tracker.

        Args:
            store: DecisionStore instance for queries
        """
        self.store = store

    def get_assessment_timeline(self, manifest_path: str) -> List[AssessmentSnapshot]:
        """Get all assessments for a manifest with timestamps.

        Args:
            manifest_path: Path to manifest

        Returns:
            List of AssessmentSnapshot ordered chronologically
        """
        versions = self.store.get_assessment_versions(manifest_path)
        snapshots = []

        for version, timestamp, count in versions:
            decisions = self.store.query_decisions(
                manifest_path=manifest_path,
                assessment_version=version,
            )

            by_priority = {}
            for decision in decisions:
                priority = decision.priority.value
                by_priority[priority] = by_priority.get(priority, 0) + 1

            snapshot = AssessmentSnapshot(
                manifest_path=manifest_path,
                assessment_version=version,
                created_at=timestamp,
                decisions=decisions,
                decision_count=count,
                by_priority=by_priority,
            )
            snapshots.append(snapshot)

        return snapshots

    def get_assessment_diff(
        self,
        manifest_path: str,
        version_from: int,
        version_to: int,
    ) -> DecisionDiff:
        """Get diff between two assessments.

        Args:
            manifest_path: Path to manifest
            version_from: Starting version (e.g., 1)
            version_to: Ending version (e.g., 2)

        Returns:
            DecisionDiff showing changes
        """
        decisions_from = self.store.query_decisions(
            manifest_path=manifest_path,
            assessment_version=version_from,
            limit=1000,
        )
        decisions_to = self.store.query_decisions(
            manifest_path=manifest_path,
            assessment_version=version_to,
            limit=1000,
        )

        # Create ID lookup maps
        from_ids = {d.id: d for d in decisions_from}
        to_ids = {d.id: d for d in decisions_to}

        # Find added, removed, modified
        added = [d for d in decisions_to if d.id not in from_ids]
        removed = [d for d in decisions_from if d.id not in to_ids]
        modified = []
        priority_changed = []

        for decision_id, new_decision in to_ids.items():
            if decision_id in from_ids:
                old_decision = from_ids[decision_id]

                # Check if modified (rationale, recommendation changed)
                if (
                    old_decision.rationale != new_decision.rationale
                    or old_decision.recommended_action != new_decision.recommended_action
                ):
                    modified.append((old_decision, new_decision))

                # Check if priority changed
                if old_decision.priority != new_decision.priority:
                    priority_changed.append(
                        (decision_id, old_decision.priority, new_decision.priority)
                    )

        return DecisionDiff(
            added=added,
            removed=removed,
            modified=modified,
            priority_changed=priority_changed,
        )

    def get_latest_version(self, manifest_path: str) -> Optional[int]:
        """Get latest assessment version for a manifest.

        Args:
            manifest_path: Path to manifest

        Returns:
            Latest version number or None if no assessments
        """
        versions = self.store.get_assessment_versions(manifest_path)
        if versions:
            return versions[0][0]  # First tuple's first element
        return None

    def get_next_version(self, manifest_path: str) -> int:
        """Get next assessment version for a manifest.

        Args:
            manifest_path: Path to manifest

        Returns:
            Next version number (1 if first assessment)
        """
        latest = self.get_latest_version(manifest_path)
        return (latest or 0) + 1

    def generate_history_markdown(self, manifest_path: str) -> str:
        """Generate human-readable history report.

        Args:
            manifest_path: Path to manifest

        Returns:
            Markdown formatted history report
        """
        timeline = self.get_assessment_timeline(manifest_path)

        if not timeline:
            return f"# Decision History: {manifest_path}\n\nNo assessments found."

        lines = [f"# Decision History: {manifest_path}\n"]

        for i, snapshot in enumerate(timeline, 1):
            lines.append(f"## Assessment v{snapshot.assessment_version}")
            lines.append(f"**Date**: {snapshot.created_at}")
            lines.append(f"**Total Decisions**: {snapshot.decision_count}\n")

            # Priority breakdown
            lines.append("**By Priority**:")
            for priority in ["P1", "P2", "P3", "P4"]:
                count = snapshot.by_priority.get(priority, 0)
                if count > 0:
                    lines.append(f"- {priority}: {count}")
            lines.append("")

            # Show changes from previous version
            if i > 1:
                prev_snapshot = timeline[i - 2]
                diff = self.get_assessment_diff(
                    manifest_path,
                    prev_snapshot.assessment_version,
                    snapshot.assessment_version,
                )

                lines.append(f"### Changes from v{prev_snapshot.assessment_version}")
                lines.append(f"**Summary**: {diff.summary}\n")

                if diff.added:
                    lines.append("**Added Decisions** ✅:")
                    for decision in diff.added:
                        lines.append(f"- {decision.id}: {decision.title} ({decision.priority.value})")
                    lines.append("")

                if diff.removed:
                    lines.append("**Removed Decisions** ❌:")
                    for decision in diff.removed:
                        lines.append(f"- {decision.id}: {decision.title} ({decision.priority.value})")
                    lines.append("")

                if diff.priority_changed:
                    lines.append("**Priority Changes** 📊:")
                    for decision_id, old_priority, new_priority in diff.priority_changed:
                        lines.append(f"- {decision_id}: {old_priority.value} → {new_priority.value}")
                    lines.append("")

            lines.append("---\n")

        return "\n".join(lines)

    def generate_comparison_matrix(self, manifest_path: str) -> str:
        """Generate comparison table for all versions.

        Args:
            manifest_path: Path to manifest

        Returns:
            Markdown table comparing all versions
        """
        timeline = self.get_assessment_timeline(manifest_path)

        if not timeline:
            return "No assessments found."

        lines = ["# Assessment Comparison\n"]
        lines.append("| Metric | " + " | ".join([f"v{s.assessment_version}" for s in timeline]) + " |")
        lines.append(
            "| --- | "
            + " | ".join(["---" for _ in timeline])
            + " |"
        )

        # Total decisions
        lines.append("| Total Decisions | " + " | ".join([str(s.decision_count) for s in timeline]) + " |")

        # By priority
        for priority in ["P1", "P2", "P3", "P4"]:
            values = [str(s.by_priority.get(priority, 0)) for s in timeline]
            lines.append(f"| {priority} | " + " | ".join(values) + " |")

        return "\n".join(lines)

    def generate_delta_markdown(
        self,
        manifest_path: str,
        version_from: int,
        version_to: int,
    ) -> str:
        """Generate detailed diff report between two versions.

        Args:
            manifest_path: Path to manifest
            version_from: Starting version
            version_to: Ending version

        Returns:
            Markdown formatted diff report
        """
        diff = self.get_assessment_diff(manifest_path, version_from, version_to)

        lines = [f"# Diff: v{version_from} → v{version_to}\n"]
        lines.append(f"Manifest: {manifest_path}\n")
        lines.append(f"**Summary**: {diff.summary}\n")

        if diff.added:
            lines.append("## Added Decisions ✅\n")
            for decision in diff.added:
                lines.append(f"### {decision.title}")
                lines.append(f"- **ID**: {decision.id}")
                lines.append(f"- **Priority**: {decision.priority.value}")
                lines.append(f"- **Category**: {decision.category.value}")
                lines.append(f"- **Owner**: {decision.owner_hint}")
                lines.append(f"- **Rationale**: {decision.rationale[:100]}...")
                lines.append("")

        if diff.removed:
            lines.append("## Removed Decisions ❌\n")
            for decision in diff.removed:
                lines.append(f"### {decision.title}")
                lines.append(f"- **ID**: {decision.id}")
                lines.append(f"- **Priority**: {decision.priority.value}")
                lines.append(f"- **Category**: {decision.category.value}")
                lines.append("")

        if diff.priority_changed:
            lines.append("## Priority Changes 📊\n")
            for decision_id, old_priority, new_priority in diff.priority_changed:
                lines.append(f"- **{decision_id}**: {old_priority.value} → {new_priority.value}")
            lines.append("")

        if diff.modified:
            lines.append("## Modified Decisions 🔄\n")
            for old_decision, new_decision in diff.modified:
                lines.append(f"### {new_decision.title} ({new_decision.id})")
                lines.append("**Rationale Changed**: Yes")
                lines.append(f"- **Old**: {old_decision.rationale[:80]}...")
                lines.append(f"- **New**: {new_decision.rationale[:80]}...")
                lines.append("")

        return "\n".join(lines)
