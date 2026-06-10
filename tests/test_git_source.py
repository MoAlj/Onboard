from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from onboard.git_source import is_git_url, repo_source


class GitSourceTests(unittest.TestCase):
    def test_is_git_url(self):
        self.assertTrue(is_git_url("https://github.com/MoAlj/Onboard.git"))
        self.assertTrue(is_git_url("git@github.com:MoAlj/Onboard.git"))
        self.assertFalse(is_git_url("./local-repo"))

    def test_repo_source_yields_local_path(self):
        with repo_source("./local-repo") as path:
            self.assertEqual(path, Path("local-repo"))

    def test_repo_source_clones_and_cleans_temp_dir(self):
        created_paths: list[Path] = []

        def fake_clone(_url: str, destination: Path, verbose: bool = False) -> None:
            destination.mkdir(parents=True)
            (destination / "README.md").write_text("# Demo\n", encoding="utf-8")
            created_paths.append(destination)

        with mock.patch("onboard.git_source._clone_repo", side_effect=fake_clone):
            with repo_source("https://github.com/MoAlj/Onboard.git") as path:
                self.assertTrue((path / "README.md").exists())
                clone_path = path

        self.assertEqual(created_paths, [clone_path])
        self.assertFalse(clone_path.exists())


if __name__ == "__main__":
    unittest.main()
