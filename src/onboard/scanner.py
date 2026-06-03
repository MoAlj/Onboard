from __future__ import annotations

from collections import Counter
from pathlib import Path

from . import detectors
from .models import ImportantFile, RepoAnalysis

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


def scan_repo(repo_path: str | Path, max_files: int = 500) -> RepoAnalysis:
    root = Path(repo_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Repository path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")
    if max_files < 1:
        raise ValueError("--max-files must be at least 1")

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
    uncertainties = _infer_uncertainties(relative_files, entry_points, command_hints, truncated)

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
    if truncated:
        uncertainties.append("The scan hit the file limit; increase --max-files for a fuller report.")
    return uncertainties
