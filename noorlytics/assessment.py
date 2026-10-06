"""Assessment Module - Customer-Context-Aware Decision Generation

Transforms verified findings into prioritized business decisions based on
customer risk preferences and constraints.

This module:
1. Loads customer context (risk priorities, constraints)
2. Loads verified findings from Phase 1
3. Prioritizes findings based on customer context
4. Generates decision records with evidence traces
5. Outputs decision support in JSON and Markdown
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional
from enum import Enum
from pathlib import Path

from .findings import FindingsCollection, FindingType, ConfidenceLevel


class Priority(str, Enum):
    """Decision priority levels."""
    P1 = "P1"  # Urgent - implement immediately
    P2 = "P2"  # High - implement next sprint
    P3 = "P3"  # Medium - implement in roadmap
    P4 = "P4"  # Low - nice to have


class DecisionCategory(str, Enum):
    """Decision categories based on finding types."""
    SECURITY = "security"
    LICENSE_COMPLIANCE = "license_compliance"
    DEPENDENCY_MANAGEMENT = "dependency_management"
    MODERNIZATION = "modernization"


@dataclass
class RiskPreference:
    """Customer risk preferences for a category."""
    security: str = "medium"  # high, medium, low
    business_continuity: str = "medium"
    cost_control: str = "medium"
    delivery_speed: str = "medium"

    def get_score(self, category: str) -> int:
        """Get priority score for a category (higher = more important)."""
        scores = {
            "high": 3,
            "medium": 2,
            "low": 1,
        }
        return scores.get(getattr(self, category.lower(), "medium"), 2)


@dataclass
class Constraint:
    """Customer constraints that affect decisions."""
    upgrade_window_days: int = 30
    requires_oss_license_review: bool = False
    legacy_runtime: Optional[str] = None
    min_security_score: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "upgrade_window_days": self.upgrade_window_days,
            "requires_oss_license_review": self.requires_oss_license_review,
            "legacy_runtime": self.legacy_runtime,
            "min_security_score": self.min_security_score,
        }


@dataclass
class CustomerContext:
    """Customer profile for assessment personalization."""
    customer_name: str
    industry: str
    deployment: str  # "internal", "customer-facing", "internal and customer-facing"
    risk_preferences: RiskPreference = field(default_factory=RiskPreference)
    constraints: Constraint = field(default_factory=Constraint)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_name": self.customer_name,
            "industry": self.industry,
            "deployment": self.deployment,
            "risk_preferences": asdict(self.risk_preferences),
            "constraints": self.constraints.to_dict(),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> CustomerContext:
        """Load customer context from dictionary."""
        prefs_data = data.get("risk_preferences", {})
        risk_prefs = RiskPreference(
            security=prefs_data.get("security", "medium"),
            business_continuity=prefs_data.get("business_continuity", "medium"),
            cost_control=prefs_data.get("cost_control", "medium"),
            delivery_speed=prefs_data.get("delivery_speed", "medium"),
        )

        constraints_data = data.get("constraints", {})
        constraints = Constraint(
            upgrade_window_days=constraints_data.get("upgrade_window_days", 30),
            requires_oss_license_review=constraints_data.get(
                "requires_oss_license_review", False
            ),
            legacy_runtime=constraints_data.get("legacy_runtime"),
            min_security_score=constraints_data.get("min_security_score", 0),
        )

        return CustomerContext(
            customer_name=data.get("customer_name", "Unknown"),
            industry=data.get("industry", "unknown"),
            deployment=data.get("deployment", "unknown"),
            risk_preferences=risk_prefs,
            constraints=constraints,
        )

    @staticmethod
    def from_json(json_str: str) -> CustomerContext:
        """Load customer context from JSON string."""
        data = json.loads(json_str)
        return CustomerContext.from_dict(data)

    @staticmethod
    def from_json_file(path: str) -> CustomerContext:
        """Load customer context from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            return CustomerContext.from_json(f.read())


