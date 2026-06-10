from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from . import detectors
from .models import CommandHint, FileSnippet, ImportEdge, ImportantFile, RepoAnalysis

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",
    ".next",
    ".turbo",
}

SECRET_LIKE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}

SNIPPET_FILE_NAMES = {
    "README.md",
    "README.rst",
    "README.txt",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
}


def scan_repo(repo_path: str | Path, max_files: int = 500, snippet_bytes: int = 4000) -> RepoAnalysis:
    root = Path(repo_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Repository path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")
    if max_files < 1:
        raise ValueError("--max-files must be at least 1")
    if snippet_bytes < 0:
        raise ValueError("--snippet-bytes must be 0 or greater")

    files = _collect_files(root, max_files)
    all_count = _count_files(root, limit=max_files + 1)
    truncated = all_count > max_files
    relative_files = [path.relative_to(root) for path in files]

    languages = Counter()
    important_files: list[ImportantFile] = []
    entry_points: list[ImportantFile] = []
    test_locations: set[str] = set()
    config_files: set[str] = set()

    for relative in relative_files:
        if language := detectors.detect_language(relative):
            languages[language] += 1
        if important := detectors.detect_important_file(relative):
            important_files.append(important)
        if entry_point := detectors.detect_entry_point(relative):
            entry_points.append(entry_point)
        if detectors.detect_test_location(relative):
            test_locations.add(_location_bucket(relative))
        if detectors.detect_config_file(relative):
            config_files.add(str(relative))

    package_managers = detectors.detect_package_managers(relative_files)
    frameworks = detectors.detect_frameworks(root, relative_files)
    command_hints = detectors.infer_command_hints(root, relative_files)
    package_scripts = _infer_package_scripts(root, relative_files)
    make_targets = _infer_make_targets(root, relative_files)
    project_purpose = detectors.infer_project_purpose(root, relative_files)
    module_hints = detectors.infer_module_hints(relative_files)
    architecture_roles = detectors.infer_architecture_roles(relative_files)
    import_graph = _build_import_graph(root, relative_files)
    file_snippets = _collect_snippets(root, important_files, entry_points, relative_files, snippet_bytes)
    uncertainties = _infer_uncertainties(relative_files, entry_points, command_hints, truncated)
    maintainer_questions = _infer_maintainer_questions(relative_files, entry_points, command_hints, test_locations)

    return RepoAnalysis(
        root=root,
        total_files_seen=min(all_count, max_files),
        scanned_files=len(files),
        truncated=truncated,
        tree=build_tree(relative_files),
        languages=dict(languages.most_common()),
        frameworks=frameworks,
        package_managers=package_managers,
        important_files=sorted(important_files, key=lambda item: item.path),
        entry_points=sorted(entry_points, key=lambda item: item.path),
        test_locations=sorted(test_locations),
        config_files=sorted(config_files),
        command_hints=command_hints,
        package_scripts=package_scripts,
        make_targets=make_targets,
        import_graph=import_graph,
        architecture_roles=architecture_roles,
        project_purpose=project_purpose,
        module_hints=module_hints,
        file_snippets=file_snippets,
        maintainer_questions=maintainer_questions,
        uncertainties=uncertainties,
    )


def build_tree(paths: list[Path], max_entries: int = 120) -> list[str]:
    tree: dict[str, dict] = {}
    for path in paths:
        current = tree
        for part in path.parts:
            current = current.setdefault(part, {})

    lines: list[str] = []
    omitted = _append_tree_lines(tree, lines, max_entries=max_entries)
    if omitted:
        lines.append(f"- ... {omitted} more entries omitted")
    return lines


def _append_tree_lines(tree: dict[str, dict], lines: list[str], max_entries: int, depth: int = 0) -> int:
    omitted = 0
    for name in sorted(tree, key=lambda item: (bool(tree[item]), item.lower())):
        children = tree[name]
        if len(lines) >= max_entries:
            omitted += 1 + _count_tree_entries(children)
            continue
        indent = "  " * depth
        suffix = "/" if children else ""
        lines.append(f"{indent}- {name}{suffix}")
        omitted += _append_tree_lines(children, lines, max_entries=max_entries, depth=depth + 1)
    return omitted


def _count_tree_entries(tree: dict[str, dict]) -> int:
    return sum(1 + _count_tree_entries(children) for children in tree.values())


def _infer_package_scripts(root: Path, relative_files: list[Path]) -> list[CommandHint]:
    if "package.json" not in {path.name for path in relative_files}:
        return []
    return detectors.infer_package_scripts(root / "package.json")


def _infer_make_targets(root: Path, relative_files: list[Path]) -> list[CommandHint]:
    if "Makefile" not in {path.name for path in relative_files}:
        return []
    return detectors.infer_make_targets(root / "Makefile")


def _build_import_graph(root: Path, relative_files: list[Path], max_nodes: int = 80) -> list[ImportEdge]:
    python_files = [path for path in relative_files if path.suffix == ".py"]
    internal_modules = _internal_python_modules(relative_files)
    edges: list[ImportEdge] = []
    for relative in python_files[:max_nodes]:
        imports = _imports_from_python_file(root / relative, relative)
        if not imports:
            continue
        internal = [module for module in imports if _is_internal_import(module, internal_modules)]
        edges.append(ImportEdge(source=str(relative), imports=imports, internal_imports=internal))
    return edges


def _imports_from_python_file(path: Path, relative: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    module_name = _module_name_for_path(relative)
    current_package = module_name.split(".")[:-1] if module_name else []
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_import_from(node, current_package)
            if module:
                imports.add(module)
    return sorted(imports)


def _resolve_import_from(node: ast.ImportFrom, current_package: list[str]) -> str | None:
    if node.level == 0:
        return node.module
    base_length = max(0, len(current_package) - node.level + 1)
    parts = current_package[:base_length]
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(part for part in parts if part)


def _module_name_for_path(path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _internal_python_modules(relative_files: list[Path]) -> set[str]:
    modules: set[str] = set()
    for path in relative_files:
        if path.suffix != ".py":
            continue
        module_name = _module_name_for_path(path)
        if module_name:
            modules.add(module_name.split(".")[0])
        if path.name == "__init__.py" and len(path.parts) >= 2:
            if path.parts[0] == "src" and len(path.parts) >= 3:
                modules.add(path.parts[1])
            else:
                modules.add(path.parts[0])
    return modules


def _is_internal_import(module: str, internal_modules: set[str]) -> bool:
    top_level = module.split(".", 1)[0]
    return top_level in internal_modules


def _collect_snippets(
    root: Path,
    important_files: list[ImportantFile],
    entry_points: list[ImportantFile],
    relative_files: list[Path],
    snippet_bytes: int,
) -> list[FileSnippet]:
    if snippet_bytes == 0:
        return []

    snippet_candidates: dict[str, str] = {}
    for item in important_files:
        snippet_candidates[item.path] = item.reason
    for item in entry_points:
        snippet_candidates[item.path] = item.reason
    for relative in relative_files:
        if relative.name in SNIPPET_FILE_NAMES or relative.match(".github/workflows/*"):
            snippet_candidates.setdefault(str(relative), "Relevant project metadata or automation file.")

    snippets: list[FileSnippet] = []
    for relative_path, reason in sorted(snippet_candidates.items()):
        relative = Path(relative_path)
        if _should_skip_snippet(relative):
            continue
        snippet = _read_text_snippet(root / relative, snippet_bytes)
        if snippet is None:
            continue
        content, truncated = snippet
        snippets.append(FileSnippet(path=relative_path, reason=reason, content=content, truncated=truncated))
    return snippets


def _should_skip_snippet(path: Path) -> bool:
    lower_name = path.name.lower()
    if lower_name in SECRET_LIKE_NAMES:
        return True
    if lower_name.endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    if "secret" in lower_name or "credential" in lower_name:
        return True
    return False


def _read_text_snippet(path: Path, snippet_bytes: int) -> tuple[str, bool] | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    truncated = len(raw) > snippet_bytes
    raw = raw[:snippet_bytes]
    if b"\x00" in raw:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.strip(), truncated


def _collect_files(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for path in _walk(root):
        if path.is_file():
            files.append(path)
            if len(files) >= max_files:
                break
    return files


def _count_files(root: Path, limit: int) -> int:
    count = 0
    for path in _walk(root):
        if path.is_file():
            count += 1
            if count >= limit:
                return count
    return count


def _walk(root: Path):
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda child: (child.is_file(), child.name.lower()))
        except OSError:
            continue
        for child in reversed(children):
            if child.is_dir():
                if child.name not in IGNORED_DIRS:
                    stack.append(child)
            else:
                yield child


def _location_bucket(path: Path) -> str:
    if len(path.parts) > 1:
        return path.parts[0]
    return str(path)


def _infer_uncertainties(
    relative_files: list[Path],
    entry_points: list[ImportantFile],
    command_hints,
    truncated: bool,
) -> list[str]:
    uncertainties: list[str] = []
    names = {path.name for path in relative_files}
    if not relative_files:
        uncertainties.append("No source files were found in the scanned repository.")
    if "README.md" not in names and "README.rst" not in names and "README.txt" not in names:
        uncertainties.append("No README was found, so project intent must be inferred from files.")
    if not entry_points:
        uncertainties.append("No obvious runtime entry point was detected.")
    if not command_hints:
        uncertainties.append("No clear local run or test commands were inferred.")
    if len(entry_points) > 3:
        uncertainties.append("Multiple possible entry points were detected; confirm the main runtime path.")
    if truncated:
        uncertainties.append("The scan hit the file limit; increase --max-files for a fuller report.")
    return uncertainties


def _infer_maintainer_questions(
    relative_files: list[Path],
    entry_points: list[ImportantFile],
    command_hints,
    test_locations: set[str],
) -> list[str]:
    names = {path.name for path in relative_files}
    questions: list[str] = []
    if "README.md" not in names and "README.rst" not in names and "README.txt" not in names:
        questions.append("What is the intended user-facing purpose of this project?")
    if not entry_points:
        questions.append("What is the canonical application entry point?")
    if not command_hints:
        questions.append("Which command should a new developer run first locally?")
    if not test_locations:
        questions.append("Where are the automated tests, or are they not added yet?")
    if "Dockerfile" in names:
        questions.append("Is Docker the recommended local development path or only a deployment artifact?")
    return questions
