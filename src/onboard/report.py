from __future__ import annotations

import re

from .llm import LlmResult
from .models import RepoAnalysis


def build_markdown_report(analysis: RepoAnalysis, llm_sections: LlmResult | None = None) -> str:
    lines = [
        f"# Onboarding Report: {analysis.root.name}",
        "",
        "## Was ist dieses Projekt?",
        f"- Pfad: `{analysis.root}`",
        f"- Gescannte Dateien: {analysis.scanned_files}",
        f"- Scan begrenzt: {'ja' if analysis.truncated else 'nein'}",
        f"- Zweck: {analysis.project_purpose or 'nicht sicher erkannt'}",
        _format_list("Sprachen", _format_mapping(analysis.languages)),
        _format_list("Frameworks/Tools", analysis.frameworks),
        _format_list("Paketmanager", analysis.package_managers),
        "",
    ]

    if llm_sections and llm_sections.summary:
        lines.extend(["## Kurzueberblick", llm_sections.summary.strip(), ""])

    lines.extend(
        [
            "## Projektstruktur",
            "### Strukturkarte",
            "```text",
            *_format_annotated_tree(analysis, llm_sections),
            "```",
            "",
            "## Wie wird die Anwendung gestartet?",
            *_format_startup_guide(analysis, llm_sections),
            "",
            "## Import-Beziehungen",
            *_format_import_graph(analysis),
            "",
            "## Naechste Fragen an Maintainer",
            *_format_plain_items(analysis.maintainer_questions),
            "",
            "## Offene Unsicherheiten",
            *_format_plain_items(analysis.uncertainties),
            "",
        ]
    )
    return "\n".join(lines)


def _format_mapping(mapping: dict[str, int]) -> list[str]:
    return [f"{key} ({value})" for key, value in mapping.items()]


def _format_list(label: str, values: list[str]) -> str:
    if not values:
        return f"- {label}: keine erkannt"
    return f"- {label}: {', '.join(values)}"


def _format_important_files(items) -> list[str]:
    if not items:
        return ["- Keine erkannt."]
    return [f"- `{item.path}`: {item.reason}" for item in items]


def _format_annotated_tree(analysis: RepoAnalysis, llm_sections: LlmResult | None) -> list[str]:
    if not analysis.tree:
        return ["(keine Dateien gefunden)"]

    explanations = _parse_project_structure_explanations(llm_sections.project_structure if llm_sections else None)
    lines: list[str] = []
    if not explanations and not llm_sections:
        lines.append('"LLM-Projektstruktur ist im --no-llm Modus nicht verfuegbar."')
    path_stack: list[str] = []
    for tree_line in analysis.tree:
        lines.append(tree_line)
        depth = (len(tree_line) - len(tree_line.lstrip(" "))) // 2
        name = tree_line.strip().removeprefix("- ").rstrip("/")
        path_stack = path_stack[:depth]
        path_stack.append(name)
        path = "/".join(path_stack)
        explanation = _explanation_for_path(path, name, explanations)
        if explanation:
            lines.append(f"{'  ' * (depth + 1)}\"{explanation}\"")
    return lines


def _parse_project_structure_explanations(project_structure: str | None) -> dict[str, str]:
    if not project_structure:
        return {}
    explanations: dict[str, str] = {}
    for raw_line in project_structure.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(?:[-*]\s*)?`([^`]+)`\s*[:\-]\s*(.+)$", line)
        if match:
            path = match.group(1).strip().strip("/")
            explanations[path] = _clean_explanation(match.group(2))
            continue
        match = re.match(r"^(?:[-*]\s*)?([^:]+?)\s*:\s*(.+)$", line)
        if match and "/" in match.group(1):
            path = match.group(1).strip().strip("` ").strip("/")
            explanations[path] = _clean_explanation(match.group(2))
    return explanations


