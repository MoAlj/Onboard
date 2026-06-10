from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass

from .models import RepoAnalysis


@dataclass(frozen=True)
class LlmResult:
    summary: str | None
    startup_guide: str | None
    project_structure: str | None
    warnings: list[str]


def generate_llm_report_sections(analysis: RepoAnalysis) -> LlmResult:
    provider = os.environ.get("ONBOARD_LLM_PROVIDER", "").lower()
    warnings: list[str] = []
    if provider in {"", "gemini"}:
        gemini_result = _generate_gemini_report_sections(analysis)
        warnings.extend(gemini_result.warnings)
        if gemini_result.summary or provider == "gemini":
            return LlmResult(gemini_result.summary, gemini_result.startup_guide, gemini_result.project_structure, warnings)
    if provider in {"", "openai"}:
        openai_result = _generate_openai_report_sections(analysis)
        warnings.extend(openai_result.warnings)
        return LlmResult(openai_result.summary, openai_result.startup_guide, openai_result.project_structure, warnings)
    return LlmResult(None, None, None, [f"unknown LLM provider '{provider}'"])


def generate_llm_summary(analysis: RepoAnalysis) -> LlmResult:
    return generate_llm_report_sections(analysis)


def _generate_gemini_report_sections(analysis: RepoAnalysis) -> LlmResult:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return LlmResult(None, None, None, ["Gemini skipped: GEMINI_API_KEY or GOOGLE_API_KEY is not set"])

    model = os.environ.get("ONBOARD_GEMINI_MODEL", "gemini-3.5-flash")
    timeout = _env_int("ONBOARD_GEMINI_TIMEOUT", default=90)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": _build_prompt(analysis),
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
            "thinkingConfig": {
                "thinkingLevel": "low",
            },
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return LlmResult(None, None, None, [_format_http_error("Gemini request failed", exc)])
    except urllib.error.URLError as exc:
        return LlmResult(None, None, None, [f"Gemini request failed: {exc.reason}"])
    except TimeoutError:
        return LlmResult(None, None, None, [f"Gemini request timed out after {timeout} seconds"])
    except socket.timeout:
        return LlmResult(None, None, None, [f"Gemini request timed out after {timeout} seconds"])
    except OSError as exc:
        return LlmResult(None, None, None, [f"Gemini request failed: {exc}"])
    except json.JSONDecodeError:
        return LlmResult(None, None, None, ["Gemini response was not valid JSON"])

    text = _extract_gemini_text(data)
    if not text:
        return LlmResult(None, None, None, [_describe_empty_gemini_response(data)])
    return _parse_llm_sections(text, provider="Gemini")


def _generate_openai_report_sections(analysis: RepoAnalysis) -> LlmResult:
    if not os.environ.get("OPENAI_API_KEY"):
        return LlmResult(None, None, None, ["OpenAI skipped: OPENAI_API_KEY is not set"])
    try:
        from openai import OpenAI
    except ImportError:
        return LlmResult(None, None, None, ["OpenAI skipped: optional dependency 'openai' is not installed"])

    client = OpenAI()
    prompt = _build_prompt(analysis)
    try:
        response = client.responses.create(
            model=os.environ.get("ONBOARD_OPENAI_MODEL", "gpt-4.1-mini"),
            input=prompt,
        )
    except Exception as exc:
        return LlmResult(None, None, None, [f"OpenAI request failed: {exc}"])
    if not response.output_text:
        return LlmResult(None, None, None, ["OpenAI returned an empty response"])
    return _parse_llm_sections(response.output_text, provider="OpenAI")


def _extract_gemini_text(data: dict) -> str | None:
    parts: list[str] = []
    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                parts.append(text)
    if not parts:
        return None
    return "\n".join(parts)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def _describe_empty_gemini_response(data: dict) -> str:
    details: list[str] = []
    prompt_feedback = data.get("promptFeedback")
    if isinstance(prompt_feedback, dict):
        block_reason = prompt_feedback.get("blockReason")
        if block_reason:
            details.append(f"prompt blockReason={block_reason}")
    for index, candidate in enumerate(data.get("candidates", [])):
        if not isinstance(candidate, dict):
            continue
        finish_reason = candidate.get("finishReason")
        if finish_reason:
            details.append(f"candidate {index} finishReason={finish_reason}")
        safety = candidate.get("safetyRatings")
        if safety:
            details.append(f"candidate {index} safetyRatings={_summarize_safety_ratings(safety)}")
    if details:
        return f"Gemini returned an empty response ({'; '.join(details)})"
    return "Gemini returned an empty response without candidates or text parts"


def _summarize_safety_ratings(safety_ratings) -> str:
    if not isinstance(safety_ratings, list):
        return "unknown"
    summaries: list[str] = []
    for rating in safety_ratings[:4]:
        if not isinstance(rating, dict):
            continue
        category = rating.get("category", "unknown")
        probability = rating.get("probability", "unknown")
        blocked = rating.get("blocked")
        if blocked is None:
            summaries.append(f"{category}:{probability}")
        else:
            summaries.append(f"{category}:{probability}:blocked={blocked}")
    return ", ".join(summaries) or "unknown"


def _format_http_error(prefix: str, exc: urllib.error.HTTPError) -> str:
    detail = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except OSError:
        body = ""
    if body:
        detail = _extract_error_message(body)
    if detail:
        return f"{prefix}: HTTP {exc.code}: {detail}"
    return f"{prefix}: HTTP {exc.code}"


def _extract_error_message(body: str) -> str:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()[:500]
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message.strip()[:500]
    return body.strip()[:500]


