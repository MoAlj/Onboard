from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from onboard.llm import LlmResult
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
                "scripts": {"dev": "vite", "test": "vitest", "storybook": "storybook dev"},
                "dependencies": {"react": "^19.0.0"},
                "devDependencies": {"vite": "^6.0.0", "typescript": "^5.0.0"},
            }
            (tmp_path / "package.json").write_text(json.dumps(package_json), encoding="utf-8")
            (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
            (tmp_path / "src").mkdir()
            (tmp_path / "src" / "main.tsx").write_text("export {}\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)
            report = build_markdown_report(
                analysis,
                LlmResult("Summary", "Run with `npm run dev`.", "- `src/main.tsx`: Frontend entry point.", []),
            )

        self.assertIn("React", analysis.frameworks)
        self.assertIn("npm run storybook", [hint.command for hint in analysis.package_scripts])
        self.assertIn("Run with `npm run dev`.", report)
        self.assertIn("## Projektstruktur", report)
        self.assertIn("## Offene Unsicherheiten", report)
        self.assertNotIn("## Wo soll ich anfangen zu lesen?", report)
        self.assertNotIn("### Dateien und Ordner", report)
        self.assertNotIn("Source package root", report)
        self.assertNotIn("Automated tests", report)
        self.assertNotIn("Python/package module", report)
        self.assertIn("Frontend entry point", report)

    def test_empty_repo_marks_uncertainty(self):
        with tempfile.TemporaryDirectory() as directory:
            analysis = scan_repo(Path(directory))
            report = build_markdown_report(analysis, LlmResult("Summary", "Use `make run`.", "Read Makefile then app.py.", []))

        self.assertEqual(analysis.scanned_files, 0)
        self.assertIn("No source files were found", report)

    def test_scan_makefile_and_dockerfile_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "Makefile").write_text(
                "test:\n\tpython -m unittest\nrun:\n\tpython app.py\nlint:\n\truff check .\nship:\n\techo ship\n",
                encoding="utf-8",
            )
            (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
            (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)
            report = build_markdown_report(analysis, LlmResult("Summary", "Use `make run`.", "Read Makefile then app.py.", []))

        commands = [hint.command for hint in analysis.command_hints]
        self.assertIn("make test", commands)
        self.assertIn("make run", commands)
        self.assertIn("make lint", [hint.command for hint in analysis.make_targets])
        self.assertIn("make ship", [hint.command for hint in analysis.make_targets])
        self.assertIn("Use `make run`.", report)
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

    def test_report_omits_relevant_snippets(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "README.md").write_text("# Demo\n\n```bash\necho hi\n```\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)
            report = build_markdown_report(analysis)

        self.assertTrue(analysis.file_snippets)
        self.assertNotIn("## Relevante Snippets", report)
        self.assertNotIn("~~~text", report)

    def test_python_import_graph_detects_internal_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            package = tmp_path / "src" / "demo"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "app.py").write_text("import os\nfrom .services import user_service\n", encoding="utf-8")
            (package / "services.py").write_text("from demo import models\n", encoding="utf-8")
            (package / "models.py").write_text("class User: pass\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)
            report = build_markdown_report(analysis, LlmResult("Summary", "Start guide", "- `src/demo/app.py`: App module.", []))

        app_edge = next(edge for edge in analysis.import_graph if edge.source == "src/demo/app.py")
        self.assertIn("os", app_edge.imports)
        self.assertIn("demo.services", app_edge.internal_imports)
        self.assertIn("## Import-Beziehungen", report)
        self.assertIn("### Interne Imports", report)
        self.assertIn("### Externe Imports", report)
        self.assertIn("demo.services", report)
        self.assertIn("`os`", report)

    def test_architecture_roles_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            for directory_name in ("api", "routes", "models", "services", "components", "pages", "migrations"):
                role_dir = tmp_path / "src" / "app" / directory_name
                role_dir.mkdir(parents=True)
                (role_dir / "placeholder.py").write_text("", encoding="utf-8")

            analysis = scan_repo(tmp_path)

        roles = "\n".join(analysis.architecture_roles)
        self.assertIn("src/app/api/", roles)
        self.assertIn("src/app/routes/", roles)
        self.assertIn("src/app/models/", roles)
        self.assertIn("src/app/services/", roles)
        self.assertIn("src/app/components/", roles)
        self.assertIn("src/app/pages/", roles)
        self.assertIn("src/app/migrations/", roles)

    def test_report_removes_old_sections_and_uses_llm_guides(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)
            report = build_markdown_report(
                analysis,
                LlmResult(
                    summary="LLM summary",
                    startup_guide="Install dependencies, then run `python app.py`.",
                    project_structure="- `README.md`: Project overview.",
                    warnings=[],
                ),
            )

        self.assertIn("## Wie wird die Anwendung gestartet?", report)
        self.assertIn("Install dependencies", report)
        self.assertIn("Project overview", report)
        self.assertIn("## Projektstruktur", report)
        self.assertNotIn("## Wo soll ich anfangen zu lesen?", report)
        self.assertNotIn("### Dateien und Ordner", report)
        self.assertNotIn("## Wie starte/teste ich es lokal?", report)
        self.assertNotIn("## Sicher erkannt vs. vermutet", report)
        self.assertNotIn("### Vermutete Architektur", report)
        self.assertNotIn("## Relevante Snippets", report)

    def test_project_structure_explanations_are_embedded_in_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
            (tmp_path / "src").mkdir()
            (tmp_path / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")

            analysis = scan_repo(tmp_path)
            report = build_markdown_report(
                analysis,
                LlmResult(
                    "Summary",
                    "Start guide",
                    "- `README.md`: Projektueberblick.\n- `src/`: Source folder.\n- `src/app.py`: Einstiegspunkt.",
                    [],
                ),
            )

        self.assertIn('- README.md\n  "Projektueberblick."', report)
        self.assertIn('- src/\n  "Source folder."', report)
        self.assertIn('  - app.py\n    "Einstiegspunkt."', report)
        self.assertNotIn("### Dateien und Ordner", report)


if __name__ == "__main__":
    unittest.main()