def _explanation_for_path(path: str, name: str, explanations: dict[str, str]) -> str | None:
    candidates = [path, path.rstrip("/"), name, name.rstrip("/")]
    for candidate in candidates:
        if candidate in explanations:
            return explanations[candidate]
    return None


def _clean_explanation(value: str) -> str:
    return value.strip().strip('"').strip()


def _format_startup_guide(analysis: RepoAnalysis, llm_sections: LlmResult | None) -> list[str]:
    if llm_sections and llm_sections.startup_guide:
        return [llm_sections.startup_guide.strip()]
    hints = _startup_command_hints(analysis)
    if hints:
        return ["- LLM-Startanleitung ist im --no-llm Modus nicht verfuegbar.", "- Erkannte Start-nahe Kommandos:", *hints]
    return ["- LLM-Startanleitung ist im --no-llm Modus nicht verfuegbar."]


def _startup_command_hints(analysis: RepoAnalysis) -> list[str]:
    keywords = ("dev", "start", "run", "serve", "preview", "build", "install", "setup", "docker")
    hints = [*analysis.package_scripts, *analysis.make_targets, *analysis.command_hints]
    lines: list[str] = []
    seen: set[str] = set()
    for hint in hints:
        command_lower = hint.command.lower()
        reason_lower = hint.reason.lower()
        if not any(keyword in command_lower or keyword in reason_lower for keyword in keywords):
            continue
        if any(skip in command_lower for skip in ("test", "lint", "format", "clean")):
            continue
        if hint.command in seen:
            continue
        seen.add(hint.command)
        lines.append(f"  - `{hint.command}`: {hint.reason}")
    return lines


def _format_command_hints(analysis: RepoAnalysis) -> list[str]:
    if not analysis.command_hints and not analysis.package_scripts and not analysis.make_targets:
        return ["- Kommandos: keine klaren Kommandos erkannt."]
    lines: list[str] = []
    if analysis.package_scripts:
        lines.append("- package.json Scripts:")
        lines.extend(f"  - `{hint.command}`: {hint.reason}" for hint in analysis.package_scripts)
    if analysis.make_targets:
        lines.append("- Makefile-Ziele:")
        lines.extend(f"  - `{hint.command}`: {hint.reason}" for hint in analysis.make_targets)
    package_commands = {hint.command for hint in analysis.package_scripts}
    make_commands = {hint.command for hint in analysis.make_targets}
    other_hints = [
        hint for hint in analysis.command_hints if hint.command not in package_commands and hint.command not in make_commands
    ]
    if other_hints:
        lines.append("- Weitere Kommandos:")
        lines.extend(f"  - `{hint.command}`: {hint.reason}" for hint in other_hints)
    return lines


def _format_import_graph(analysis: RepoAnalysis) -> list[str]:
    if not analysis.import_graph:
        return ["- Keine Python-Import-Beziehungen erkannt."]
    lines: list[str] = []
    internal_lines: list[str] = []
    external_lines: list[str] = []
    for edge in analysis.import_graph[:20]:
        if edge.internal_imports:
            internal_lines.append(f"- `{edge.source}` -> {', '.join(f'`{module}`' for module in edge.internal_imports[:8])}")
        external_imports = [module for module in edge.imports if module not in edge.internal_imports]
        if external_imports:
            external_lines.append(f"- `{edge.source}` -> {', '.join(f'`{module}`' for module in external_imports[:8])}")
    lines.append("### Interne Imports")
    lines.extend(internal_lines or ["- Keine internen Imports erkannt."])
    lines.append("")
    lines.append("### Externe Imports")
    lines.extend(external_lines or ["- Keine externen Imports erkannt."])
    if len(analysis.import_graph) > 20:
        lines.append(f"- ... {len(analysis.import_graph) - 20} weitere Import-Knoten ausgelassen")
    return lines


def _format_plain_items(items: list[str]) -> list[str]:
    if not items:
        return ["- Keine erkannt."]
    return [f"- {item}" for item in items]
