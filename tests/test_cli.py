from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from onboard.cli import main


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


if __name__ == "__main__":
    unittest.main()
