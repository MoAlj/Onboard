from __future__ import annotations

import json
import re
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
        hints.extend(infer_make_targets(root / "Makefile"))
    if "pyproject.toml" in names:
        hints.append(CommandHint("python -m pytest", "Common Python test command when pytest is configured."))
    if "requirements.txt" in names:
        hints.append(CommandHint("python -m pip install -r requirements.txt", "Install Python dependencies from requirements.txt."))
    if "package.json" in names:
        hints.extend(infer_package_scripts(root / "package.json"))
    if "Cargo.toml" in names:
        hints.append(CommandHint("cargo test", "Run Rust tests."))
        hints.append(CommandHint("cargo run", "Run the Rust binary if one exists."))
    if "go.mod" in names:
        hints.append(CommandHint("go test ./...", "Run Go tests across the module."))

    return hints


def infer_package_scripts(path: Path) -> list[CommandHint]:
    scripts = _scripts_from_package_json(path)
    hints: list[CommandHint] = []
    known_reasons = {
        "dev": "Starts the development server or watcher.",
        "start": "Starts the application in its default runtime mode.",
        "test": "Runs the project test suite.",
        "build": "Builds production artifacts.",
        "lint": "Runs static checks or linting.",
        "format": "Formats source files.",
        "typecheck": "Runs TypeScript or static type checks.",
        "preview": "Previews a production build locally.",
        "clean": "Removes generated artifacts.",
    }
    for script, body in scripts.items():
        reason = known_reasons.get(script, "package.json script.")
        if body:
            reason = f"{reason} Script body: `{body}`."
        hints.append(CommandHint(f"npm run {script}", reason))
    return hints


def infer_make_targets(path: Path) -> list[CommandHint]:
    targets = _targets_from_makefile(path)
    known_reasons = {
        "test": "Runs tests.",
        "run": "Runs the application.",
        "dev": "Starts a development workflow.",
        "build": "Builds project artifacts.",
        "lint": "Runs linting or static checks.",
        "format": "Formats source files.",
        "clean": "Removes generated artifacts.",
        "install": "Installs dependencies or local tooling.",
    }
    hints: list[CommandHint] = []
    for target, recipe in targets.items():
        reason = known_reasons.get(target, "Makefile target.")
        if recipe:
            preview = " && ".join(recipe[:2])
            reason = f"{reason} Recipe preview: `{preview}`."
        hints.append(CommandHint(f"make {target}", reason))
    return hints


def infer_project_purpose(root: Path, paths: Iterable[Path]) -> str | None:
    relative_paths = list(paths)
    names = {path.name for path in relative_paths}
    for readme_name in ("README.md", "README.rst", "README.txt"):
        if readme_name in names:
            purpose = _purpose_from_readme(root / readme_name)
            if purpose:
                return purpose

    package_json = root / "package.json"
    if package_json.exists():
        purpose = _purpose_from_package_json(package_json)
        if purpose:
            return purpose

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        purpose = _purpose_from_pyproject(pyproject)
        if purpose:
            return purpose
    return None


def infer_module_hints(paths: Iterable[Path]) -> list[str]:
    relative_paths = list(paths)
    hints: list[str] = []
    top_level_dirs = sorted({path.parts[0] for path in relative_paths if len(path.parts) > 1})
    common_roles = {
        "src": "Source package root.",
        "app": "Application code.",
        "backend": "Backend service code.",
        "frontend": "Frontend application code.",
        "tests": "Automated tests.",
        "docs": "Project documentation.",
        "scripts": "Developer or deployment scripts.",
        "config": "Configuration files.",
        ".github": "GitHub automation and CI configuration.",
    }
    for directory in top_level_dirs:
        reason = common_roles.get(directory)
        if reason:
            hints.append(f"`{directory}/`: {reason}")

    src_children = sorted({path.parts[1] for path in relative_paths if len(path.parts) > 2 and path.parts[0] == "src"})
    for child in src_children[:5]:
        hints.append(f"`src/{child}/`: Python/package module or source namespace.")

    if not hints and top_level_dirs:
        hints.append(f"Top-level directories detected: {', '.join(f'`{name}/`' for name in top_level_dirs[:8])}.")
    return hints


def infer_architecture_roles(paths: Iterable[Path]) -> list[str]:
    role_names = {
        "api": "API boundary or endpoint definitions.",
        "routes": "HTTP route definitions.",
        "models": "Domain, database, or validation models.",
        "services": "Business logic or integration services.",
        "components": "Reusable UI components.",
        "pages": "Page-level UI routes or views.",
        "migrations": "Database/schema migrations.",
    }
    roles: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if len(path.parts) < 2:
            continue
        for index, part in enumerate(path.parts[:-1]):
            role = role_names.get(part)
            if role is None:
                continue
            prefix = Path(*path.parts[: index + 1])
            key = str(prefix)
            if key in seen:
                continue
            seen.add(key)
            roles.append(f"`{key}/`: {role}")
    return sorted(roles)


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


def _scripts_from_package_json(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return {}
    return {str(name): str(command) for name, command in scripts.items()}


def _targets_from_makefile(path: Path) -> dict[str, list[str]]:
    text = _safe_read(path)
    targets: dict[str, list[str]] = {}
    current_target: str | None = None
    for line in text.splitlines():
        if line.startswith("\t"):
            if current_target is not None:
                recipe = line.strip()
                if recipe and len(targets[current_target]) < 3:
                    targets[current_target].append(recipe)
            continue
        current_target = None
        if line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+):(?:\s|$)", line)
        if not match:
            continue
        target = match.group(1)
        if target not in targets and not target.startswith("."):
            targets[target] = []
            current_target = target
    return dict(list(targets.items())[:12])


def _purpose_from_readme(path: Path) -> str | None:
    text = _safe_read(path)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    heading = lines[0].lstrip("# ").strip()
    paragraph = next((line for line in lines[1:] if not line.startswith("#") and not line.startswith("```")), "")
    if paragraph:
        return f"{heading}: {paragraph}" if heading else paragraph
    return heading or None


def _purpose_from_package_json(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    name = data.get("name")
    description = data.get("description")
    if name and description:
        return f"{name}: {description}"
    return description or name


def _purpose_from_pyproject(path: Path) -> str | None:
    text = _safe_read(path)
    name = _first_toml_string(text, "name")
    description = _first_toml_string(text, "description")
    if name and description:
        return f"{name}: {description}"
    return description or name


def _first_toml_string(text: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
    if not match:
        return None
    return match.group(1)


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