@dataclass
class TradeoffSummary:
    """Impact of a decision on different categories."""
    security: str = "neutral"  # high gain/reduction, medium, low, neutral
    business_continuity: str = "neutral"
    cost_control: str = "neutral"
    delivery_speed: str = "neutral"

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass
class Decision:
    """A prioritized decision based on findings and customer context."""
    id: str
    priority: Priority
    title: str
    category: DecisionCategory
    rationale: str
    tradeoff_summary: TradeoffSummary
    evidence_ids: List[str]  # Links to VF-* finding IDs
    affected_packages: List[str]
    recommended_action: str
    owner_hint: str  # "security_team", "devops", "engineering", etc.
    target_timeframe: str
    effort_estimate: str
    business_impact: str

    def __post_init__(self):
        if not self.id:
            self.id = f"DEC-{uuid.uuid4().hex[:8].upper()}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.id,
            "priority": self.priority.value,
            "title": self.title,
            "category": self.category.value,
            "rationale": self.rationale,
            "tradeoff_summary": self.tradeoff_summary.to_dict(),
            "evidence_ids": self.evidence_ids,
            "affected_packages": self.affected_packages,
            "recommended_action": self.recommended_action,
            "owner_hint": self.owner_hint,
            "target_timeframe": self.target_timeframe,
            "effort_estimate": self.effort_estimate,
            "business_impact": self.business_impact,
        }


@dataclass
class AssessmentResult:
    """Complete assessment output with decisions."""
    manifest_path: str
    customer_context: CustomerContext
    findings_count: int
    decisions: List[Decision] = field(default_factory=list)
    generated_at: str = ""

    def add_decision(self, decision: Decision) -> None:
        """Add a decision to the result."""
        self.decisions.append(decision)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_path": self.manifest_path,
            "customer_context": self.customer_context.to_dict(),
            "findings_count": self.findings_count,
            "decision_count": len(self.decisions),
            "decisions": [d.to_dict() for d in self.decisions],
            "generated_at": self.generated_at,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_json_file(self, path: str) -> None:
        """Write to JSON file."""
        Path(path).write_text(self.to_json(), encoding="utf-8")

    def to_markdown(self) -> str:
        """Convert to human-readable Markdown."""
        lines = []

        lines.append(f"# Assessment Report: {self.manifest_path}")
        lines.append("")
        lines.append(f"**Customer**: {self.customer_context.customer_name}")
        lines.append(
            f"**Industry**: {self.customer_context.industry} / {self.customer_context.deployment}"
        )
        lines.append("")

        lines.append("## Customer Risk Profile")
        prefs = self.customer_context.risk_preferences
        lines.append(f"- Security: **{prefs.security.upper()}**")
        lines.append(f"- Business Continuity: **{prefs.business_continuity.upper()}**")
        lines.append(f"- Cost Control: **{prefs.cost_control.upper()}**")
        lines.append(f"- Delivery Speed: **{prefs.delivery_speed.upper()}**")
        lines.append("")

        lines.append("## Customer Constraints")
        cons = self.customer_context.constraints
        lines.append(
            f"- Upgrade Window: **{cons.upgrade_window_days} days**"
        )
        if cons.requires_oss_license_review:
            lines.append("- Requires OSS License Review: **YES**")
        if cons.legacy_runtime:
            lines.append(f"- Legacy Runtime: **{cons.legacy_runtime}**")
        lines.append("")

        lines.append("## Summary")
        lines.append(f"- Findings Analyzed: {self.findings_count}")
        lines.append(f"- Decisions Generated: {len(self.decisions)}")
        lines.append("")

        # Group decisions by priority
        by_priority = {}
        for decision in self.decisions:
            if decision.priority not in by_priority:
                by_priority[decision.priority] = []
            by_priority[decision.priority].append(decision)

        for priority in [Priority.P1, Priority.P2, Priority.P3, Priority.P4]:
            decisions_at_priority = by_priority.get(priority, [])
            if not decisions_at_priority:
                continue

            lines.append(f"## {priority.value} - Priority Decisions")
            lines.append("")

            for decision in decisions_at_priority:
                lines.append(f"### {decision.title}")
                lines.append(f"**Category**: {decision.category.value}")
                lines.append(f"**Timeframe**: {decision.target_timeframe}")
                lines.append(f"**Effort**: {decision.effort_estimate}")
                lines.append("")

                lines.append("**Rationale**:")
                lines.append(f"> {decision.rationale}")
                lines.append("")

                lines.append("**Recommended Action**:")
                lines.append(f"> {decision.recommended_action}")
                lines.append("")

                lines.append("**Business Impact**:")
                lines.append(f"> {decision.business_impact}")
                lines.append("")

                if decision.evidence_ids:
                    lines.append(f"**Evidence**: {', '.join(decision.evidence_ids)}")
                    lines.append("")

                if decision.affected_packages:
                    lines.append("**Affected Packages**:")
                    for pkg in decision.affected_packages[:10]:
                        lines.append(f"  - {pkg}")
                    if len(decision.affected_packages) > 10:
                        lines.append(
                            f"  - ... and {len(decision.affected_packages) - 10} more"
                        )
                    lines.append("")

                lines.append("---")
                lines.append("")

        return "\n".join(lines)


