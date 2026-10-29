"""Standards Compliance Scanner - HIPAA, PCI-DSS, SOC 2

Scans code and dependencies for compliance with industry standards:
- HIPAA: Healthcare data protection
- PCI-DSS: Payment card data protection
- SOC 2: Service organization controls
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ComplianceFinding:
    """A compliance finding for industry standards."""
    standard: str      # 'hipaa', 'pci-dss', 'soc2'
    requirement: str   # e.g., "R1.2.1" (requirement ID)
    severity: str      # 'high', 'medium', 'low'
    message: str
    filename: str
    line: int
    evidence: str
    remediation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "standard": self.standard,
            "requirement": self.requirement,
            "severity": self.severity,
            "message": self.message,
            "filename": self.filename,
            "line": self.line,
            "evidence": self.evidence,
            "remediation": self.remediation,
        }


# ============================================================================
# HIPAA CHECKS (Healthcare Data Protection)
# ============================================================================

def _check_hipaa_encryption(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """HIPAA: Check for encryption of Protected Health Information (PHI)."""
    findings = []
    lowered = line.lower()

    # PHI patterns
    phi_patterns = ["ssn", "medical_id", "patient_id", "health_record", "diagnosis", "medication", "prescription", "dob", "date_of_birth"]

    if any(pattern in lowered for pattern in phi_patterns):
        # Check if transmission is encrypted
        if "http://" in lowered:
            findings.append(
                ComplianceFinding(
                    standard="hipaa",
                    requirement="164.312(a)(2)(ii)",
                    severity="high",
                    message="PHI transmitted over unencrypted HTTP. HIPAA requires encryption in transit.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Use HTTPS/TLS for all PHI transmission. Implement encryption at-rest using AES-256.",
                )
            )
        # Check if stored in plaintext
        if re.search(r"(save|store|persist|database)\s*.*ph", line, re.IGNORECASE):
            findings.append(
                ComplianceFinding(
                    standard="hipaa",
                    requirement="164.312(a)(2)(i)",
                    severity="high",
                    message="PHI storage detected. HIPAA requires encryption at-rest.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Encrypt PHI at-rest using AES-256. Use secure key management.",
                )
            )

    return findings


def _check_hipaa_access_controls(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """HIPAA: Check for access controls and authentication."""
    findings = []
    lowered = line.lower()

    # Check for missing access controls on PHI operations
    if any(op in lowered for op in ["read_medical_record", "access_health_data", "get_phi", "retrieve_patient"]):
        if not any(auth in lowered for auth in ["authenticate", "authorize", "permission", "role", "access_control"]):
            findings.append(
                ComplianceFinding(
                    standard="hipaa",
                    requirement="164.312(a)(2)(i)",
                    severity="high",
                    message="PHI access without documented access control. HIPAA requires role-based access control (RBAC).",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Implement RBAC. Document all access. Use audit logging.",
                )
            )

    return findings


def _check_hipaa_audit_logging(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """HIPAA: Check for audit logging of PHI access."""
    findings = []
    lowered = line.lower()

    phi_operations = ["read.*patient", "access.*health", "delete.*medical", "update.*diagnosis", "export.*record"]

    for op in phi_operations:
        if re.search(op, lowered):
            if not any(log in lowered for log in ["log", "audit", "track", "record"]):
                findings.append(
                    ComplianceFinding(
                        standard="hipaa",
                        requirement="164.312(b)",
                        severity="high",
                        message="PHI operation without audit logging. HIPAA requires logging of all PHI access.",
                        filename=filename,
                        line=idx,
                        evidence=line.strip(),
                        remediation="Add audit logging for all PHI operations. Log who, what, when, why.",
                    )
                )
                break

    return findings


# ============================================================================
# PCI-DSS CHECKS (Payment Card Data Protection)
# ============================================================================

def _check_pci_dss_cardholder_data(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """PCI-DSS: Check for cardholder data protection."""
    findings = []
    lowered = line.lower()

    card_patterns = ["credit_card", "card_number", "cardholder", "cvv", "cvc", "pan", "primary_account_number"]

    if any(pattern in lowered for pattern in card_patterns):
        # Check for plaintext storage
        if re.search(r"(store|save|persist|cache|pickle|serialize)", lowered):
            findings.append(
                ComplianceFinding(
                    standard="pci-dss",
                    requirement="3.2.1",
                    severity="high",
                    message="Cardholder data storage detected. PCI-DSS prohibits storing full card numbers.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Never store full card numbers. Use tokenization or encryption. Store only last 4 digits.",
                )
            )
        # Check for logging
        if re.search(r"(log|print|debug|console)", lowered):
            findings.append(
                ComplianceFinding(
                    standard="pci-dss",
                    requirement="3.2.1",
                    severity="high",
                    message="Cardholder data in logs. PCI-DSS prohibits logging sensitive card data.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Never log card data. Use masking or tokenization.",
                )
            )

    return findings


def _check_pci_dss_network_security(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """PCI-DSS: Check for network security (encryption in transit)."""
    findings = []
    lowered = line.lower()

    # Check for unencrypted payment operations
    if any(op in lowered for op in ["payment", "charge", "transaction", "checkout", "billing"]):
        if "http://" in lowered and "https" not in lowered:
            findings.append(
                ComplianceFinding(
                    standard="pci-dss",
                    requirement="4.1",
                    severity="high",
                    message="Payment operation over unencrypted HTTP. PCI-DSS requires TLS 1.2+ for all transmissions.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Use HTTPS with TLS 1.2 or higher. Disable SSLv3 and older protocols.",
                )
            )

    return findings


def _check_pci_dss_access_control(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """PCI-DSS: Check for access control on payment systems."""
    findings = []
    lowered = line.lower()

    if any(op in lowered for op in ["payment_gateway", "transaction_processor", "card_processor"]):
        if not any(control in lowered for control in ["authenticate", "authorize", "role", "permission"]):
            findings.append(
                ComplianceFinding(
                    standard="pci-dss",
                    requirement="7.1",
                    severity="high",
                    message="Payment system access without documented access control. PCI-DSS requires role-based access.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Implement role-based access control (RBAC). Restrict to authorized personnel only.",
                )
            )

    return findings


# ============================================================================
# SOC 2 CHECKS (Service Organization Controls)
# ============================================================================

def _check_soc2_availability(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """SOC 2: Check for availability controls."""
    findings = []
    lowered = line.lower()

    # Check for retry logic
    if any(op in lowered for op in ["database.query", "api.call", "external_service", "network_request"]):
        if "retry" not in lowered and "exception" not in lowered:
            findings.append(
                ComplianceFinding(
                    standard="soc2",
                    requirement="CC7.2",
                    severity="medium",
                    message="External dependency without retry logic. SOC 2 requires availability controls.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Implement retry logic with exponential backoff. Add circuit breaker pattern.",
                )
            )

    return findings


def _check_soc2_integrity(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """SOC 2: Check for data integrity controls."""
    findings = []
    lowered = line.lower()

    # Check for validation
    if any(op in lowered for op in ["database.update", "database.insert", "data.modify", "record.change"]):
        if not any(check in lowered for check in ["validate", "check", "assert", "verify"]):
            findings.append(
                ComplianceFinding(
                    standard="soc2",
                    requirement="CC6.1",
                    severity="medium",
                    message="Data modification without validation. SOC 2 requires data integrity controls.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Add input validation. Implement checksums or digital signatures for critical data.",
                )
            )

    return findings


def _check_soc2_confidentiality(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """SOC 2: Check for confidentiality controls."""
    findings = []
    lowered = line.lower()

    # Check for sensitive data handling
    if any(data in lowered for data in ["customer_data", "user_data", "private_info", "sensitive_info", "pii"]):
        if "http://" in lowered or "plaintext" in lowered or "encrypt" not in lowered:
            findings.append(
                ComplianceFinding(
                    standard="soc2",
                    requirement="CC6.2",
                    severity="high",
                    message="Sensitive data handling without encryption. SOC 2 requires confidentiality controls.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Encrypt sensitive data at-rest and in-transit. Use key management services.",
                )
            )

    return findings


def _check_soc2_security_monitoring(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """SOC 2: Check for monitoring and logging."""
    findings = []
    lowered = line.lower()

    # Check for admin/sensitive operations without logging
    if any(op in lowered for op in ["admin", "permission_change", "role_change", "access_grant", "security_setting"]):
        if not any(log in lowered for log in ["log", "audit", "monitor", "track"]):
            findings.append(
                ComplianceFinding(
                    standard="soc2",
                    requirement="CC7.2",
                    severity="high",
                    message="Admin operation without monitoring. SOC 2 requires logging of security-relevant events.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Add audit logging for all admin operations. Centralize logs for review.",
                )
            )

    return findings


# ============================================================================
# MAIN SCANNER
# ============================================================================

def scan_standards(
    source: str,
    filename: str = "unknown.py",
    standards: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Scan source code for compliance with industry standards.

    Args:
        source: Source code to scan
        filename: Name of the file being scanned
        standards: List of standards to check. If None, checks all.
                  Valid: ['hipaa', 'pci-dss', 'soc2', 'iso27001', 'fedramp']

    Returns:
        List of findings as dictionaries
    """
    if standards is None:
        standards = ["hipaa", "pci-dss", "soc2", "iso27001", "fedramp"]

    findings: List[ComplianceFinding] = []
    lines = source.splitlines()

    for idx, line in enumerate(lines, start=1):
        if "hipaa" in standards:
            findings.extend(_check_hipaa_encryption(line, idx, filename))
            findings.extend(_check_hipaa_access_controls(line, idx, filename))
            findings.extend(_check_hipaa_audit_logging(line, idx, filename))

        if "pci-dss" in standards:
            findings.extend(_check_pci_dss_cardholder_data(line, idx, filename))
            findings.extend(_check_pci_dss_network_security(line, idx, filename))
            findings.extend(_check_pci_dss_access_control(line, idx, filename))

        if "soc2" in standards:
            findings.extend(_check_soc2_availability(line, idx, filename))
            findings.extend(_check_soc2_integrity(line, idx, filename))
            findings.extend(_check_soc2_confidentiality(line, idx, filename))
            findings.extend(_check_soc2_security_monitoring(line, idx, filename))

        if "iso27001" in standards:
            findings.extend(_check_iso27001_asset_management(line, idx, filename))
            findings.extend(_check_iso27001_access_control(line, idx, filename))
            findings.extend(_check_iso27001_cryptography(line, idx, filename))
            findings.extend(_check_iso27001_incident_management(line, idx, filename))

        if "fedramp" in standards:
            findings.extend(_check_fedramp_data_classification(line, idx, filename))
            findings.extend(_check_fedramp_encryption(line, idx, filename))
            findings.extend(_check_fedramp_access_controls(line, idx, filename))
            findings.extend(_check_fedramp_audit_logging(line, idx, filename))

    # Deduplicate findings
    seen = set()
    unique_findings = []
    for finding in findings:
        key = (finding.standard, finding.line, finding.filename)
        if key not in seen:
            seen.add(key)
            unique_findings.append(finding)

    return [f.to_dict() for f in unique_findings]


