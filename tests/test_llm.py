from __future__ import annotations

import io
import json
import urllib.error
import unittest
from pathlib import Path
from unittest import mock

from onboard.llm import _extract_gemini_text, _generate_gemini_report_sections, generate_llm_report_sections
from onboard.models import RepoAnalysis


class BytesHttpError(urllib.error.HTTPError):
    def __init__(self, body: bytes):
        super().__init__(
            url="https://example.test",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=None,
        )
        self._body = body

    def read(self, *args, **kwargs):
        return self._body


class LlmTests(unittest.TestCase):
    def test_extract_gemini_text(self):
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Teil 1"},
                            {"text": "Teil 2"},
                        ]
                    }
                }
            ]
        }

        self.assertEqual(_extract_gemini_text(data), "Teil 1\nTeil 2")

    def test_extract_gemini_text_returns_none_for_empty_response(self):
        self.assertIsNone(_extract_gemini_text({"candidates": []}))

    def test_generate_summary_warns_when_provider_key_is_missing(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)

        with mock.patch.dict("os.environ", {"ONBOARD_LLM_PROVIDER": "gemini"}, clear=True):
            result = generate_llm_report_sections(analysis)

        self.assertIsNone(result.summary)
        self.assertIn("Gemini skipped", result.warnings[0])

    def test_gemini_empty_response_returns_warning(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(
            return_value=io.BytesIO(b'{"candidates": [{"finishReason": "MAX_TOKENS"}]}')
        )
        fake_response.__exit__ = mock.Mock(return_value=False)

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"}, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=fake_response):
                result = _generate_gemini_report_sections(analysis)

        self.assertIsNone(result.summary)
        self.assertIn("empty response", result.warnings[0])
        self.assertIn("finishReason=MAX_TOKENS", result.warnings[0])

    def test_gemini_request_uses_larger_output_and_low_thinking(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json_text(
                                    {
                                        "summary": "Kurzueberblick",
                                        "startup_guide": "Starte mit `npm run dev`.",
                                        "project_structure": "- `README.md`: Projektueberblick.",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(return_value=io.BytesIO(json_text(payload).encode("utf-8")))
        fake_response.__exit__ = mock.Mock(return_value=False)

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key", "ONBOARD_GEMINI_TIMEOUT": "123"}, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=fake_response) as urlopen:
                _generate_gemini_report_sections(analysis)

        request = urlopen.call_args.args[0]
        timeout = urlopen.call_args.kwargs["timeout"]
        request_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(timeout, 123)
        self.assertEqual(request_payload["generationConfig"]["maxOutputTokens"], 2048)
        self.assertEqual(request_payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "low")

    def test_gemini_timeout_returns_clear_warning(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key", "ONBOARD_GEMINI_TIMEOUT": "7"}, clear=True):
            with mock.patch("urllib.request.urlopen", side_effect=TimeoutError):
                result = _generate_gemini_report_sections(analysis)

        self.assertIsNone(result.summary)
        self.assertIn("timed out after 7 seconds", result.warnings[0])

    def test_gemini_invalid_json_returns_warning(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(return_value=io.BytesIO(b"not-json"))
        fake_response.__exit__ = mock.Mock(return_value=False)

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"}, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=fake_response):
                result = _generate_gemini_report_sections(analysis)

        self.assertIsNone(result.summary)
        self.assertIn("not valid JSON", result.warnings[0])

    def test_gemini_http_error_includes_body_message(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)
        error_body = b'{"error": {"message": "Model is not found"}}'
        http_error = BytesHttpError(error_body)

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"}, clear=True):
            with mock.patch("urllib.request.urlopen", side_effect=http_error):
                result = _generate_gemini_report_sections(analysis)

        self.assertIsNone(result.summary)
        self.assertIn("HTTP 400: Model is not found", result.warnings[0])

    def test_gemini_json_response_returns_report_sections(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json_text(
                                    {
                                        "summary": "Kurzueberblick",
                                        "startup_guide": "Starte mit `npm run dev`.",
                                        "project_structure": "- `README.md`: Projektueberblick.",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(return_value=io.BytesIO(json_text(payload).encode("utf-8")))
        fake_response.__exit__ = mock.Mock(return_value=False)

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"}, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=fake_response):
                result = _generate_gemini_report_sections(analysis)

        self.assertEqual(result.summary, "Kurzueberblick")
        self.assertEqual(result.startup_guide, "Starte mit `npm run dev`.")
        self.assertEqual(result.project_structure, "- `README.md`: Projektueberblick.")
        self.assertEqual(result.warnings, [])

    def test_gemini_accepts_legacy_structure_guide_alias(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json_text(
                                    {
                                        "summary": "Kurzueberblick",
                                        "startup_guide": "Starte mit `npm run dev`.",
                                        "structure_guide": "- `README.md`: Alias wird akzeptiert.",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(return_value=io.BytesIO(json_text(payload).encode("utf-8")))
        fake_response.__exit__ = mock.Mock(return_value=False)

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"}, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=fake_response):
                result = _generate_gemini_report_sections(analysis)

        self.assertEqual(result.project_structure, "- `README.md`: Alias wird akzeptiert.")
        self.assertEqual(result.warnings, [])

    def test_gemini_accepts_german_key_aliases(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json_text(
                                    {
                                        "summary": "Kurzueberblick",
                                        "startanleitung": "Starte mit `python app.py`.",
                                        "projektstruktur": "- `app.py`: Einstiegspunkt.",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(return_value=io.BytesIO(json_text(payload).encode("utf-8")))
        fake_response.__exit__ = mock.Mock(return_value=False)

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"}, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=fake_response):
                result = _generate_gemini_report_sections(analysis)

        self.assertEqual(result.startup_guide, "Starte mit `python app.py`.")
        self.assertEqual(result.project_structure, "- `app.py`: Einstiegspunkt.")
        self.assertEqual(result.warnings, [])

    def test_missing_fields_warning_includes_received_keys(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": json_text({"summary": "Kurzueberblick", "foo": "bar"})}
                        ]
                    }
                }
            ]
        }
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(return_value=io.BytesIO(json_text(payload).encode("utf-8")))
        fake_response.__exit__ = mock.Mock(return_value=False)

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"}, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=fake_response):
                result = _generate_gemini_report_sections(analysis)

        self.assertIn("Received keys: foo, summary", result.warnings[0])

    def test_structured_section_values_are_converted_to_markdown(self):
        analysis = RepoAnalysis(root=Path("demo"), total_files_seen=0, scanned_files=0, truncated=False)
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json_text(
                                    {
                                        "summary": "Kurzueberblick",
                                        "startup_guide": [
                                            {"command": "npm run dev", "description": "Startet den Dev-Server."}
                                        ],
                                        "project_structure": {
                                            "README.md": "Projektueberblick.",
                                            "src/onboard/cli.py": {"description": "CLI-Einstieg."},
                                        },
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(return_value=io.BytesIO(json_text(payload).encode("utf-8")))
        fake_response.__exit__ = mock.Mock(return_value=False)

        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"}, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=fake_response):
                result = _generate_gemini_report_sections(analysis)

        self.assertIn("Startet den Dev-Server", result.startup_guide)
        self.assertIn("README.md", result.project_structure)
        self.assertIn("CLI-Einstieg", result.project_structure)
        self.assertEqual(result.warnings, [])


def json_text(data: dict) -> str:
    import json

    return json.dumps(data)


if __name__ == "__main__":
    unittest.main()
