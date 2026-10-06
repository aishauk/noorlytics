"""Decision Store - Persistent storage and querying of decisions.

Manages decision persistence with immutable audit trail and compliance support.
Provides SQLite by default, with PostgreSQL support for production scale.
"""

from __future__ import annotations

import json
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, UTC
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum

from .assessment import Decision, Priority, DecisionCategory, CustomerContext

logger = logging.getLogger(__name__)


class DecisionStatus(str, Enum):
    """Status of a decision in implementation."""
    PROPOSED = "proposed"           # Initial generation
    ACKNOWLEDGED = "acknowledged"   # Reviewed and accepted
    IN_PROGRESS = "in_progress"     # Actively being worked on
    IMPLEMENTED = "implemented"     # Changes deployed
    VERIFIED = "verified"           # Verification complete


class DecisionStore:
    """Manages decision persistence with audit trail."""

    SCHEMA = """
-- Decisions table (immutable append-only)
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    priority TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    rationale TEXT,
    tradeoff_summary JSON,
    evidence_ids JSON,
    affected_packages JSON,
    recommended_action TEXT,
    owner_hint TEXT,
    target_timeframe TEXT,
    effort_estimate TEXT,
    business_impact TEXT,
    
    -- Audit fields
    created_at TEXT NOT NULL,
    created_by TEXT,
    assessment_version INTEGER NOT NULL DEFAULT 1,
    rationale_source TEXT DEFAULT 'static',
    
    -- Metadata
    metadata JSON,
    
    PRIMARY KEY(manifest_path, decision_id, assessment_version)
);

-- Customer context snapshots for audit trail
CREATE TABLE IF NOT EXISTS customer_contexts (
    context_id TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    industry TEXT,
    deployment TEXT,
    risk_preferences JSON,
    constraints JSON,
    created_at TEXT NOT NULL,
    
    UNIQUE(customer_name, created_at)
);

-- Decision status tracking (mutable)
CREATE TABLE IF NOT EXISTS decision_status (
    status_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    assigned_to TEXT,
    notes TEXT,
    
    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id)
);

-- Audit log (immutable)
CREATE TABLE IF NOT EXISTS audit_log (
    log_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    decision_id TEXT,
    timestamp TEXT NOT NULL,
    user_id TEXT,
    details JSON
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_decisions_customer ON decisions(customer_name);
CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON decisions(created_at);
CREATE INDEX IF NOT EXISTS idx_decisions_priority ON decisions(priority);
CREATE INDEX IF NOT EXISTS idx_decisions_category ON decisions(category);
CREATE INDEX IF NOT EXISTS idx_decisions_manifest ON decisions(manifest_path);
CREATE INDEX IF NOT EXISTS idx_decisions_manifest_version ON decisions(manifest_path, assessment_version);
CREATE INDEX IF NOT EXISTS idx_status_decision ON decision_status(decision_id);
CREATE INDEX IF NOT EXISTS idx_audit_decision ON audit_log(decision_id);
"""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize decision store.

        Args:
            db_path: Path to SQLite database. Defaults to ./noorlytics/decisions.db
        """
        if db_path is None:
            # Use project directory instead of home directory
            self.db_path = Path(__file__).parent / "decisions.db"
        else:
            self.db_path = Path(db_path)

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        try:
            with self.get_connection() as conn:
                conn.executescript(self.SCHEMA)
                conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def store_decision(
        self,
        decision: Decision,
        customer_context: CustomerContext,
        manifest_path: str,
        assessment_version: int = 1,
        llm_model: Optional[str] = None,
    ) -> None:
        """Store a decision immutably.

        Args:
            decision: Decision to store
            customer_context: Customer context for this decision
            manifest_path: Path to manifest file
            assessment_version: Version number of assessment (v1, v2, etc.)
            llm_model: LLM model used if generated (e.g., "ollama:mistral")
        """
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO decisions (
                        decision_id, manifest_path, customer_name, priority, category,
                        title, rationale, tradeoff_summary, evidence_ids, affected_packages,
                        recommended_action, owner_hint, target_timeframe, effort_estimate,
                        business_impact, created_at, created_by, assessment_version,
                        rationale_source, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        decision.id,
                        manifest_path,
                        customer_context.customer_name,
                        decision.priority.value,
                        decision.category.value,
                        decision.title,
                        decision.rationale,
                        json.dumps(decision.tradeoff_summary.to_dict()),
                        json.dumps(decision.evidence_ids),
                        json.dumps(decision.affected_packages),
                        decision.recommended_action,
                        decision.owner_hint,
                        decision.target_timeframe,
                        decision.effort_estimate,
                        decision.business_impact,
                        datetime.now(UTC).isoformat(),
                        llm_model,
                        assessment_version,
                        getattr(decision, "rationale_source", "static"),
                        json.dumps(getattr(decision, "metadata", {})),
                    ),
                )
                conn.commit()
                logger.info(f"Stored decision {decision.id} for {customer_context.customer_name}")
        except sqlite3.IntegrityError as e:
            logger.warning(f"Decision {decision.id} already exists: {e}")
        except sqlite3.Error as e:
            logger.error(f"Error storing decision: {e}")
            raise

    def get_decision(self, decision_id: str) -> Optional[Decision]:
        """Get a decision by ID.

        Args:
            decision_id: Decision ID (e.g., "DEC-ABC123")

        Returns:
            Decision object or None if not found
        """
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM decisions WHERE decision_id = ? ORDER BY assessment_version DESC LIMIT 1",
                    (decision_id,),
                ).fetchone()

            if row:
                return self._row_to_decision(dict(row))
            return None
        except sqlite3.Error as e:
            logger.error(f"Error retrieving decision {decision_id}: {e}")
            return None

    def query_decisions(
        self,
        customer_name: Optional[str] = None,
        priority: Optional[Priority] = None,
        category: Optional[DecisionCategory] = None,
        manifest_path: Optional[str] = None,
        days: Optional[int] = None,
        assessment_version: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Decision]:
        """Query decisions with optional filters.

        Args:
            customer_name: Filter by customer name
            priority: Filter by priority (P1-P4)
            category: Filter by decision category
            manifest_path: Filter by manifest path
            days: Filter by last N days
            assessment_version: Filter by assessment version
            limit: Maximum results to return
            offset: Number of results to skip

        Returns:
            List of Decision objects matching filters
        """
        query = "SELECT * FROM decisions WHERE 1=1"
        params = []

        if customer_name:
            query += " AND customer_name = ?"
            params.append(customer_name)
        if priority:
            query += " AND priority = ?"
            params.append(priority.value)
        if category:
            query += " AND category = ?"
            params.append(category.value)
        if manifest_path:
            query += " AND manifest_path = ?"
            params.append(manifest_path)
        if days:
            query += " AND created_at >= datetime('now', '-' || ? || ' days')"
            params.append(days)
        if assessment_version:
            query += " AND assessment_version = ?"
            params.append(assessment_version)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        try:
            with self.get_connection() as conn:
                rows = conn.execute(query, params).fetchall()
            return [self._row_to_decision(dict(row)) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error querying decisions: {e}")
            return []

    def get_assessment_versions(self, manifest_path: str) -> List[Tuple[int, str, int]]:
        """Get all assessment versions for a manifest.

        Args:
            manifest_path: Path to manifest

        Returns:
            List of (version, timestamp, decision_count) tuples
        """
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT assessment_version, MAX(created_at) as timestamp, COUNT(*) as count
                    FROM decisions
                    WHERE manifest_path = ?
                    GROUP BY assessment_version
                    ORDER BY assessment_version DESC
                    """,
                    (manifest_path,),
                ).fetchall()

            return [(row["assessment_version"], row["timestamp"], row["count"]) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error getting assessment versions: {e}")
            return []

    def update_decision_status(
        self,
        decision_id: str,
        manifest_path: str,
        status: DecisionStatus,
        assigned_to: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Update decision status (mutable tracking).

        Args:
            decision_id: Decision ID
            manifest_path: Manifest path
            status: New status
            assigned_to: Who is working on it
            notes: Status notes

        Returns:
            True if successful, False otherwise
        """
        try:
            import uuid

            status_id = str(uuid.uuid4())
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO decision_status (status_id, decision_id, manifest_path, status, updated_at, assigned_to, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        status_id,
                        decision_id,
                        manifest_path,
                        status.value,
                        datetime.now(UTC).isoformat(),
                        assigned_to,
                        notes,
                    ),
                )
                conn.commit()
            logger.info(f"Updated decision {decision_id} status to {status.value}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating decision status: {e}")
            return False

    def get_decision_status(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a decision.

        Args:
            decision_id: Decision ID

        Returns:
            Status dict or None if not found
        """
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM decision_status WHERE decision_id = ? ORDER BY updated_at DESC LIMIT 1",
                    (decision_id,),
                ).fetchone()

            if row:
                return dict(row)
            return None
        except sqlite3.Error as e:
            logger.error(f"Error retrieving decision status: {e}")
            return None

    def export_decisions(
        self,
        format: str = "json",
        customer_name: Optional[str] = None,
        **filters,
    ) -> str:
        """Export decisions in specified format.

        Args:
            format: Export format ("json", "csv", "markdown")
            customer_name: Optional customer filter
            **filters: Additional query filters

        Returns:
            Formatted string of decisions
        """
        decisions = self.query_decisions(customer_name=customer_name, **filters)

        if format == "json":
            return json.dumps([d.to_dict() for d in decisions], indent=2)
        elif format == "csv":
            return self._export_csv(decisions)
        elif format == "markdown":
            return self._export_markdown(decisions)
        else:
            raise ValueError(f"Unknown export format: {format}")

    def get_audit_trail(self, decision_id: str) -> List[Dict[str, Any]]:
        """Get audit trail for a decision.

        Args:
            decision_id: Decision ID

        Returns:
            List of audit log entries
        """
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE decision_id = ? ORDER BY timestamp ASC",
                    (decision_id,),
                ).fetchall()

            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error retrieving audit trail: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics.

        Returns:
            Stats dictionary
        """
        try:
            with self.get_connection() as conn:
                total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
                by_priority = {}
                for priority in ["P1", "P2", "P3", "P4"]:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM decisions WHERE priority = ?", (priority,)
                    ).fetchone()[0]
                    by_priority[priority] = count

                by_category = {}
                for row in conn.execute(
                    "SELECT DISTINCT category FROM decisions"
                ).fetchall():
                    category = row[0]
                    count = conn.execute(
                        "SELECT COUNT(*) FROM decisions WHERE category = ?", (category,)
                    ).fetchone()[0]
                    by_category[category] = count

                customers = conn.execute(
                    "SELECT COUNT(DISTINCT customer_name) FROM decisions"
                ).fetchone()[0]

            return {
                "total_decisions": total,
                "by_priority": by_priority,
                "by_category": by_category,
                "unique_customers": customers,
            }
        except sqlite3.Error as e:
            logger.error(f"Error retrieving statistics: {e}")
            return {}

    def _row_to_decision(self, row: Dict[str, Any]) -> Decision:
        """Convert database row to Decision object."""
        from .assessment import TradeoffSummary

        return Decision(
            id=row["decision_id"],
            priority=Priority[row["priority"]],
            title=row["title"],
            category=DecisionCategory(row["category"]),
            rationale=row["rationale"],
            tradeoff_summary=TradeoffSummary(**json.loads(row["tradeoff_summary"])),
            evidence_ids=json.loads(row["evidence_ids"]),
            affected_packages=json.loads(row["affected_packages"]),
            recommended_action=row["recommended_action"],
            owner_hint=row["owner_hint"],
            target_timeframe=row["target_timeframe"],
            effort_estimate=row["effort_estimate"],
            business_impact=row["business_impact"],
        )

    def _export_csv(self, decisions: List[Decision]) -> str:
        """Export decisions as CSV."""
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "Decision ID",
            "Priority",
            "Category",
            "Title",
            "Owner",
            "Timeframe",
            "Effort",
            "Business Impact",
        ])

        # Rows
        for decision in decisions:
            writer.writerow([
                decision.id,
                decision.priority.value,
                decision.category.value,
                decision.title,
                decision.owner_hint,
                decision.target_timeframe,
                decision.effort_estimate,
                decision.business_impact,
            ])

        return output.getvalue()

    def _export_markdown(self, decisions: List[Decision]) -> str:
        """Export decisions as Markdown."""
        lines = ["# Decisions Export\n"]

        by_priority = {}
        for decision in decisions:
            if decision.priority not in by_priority:
                by_priority[decision.priority] = []
            by_priority[decision.priority].append(decision)

        for priority in [Priority.P1, Priority.P2, Priority.P3, Priority.P4]:
            if priority not in by_priority:
                continue

            lines.append(f"## {priority.value} Decisions\n")
            for decision in by_priority[priority]:
                lines.append(f"### {decision.title}")
                lines.append(f"- **ID**: {decision.id}")
                lines.append(f"- **Category**: {decision.category.value}")
                lines.append(f"- **Owner**: {decision.owner_hint}")
                lines.append(f"- **Timeframe**: {decision.target_timeframe}")
                lines.append(f"- **Effort**: {decision.effort_estimate}\n")

        return "\n".join(lines)
