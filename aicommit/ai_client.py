"""Shared AI client for aicommit — single point for all API calls."""

import time
from typing import Optional

import httpx

from .config import load_config


class AIError(Exception):
    """Raised when AI API calls fail."""
    pass


def call_ai(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 500,
    temperature: float = 0.3,
    timeout_sec: float = 90.0,
) -> dict:
    """Make a single, standardized AI API call.

    Returns dict with keys: content, model, prompt_tokens, completion_tokens, time_ms
    """
    config = load_config()
    endpoint = config["api"]["endpoint"].rstrip("/")
    api_key = config["api"]["key"]
    model = config["api"]["model"]
    provider = config["api"].get("provider", "openai")

    if not api_key:
        raise AIError("No API key configured. Run `aicommit --config` to set up.")

    start_time = time.time()
    timeout = httpx.Timeout(timeout_sec, connect=15.0)

    # Build provider-specific request
    if provider == "anthropic":
        headers, body = _build_anthropic_request(model, system_prompt, user_prompt, max_tokens, temperature, api_key)
        url = f"{endpoint}/messages"
    else:
        headers, body = _build_openai_request(model, system_prompt, user_prompt, max_tokens, temperature, api_key)
        url = f"{endpoint}/chat/completions"

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

            elapsed_ms = (time.time() - start_time) * 1000

            if provider == "anthropic":
                if not data.get("content"):
                    raise AIError("Empty response from AI provider")
                message = data["content"][0]["text"].strip()
                usage = data.get("usage", {})
                return {
                    "content": message,
                    "model": model,
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "time_ms": elapsed_ms,
                }
            else:
                if "choices" not in data or not data["choices"]:
                    raise AIError("Empty response from AI provider")
                message = data["choices"][0]["message"]["content"].strip()
                usage = data.get("usage", {})
                return {
                    "content": message,
                    "model": model,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "time_ms": elapsed_ms,
                }

    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 401:
            raise AIError("Invalid API key. Run `aicommit --config` to update.")
        elif status == 429:
            raise AIError("API rate limit exceeded. Please try again later.")
        elif status == 404:
            raise AIError(f"Model '{model}' not found. Check your configuration.")
        elif status >= 500:
            raise AIError(f"API server error ({status}). The provider may be down.")
        else:
            body = e.response.text[:300]
            raise AIError(f"API error ({status}): {body}")
    except httpx.ConnectError:
        raise AIError(f"Could not connect to {endpoint}. Check network and endpoint URL.")
    except httpx.TimeoutException:
        raise AIError("Request timed out. The AI provider may be slow or unreachable.")
    except httpx.RequestError as e:
        raise AIError(f"Connection failed: {e}")


def _build_openai_request(model: str, system: str, user: str, max_tok: int, temp: float, key: str):
    """Build OpenAI-compatible request."""
    return (
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temp,
            "max_tokens": max_tok,
        },
    )


def _build_anthropic_request(model: str, system: str, user: str, max_tok: int, temp: float, key: str):
    """Build Anthropic Messages API request."""
    return (
        {
            "x-api-key": key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        {
            "model": model,
            "system": system,
            "messages": [
                {"role": "user", "content": user},
            ],
            "temperature": temp,
            "max_tokens": max_tok,
        },
    )
