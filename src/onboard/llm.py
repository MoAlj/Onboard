from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .models import RepoAnalysis


def generate_llm_summary(analysis: RepoAnalysis) -> str | None:
    provider = os.environ.get("ONBOARD_LLM_PROVIDER", "").lower()
    if provider in {"", "gemini"}:
        gemini_summary = _generate_gemini_summary(analysis)
        if gemini_summary or provider == "gemini":
            return gemini_summary
    if provider in {"", "openai"}:
        return _generate_openai_summary(analysis)
    return None


def _generate_gemini_summary(analysis: RepoAnalysis) -> str | None:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    model = os.environ.get("ONBOARD_GEMINI_MODEL", "gemini-2.5-flash")
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
            "maxOutputTokens": 700,
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
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError):
        return None

    return _extract_gemini_text(data)


def _generate_openai_summary(analysis: RepoAnalysis) -> str | None:
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI()
    prompt = _build_prompt(analysis)
    response = client.responses.create(
        model=os.environ.get("ONBOARD_OPENAI_MODEL", "gpt-4.1-mini"),
        input=prompt,
    )
    return response.output_text


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


def _build_prompt(analysis: RepoAnalysis) -> str:
    return "\n".join(
        [
            "Explain this repository to a new developer in concise German.",
            "Use only the scan facts below. Mark uncertainty clearly.",
            "",
            f"Repo: {analysis.root.name}",
            f"Languages: {analysis.languages}",
            f"Frameworks: {analysis.frameworks}",
            f"Package managers: {analysis.package_managers}",
            f"Important files: {[item.path for item in analysis.important_files]}",
            f"Entry points: {[item.path for item in analysis.entry_points]}",
            f"Tests: {analysis.test_locations}",
            f"Commands: {[hint.command for hint in analysis.command_hints]}",
            f"Project purpose: {analysis.project_purpose}",
            f"Module hints: {analysis.module_hints}",
            "Curated snippets:",
            *[
                f"- {snippet.path}: {snippet.content[:1200]}"
                for snippet in analysis.file_snippets[:8]
            ],
            f"Uncertainties: {analysis.uncertainties}",
            f"Maintainer questions: {analysis.maintainer_questions}",
        ]
    )
