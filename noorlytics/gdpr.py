import re
from dataclasses import dataclass
from typing import Any, Dict, List


PII_PATTERNS = (
    "email",
    "phone",
    "ssn",
    "passport",
    "national_id",
    "date_of_birth",
    "dob",
    "address",
    "ip_address",
    "customer_id",
    "billing_address",
    "credit_card",
    "card_number",
    "full_name",
    "name",
)


@dataclass
class GDPRFinding:
    rule: str
    severity: str
    message: str
    filename: str
    line: int
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "filename": self.filename,
            "line": self.line,
            "evidence": self.evidence,
        }


def _line_has_pii(line: str) -> bool:
    lowered = line.lower()
    return any(term in lowered for term in PII_PATTERNS)


def scan_gdpr_violations(source: str, filename: str = "unknown.py") -> List[Dict[str, Any]]:
    """Scan source code for common GDPR/privacy design issues.

    This is a static heuristic scanner intended for developer guidance, not legal certification.
    """
    findings: List[GDPRFinding] = []
    lines = source.splitlines()

    for idx, line in enumerate(lines, start=1):
        lowered = line.lower()

        if re.search(r"(?:logging|logger|print|console\.(?:log|debug|info|warn|error|warning))(?:\.\w+)?\s*\(", lowered):
            if _line_has_pii(line):
                findings.append(
                    GDPRFinding(
                        rule="PII_LOGGING",
                        severity="high",
                        message="Personal data is being logged without masking or encryption.",
                        filename=filename,
                        line=idx,
                        evidence=line.strip(),
                    )
                )

        if re.search(r"(requests|httpx|urllib|aiohttp|fetch)\s*\.", lowered) and re.search(r"http://", lowered):
            if _line_has_pii(line):
                findings.append(
                    GDPRFinding(
                        rule="INSECURE_DATA_TRANSMISSION",
                        severity="high",
                        message="Personal data appears to be transmitted over an insecure HTTP endpoint.",
                        filename=filename,
                        line=idx,
                        evidence=line.strip(),
                    )
                )

        if re.search(r"(save|store|persist|insert|update|write|cache|redis|session|cookie)\s*\(", lowered):
            if _line_has_pii(line):
                findings.append(
                    GDPRFinding(
                        rule="UNSAFE_PII_STORAGE",
                        severity="medium",
                        message="Personal data is being stored without an obvious minimization or retention control.",
                        filename=filename,
                        line=idx,
                        evidence=line.strip(),
                    )
                )

    seen = set()
    deduped: List[Dict[str, Any]] = []
    for finding in findings:
        key = (finding.rule, finding.filename, finding.line, finding.evidence)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding.to_dict())

    return deduped


class GDPRScanner:
    def __init__(self, filename: str = "unknown.py"):
        self.filename = filename

    def scan(self, source: str) -> List[Dict[str, Any]]:
        return scan_gdpr_violations(source, self.filename)


def detect_gdpr_issues(source: str, filename: str = "unknown.py") -> List[Dict[str, Any]]:
    return scan_gdpr_violations(source, filename)
