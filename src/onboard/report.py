from __future__ import annotations

from .models import RepoAnalysis


def build_markdown_report(analysis: RepoAnalysis, llm_summary: str | None = None) -> str:
    lines = [
        f"# Onboarding Report: {analysis.root.name}",
        "",
        "## Projektueberblick",
        f"- Pfad: `{analysis.root}`",
        f"- Gescannte Dateien: {analysis.scanned_files}",
        f"- Scan begrenzt: {'ja' if analysis.truncated else 'nein'}",
        _format_list("Sprachen", _format_mapping(analysis.languages)),
        _format_list("Frameworks/Tools", analysis.frameworks),
        _format_list("Paketmanager", analysis.package_managers),
        "",
    ]

    if llm_summary:
        lines.extend(["## Agent-Erklaerung", llm_summary.strip(), ""])

    lines.extend(
        [
            "## Strukturkarte",
            "```text",
            *(analysis.tree or ["(keine Dateien gefunden)"]),
            "```",
            "",
            "## Vermutete Architektur",
            _architecture_summary(analysis),
            "",
            "## Wichtigste Dateien zum Lesen",
            *_format_important_files(analysis.important_files),
            "",
            "## Moegliche Einstiegspunkte",
            *_format_important_files(analysis.entry_points),
            "",
            "## Tests und lokale Kommandos",
            _format_list("Test-Orte", analysis.test_locations),
            *_format_command_hints(analysis),
            "",
            "## Offene Fragen und Unsicherheiten",
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


def _format_command_hints(analysis: RepoAnalysis) -> list[str]:
    if not analysis.command_hints:
        return ["- Kommandos: keine klaren Kommandos erkannt."]
    lines = ["- Kommandos:"]
    lines.extend(f"  - `{hint.command}`: {hint.reason}" for hint in analysis.command_hints)
    return lines


def _format_plain_items(items: list[str]) -> list[str]:
    if not items:
        return ["- Keine offensichtlichen Unsicherheiten."]
    return [f"- {item}" for item in items]

