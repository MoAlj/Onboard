from __future__ import annotations

from .models import RepoAnalysis


def build_markdown_report(analysis: RepoAnalysis, llm_summary: str | None = None) -> str:
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

    if llm_summary:
        lines.extend(["## Agent-Erklaerung", llm_summary.strip(), ""])

    lines.extend(
        [
            "## Wie ist es aufgebaut?",
            *_format_plain_items(analysis.module_hints),
            "",
            "### Strukturkarte",
            "```text",
            *(analysis.tree or ["(keine Dateien gefunden)"]),
            "```",
            "",
            "### Vermutete Architektur",
            _architecture_summary(analysis),
            "",
            "## Wo soll ich anfangen zu lesen?",
            *_format_reading_path(analysis),
            "",
            "## Wie starte/teste ich es lokal?",
            _format_list("Test-Orte", analysis.test_locations),
            *_format_command_hints(analysis),
            "",
            "## Sicher erkannt vs. vermutet",
            *_format_confidence_notes(analysis),
            "",
            "## Relevante Snippets",
            *_format_snippets(analysis),
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


def _architecture_summary(analysis: RepoAnalysis) -> str:
    if not analysis.languages:
        return "Es wurden noch nicht genug Dateien gefunden, um eine Architektur abzuleiten."
    primary = next(iter(analysis.languages))
    hints = [f"Das Repo wirkt primaer wie ein {primary}-Projekt."]
    if analysis.frameworks:
        hints.append(f"Erkannte Frameworks/Tools: {', '.join(analysis.frameworks)}.")
    if analysis.entry_points:
        paths = ", ".join(f"`{item.path}`" for item in analysis.entry_points[:3])
        hints.append(f"Die wahrscheinlichsten Einstiegspunkte sind {paths}.")
    return " ".join(hints)


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


def _format_reading_path(analysis: RepoAnalysis) -> list[str]:
    lines: list[str] = []
    if analysis.important_files:
        lines.append("- Erst diese Projektdateien lesen:")
        lines.extend(f"  - `{item.path}`: {item.reason}" for item in analysis.important_files[:6])
    if analysis.entry_points:
        lines.append("- Danach diese Einstiegspunkte pruefen:")
        lines.extend(f"  - `{item.path}`: {item.reason}" for item in analysis.entry_points[:6])
    if not lines:
        lines.append("- Keine klaren Startdateien erkannt.")
    return lines


def _format_command_hints(analysis: RepoAnalysis) -> list[str]:
    if not analysis.command_hints:
        return ["- Kommandos: keine klaren Kommandos erkannt."]
    lines = ["- Kommandos:"]
    lines.extend(f"  - `{hint.command}`: {hint.reason}" for hint in analysis.command_hints)
    return lines


def _format_confidence_notes(analysis: RepoAnalysis) -> list[str]:
    notes = [
        f"- Sicher erkannt: {analysis.scanned_files} Dateien, {len(analysis.important_files)} wichtige Dateien, {len(analysis.entry_points)} moegliche Einstiegspunkte.",
    ]
    if analysis.languages:
        notes.append(f"- Sicher erkannt: Dateiendungen deuten auf {', '.join(analysis.languages)} hin.")
    if analysis.project_purpose:
        notes.append("- Vermutet: Der Projektzweck wurde aus README oder Projektmetadaten abgeleitet.")
    if analysis.frameworks:
        notes.append("- Vermutet: Frameworks/Tools wurden aus Dependencies und Konfigurationsdateien abgeleitet.")
    if analysis.command_hints:
        notes.append("- Vermutet: Lokale Kommandos stammen aus bekannten Manifesten, Scripts oder Makefile-Zielen.")
    return notes


def _format_snippets(analysis: RepoAnalysis) -> list[str]:
    if not analysis.file_snippets:
        return ["- Keine sicheren Text-Snippets gesammelt."]
    lines: list[str] = []
    for snippet in analysis.file_snippets[:8]:
        suffix = " (gekuerzt)" if snippet.truncated else ""
        lines.extend(
            [
                f"### `{snippet.path}`{suffix}",
                f"_Warum relevant:_ {snippet.reason}",
                "",
                *_fenced_text(snippet.content or "(leer)"),
                "",
            ]
        )
    return lines


def _fenced_text(content: str) -> list[str]:
    fence = "~~~" if "```" in content else "```"
    return [f"{fence}text", content, fence]


def _format_plain_items(items: list[str]) -> list[str]:
    if not items:
        return ["- Keine erkannt."]
    return [f"- {item}" for item in items]
