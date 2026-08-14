"""The single place where a Gemini request is built and sent.
"""
import json
import os
import re

from google import genai
from google.genai import types

from core import config


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("html"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    # Convert leftover markdown bold/italic to HTML tags
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    return text.strip()


_client = None


def _gemini():
    """The shared Gemini client, built on first use.

    Lazy on purpose: importing this module must not require an API key, so
    the app can still serve the profile/tracker/queue views without one.
    """
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _generate(prompt: str, max_tokens: int, *, as_json: bool = False, temperature: float = 0.7) -> str:
    """One place where a Gemini request is configured.

    `thinking_budget=0` matters: with thinking mode on (the default on some
    models) tokens are silently consumed before the visible text, so longer
    prompts come back empty.
    """
    response = _gemini().models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            **({"response_mime_type": "application/json"} if as_json else {}),
        ),
    )
    return response.text


def call_gemini(prompt: str, max_tokens: int = 8192) -> str:
    """Free-text generation; fences and stray markdown are stripped."""
    return strip_code_fence(_generate(prompt, max_tokens))


def _call_gemini_json(prompt: str, max_tokens: int = 4096) -> dict:
    """Structured generation — the model is pinned to JSON output."""
    return json.loads(_generate(prompt, max_tokens, as_json=True))
