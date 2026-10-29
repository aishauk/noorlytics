"""Unified Security & Compliance Scanner

Combines findings from audit_security and scan_standards into a unified report
with correlation and deduplication.

Features:
- Merge security findings with compliance violations
- Deduplicate overlapping issues
- Cross-reference related findings
- Generate unified summary reports
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Optional, Set, Any
from enum import Enum


class FindingCategory(Enum):
    """Categorize findings as security, compliance, or both."""
    SECURITY_ONLY = "security_only"
    COMPLIANCE_ONLY = "compliance_only"
    BOTH = "both"  # Overlapping security and compliance issue


class CorrelationType(Enum):
    """Types of correlations between findings."""
    SAME_LOCATION = "same_location"  # Same file and line
    SAME_ISSUE = "same_issue"  # Same type of issue, different detectors
    RELATED = "related"  # Related but different issues
    NONE = "none"  # No correlation


@dataclass
class UnifiedFinding:
    """A unified finding combining security and compliance perspectives."""
    
    # Identification
    finding_id: str  # e.g., "UF-001"
    
    # Core issue
    title: str  # Human-readable title
    description: str  # Detailed description
    severity: str  # high, medium, low
    
    # Location
    filename: str
    line: int
    evidence: str  # Code snippet
    
    # Sources (which scanners detected this)
    sources: List[str]  # ["audit_security", "scan_standards"]
    category: FindingCategory
    
    # Security perspective
    security_check_type: Optional[str] = None  # e.g., "encryption", "audit_logging"
    security_severity: Optional[str] = None
    
    # Compliance perspective
    compliance_standard: Optional[str] = None  # e.g., "hipaa", "pci-dss"
    compliance_requirement: Optional[str] = None  # e.g., "164.312(a)(2)(ii)"
    compliance_severity: Optional[str] = None
    
    # Remediation
    remediation_steps: List[str] = field(default_factory=list)
    remediation_priority: str = "medium"  # high, medium, low
    
    # Correlation
    correlated_finding_ids: List[str] = field(default_factory=list)
    correlation_reason: str = ""
    
    # Metadata
    confidence: float = 0.95  # 0.0-1.0
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["category"] = self.category.value
        data["correlation_type"] = self.correlation_reason
        return data


class UnifiedScanResult:
    """Container for unified scan results."""
    
    def __init__(self, filename: str):
        self.filename = filename
        self.findings: Dict[str, UnifiedFinding] = {}
        self.security_findings: List[Dict[str, Any]] = []
        self.compliance_findings: List[Dict[str, Any]] = []
        self.correlations: Dict[str, List[str]] = {}  # finding_id -> correlated_ids
        
    def add_security_finding(self, finding: Dict[str, Any]) -> None:
        """Add a finding from audit_security."""
        self.security_findings.append(finding)
    
    def add_compliance_finding(self, finding: Dict[str, Any]) -> None:
        """Add a finding from scan_standards."""
        self.compliance_findings.append(finding)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        return {
            "filename": self.filename,
            "total_findings": len(self.findings),
            "security_only": sum(1 for f in self.findings.values() if f.category == FindingCategory.SECURITY_ONLY),
            "compliance_only": sum(1 for f in self.findings.values() if f.category == FindingCategory.COMPLIANCE_ONLY),
            "overlapping": sum(1 for f in self.findings.values() if f.category == FindingCategory.BOTH),
            "high_severity": sum(1 for f in self.findings.values() if f.severity == "high"),
            "medium_severity": sum(1 for f in self.findings.values() if f.severity == "medium"),
            "low_severity": sum(1 for f in self.findings.values() if f.severity == "low"),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary."""
        return {
            "filename": self.filename,
            "summary": self.get_summary(),
            "findings": [f.to_dict() for f in self.findings.values()],
            "correlations": self.correlations,
        }


