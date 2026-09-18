import unittest
from types import SimpleNamespace
from unittest.mock import patch

from noorlytics.analyze_dependencies import (
    analyze_dependencies_file,
    detect_ecosystem,
    parse_package_json,
    parse_requirements_txt,
)


class AnalyzeDependenciesTests(unittest.TestCase):
    def test_detect_ecosystem_for_supported_manifests(self):
        self.assertEqual(detect_ecosystem("requirements.txt", ""), "python")
        self.assertEqual(detect_ecosystem("package.json", "{}"), "node")
        self.assertEqual(detect_ecosystem("packages.config", ""), "dotnet")

    def test_parse_requirements_txt_ignores_comments_and_extracts_versions(self):
        parsed = parse_requirements_txt("# comment\nrequests==2.31.0\nflask\n")
        self.assertEqual(parsed, [("requests", "2.31.0"), ("flask", None)])

    def test_parse_package_json_merges_dependency_sections(self):
        parsed = parse_package_json(
            '{"dependencies":{"react":"18.0.0"},"devDependencies":{"vite":"5.0.0"}}'
        )
        self.assertEqual(parsed["react"], "18.0.0")
        self.assertEqual(parsed["vite"], "5.0.0")

    def test_analyze_dependencies_file_returns_structured_result_without_network(self):
        client = SimpleNamespace()
        manifest = "/Users/li/Desktop/noorlytics/examples/requirements.txt"

        with patch("noorlytics.analyze_dependencies._expand_from_lockfiles", return_value=([], [])), \
             patch("noorlytics.analyze_dependencies._detect_license_python", return_value=("MIT", "pip-show")), \
             patch("noorlytics.analyze_dependencies._collect_known_vulns", return_value=([], {"python": "osv"})):
            result = analyze_dependencies_file(__import__("pathlib").Path(manifest), client)

        self.assertEqual(result["ecosystem"], "python")
        self.assertIn("dependencies", result)
        self.assertIn("license_risk", result)
        self.assertIn("notes_md", result)
        self.assertTrue(any(dep["name"] == "requests" for dep in result["dependencies"]))


if __name__ == "__main__":
    unittest.main()