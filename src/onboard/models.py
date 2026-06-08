from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ImportantFile:
    path: str
    reason: str


@dataclass(frozen=True)
class CommandHint:
    command: str
    reason: str


@dataclass(frozen=True)
class FileSnippet:
    path: str
    reason: str
    content: str
    truncated: bool


@dataclass
class RepoAnalysis:
    root: Path
    total_files_seen: int
    scanned_files: int
    truncated: bool
    tree: list[str] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    important_files: list[ImportantFile] = field(default_factory=list)
    entry_points: list[ImportantFile] = field(default_factory=list)
    test_locations: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    command_hints: list[CommandHint] = field(default_factory=list)
    project_purpose: str | None = None
    module_hints: list[str] = field(default_factory=list)
    file_snippets: list[FileSnippet] = field(default_factory=list)
    maintainer_questions: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