class UnifiedScanner:
    """Merge and correlate security and compliance findings."""
    
    def __init__(self):
        self.findings_counter = 0
    
    def _generate_finding_id(self) -> str:
        """Generate unique finding ID."""
        self.findings_counter += 1
        return f"UF-{self.findings_counter:03d}"
    
    def _normalize_severity(self, severity: str) -> str:
        """Normalize severity levels."""
        severity_map = {
            "critical": "high",
            "high": "high",
            "medium": "medium",
            "low": "low",
            "info": "low",
        }
        return severity_map.get(severity.lower(), "medium")
    
    def _calculate_combined_severity(
        self,
        security_severity: Optional[str],
        compliance_severity: Optional[str],
    ) -> str:
        """Calculate severity when both security and compliance apply."""
        severity_order = {"high": 3, "medium": 2, "low": 1}
        
        if security_severity and compliance_severity:
            sec_level = severity_order.get(security_severity, 1)
            comp_level = severity_order.get(compliance_severity, 1)
            return "high" if max(sec_level, comp_level) >= 3 else (
                "medium" if max(sec_level, comp_level) >= 2 else "low"
            )
        elif security_severity:
            return security_severity
        elif compliance_severity:
            return compliance_severity
        return "medium"
    
    def _correlate_findings(
        self,
        result: UnifiedScanResult,
    ) -> None:
        """Identify and link correlated findings."""
        findings_list = list(result.findings.values())
        
        for i, finding1 in enumerate(findings_list):
            for finding2 in findings_list[i + 1 :]:
                if self._should_correlate(finding1, finding2):
                    # Link them bidirectionally
                    if finding2.finding_id not in finding1.correlated_finding_ids:
                        finding1.correlated_finding_ids.append(finding2.finding_id)
                    if finding1.finding_id not in finding2.correlated_finding_ids:
                        finding2.correlated_finding_ids.append(finding1.finding_id)
                    
                    # Update correlations map
                    if finding1.finding_id not in result.correlations:
                        result.correlations[finding1.finding_id] = []
                    result.correlations[finding1.finding_id].append(finding2.finding_id)
    
    def _should_correlate(self, finding1: UnifiedFinding, finding2: UnifiedFinding) -> bool:
        """Determine if two findings should be correlated."""
        # Same location
        if (
            finding1.filename == finding2.filename
            and finding1.line == finding2.line
        ):
            return True
        
        # Same file, related issues (e.g., HTTP and unencrypted)
        if finding1.filename == finding2.filename:
            related_pairs = [
                ("http", "unencrypted"),
                ("hardcoded", "credential"),
                ("plaintext", "password"),
                ("audit_logging", "sensitive"),
            ]
            evidence_lower = (finding1.evidence + finding2.evidence).lower()
            for term1, term2 in related_pairs:
                if term1 in evidence_lower and term2 in evidence_lower:
                    return True
        
        return False
    
    def scan(
        self,
        filename: str,
        security_findings: List[Dict[str, Any]],
        compliance_findings: List[Dict[str, Any]],
    ) -> UnifiedScanResult:
        """Merge and correlate findings from both scanners.
        
        Args:
            filename: File being scanned
            security_findings: Output from audit_security
            compliance_findings: Output from scan_standards
            
        Returns:
            UnifiedScanResult with merged and correlated findings
        """
        result = UnifiedScanResult(filename)
        
        # Add raw findings
        for finding in security_findings:
            result.add_security_finding(finding)
        for finding in compliance_findings:
            result.add_compliance_finding(finding)
        
        # Build location index for deduplication
        location_index = {}  # (filename, line) -> (finding_id, type)
        
        # Create unified findings from security-only issues
        for sec_finding in security_findings:
            location = (sec_finding['filename'], sec_finding['line'])
            
            # Check if compliance finding already exists at same location
            matching_compliance = None
            for comp_finding in compliance_findings:
                comp_location = (comp_finding['filename'], comp_finding.get('line', -1))
                if comp_location == location:
                    matching_compliance = comp_finding
                    break
            
            finding_id = self._generate_finding_id()
            
            if matching_compliance:
                # Create merged finding (both security and compliance apply)
                finding = UnifiedFinding(
                    finding_id=finding_id,
                    title=f"{sec_finding['check_type'].upper()} + {matching_compliance['standard'].upper()}: {sec_finding['message'][:40]}",
                    description=f"Security: {sec_finding['message']}\nCompliance: {matching_compliance['message']}",
                    severity=self._calculate_combined_severity(
                        self._normalize_severity(sec_finding['severity']),
                        self._normalize_severity(matching_compliance['severity']),
                    ),
                    filename=sec_finding['filename'],
                    line=sec_finding['line'],
                    evidence=sec_finding['evidence'],
                    sources=["audit_security", "scan_standards"],
                    category=FindingCategory.BOTH,
                    security_check_type=sec_finding['check_type'],
                    security_severity=self._normalize_severity(sec_finding['severity']),
                    compliance_standard=matching_compliance['standard'],
                    compliance_requirement=matching_compliance['requirement'],
                    compliance_severity=self._normalize_severity(matching_compliance['severity']),
                    remediation_steps=[
                        f"Address {sec_finding['check_type']}: {sec_finding['message']}",
                        f"Comply with {matching_compliance['standard']}: {matching_compliance['remediation']}",
                    ],
                    tags=["security", "compliance", sec_finding['check_type'], matching_compliance['standard']],
                )
                result.findings[finding_id] = finding
                location_index[location] = (finding_id, "both")
                
                # Mark compliance finding as processed (don't create duplicate)
                compliance_findings = [f for f in compliance_findings if f != matching_compliance]
            else:
                # Security-only finding
                finding = UnifiedFinding(
                    finding_id=finding_id,
                    title=f"{sec_finding['check_type'].upper()}: {sec_finding['message'][:50]}",
                    description=sec_finding['message'],
                    severity=self._normalize_severity(sec_finding['severity']),
                    filename=sec_finding['filename'],
                    line=sec_finding['line'],
                    evidence=sec_finding['evidence'],
                    sources=["audit_security"],
                    category=FindingCategory.SECURITY_ONLY,
                    security_check_type=sec_finding['check_type'],
                    security_severity=self._normalize_severity(sec_finding['severity']),
                    remediation_steps=[
                        f"Address {sec_finding['check_type']}: {sec_finding['message']}"
                    ],
                    tags=["security", sec_finding['check_type']],
                )
                result.findings[finding_id] = finding
                location_index[location] = (finding_id, "security")
        
        # Create unified findings from remaining compliance-only issues
        for comp_finding in compliance_findings:
            # Already merged above, skip if no security finding at same location
            finding_id = self._generate_finding_id()
            result.findings[finding_id] = UnifiedFinding(
                finding_id=finding_id,
                title=f"{comp_finding['standard'].upper()} {comp_finding['requirement']}: {comp_finding['message'][:50]}",
                description=comp_finding['message'],
                severity=self._normalize_severity(comp_finding['severity']),
                filename=comp_finding['filename'],
                line=comp_finding.get('line', -1),
                evidence=comp_finding['evidence'],
                sources=["scan_standards"],
                category=FindingCategory.COMPLIANCE_ONLY,
                compliance_standard=comp_finding['standard'],
                compliance_requirement=comp_finding['requirement'],
                compliance_severity=self._normalize_severity(comp_finding['severity']),
                remediation_steps=[comp_finding['remediation']],
                tags=["compliance", comp_finding['standard']],
            )
        
        # Correlate findings
        self._correlate_findings(result)
        
        return result
    
    def merge_results(
        self,
        results: List[UnifiedScanResult],
    ) -> Dict[str, Any]:
        """Merge multiple scan results into a unified report.
        
        Args:
            results: List of UnifiedScanResult from multiple files
            
        Returns:
            Dictionary with aggregated statistics and findings
        """
        total_findings = 0
        by_severity = {"high": 0, "medium": 0, "low": 0}
        by_category = {
            "security_only": 0,
            "compliance_only": 0,
            "both": 0,
        }
        by_file = {}
        
        for result in results:
            summary = result.get_summary()
            by_file[result.filename] = summary
            
            total_findings += summary["total_findings"]
            by_severity["high"] += summary["high_severity"]
            by_severity["medium"] += summary["medium_severity"]
            by_severity["low"] += summary["low_severity"]
            by_category["security_only"] += summary["security_only"]
            by_category["compliance_only"] += summary["compliance_only"]
            by_category["both"] += summary["overlapping"]
        
        return {
            "timestamp": str(Path.cwd()),
            "total_findings": total_findings,
            "by_severity": by_severity,
            "by_category": by_category,
            "by_file": by_file,
            "files_scanned": len(results),
            "files_with_issues": sum(1 for r in results if r.findings),
        }
