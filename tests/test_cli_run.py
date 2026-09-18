import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from noorlytics.cli.run import _next_versioned_markdown_path, _save_and_print


class CliRunTests(unittest.TestCase):
    def test_next_versioned_markdown_path_increments_from_legacy_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reports_dir = Path(tmpdir)
            (reports_dir / "legacyfile.py.analyze.md").write_text("old", encoding="utf-8")
            next_path = _next_versioned_markdown_path(reports_dir, "legacyfile.py.analyze")
            self.assertEqual(next_path.name, "legacyfile.py.analyze.v2.md")

    def test_next_versioned_markdown_path_uses_highest_existing_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reports_dir = Path(tmpdir)
            (reports_dir / "legacyfile.py.analyze.v2.md").write_text("v2", encoding="utf-8")
            (reports_dir / "legacyfile.py.analyze.v4.md").write_text("v4", encoding="utf-8")
            next_path = _next_versioned_markdown_path(reports_dir, "legacyfile.py.analyze")
            self.assertEqual(next_path.name, "legacyfile.py.analyze.v5.md")

    def test_save_and_print_prepends_generated_timestamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "report.md"
            with patch("noorlytics.cli.run.render_markdown_cli") as render_mock:
                _save_and_print("## Executive Summary\nHello", out_path, header="report")

            saved = out_path.read_text(encoding="utf-8")
            self.assertRegex(saved, r"^Generated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}Z\n\n## Executive Summary")
            render_mock.assert_called_once()
            rendered_text = render_mock.call_args.args[1]
            self.assertTrue(rendered_text.startswith("Generated: "))


if __name__ == "__main__":
    unittest.main()