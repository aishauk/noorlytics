"""Security Audit Module - Encryption & Audit Logging Pattern Detection

Scans source code for security hardening patterns:
- Encryption at-rest and in-transit
- Audit logging for sensitive operations
- Authentication best practices
- Secret/credential handling
- Error handling for security operations
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class SecurityFinding:
    """A security audit finding."""
    check_type: str  # 'encryption', 'audit_logging', 'authentication', 'secrets', 'error_handling'
    severity: str    # 'high', 'medium', 'low'
    message: str
    filename: str
    line: int
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_type": self.check_type,
            "severity": self.severity,
            "message": self.message,
            "filename": self.filename,
            "line": self.line,
            "evidence": self.evidence,
        }


# ============================================================================
# ENCRYPTION CHECKS
# ============================================================================

def _check_encryption_at_transit(line: str, idx: int, filename: str) -> List[SecurityFinding]:
    """Detect insecure data transmission (HTTP instead of HTTPS)."""
    findings = []
    lowered = line.lower()

    # Check for HTTP usage with potential sensitive data
    if "http://" in lowered and not "# " in lowered[:lowered.find("http://")]:
        if re.search(r"(requests|httpx|urllib|aiohttp|fetch|socket)\.", lowered):
            findings.append(
                SecurityFinding(
                    check_type="encryption",
                    severity="high",
                    message="Insecure HTTP connection detected. Use HTTPS for data transmission.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                )
            )
    return findings


def _check_encryption_at_rest(line: str, idx: int, filename: str) -> List[SecurityFinding]:
    """Detect unencrypted storage patterns."""
    findings = []
    lowered = line.lower()

    # Check for plaintext password/key storage
    if re.search(r"(password|api_key|secret|token|credential)\s*=\s*['\"]", lowered):
        if not re.search(r"(os\.getenv|environ\[|config\.|settings\.)", lowered):
            findings.append(
                SecurityFinding(
                    check_type="encryption",
                    severity="high",
                    message="Hardcoded credential detected. Use environment variables or secure vaults.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                )
            )

    # Check for file operations without encryption
    if re.search(r"(pickle|json|csv)\.dump|open\(['\"].*['\"],\s*['\"]w", lowered):
        if any(term in lowered for term in ["password", "secret", "key", "token", "credential", "pii", "ssn", "credit"]):
            findings.append(
                SecurityFinding(
                    check_type="encryption",
                    severity="high",
                    message="Serializing sensitive data without encryption. Use encrypted storage.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                )
            )

    # Check for plaintext database connections
    if re.search(r"(sqlite|mysql|postgresql|mongo)://.*@", lowered):
        if re.search(r"['\"].*password.*['\"]", line, re.IGNORECASE):
            findings.append(
                SecurityFinding(
                    check_type="encryption",
                    severity="high",
                    message="Database credentials in connection string. Use environment variables.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                )
            )

    return findings


# ============================================================================
# AUDIT LOGGING CHECKS
# ============================================================================

def _check_audit_logging(line: str, idx: int, filename: str) -> List[SecurityFinding]:
    """Detect missing audit logging for sensitive operations."""
    findings = []
    lowered = line.lower()

    # Sensitive operations that should have audit logging
    sensitive_ops = [
        "delete", "drop", "truncate",  # Data deletion
        "grant", "revoke",              # Permission changes
        "create_user", "delete_user",   # User management
        "update.*password", "reset.*password",  # Auth changes
        "login", "logout", "authenticate",      # Authentication
        "transfer", "payment", "transaction",   # Financial
    ]

    for op in sensitive_ops:
        if re.search(op, lowered):
            # Check if there's logging nearby (within same line)
            if not re.search(r"(log|audit|track|record)\s*\(", lowered):
                findings.append(
                    SecurityFinding(
                        check_type="audit_logging",
                        severity="high",
                        message=f"Sensitive operation '{op}' detected without audit logging. Add logging for compliance.",
                        filename=filename,
                        line=idx,
                        evidence=line.strip(),
                    )
                )
                break  # One finding per line is enough

    return findings


# ============================================================================
# AUTHENTICATION CHECKS
# ============================================================================

def _check_authentication(line: str, idx: int, filename: str) -> List[SecurityFinding]:
    """Detect weak authentication patterns."""
    findings = []
    lowered = line.lower()

    # Check for hardcoded authentication
    if re.search(r"(username|user|login)\s*=\s*['\"]", lowered):
        findings.append(
            SecurityFinding(
                check_type="authentication",
                severity="medium",
                message="Hardcoded username detected. Use secure configuration or environment variables.",
                filename=filename,
                line=idx,
                evidence=line.strip(),
            )
        )

    # Check for weak password validation
    if "len(password)" in lowered and "<" in lowered:
        if re.search(r"len\(password\)\s*<\s*[0-8]", lowered):
            findings.append(
                SecurityFinding(
                    check_type="authentication",
                    severity="high",
                    message="Weak password length requirement (< 8 characters). Enforce minimum 12+ characters.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                )
            )

    # Check for missing rate limiting on authentication
    if re.search(r"def\s+(login|authenticate|sign_in)", lowered):
        findings.append(
            SecurityFinding(
                check_type="authentication",
                severity="medium",
                message="Authentication function detected. Ensure rate limiting is implemented to prevent brute force.",
                filename=filename,
                line=idx,
                evidence=line.strip(),
            )
        )

    return findings


# ============================================================================
# SECRETS/CREDENTIALS CHECKS
# ============================================================================

def _check_secrets_handling(line: str, idx: int, filename: str) -> List[SecurityFinding]:
    """Detect poor secrets/credentials handling."""
    findings = []
    lowered = line.lower()

    # Check for secrets in logs
    if re.search(r"(log|print|console|debug|info|warning|error)\s*\(", lowered):
        if any(term in lowered for term in ["password", "token", "secret", "api_key", "credential"]):
            findings.append(
                SecurityFinding(
                    check_type="secrets",
                    severity="high",
                    message="Secret/credential logged. This is a critical security risk.",
                    filename=filename,
                    line=idx,
                    evidence=line.strip(),
                )
            )

    # Check for secrets in URLs
    if re.search(r"['\"]https?://.*:.*@", line):
        findings.append(
            SecurityFinding(
                check_type="secrets",
                severity="high",
                message="Credentials embedded in URL. Use authentication headers or environment variables.",
                filename=filename,
                line=idx,
                evidence=line.strip(),
            )
        )

    # Check for unmasked secrets in config
    if re.search(r"(export|setenv|os\.environ)\s+(.*_KEY|.*_TOKEN|.*_SECRET)\s*=", lowered):
        findings.append(
            SecurityFinding(
                check_type="secrets",
                severity="medium",
                message="Secret management should use .env files or secure vaults, not export commands.",
                filename=filename,
                line=idx,
                evidence=line.strip(),
            )
        )

    return findings


# ============================================================================
# ERROR HANDLING CHECKS
# ============================================================================

def _check_error_handling(lines: List[str], start_idx: int, filename: str) -> List[SecurityFinding]:
    """Detect missing error handling for security operations."""
    findings = []

    # Look for try-except patterns around security operations
    for idx in range(max(0, start_idx - 5), min(len(lines), start_idx + 10)):
        line = lines[idx].lower()

        if any(op in line for op in ["authenticate", "decrypt", "validate", "verify", "authorization", "permission"]):
            # Check if there's a try-except block
            found_try = any("try:" in lines[i] for i in range(max(0, idx - 3), idx))
            found_except = any("except" in lines[i] for i in range(idx, min(len(lines), idx + 10)))

            if not (found_try and found_except):
                findings.append(
                    SecurityFinding(
                        check_type="error_handling",
                        severity="medium",
                        message="Security operation detected without proper error handling. Use try-except to handle failures gracefully.",
                        filename=filename,
                        line=idx + 1,
                        evidence=lines[idx].strip(),
                    )
                )
                break

    return findings


# ============================================================================
# MAIN SCANNER
# ============================================================================

def scan_audit_security(source: str, filename: str = "unknown.py", checks: List[str] | None = None) -> List[Dict[str, Any]]:
    """Scan source code for security hardening issues.

    Args:
        source: Source code to scan
        filename: Name of the file being scanned
        checks: List of checks to run. If None, runs all checks.
               Valid: ['encryption', 'audit_logging', 'authentication', 'secrets', 'error_handling']

    Returns:
        List of findings as dictionaries
    """
    if checks is None:
        checks = ["encryption", "audit_logging", "authentication", "secrets", "error_handling"]

    findings: List[SecurityFinding] = []
    lines = source.splitlines()

    for idx, line in enumerate(lines, start=1):
        if "encryption" in checks:
            findings.extend(_check_encryption_at_transit(line, idx, filename))
            findings.extend(_check_encryption_at_rest(line, idx, filename))

        if "audit_logging" in checks:
            findings.extend(_check_audit_logging(line, idx, filename))

        if "authentication" in checks:
            findings.extend(_check_authentication(line, idx, filename))

        if "secrets" in checks:
            findings.extend(_check_secrets_handling(line, idx, filename))

    # Error handling check needs context (look at surrounding lines)
    if "error_handling" in checks:
        for idx in range(len(lines)):
            findings.extend(_check_error_handling(lines, idx, filename))

    # Deduplicate findings
    seen = set()
    unique_findings = []
    for finding in findings:
        key = (finding.check_type, finding.line, finding.filename)
        if key not in seen:
            seen.add(key)
            unique_findings.append(finding)

    return [f.to_dict() for f in unique_findings]