class AssessmentEngine:
    """Generates prioritized decisions from findings and customer context."""

    def __init__(self, customer_context: CustomerContext):
        self.customer_context = customer_context

    def assess(
        self, findings: FindingsCollection, manifest_path: str = ""
    ) -> AssessmentResult:
        """Generate decisions from findings based on customer context."""
        result = AssessmentResult(
            manifest_path=manifest_path or findings.manifest_path,
            customer_context=self.customer_context,
            findings_count=len(findings.findings),
        )

        # Group findings by type and generate decisions
        vulnerability_findings = findings.by_type(FindingType.VULNERABILITY)
        if vulnerability_findings:
            self._generate_security_decisions(
                result, vulnerability_findings, findings
            )

        license_findings = findings.by_type(FindingType.LICENSE_RISK) + findings.by_type(
            FindingType.LICENSE_UNKNOWN
        )
        if license_findings:
            self._generate_compliance_decisions(result, license_findings, findings)

        unpinned_findings = findings.by_type(FindingType.UNPINNED_DEPENDENCY)
        if unpinned_findings:
            self._generate_dependency_management_decisions(
                result, unpinned_findings, findings
            )

        legacy_findings = findings.by_type(FindingType.LEGACY_DEPENDENCY)
        if legacy_findings:
            self._generate_modernization_decisions(result, legacy_findings, findings)

        return result

    def _generate_security_decisions(
        self,
        result: AssessmentResult,
        vuln_findings: List,
        all_findings: FindingsCollection,
    ) -> None:
        """Generate security-focused decisions."""
        if not vuln_findings:
            return

        # Count high vs medium severity
        high_severity = [f for f in vuln_findings if f.severity == "high"]
        medium_severity = [f for f in vuln_findings if f.severity == "medium"]

        # Determine priority based on customer preferences
        security_pref = self.customer_context.risk_preferences.security
        priority = Priority.P1 if security_pref == "high" else Priority.P2

        if high_severity:
            affected_packages = list(
                {pkg for f in high_severity for pkg in f.affected_artifacts}
            )
            decision = Decision(
                id="",
                priority=priority,
                title=f"Address {len(high_severity)} high-severity vulnerabilities",
                category=DecisionCategory.SECURITY,
                rationale=self._build_security_rationale(
                    high_severity, security_pref
                ),
                tradeoff_summary=TradeoffSummary(
                    security="high gain",
                    business_continuity="risk reduction",
                    cost_control="medium effort",
                    delivery_speed="1-2 week sprint",
                ),
                evidence_ids=[f.id for f in high_severity],
                affected_packages=affected_packages[:10],
                recommended_action="Create security upgrade sprint. Prioritize internet-facing services. Validate in staging. Deploy within upgrade window.",
                owner_hint="security_team",
                target_timeframe=f"{self.customer_context.constraints.upgrade_window_days} days",
                effort_estimate="2-5 days",
                business_impact=f"Eliminates {len(high_severity)} high-severity vulnerabilities affecting customer-facing systems",
            )
            result.add_decision(decision)

        if medium_severity:
            priority_medium = Priority.P2 if security_pref in ("high", "medium") else Priority.P3
            affected_packages = list(
                {pkg for f in medium_severity for pkg in f.affected_artifacts}
            )
            decision = Decision(
                id="",
                priority=priority_medium,
                title=f"Plan remediation of {len(medium_severity)} medium-severity vulnerabilities",
                category=DecisionCategory.SECURITY,
                rationale=self._build_security_rationale(
                    medium_severity, security_pref
                ),
                tradeoff_summary=TradeoffSummary(
                    security="medium gain",
                    business_continuity="neutral",
                    cost_control="medium effort",
                    delivery_speed="next sprint",
                ),
                evidence_ids=[f.id for f in medium_severity],
                affected_packages=affected_packages[:10],
                recommended_action="Schedule for next monthly security patch cycle. Monitor for exploitation. Add to dependency review checklist.",
                owner_hint="devops",
                target_timeframe="30 days",
                effort_estimate="1-2 days",
                business_impact=f"Reduces attack surface by addressing {len(medium_severity)} known vulnerabilities",
            )
            result.add_decision(decision)

    def _generate_compliance_decisions(
        self, result: AssessmentResult, lic_findings: List, all_findings: FindingsCollection
    ) -> None:
        """Generate license compliance decisions."""
        if not lic_findings:
            return

        unknown_licenses = [
            f for f in lic_findings if f.finding_type == FindingType.LICENSE_UNKNOWN
        ]
        risky_licenses = [
            f for f in lic_findings if f.finding_type == FindingType.LICENSE_RISK
        ]

        if risky_licenses and self.customer_context.constraints.requires_oss_license_review:
            affected_packages = list(
                {pkg for f in risky_licenses for pkg in f.affected_artifacts}
            )
            decision = Decision(
                id="",
                priority=Priority.P1,
                title=f"Conduct license review for {len(risky_licenses)} high-risk dependencies",
                category=DecisionCategory.LICENSE_COMPLIANCE,
                rationale=f"Customer {self.customer_context.customer_name} (industry: {self.customer_context.industry}) requires explicit OSS license review. Risky licenses detected that may violate corporate policy.",
                tradeoff_summary=TradeoffSummary(
                    security="neutral",
                    business_continuity="compliance gain",
                    cost_control="medium effort",
                    delivery_speed="1 week",
                ),
                evidence_ids=[f.id for f in risky_licenses],
                affected_packages=affected_packages[:10],
                recommended_action="Involve legal/compliance team. Review alternatives for each package. Document approval or replacement plan.",
                owner_hint="compliance_team",
                target_timeframe="7 days",
                effort_estimate="2-3 days",
                business_impact="Ensures OSS dependencies comply with corporate licensing policy",
            )
            result.add_decision(decision)

        if unknown_licenses:
            priority = Priority.P2 if self.customer_context.constraints.requires_oss_license_review else Priority.P3
            affected_packages = list(
                {pkg for f in unknown_licenses for pkg in f.affected_artifacts}
            )
            decision = Decision(
                id="",
                priority=priority,
                title=f"Investigate licenses for {len(unknown_licenses)} packages",
                category=DecisionCategory.LICENSE_COMPLIANCE,
                rationale=f"License information missing for {len(unknown_licenses)} dependencies. Investigation needed to verify compliance.",
                tradeoff_summary=TradeoffSummary(
                    security="neutral",
                    business_continuity="neutral",
                    cost_control="low effort",
                    delivery_speed="low impact",
                ),
                evidence_ids=[f.id for f in unknown_licenses],
                affected_packages=affected_packages[:10],
                recommended_action="Check PyPI/npm/NuGet metadata. Verify with package maintainers. Document findings in dependency registry.",
                owner_hint="engineering",
                target_timeframe="14 days",
                effort_estimate="1-2 days",
                business_impact="Completes license inventory for risk management and compliance",
            )
            result.add_decision(decision)

    def _generate_dependency_management_decisions(
        self, result: AssessmentResult, unpinned_findings: List, all_findings: FindingsCollection
    ) -> None:
        """Generate dependency management decisions."""
        if not unpinned_findings:
            return

        affected_packages = list(
            {pkg for f in unpinned_findings for pkg in f.affected_artifacts}
        )
        priority = Priority.P2 if self.customer_context.risk_preferences.delivery_speed == "high" else Priority.P3

        decision = Decision(
            id="",
            priority=priority,
            title=f"Pin {len(unpinned_findings)} unpinned dependencies to specific versions",
            category=DecisionCategory.DEPENDENCY_MANAGEMENT,
            rationale="Unpinned dependencies introduce non-deterministic builds and make vulnerability tracking difficult. Pinning enables reproducible builds and easier patching.",
            tradeoff_summary=TradeoffSummary(
                security="medium gain",
                business_continuity="high gain",
                cost_control="low effort",
                delivery_speed="low impact",
            ),
            evidence_ids=[f.id for f in unpinned_findings],
            affected_packages=affected_packages[:10],
            recommended_action="Review current pinned version strategy. Pin unpinned packages to latest stable. Add CI check to require pinned versions.",
            owner_hint="devops",
            target_timeframe="14 days",
            effort_estimate="1 day",
            business_impact="Improves build reproducibility and enables faster vulnerability response",
        )
        result.add_decision(decision)

    def _generate_modernization_decisions(
        self, result: AssessmentResult, legacy_findings: List, all_findings: FindingsCollection
    ) -> None:
        """Generate modernization decisions."""
        if not legacy_findings:
            return

        affected_packages = list(
            {pkg for f in legacy_findings for pkg in f.affected_artifacts}
        )
        priority = Priority.P3  # Typically lower priority unless customer prefers modernization

        decision = Decision(
            id="",
            priority=priority,
            title=f"Plan modernization of {len(legacy_findings)} legacy dependencies",
            category=DecisionCategory.MODERNIZATION,
            rationale="Legacy versions lack recent security patches and features. Modernization improves maintainability and future-proofs the system.",
            tradeoff_summary=TradeoffSummary(
                security="medium gain",
                business_continuity="neutral",
                cost_control="high effort",
                delivery_speed="high impact",
            ),
            evidence_ids=[f.id for f in legacy_findings],
            affected_packages=affected_packages[:10],
            recommended_action="Evaluate modern alternatives. Plan gradual migration. Consider impact on downstream code. Schedule for major version release.",
            owner_hint="architecture",
            target_timeframe="Q2-Q3",
            effort_estimate="5-10 days",
            business_impact="Reduces technical debt and prepares system for future compatibility requirements",
        )
        result.add_decision(decision)

    def _build_security_rationale(self, findings: List, security_pref: str) -> str:
        """Build a customer-specific security rationale."""
        customer = self.customer_context.customer_name
        industry = self.customer_context.industry
        deployment = self.customer_context.deployment

        if security_pref == "high":
            return (
                f"Customer {customer} (industry: {industry}) prioritizes security. "
                f"Vulnerabilities in {deployment} systems require immediate remediation to protect customer data and maintain compliance."
            )
        else:
            return (
                f"Customer {customer} has {security_pref} security priority. "
                f"Vulnerabilities should be addressed in the next planned maintenance window."
            )
