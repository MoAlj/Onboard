from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import CommandHint, ImportantFile


LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".c": "C",
    ".h": "C/C++",
    ".cpp": "C++",
    ".hpp": "C++",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
    ".sh": "Shell",
}

IMPORTANT_FILE_REASONS = {
    "README.md": "Primary project documentation.",
    "README.rst": "Primary project documentation.",
    "README.txt": "Primary project documentation.",
    "pyproject.toml": "Python package metadata and tooling configuration.",
    "requirements.txt": "Python dependency list.",
    "package.json": "Node package metadata, scripts, and dependencies.",
    "Cargo.toml": "Rust package metadata and dependencies.",
    "go.mod": "Go module metadata and dependencies.",
    "Dockerfile": "Container build instructions.",
    "docker-compose.yml": "Local multi-service runtime configuration.",
    "docker-compose.yaml": "Local multi-service runtime configuration.",
    "Makefile": "Common project automation commands.",
}

CONFIG_NAMES = {
    ".env.example",
    ".gitignore",
    ".prettierrc",
    ".eslintrc",
    ".eslintrc.json",
    "ruff.toml",
    "mypy.ini",
    "pytest.ini",
    "tox.ini",
    "tsconfig.json",
    "vite.config.ts",
    "next.config.js",
    "next.config.mjs",
}


def detect_language(path: Path) -> str | None:
    return LANGUAGE_BY_EXTENSION.get(path.suffix.lower())


def detect_important_file(path: Path) -> ImportantFile | None:
    reason = IMPORTANT_FILE_REASONS.get(path.name)
    if reason is None and path.match(".github/workflows/*"):
        reason = "CI workflow configuration."
    if reason is None:
        return None
    return ImportantFile(str(path), reason)


def detect_config_file(path: Path) -> bool:
    return path.name in CONFIG_NAMES or path.match(".github/workflows/*")


def detect_test_location(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    return (
        "tests" in parts
        or "test" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.tsx")
    )


def detect_entry_point(path: Path) -> ImportantFile | None:
    name = path.name
    if name in {"main.py", "app.py", "manage.py", "__main__.py"}:
        return ImportantFile(str(path), "Likely Python application entry point.")
    if name in {"index.js", "index.ts", "main.ts", "main.tsx", "server.js", "server.ts"}:
        return ImportantFile(str(path), "Likely JavaScript/TypeScript entry point.")
    if str(path) == "src/main.rs":
        return ImportantFile(str(path), "Rust binary entry point.")
    if str(path) == "cmd/main.go" or name == "main.go":
        return ImportantFile(str(path), "Go application entry point.")
    return None


def detect_package_managers(paths: Iterable[Path]) -> list[str]:
    names = {path.name for path in paths}
    managers = []
    if "pyproject.toml" in names or "requirements.txt" in names:
        managers.append("Python packaging/pip")
    if "poetry.lock" in names:
        managers.append("Poetry")
    if "uv.lock" in names:
        managers.append("uv")
    if "package-lock.json" in names:
        managers.append("npm")
    if "yarn.lock" in names:
        managers.append("Yarn")
    if "pnpm-lock.yaml" in names:
        managers.append("pnpm")
    if "Cargo.toml" in names:
        managers.append("Cargo")
    if "go.mod" in names:
        managers.append("Go modules")
    return managers


def detect_frameworks(root: Path, paths: Iterable[Path]) -> list[str]:
    relative_paths = list(paths)
    names = {path.name for path in relative_paths}
    frameworks: set[str] = set()

    package_json = root / "package.json"
    if package_json.exists():
        frameworks.update(_frameworks_from_package_json(package_json))

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = _safe_read(pyproject).lower()
        for marker, framework in {
            "django": "Django",
            "fastapi": "FastAPI",
            "flask": "Flask",
            "pytest": "pytest",
            "ruff": "Ruff",
        }.items():
            if marker in text:
                frameworks.add(framework)

    if "vite.config.ts" in names or "vite.config.js" in names:
        frameworks.add("Vite")
    if "next.config.js" in names or "next.config.mjs" in names:
        frameworks.add("Next.js")
    if "manage.py" in names:
        frameworks.add("Django")

    return sorted(frameworks)


def infer_command_hints(root: Path, paths: Iterable[Path]) -> list[CommandHint]:
    relative_paths = list(paths)
    names = {path.name for path in relative_paths}
    hints: list[CommandHint] = []

    if "Makefile" in names:
        hints.append(CommandHint("make", "Project includes a Makefile with automation targets."))
    if "pyproject.toml" in names:
        hints.append(CommandHint("python -m pytest", "Common Python test command when pytest is configured."))
    if "requirements.txt" in names:
        hints.append(CommandHint("python -m pip install -r requirements.txt", "Install Python dependencies from requirements.txt."))
    if "package.json" in names:
        scripts = _scripts_from_package_json(root / "package.json")
        for script in ("dev", "start", "test", "build"):
            if script in scripts:
                hints.append(CommandHint(f"npm run {script}", f"package.json defines the '{script}' script."))
    if "Cargo.toml" in names:
        hints.append(CommandHint("cargo test", "Run Rust tests."))
        hints.append(CommandHint("cargo run", "Run the Rust binary if one exists."))
    if "go.mod" in names:
        hints.append(CommandHint("go test ./...", "Run Go tests across the module."))

    return hints


def _frameworks_from_package_json(path: Path) -> set[str]:
    frameworks: set[str] = set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return frameworks
    dependencies = {}
    dependencies.update(data.get("dependencies", {}))
    dependencies.update(data.get("devDependencies", {}))
    markers = {
        "react": "React",
        "next": "Next.js",
        "vue": "Vue",
        "svelte": "Svelte",
        "express": "Express",
        "vite": "Vite",
        "typescript": "TypeScript",
        "jest": "Jest",
        "vitest": "Vitest",
    }
    for package_name, framework in markers.items():
        if package_name in dependencies:
            frameworks.add(framework)
    return frameworks


def _scripts_from_package_json(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return set()
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return set()
    return set(scripts)


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""

