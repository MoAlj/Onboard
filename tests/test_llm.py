from __future__ import annotations

import unittest

from onboard.llm import _extract_gemini_text


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


if __name__ == "__main__":
    unittest.main()
