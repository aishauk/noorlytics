"""Verified Findings Module

Defines normalized verified finding records for deterministic dependency analysis.
Every finding is traceable to specific evidence and can be consistently regenerated.

Confidence Levels:
- 'verified': parser results, OSV matches, explicit metadata lookups
- 'heuristic': curated fallback rules, legacy-pattern detection
- 'ai_interpreted': business interpretation, decision weighting (Phase 2+)

Finding Types:
- vulnerability: known security vulnerability from OSV or similar
- license_risk: risky license with known restrictions
- license_unknown: license could not be determined
- unpinned_dependency: version not specified in manifest
- legacy_dependency: appears very old and should be reviewed
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional
from enum import Enum


class ConfidenceLevel(str, Enum):
    """Confidence classification for findings."""
    VERIFIED = "verified"
    HEURISTIC = "heuristic"
    AI_INTERPRETED = "ai_interpreted"


class FindingType(str, Enum):
    """Taxonomy of finding types."""
    VULNERABILITY = "vulnerability"
    LICENSE_RISK = "license_risk"
    LICENSE_UNKNOWN = "license_unknown"
    UNPINNED_DEPENDENCY = "unpinned_dependency"
    LEGACY_DEPENDENCY = "legacy_dependency"
    GDPR_VIOLATION = "gdpr_violation"


class RemediationEffort(str, Enum):
    """Effort classification for remediation."""
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass
class Evidence:
    """Raw evidence supporting a finding.
    
    Attributes:
        source: Where the evidence came from (osv, pypi, nuget, manifest, etc.)
        raw: Raw evidence data (advisory ID, package name, version, etc.)
    """
    source: str  # 'osv', 'pypi', 'nuget', 'manifest', 'heuristic', etc.
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"source": self.source, "raw": self.raw}


@dataclass
class VerifiedFinding:
    """A single verified finding from deterministic analysis.
    
    Attributes:
        id: Unique finding identifier (auto-generated if not provided)
        finding_type: Classification of the finding
        title: Human-readable summary
        severity: high, medium, low, info (vulnerability) or high, medium, low (license risk)
        confidence: verified, heuristic, ai_interpreted
        affected_artifacts: Files and packages affected
        evidence: Raw evidence supporting this finding
        remediation: Suggested remediation action
        remediation_effort: small, medium, large
        business_tags: Tags for filtering/prioritization (security, availability, compliance, etc.)
        manifest_path: Path to the manifest file this finding comes from
    """
    finding_type: FindingType
    title: str
    severity: str
    confidence: ConfidenceLevel
    affected_artifacts: List[str]
    evidence: Evidence
    remediation: str
    remediation_effort: RemediationEffort
    business_tags: List[str]
    manifest_path: str
    id: str = field(default_factory=lambda: f"VF-{uuid.uuid4().hex[:8].upper()}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "finding_type": self.finding_type.value,
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence.value,
            "affected_artifacts": self.affected_artifacts,
            "evidence": self.evidence.to_dict(),
            "remediation": self.remediation,
            "remediation_effort": self.remediation_effort.value,
            "business_tags": self.business_tags,
            "manifest_path": self.manifest_path,
        }


class FindingBuilder:
    """Helper class to build findings consistently."""

    @staticmethod
    def vulnerability(
        package: str,
        current_version: str,
        advisory_id: str,
        severity: str = "high",
        fix_version: Optional[str] = None,
        source: str = "osv",
        manifest_path: str = "",
    ) -> VerifiedFinding:
        """Create a vulnerability finding."""
        return VerifiedFinding(
            finding_type=FindingType.VULNERABILITY,
            title=f"Known vulnerability in {package}@{current_version}",
            severity=severity,
            confidence=ConfidenceLevel.VERIFIED,
            affected_artifacts=[f"{package}@{current_version}", manifest_path],
            evidence=Evidence(
                source=source,
                raw={
                    "advisory_id": advisory_id,
                    "package": package,
                    "current_version": current_version,
                    "fix_version": fix_version,
                },
            ),
            remediation=f"Upgrade {package} to {fix_version or 'a newer version'}",
            remediation_effort=RemediationEffort.SMALL,
            business_tags=["security", "vulnerability"],
            manifest_path=manifest_path,
        )

    @staticmethod
    def license_risk(
        package: str,
        license_name: str,
        version: Optional[str] = None,
        source: str = "pypi",
        manifest_path: str = "",
    ) -> VerifiedFinding:
        """Create a risky license finding."""
        return VerifiedFinding(
            finding_type=FindingType.LICENSE_RISK,
            title=f"Risky license on {package}: {license_name}",
            severity="high",
            confidence=ConfidenceLevel.HEURISTIC,
            affected_artifacts=[f"{package}@{version}" if version else package, manifest_path],
            evidence=Evidence(
                source=source,
                raw={"package": package, "version": version, "license": license_name},
            ),
            remediation=f"Review {license_name} license compatibility and consider {package} alternatives",
            remediation_effort=RemediationEffort.MEDIUM,
            business_tags=["license", "compliance"],
            manifest_path=manifest_path,
        )

    @staticmethod
    def license_unknown(
        package: str,
        version: Optional[str] = None,
        source: str = "pypi",
        manifest_path: str = "",
    ) -> VerifiedFinding:
        """Create an unknown license finding."""
        return VerifiedFinding(
            finding_type=FindingType.LICENSE_UNKNOWN,
            title=f"Unknown license on {package}",
            severity="medium",
            confidence=ConfidenceLevel.HEURISTIC,
            affected_artifacts=[f"{package}@{version}" if version else package, manifest_path],
            evidence=Evidence(
                source=source,
                raw={"package": package, "version": version},
            ),
            remediation=f"Investigate and document the license for {package}",
            remediation_effort=RemediationEffort.SMALL,
            business_tags=["license", "compliance"],
            manifest_path=manifest_path,
        )

    @staticmethod
    def unpinned_dependency(
        package: str,
        source: str = "manifest",
        manifest_path: str = "",
    ) -> VerifiedFinding:
        """Create an unpinned dependency finding."""
        return VerifiedFinding(
            finding_type=FindingType.UNPINNED_DEPENDENCY,
            title=f"Unpinned dependency: {package}",
            severity="medium",
            confidence=ConfidenceLevel.VERIFIED,
            affected_artifacts=[package, manifest_path],
            evidence=Evidence(
                source=source,
                raw={"package": package, "version": None},
            ),
            remediation=f"Pin {package} to a specific version",
            remediation_effort=RemediationEffort.SMALL,
            business_tags=["dependency_management", "reproducibility"],
            manifest_path=manifest_path,
        )

    @staticmethod
    def legacy_dependency(
        package: str,
        version: str,
        ecosystem: str = "dotnet",
        source: str = "heuristic",
        manifest_path: str = "",
    ) -> VerifiedFinding:
        """Create a legacy dependency finding."""
        return VerifiedFinding(
            finding_type=FindingType.LEGACY_DEPENDENCY,
            title=f"Legacy dependency: {package}@{version}",
            severity="medium",
            confidence=ConfidenceLevel.HEURISTIC,
            affected_artifacts=[f"{package}@{version}", manifest_path],
            evidence=Evidence(
                source=source,
                raw={"package": package, "version": version, "ecosystem": ecosystem},
            ),
            remediation=f"Review {package}@{version} and consider upgrading to a modern version",
            remediation_effort=RemediationEffort.LARGE,
            business_tags=["modernization", "maintenance"],
            manifest_path=manifest_path,
        )

    @staticmethod
    def gdpr_violation(
        rule: str,
        description: str,
        filename: str = "",
        line_number: int = 0,
        severity: str = "high",
        source: str = "static_scan",
    ) -> VerifiedFinding:
        """Create a GDPR/privacy violation finding."""
        return VerifiedFinding(
            finding_type=FindingType.GDPR_VIOLATION,
            title=f"GDPR violation: {rule}",
            severity=severity,
            confidence=ConfidenceLevel.HEURISTIC,
            affected_artifacts=[filename or "unknown.py"],
            evidence=Evidence(
                source=source,
                raw={"rule": rule, "line": line_number, "description": description},
            ),
            remediation="Mask or minimize personal data, use encrypted transport, and review consent/retention handling.",
            remediation_effort=RemediationEffort.MEDIUM,
            business_tags=["privacy", "gdpr", "compliance"],
            manifest_path=filename or "",
        )


class FindingsCollection:
    """Container for multiple findings with sorting and filtering."""

    def __init__(self, findings: Optional[List[VerifiedFinding]] = None, manifest_path: str = ""):
        self.findings = findings or []
        self.manifest_path = manifest_path

    def add(self, finding: VerifiedFinding) -> None:
        """Add a finding to the collection."""
        self.findings.append(finding)

    def add_all(self, findings: List[VerifiedFinding]) -> None:
        """Add multiple findings to the collection."""
        self.findings.extend(findings)

    def by_type(self, finding_type: FindingType) -> List[VerifiedFinding]:
        """Filter findings by type."""
        return [f for f in self.findings if f.finding_type == finding_type]

    def by_severity(self, severity: str) -> List[VerifiedFinding]:
        """Filter findings by severity."""
        return [f for f in self.findings if f.severity == severity]

    def by_confidence(self, confidence: ConfidenceLevel) -> List[VerifiedFinding]:
        """Filter findings by confidence level."""
        return [f for f in self.findings if f.confidence == confidence]

    def by_tag(self, tag: str) -> List[VerifiedFinding]:
        """Filter findings by business tag."""
        return [f for f in self.findings if tag in f.business_tags]

    def sorted_by_severity(self) -> List[VerifiedFinding]:
        """Return findings sorted by severity (high -> low) then by type."""
        severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        return sorted(
            self.findings,
            key=lambda f: (severity_order.get(f.severity, 999), f.finding_type.value),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert collection to dictionary."""
        return {
            "manifest_path": self.manifest_path,
            "finding_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert collection to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_json_file(self, path: str) -> None:
        """Write findings to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @staticmethod
    def from_json(json_str: str) -> FindingsCollection:
        """Create collection from JSON string."""
        data = json.loads(json_str)
        findings = []
        for f_dict in data.get("findings", []):
            evidence = Evidence(
                source=f_dict["evidence"]["source"],
                raw=f_dict["evidence"]["raw"],
            )
            finding = VerifiedFinding(
                id=f_dict["id"],
                finding_type=FindingType(f_dict["finding_type"]),
                title=f_dict["title"],
                severity=f_dict["severity"],
                confidence=ConfidenceLevel(f_dict["confidence"]),
                affected_artifacts=f_dict["affected_artifacts"],
                evidence=evidence,
                remediation=f_dict["remediation"],
                remediation_effort=RemediationEffort(f_dict["remediation_effort"]),
                business_tags=f_dict["business_tags"],
                manifest_path=f_dict["manifest_path"],
            )
            findings.append(finding)
        return FindingsCollection(findings, data.get("manifest_path", ""))

    @staticmethod
    def from_json_file(path: str) -> FindingsCollection:
        """Create collection from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            return FindingsCollection.from_json(f.read())

    def stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        by_type = {}
        by_severity = {}
        by_confidence = {}

        for f in self.findings:
            by_type[f.finding_type.value] = by_type.get(f.finding_type.value, 0) + 1
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            by_confidence[f.confidence.value] = by_confidence.get(f.confidence.value, 0) + 1

        return {
            "total": len(self.findings),
            "by_type": by_type,
            "by_severity": by_severity,
            "by_confidence": by_confidence,
        }
