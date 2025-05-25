
import pkg_resources

# Licenses that may be considered risky for regulated environments like banks
RISKY_LICENSES = {
    'GPL', 'GPL-2.0', 'GPL-3.0', 'AGPL', 'AGPL-3.0', 'LGPL', 'LGPL-2.1', 'LGPL-3.0', 'Unknown', 'NONE', None
}

def audit_licenses():
    report = []
    for dist in pkg_resources.working_set:
        name = dist.project_name
        version = dist.version
        license = dist.get_metadata('METADATA') if dist.has_metadata('METADATA') else ''
        license_type = 'Unknown'

        for line in license.splitlines():
            if line.startswith('License:'):
                license_type = line.split(':', 1)[-1].strip()
                break

        risk = "HIGH ❌" if license_type in RISKY_LICENSES else "Low ✅"
        report.append({
            'package': name,
            'version': version,
            'license': license_type,
            'risk': risk
        })

    return report