# ============================================================================
# ISO 27001 CHECKS (Information Security Management)
# ============================================================================

def _check_iso27001_asset_management(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """ISO 27001: Check for asset inventory and classification."""
    findings = []
    lowered = line.lower()

    # Check for missing asset classification
    if any(op in lowered for op in ["database", "api_key", "secret", "credential", "token"]):
        if not any(label in lowered for label in ["classified", "confidential", "restricted", "public", "internal"]):
            findings.append(
                ComplianceFinding(
                    standard="iso27001",
                    requirement="A.8.1.1",
                    severity="medium",
                    message="Asset detected without classification label. ISO 27001 requires asset classification.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Classify asset and label appropriately (Public, Internal, Confidential, Restricted).",
                )
            )

    return findings


def _check_iso27001_access_control(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """ISO 27001: Check for access control implementation."""
    findings = []
    lowered = line.lower()

    # Check for missing access control
    if any(op in lowered for op in ["admin", "privileged", "root", "sudo", "elevated"]):
        if not any(ctrl in lowered for ctrl in ["authenticate", "authorize", "permission", "role", "acl"]):
            findings.append(
                ComplianceFinding(
                    standard="iso27001",
                    requirement="A.9.2.1",
                    severity="high",
                    message="Privileged access detected without access control. ISO 27001 requires RBAC.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Implement role-based access control (RBAC) and document access policies.",
                )
            )

    return findings


def _check_iso27001_cryptography(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """ISO 27001: Check for cryptographic controls."""
    findings = []
    lowered = line.lower()

    # Check for cryptographic key management
    if "key" in lowered and ("=" in line or ":" in line):
        if not any(mgmt in lowered for mgmt in ["encrypt", "kms", "vault", "keyring", "hsm"]):
            if "key" in lowered and ("password" in lowered or "secret" in lowered):
                findings.append(
                    ComplianceFinding(
                        standard="iso27001",
                        requirement="A.10.1.1",
                        severity="high",
                        message="Cryptographic key without proper management. ISO 27001 requires key management.",
                        filename=filename,
                        line=idx,
                        evidence=line.strip(),
                        remediation="Use a Key Management Service (KMS) or Hardware Security Module (HSM) for key management.",
                    )
                )

    # Check for weak encryption algorithms
    if any(algo in lowered for algo in ["md5", "sha1", "des", "rc4"]):
        findings.append(
            ComplianceFinding(
                standard="iso27001",
                requirement="A.10.1.1",
                severity="high",
                message=f"Weak cryptographic algorithm detected. ISO 27001 requires strong encryption (AES-256, SHA-256+).",
                filename=filename,
                line=idx,
                evidence=line.strip(),
                remediation="Replace with strong algorithms: AES-256 for encryption, SHA-256+ for hashing.",
            )
        )

    return findings


def _check_iso27001_incident_management(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """ISO 27001: Check for incident management and reporting."""
    findings = []
    lowered = line.lower()

    # Check for error handling without incident reporting
    if "except" in lowered or "try:" in lowered:
        if not any(incident in lowered for incident in ["log", "report", "alert", "notify", "incident"]):
            findings.append(
                ComplianceFinding(
                    standard="iso27001",
                    requirement="A.16.1.5",
                    severity="medium",
                    message="Exception handling without incident logging. ISO 27001 requires incident reporting.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Add incident logging and alerting to exception handlers.",
                )
            )

    return findings


# ============================================================================
# FEDRAMP CHECKS (Federal Risk and Authorization Management Program)
# ============================================================================

def _check_fedramp_data_classification(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """FedRAMP: Check for federal data classification."""
    findings = []
    lowered = line.lower()

    # Check for government/federal data handling
    if any(term in lowered for term in ["federal", "government", "classified", "sensitive"]):
        if not any(label in lowered for label in ["u", "s", "ts", "tsk", "unclassified", "secret", "top secret"]):
            findings.append(
                ComplianceFinding(
                    standard="fedramp",
                    requirement="SC-12",
                    severity="high",
                    message="Government data handling without classification. FedRAMP requires data classification.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Classify as U (Unclassified), S (Secret), or TS (Top Secret). Document classification level.",
                )
            )

    return findings


def _check_fedramp_encryption(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """FedRAMP: Check for encryption standards compliance."""
    findings = []
    lowered = line.lower()

    # Check for FIPS 140-2 compliance
    if any(op in lowered for op in ["encrypt", "tls", "ssl", "https"]):
        if "fips" not in lowered and "140" not in lowered:
            findings.append(
                ComplianceFinding(
                    standard="fedramp",
                    requirement="SC-13",
                    severity="high",
                    message="Encryption without FIPS 140-2 compliance statement. FedRAMP requires FIPS-validated crypto.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Use FIPS 140-2 validated cryptographic modules. Document validation certificate.",
                )
            )

    return findings


def _check_fedramp_access_controls(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """FedRAMP: Check for federal access control requirements."""
    findings = []
    lowered = line.lower()

    # Check for multi-factor authentication (MFA)
    if any(auth in lowered for auth in ["login", "authenticate", "sign_in"]):
        if "mfa" not in lowered and "multi" not in lowered and "2fa" not in lowered:
            findings.append(
                ComplianceFinding(
                    standard="fedramp",
                    requirement="AC-2(1)",
                    severity="high",
                    message="Authentication without multi-factor verification. FedRAMP requires MFA for federal access.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Implement multi-factor authentication (MFA) for all user access to federal systems.",
                )
            )

    return findings


def _check_fedramp_audit_logging(line: str, idx: int, filename: str) -> List[ComplianceFinding]:
    """FedRAMP: Check for comprehensive audit logging."""
    findings = []
    lowered = line.lower()

    # Check for missing audit trail
    if any(op in lowered for op in ["access", "modify", "delete", "create"]):
        if not any(audit in lowered for audit in ["log", "audit", "trail", "record", "track"]):
            findings.append(
                ComplianceFinding(
                    standard="fedramp",
                    requirement="AU-12",
                    severity="high",
                    message="Data operation without audit logging. FedRAMP requires comprehensive audit trails.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                    remediation="Add comprehensive audit logging: who, what, when, where, why for all data operations.",
                )
            )

    return findings


# ============================================================================
# DEPENDENCY STANDARD CHECKS
# ============================================================================

def check_dependency_standards(
    package_name: str,
    version: Optional[str] = None,
    standard: str = "all",
) -> List[Dict[str, Any]]:
    """Check if a dependency meets compliance requirements.

    Args:
        package_name: Name of the package
        version: Version of the package (optional)
        standard: Which standard to check against ('hipaa', 'pci-dss', 'soc2', 'all')

    Returns:
        List of compliance issues
    """
    findings = []

    # Known packages with compliance issues
    compliance_issues = {
        "hipaa": {
            "telnet": "Unencrypted protocol. Not suitable for HIPAA.",
            "ftp": "Unencrypted protocol. Not suitable for HIPAA.",
            "http": "Unencrypted protocol. Not suitable for HIPAA.",
            "requests": "Check configuration: must use HTTPS only",
        },
        "pci-dss": {
            "telnet": "Unencrypted protocol. Not suitable for PCI-DSS.",
            "ftp": "Unencrypted protocol. Not suitable for PCI-DSS.",
            "pickle": "Unsafe serialization. PCI-DSS requires secure data handling.",
        },
        "soc2": {
            "telnet": "Unencrypted protocol. May violate SOC 2 confidentiality.",
            "ftp": "Unencrypted protocol. May violate SOC 2 confidentiality.",
        },
    }

    standards_to_check = ["hipaa", "pci-dss", "soc2"] if standard == "all" else [standard]

    for std in standards_to_check:
        if std in compliance_issues:
            for pkg, issue in compliance_issues[std].items():
                if pkg.lower() in package_name.lower():
                    findings.append({
                        "standard": std,
                        "package": package_name,
                        "version": version,
                        "severity": "high",
                        "message": issue,
                        "remediation": f"Review {package_name} against {std.upper()} requirements. Consider alternatives if non-compliant.",
                    })

    return findings
