from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from onboard.report import build_markdown_report
from onboard.scanner import scan_repo


class ScannerReportTests(unittest.TestCase):
    def test_scan_python_project(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n[tool.pytest.ini_options]\n", encoding="utf-8")
            (tmp_path / "README.md").write_text("# Demo\n\nA tiny sample service.\n", encoding="utf-8")
            (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
            tests = tmp_path / "tests"
            tests.mkdir()
            (tests / "test_app.py").write_text("def test_ok(): assert True\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)

        self.assertEqual(analysis.languages["Python"], 2)
        self.assertIn("Python packaging/pip", analysis.package_managers)
        self.assertTrue(any(item.path == "app.py" for item in analysis.entry_points))
        self.assertIn("tests", analysis.test_locations)
        self.assertEqual(analysis.project_purpose, "Demo: A tiny sample service.")
        self.assertTrue(any(snippet.path == "README.md" for snippet in analysis.file_snippets))

    def test_scan_node_project_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            package_json = {
                "scripts": {"dev": "vite", "test": "vitest"},
                "dependencies": {"react": "^19.0.0"},
                "devDependencies": {"vite": "^6.0.0", "typescript": "^5.0.0"},
            }
            (tmp_path / "package.json").write_text(json.dumps(package_json), encoding="utf-8")
            (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
            (tmp_path / "src").mkdir()
            (tmp_path / "src" / "main.tsx").write_text("export {}\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)
            report = build_markdown_report(analysis)

        self.assertIn("React", analysis.frameworks)
        self.assertIn("npm run dev", report)
        self.assertIn("## Wie ist es aufgebaut?", report)
        self.assertIn("## Offene Unsicherheiten", report)
        self.assertIn("## Wo soll ich anfangen zu lesen?", report)

    def test_empty_repo_marks_uncertainty(self):
        with tempfile.TemporaryDirectory() as directory:
            analysis = scan_repo(Path(directory))
            report = build_markdown_report(analysis)

        self.assertEqual(analysis.scanned_files, 0)
        self.assertIn("No source files were found", report)

    def test_scan_makefile_and_dockerfile_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "Makefile").write_text("test:\n\tpython -m unittest\nrun:\n\tpython app.py\n", encoding="utf-8")
            (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
            (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)
            report = build_markdown_report(analysis)

        commands = [hint.command for hint in analysis.command_hints]
        self.assertIn("make test", commands)
        self.assertIn("make run", commands)
        self.assertIn("Dockerfile", report)
        self.assertTrue(any("Docker" in question for question in analysis.maintainer_questions))

    def test_snippet_bytes_limits_large_files(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "README.md").write_text("# Demo\n\n" + "x" * 200, encoding="utf-8")

            analysis = scan_repo(tmp_path, snippet_bytes=20)

        readme = next(snippet for snippet in analysis.file_snippets if snippet.path == "README.md")
        self.assertTrue(readme.truncated)
        self.assertLessEqual(len(readme.content.encode("utf-8")), 20)

    def test_env_files_are_not_snippeted(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / ".env").write_text("SECRET=real-ish\n", encoding="utf-8")
            (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)

        self.assertFalse(any(snippet.path == ".env" for snippet in analysis.file_snippets))

    def test_report_uses_safe_fence_for_markdown_snippets(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "README.md").write_text("# Demo\n\n```bash\necho hi\n```\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)
            report = build_markdown_report(analysis)

        self.assertIn("~~~text", report)


if __name__ == "__main__":
    unittest.main()
