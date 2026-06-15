"""LLM-based HTML generator for academic papers."""

import re
import json
import requests
from pathlib import Path
from urllib.parse import urlparse

from paper2html.config import LLM_API_KEY, LLM_MODEL, LLM_BASE_URL, LLM_REQUEST_TIMEOUT

PROMPT_PATH = Path(__file__).parent / "prompts" / "html_generate.txt"


class HTMLGenerator:
    """Generate HTML from parsed paper markdown using LLM."""

    def __init__(self, api_key: str = None, model: str = None, base_url: str = None):
        self.api_key = api_key or LLM_API_KEY
        self.model = model or LLM_MODEL
        self.base_url = self._normalize_base_url(base_url or LLM_BASE_URL)
        self.timeout = LLM_REQUEST_TIMEOUT

        if not self.api_key:
            raise ValueError(
                "LLM API key is required. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    def generate(self, markdown_content: str) -> str:
        """
        Generate HTML from paper markdown content.

        Args:
            markdown_content: Parsed paper in markdown format.

        Returns:
            Complete HTML string.
        """
        max_chars = 60000
        if len(markdown_content) > max_chars:
            print(f"[HTMLGenerator] Content too long ({len(markdown_content)} chars), truncating to {max_chars}")
            markdown_content = markdown_content[:max_chars] + "\n\n[... content truncated ...]"

        prompt = self.prompt_template.replace("{paper_content}", markdown_content)

        print(f"[HTMLGenerator] Calling {self.model}...")

        # Use requests directly for full control over the endpoint
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a senior front-end designer who builds polished academic "
                        "project pages (Nerfies / GauGAN style). Output only valid, complete "
                        "HTML — no markdown fences, no commentary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.5,
            "max_tokens": 20000,
        }

        resp = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload).encode("utf-8"),
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"LLM API error ({resp.status_code}): {resp.text}"
            )

        data = resp.json()
        html = data["choices"][0]["message"]["content"]

        # Clean up: remove markdown code fences if LLM wraps output
        html = self._clean_html(html)

        print(f"[HTMLGenerator] HTML generated ({len(html)} chars)")
        return html

    def _clean_html(self, html: str) -> str:
        """Remove markdown code fences and ensure valid HTML."""
        html = re.sub(r"^```html?\s*\n?", "", html.strip())
        html = re.sub(r"\n?```\s*$", "", html.strip())

        if not html.lower().startswith("<!doctype"):
            html = "<!DOCTYPE html>\n" + html

        return html

    def _normalize_base_url(self, base_url: str) -> str:
        """Normalize common OpenAI-compatible gateway roots to their v1 API URL."""
        normalized = base_url.rstrip("/")
        parsed = urlparse(normalized)
        if parsed.path in ("", "/"):
            return f"{normalized}/v1"
        return normalized
