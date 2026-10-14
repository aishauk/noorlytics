# Customer Context Templates

This directory contains pre-configured customer context templates for use with the `noor assess` command.

## Quick Start

Use the default template for most cases:

```bash
noor assess requirements.txt -c noorlytics/templates/customer_context_default.json
```

## Available Templates

### Default (Recommended)

- **customer_context_default.json** - Balanced profile suitable for general use
  - Security: High
  - Business Continuity: Medium
  - Cost Control: Medium
  - Delivery Speed: Medium
  - Upgrade Window: 30 days

### Industry-Specific

- **customer_context_fintech.json** - FinTech startup
  - Focus: Speed + Cost efficiency
  - Upgrade Window: 7 days (fast iteration)

- **customer_context_enterprise.json** - Enterprise deployment
  - Focus: Comprehensive management
  - Upgrade Window: 60 days (careful planning)
  - Requires OSS license review

- **customer_context_healthcare.json** - Healthcare industry
  - Focus: Security + Compliance
  - Upgrade Window: 30 days
  - Requires OSS license review
  - Maintains legacy Java runtime

- **customer_context_startup.json** - Growth-focused startup
  - Focus: Cost + Speed
  - Minimal compliance requirements
  - Upgrade Window: 14 days

## Usage

### Option 1: Use a Template Directly

```bash
noor assess requirements.txt -c noorlytics/templates/customer_context_default.json
noor assess requirements.txt -c noorlytics/templates/customer_context_enterprise.json
```

### Option 2: Copy and Customize

```bash
cp noorlytics/templates/customer_context_default.json my_context.json
# Edit my_context.json with your settings
noor assess requirements.txt -c my_context.json
```

### Option 3: Create Your Own

Create a JSON file with the same structure as the templates:

```json
{
  "customer_name": "Your Company",
  "industry": "your-industry",
  "deployment": "deployment-type",
  "risk_preferences": {
    "security": "high|medium|low",
    "business_continuity": "high|medium|low",
    "cost_control": "high|medium|low",
    "delivery_speed": "high|medium|low"
  },
  "constraints": {
    "upgrade_window_days": 14,
    "requires_oss_license_review": true,
    "legacy_runtime": "python3.8",
    "min_security_score": 75
  }
}
```

## Template Field Reference

### Risk Preferences

These control how Noorlytics prioritizes decisions:

- **security**: How critical is vulnerability protection? (high/medium/low)
- **business_continuity**: How critical is operational stability? (high/medium/low)
- **cost_control**: How important is minimizing remediation cost? (high/medium/low)
- **delivery_speed**: How important is quick implementation? (high/medium/low)

### Constraints

These enforce business rules:

- **upgrade_window_days**: Days available to deploy fixes (default: 14)
- **requires_oss_license_review**: Block risky OSS licenses? (default: false)
- **legacy_runtime**: Legacy runtime to maintain compatibility (e.g., "python3.8", null for none)
- **min_security_score**: Minimum acceptable security score 0-100 (default: 75)
