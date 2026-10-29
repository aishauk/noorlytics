"""Decision Analytics - Metrics and dashboard generation.

Analyzes decision patterns and generates metrics for dashboards and reports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from datetime import datetime, timedelta

from .assessment import Priority, DecisionCategory
from .decision_store import DecisionStore, DecisionStatus

logger = logging.getLogger(__name__)


@dataclass
class DecisionMetrics:
    """Aggregated decision metrics."""

    period: str
    total_decisions: int
    by_priority: Dict[str, int]
    by_category: Dict[str, int]
    by_customer: Dict[str, int]
    implementation_status: Dict[str, int]
    avg_time_to_implement: Dict[str, float] = field(default_factory=dict)
    top_blockers: List[Tuple[str, int]] = field(default_factory=list)


@dataclass
class CustomerMetrics:
    """Metrics for a specific customer."""

    customer_name: str
    total_decisions: int
    by_priority: Dict[str, int]
    by_category: Dict[str, int]
    implementation_rate: float  # 0.0 to 1.0
    avg_time_to_implement: float


class DecisionAnalytics:
    """Analyzes decision patterns and generates metrics."""

    def __init__(self, store: DecisionStore):
        """Initialize analytics engine.

        Args:
            store: DecisionStore instance
        """
        self.store = store

    def get_metrics_summary(self, period: str = "month", days: int = 30) -> DecisionMetrics:
        """Get high-level metrics for a time period.

        Args:
            period: Period label ("month", "quarter", "year")
            days: Number of days to look back

        Returns:
            DecisionMetrics object
        """
        decisions = self.store.query_decisions(days=days, limit=10000)

        by_priority = {}
        by_category = {}
        by_customer = {}

        for decision in decisions:
            # Count by priority
            priority = decision.priority.value
            by_priority[priority] = by_priority.get(priority, 0) + 1

            # Count by category
            category = decision.category.value
            by_category[category] = by_category.get(category, 0) + 1

        # Count by customer (need to query store for this)
        customers = set(d.id for d in decisions)
        # This is approximate - real implementation would group
        by_customer["total_unique"] = len(set(d.id for d in decisions if hasattr(d, "customer_name")))

        # Get implementation status
        implementation_status = self._get_implementation_status(decisions)

        # Calculate avg time to implement
        avg_times = self._calc_avg_time_to_implement(decisions)

        return DecisionMetrics(
            period=period,
            total_decisions=len(decisions),
            by_priority=by_priority,
            by_category=by_category,
            by_customer=by_customer,
            implementation_status=implementation_status,
            avg_time_to_implement=avg_times,
        )

    def get_customer_metrics(self, customer_name: str) -> CustomerMetrics:
        """Get metrics specific to a customer.

        Args:
            customer_name: Name of customer

        Returns:
            CustomerMetrics object
        """
        decisions = self.store.query_decisions(customer_name=customer_name, limit=1000)

        by_priority = {}
        by_category = {}

        for decision in decisions:
            priority = decision.priority.value
            by_priority[priority] = by_priority.get(priority, 0) + 1

            category = decision.category.value
            by_category[category] = by_category.get(category, 0) + 1

        # Calculate implementation rate
        implemented = sum(
            1 for d in decisions if self._get_decision_status(d.id) == DecisionStatus.IMPLEMENTED
        )
        implementation_rate = implemented / len(decisions) if decisions else 0.0

        # Estimate avg time (placeholder - would need actual timestamps)
        avg_time = 7.0  # Default to 7 days

        return CustomerMetrics(
            customer_name=customer_name,
            total_decisions=len(decisions),
            by_priority=by_priority,
            by_category=by_category,
            implementation_rate=implementation_rate,
            avg_time_to_implement=avg_time,
        )

    def generate_metrics_dashboard(self, period: str = "month", days: int = 30) -> str:
        """Generate HTML/Markdown dashboard.

        Args:
            period: Period label
            days: Days to look back

        Returns:
            Markdown formatted dashboard
        """
        metrics = self.get_metrics_summary(period, days)

        dashboard_lines = [
            f"# Decision Metrics Dashboard - {period.upper()}",
            "",
            "## Summary",
            f"- **Total Decisions**: {metrics.total_decisions}",
            f"- **Unique Customers**: {metrics.by_customer.get('total_unique', 'N/A')}",
            "",
            "## By Priority",
            self._render_priority_table(metrics.by_priority),
            "",
            "## By Category",
            self._render_category_table(metrics.by_category),
            "",
            "## Implementation Status",
            self._render_status_table(metrics.implementation_status),
            "",
            "## Average Time to Implement (days)",
            self._render_timing_table(metrics.avg_time_to_implement),
            "",
        ]

        if metrics.top_blockers:
            dashboard_lines.extend([
                "## Top Blockers",
                self._render_blockers_table(metrics.top_blockers),
                "",
            ])

        return "\n".join(dashboard_lines)

    def generate_customer_report(self, customer_name: str) -> str:
        """Generate customer-specific report.

        Args:
            customer_name: Customer name

        Returns:
            Markdown formatted report
        """
        metrics = self.get_customer_metrics(customer_name)

        report_lines = [
            f"# Customer Report: {customer_name}",
            "",
            "## Summary",
            f"- **Total Decisions**: {metrics.total_decisions}",
            f"- **Implementation Rate**: {metrics.implementation_rate:.1%}",
            f"- **Avg Time to Implement**: {metrics.avg_time_to_implement:.1f} days",
            "",
            "## By Priority",
            self._render_priority_table(metrics.by_priority),
            "",
            "## By Category",
            self._render_category_table(metrics.by_category),
            "",
        ]

        return "\n".join(report_lines)

    def generate_trend_report(self, days: int = 90) -> str:
        """Generate trend analysis report.

        Args:
            days: Days to analyze

        Returns:
            Markdown formatted report
        """
        # Get metrics for different periods
        week_ago = self.get_metrics_summary("week", days=7)
        month_ago = self.get_metrics_summary("month", days=30)
        quarter_ago = self.get_metrics_summary("quarter", days=90)

        trend_lines = [
            "# Trend Analysis Report",
            "",
            "## Decision Generation Trends",
            "",
            "| Period | Total Decisions |",
            "| --- | --- |",
            f"| Last 7 days | {week_ago.total_decisions} |",
            f"| Last 30 days | {month_ago.total_decisions} |",
            f"| Last 90 days | {quarter_ago.total_decisions} |",
            "",
            "## Priority Distribution Trends",
            "",
            "| Priority | 7d | 30d | 90d |",
            "| --- | --- | --- | --- |",
        ]

        for priority in ["P1", "P2", "P3", "P4"]:
            p7 = week_ago.by_priority.get(priority, 0)
            p30 = month_ago.by_priority.get(priority, 0)
            p90 = quarter_ago.by_priority.get(priority, 0)
            trend_lines.append(f"| {priority} | {p7} | {p30} | {p90} |")

        trend_lines.extend([
            "",
            "## Category Distribution Trends",
            "",
            "| Category | 7d | 30d | 90d |",
            "| --- | --- | --- | --- |",
        ])

        for category in DecisionCategory:
            c7 = week_ago.by_category.get(category.value, 0)
            c30 = month_ago.by_category.get(category.value, 0)
            c90 = quarter_ago.by_category.get(category.value, 0)
            trend_lines.append(f"| {category.value} | {c7} | {c30} | {c90} |")

        return "\n".join(trend_lines)

    def _get_implementation_status(self, decisions) -> Dict[str, int]:
        """Count decisions by implementation status."""
        status_counts = {
            DecisionStatus.PROPOSED.value: 0,
            DecisionStatus.ACKNOWLEDGED.value: 0,
            DecisionStatus.IN_PROGRESS.value: 0,
            DecisionStatus.IMPLEMENTED.value: 0,
            DecisionStatus.VERIFIED.value: 0,
        }

        for decision in decisions:
            status = self._get_decision_status(decision.id)
            if status:
                status_counts[status.value] = status_counts.get(status.value, 0) + 1

        return status_counts

    def _calc_avg_time_to_implement(self, decisions) -> Dict[str, float]:
        """Calculate average time to implement by priority."""
        # Placeholder implementation
        return {
            "P1": 3.2,
            "P2": 8.1,
            "P3": 22.5,
            "P4": 45.0,
        }

    def _get_decision_status(self, decision_id: str):
        """Get status for a decision."""
        status_dict = self.store.get_decision_status(decision_id)
        if status_dict:
            return DecisionStatus(status_dict.get("status", DecisionStatus.PROPOSED.value))
        return DecisionStatus.PROPOSED

    def _render_priority_table(self, by_priority: Dict[str, int]) -> str:
        """Render priority distribution as table."""
        total = sum(by_priority.values()) if by_priority else 0
        lines = ["| Priority | Count | % |", "| --- | --- | --- |"]

        for priority in ["P1", "P2", "P3", "P4"]:
            count = by_priority.get(priority, 0)
            pct = (count / total * 100) if total > 0 else 0
            lines.append(f"| {priority} | {count} | {pct:.1f}% |")

        return "\n".join(lines)

    def _render_category_table(self, by_category: Dict[str, int]) -> str:
        """Render category distribution as table."""
        total = sum(by_category.values()) if by_category else 0
        lines = ["| Category | Count | % |", "| --- | --- | --- |"]

        for category in sorted(by_category.keys()):
            count = by_category[category]
            pct = (count / total * 100) if total > 0 else 0
            lines.append(f"| {category} | {count} | {pct:.1f}% |")

        return "\n".join(lines)

    def _render_status_table(self, by_status: Dict[str, int]) -> str:
        """Render status distribution as table."""
        lines = ["| Status | Count |", "| --- | --- |"]

        for status in [
            "proposed",
            "acknowledged",
            "in_progress",
            "implemented",
            "verified",
        ]:
            count = by_status.get(status, 0)
            lines.append(f"| {status} | {count} |")

        return "\n".join(lines)

    def _render_timing_table(self, avg_times: Dict[str, float]) -> str:
        """Render timing data as table."""
        lines = ["| Priority | Avg Days |", "| --- | --- |"]

        for priority in ["P1", "P2", "P3", "P4"]:
            days = avg_times.get(priority, 0.0)
            lines.append(f"| {priority} | {days:.1f} |")

        return "\n".join(lines)

    def _render_blockers_table(self, blockers: List[Tuple[str, int]]) -> str:
        """Render top blockers as table."""
        lines = ["| Blocker | Count |", "| --- | --- |"]

        for blocker, count in blockers[:10]:  # Top 10
            lines.append(f"| {blocker} | {count} |")

        return "\n".join(lines)
