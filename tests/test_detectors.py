from __future__ import annotations

import unittest
from pathlib import Path

from onboard import detectors


class DetectorTests(unittest.TestCase):
    def test_detect_language_for_common_extensions(self):
        self.assertEqual(detectors.detect_language(Path("app.py")), "Python")
        self.assertEqual(detectors.detect_language(Path("src/main.ts")), "TypeScript")
        self.assertEqual(detectors.detect_language(Path("src/main.rs")), "Rust")

    def test_detect_package_managers(self):
        paths = [Path("pyproject.toml"), Path("package-lock.json"), Path("Cargo.toml")]
        self.assertEqual(detectors.detect_package_managers(paths), ["Python packaging/pip", "npm", "Cargo"])

    def test_detect_entry_points(self):
        self.assertIsNotNone(detectors.detect_entry_point(Path("app.py")))
        self.assertIsNotNone(detectors.detect_entry_point(Path("src/main.rs")))
        self.assertIsNone(detectors.detect_entry_point(Path("docs/index.md")))


if __name__ == "__main__":
    unittest.main()
