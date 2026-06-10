from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from onboard.cli import main
from onboard.llm import LlmResult


class CliTests(unittest.TestCase):
    def test_cli_invalid_path(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = main(["scan", "/definitely/not/a/repo", "--no-llm"])

        self.assertEqual(exit_code, 2)
        self.assertIn("does not exist", stderr.getvalue())

    def test_cli_no_llm_outputs_report(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(["scan", str(repo), "--no-llm"])

        self.assertEqual(exit_code, 0)
        self.assertIn("# Onboarding Report", stdout.getvalue())

    def test_cli_output_file(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            repo = tmp_path / "repo"
            repo.mkdir()
            (repo / "main.py").write_text("print('hi')\n", encoding="utf-8")
            output = tmp_path / "onboarding.md"

            exit_code = main(["scan", str(repo), "--no-llm", "--output", str(output)])
            content = output.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("main.py", content)

    def test_cli_accepts_snippet_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "README.md").write_text("# Demo\n\n" + "x" * 100, encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(["scan", str(repo), "--no-llm", "--snippet-bytes", "10"])

        self.assertEqual(exit_code, 0)
        self.assertIn("# Onboarding Report", stdout.getvalue())
        self.assertNotIn("Relevante Snippets", stdout.getvalue())

    def test_cli_scans_git_url_via_temp_clone(self):
        def fake_clone(_url: str, destination: Path, verbose: bool = False) -> None:
            destination.mkdir(parents=True)
            (destination / "README.md").write_text("# Remote Demo\n", encoding="utf-8")

        stdout = io.StringIO()
        with mock.patch("onboard.git_source._clone_repo", side_effect=fake_clone):
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["scan", "https://github.com/MoAlj/Onboard.git", "--no-llm"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Remote Demo", stdout.getvalue())

    def test_cli_without_api_key_fails_without_no_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with mock.patch.dict("os.environ", {"ONBOARD_LLM_PROVIDER": "gemini"}, clear=True):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    exit_code = main(["scan", str(repo)])

        self.assertEqual(exit_code, 2)
        self.assertIn("LLM report generation failed", stderr.getvalue())

    def test_cli_verbose_prints_llm_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            result = LlmResult("Summary", "Start guide", "- `README.md`: Overview.", ["Provider was slow"])

            with mock.patch("onboard.cli.generate_llm_report_sections", return_value=result):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    exit_code = main(["scan", str(repo), "--verbose"])

        self.assertEqual(exit_code, 0)
        self.assertIn("llm warning: Provider was slow", stderr.getvalue())
        self.assertIn("Start guide", stdout.getvalue())

    def test_cli_no_llm_skips_provider_call(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            stdout = io.StringIO()

            with mock.patch("onboard.cli.generate_llm_report_sections") as generate:
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(["scan", str(repo), "--no-llm"])

        self.assertEqual(exit_code, 0)
        generate.assert_not_called()

    def test_cli_uses_mocked_llm_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
            stdout = io.StringIO()
            result = LlmResult("Summary", "Run with `npm run dev`.", "- `README.md`: Project overview.", [])

            with mock.patch("onboard.cli.generate_llm_report_sections", return_value=result):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(["scan", str(repo)])

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Run with `npm run dev`.", output)
        self.assertIn("Project overview", output)


if __name__ == "__main__":
    unittest.main()