def _parse_llm_sections(text: str, provider: str) -> LlmResult:
    payload = _extract_json_object(text)
    if payload is None:
        return LlmResult(None, None, None, [f"{provider} response did not contain valid report JSON"])

    summary = _first_text(payload, "summary")
    startup_guide = _first_text(
        payload,
        "startup_guide",
        "startupGuide",
        "start_guide",
        "startGuide",
        "startup",
        "start",
        "startanleitung",
        "start_anleitung",
        "wie_wird_die_anwendung_gestartet",
    )
    project_structure = _first_text(
        payload,
        "project_structure",
        "structure_guide",
        "projectStructure",
        "structure",
        "struktur",
        "projektstruktur",
        "projekt_struktur",
        "dateien_und_ordner",
    )
    missing = [
        name
        for name, value in {
            "summary": summary,
            "startup_guide": startup_guide,
            "project_structure": project_structure,
        }.items()
        if not value
    ]
    if missing:
        keys = ", ".join(sorted(str(key) for key in payload))
        return LlmResult(
            summary,
            startup_guide,
            project_structure,
            [f"{provider} response missed fields: {', '.join(missing)}. Received keys: {keys or '(none)'}"],
        )
    return LlmResult(summary, startup_guide, project_structure, [])


def _extract_json_object(text: str) -> dict | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            data = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return data


def _string_or_none(value) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _first_text(payload: dict, *keys: str) -> str | None:
    for key in keys:
        value = _text_or_none(payload.get(key))
        if value:
            return value
    return None


def _text_or_none(value) -> str | None:
    if isinstance(value, str):
        return _string_or_none(value)
    if isinstance(value, list):
        lines = [_list_item_to_markdown(item) for item in value]
        return "\n".join(line for line in lines if line).strip() or None
    if isinstance(value, dict):
        lines = [_dict_item_to_markdown(key, item) for key, item in value.items()]
        return "\n".join(line for line in lines if line).strip() or None
    return None


def _list_item_to_markdown(item) -> str:
    if isinstance(item, str):
        return f"- {item.strip()}" if item.strip() else ""
    if isinstance(item, dict):
        label = _string_or_none(item.get("path")) or _string_or_none(item.get("file")) or _string_or_none(item.get("name"))
        description = (
            _string_or_none(item.get("description"))
            or _string_or_none(item.get("purpose"))
            or _string_or_none(item.get("summary"))
            or _string_or_none(item.get("command"))
        )
        if label and description:
            return f"- `{label}`: {description}"
        if description:
            return f"- {description}"
        if label:
            return f"- `{label}`"
        parts = [f"{key}: {value}" for key, value in item.items() if isinstance(value, (str, int, float, bool))]
        return f"- {', '.join(parts)}" if parts else ""
    return ""


def _dict_item_to_markdown(key, value) -> str:
    label = str(key)
    if isinstance(value, str):
        value = value.strip()
        return f"- `{label}`: {value}" if value else ""
    if isinstance(value, list):
        nested = "\n".join(f"  {line}" for line in (_list_item_to_markdown(item) for item in value) if line)
        return f"- `{label}`:\n{nested}" if nested else f"- `{label}`"
    if isinstance(value, dict):
        description = (
            _string_or_none(value.get("description"))
            or _string_or_none(value.get("purpose"))
            or _string_or_none(value.get("summary"))
            or _string_or_none(value.get("command"))
        )
        return f"- `{label}`: {description}" if description else f"- `{label}`"
    return ""


def _build_prompt(analysis: RepoAnalysis) -> str:
    return "\n".join(
        [
            "Du erzeugst strukturierte Abschnitte fuer einen Repo-Onboarding-Report.",
            "Antworte ausschliesslich als JSON-Objekt. Nutze exakt diese drei Keys: summary, startup_guide, project_structure.",
            "Verwende nicht den Key structure_guide. Verwende project_structure.",
            "Schreibe auf Deutsch. Nutze nur die Scan-Fakten und Snippets unten.",
            "startup_guide: Liste alle Wege zum Starten der Anwendung auf. Fokus auf setup/install/dev/start/run/build/Docker. Keine Test-, Lint-, Format- oder Clean-Kommandos.",
            "project_structure: Erklaere jede Datei und jeden relevanten Ordner aus der Strukturkarte grob. Schreibe fuer Kollegen, die das Repo neu sehen.",
            "Nutze fuer project_structure kurze Markdown-Bullets im Format: - `pfad/zur/datei`: ein kurzer erklaerender Satz.",
            "Wenn Informationen fehlen, sage knapp, welche Startinformation nicht im Repo erkennbar ist.",
            "",
            f"Repo: {analysis.root.name}",
            f"Languages: {analysis.languages}",
            f"Frameworks: {analysis.frameworks}",
            f"Package managers: {analysis.package_managers}",
            f"Important files: {[item.path for item in analysis.important_files]}",
            f"Entry points: {[item.path for item in analysis.entry_points]}",
            f"Tests: {analysis.test_locations}",
            f"Commands: {[hint.command for hint in analysis.command_hints]}",
            f"Package scripts: {[hint.command for hint in analysis.package_scripts]}",
            f"Make targets: {[hint.command for hint in analysis.make_targets]}",
            f"Project purpose: {analysis.project_purpose}",
            f"Module hints: {analysis.module_hints}",
            f"Architecture roles: {analysis.architecture_roles}",
            "Import graph excerpt:",
            *[
                f"- {edge.source}: imports={edge.imports[:8]}, internal={edge.internal_imports[:8]}"
                for edge in analysis.import_graph[:20]
            ],
            "Curated snippets:",
            *[
                f"- {snippet.path}: {snippet.content[:1200]}"
                for snippet in analysis.file_snippets[:8]
            ],
            f"Uncertainties: {analysis.uncertainties}",
            f"Maintainer questions: {analysis.maintainer_questions}",
        ]
    )
