import unittest

import requests

from noorlytics.llm_interface import _summarize_ollama_http_error


class _FakeJsonResponse:
    def __init__(self, *, url: str, status_code: int, text: str, json_payload=None):
        self.url = url
        self.status_code = status_code
        self.text = text
        self._json_payload = json_payload

    def json(self):
        if isinstance(self._json_payload, Exception):
            raise self._json_payload
        return self._json_payload


class LlmInterfaceTests(unittest.TestCase):
    def test_summarize_ollama_http_error_includes_json_body(self):
        response = _FakeJsonResponse(
            url="http://localhost:11434/api/chat",
            status_code=500,
            text='{"error":"model crashed"}',
            json_payload={"error": "model crashed"},
        )
        error = requests.exceptions.HTTPError("500 Server Error", response=response)

        message = _summarize_ollama_http_error(error)

        self.assertIn("Status: 500", message)
        self.assertIn("Response body: model crashed", message)
        self.assertIn("URL: http://localhost:11434/api/chat", message)

    def test_summarize_ollama_http_error_falls_back_to_plain_text_body(self):
        response = _FakeJsonResponse(
            url="http://localhost:11434/api/chat",
            status_code=502,
            text="upstream timeout",
            json_payload=ValueError("not json"),
        )
        error = requests.exceptions.HTTPError("502 Bad Gateway", response=response)

        message = _summarize_ollama_http_error(error)

        self.assertIn("Status: 502", message)
        self.assertIn("Response body: upstream timeout", message)


if __name__ == "__main__":
    unittest.main()