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
    retries: int = 2,
) -> dict:
    """Make a single, standardized AI API call with retry on transient errors.

    Returns dict with keys: content, model, prompt_tokens, completion_tokens, time_ms
    """
    config = load_config()
    endpoint = config["api"]["endpoint"].rstrip("/")
    api_key = config["api"]["key"]
    model = config["api"]["model"]
    provider = config["api"].get("provider", "openai")

    if not api_key:
        raise AIError("No API key configured. Run `aicommit --config` to set up.")

    last_error = None
    for attempt in range(retries + 1):
        try:
            return _call_ai_once(
                endpoint=endpoint, api_key=api_key, model=model, provider=provider,
                system_prompt=system_prompt, user_prompt=user_prompt,
                max_tokens=max_tokens, temperature=temperature, timeout_sec=timeout_sec,
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            last_error = e
            if attempt < retries:
                wait = (attempt + 1) * 2
                time.sleep(wait)
                continue
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < retries:
                last_error = e
                wait = (attempt + 1) * 2
                time.sleep(wait)
                continue
            # Non-retryable HTTP errors — raise immediately
            _raise_http_error(e, model)
        except AIError:
            raise

    # All retries exhausted
    if isinstance(last_error, httpx.TimeoutException):
        raise AIError("Request timed out after retries. The AI provider may be slow or unreachable.")
    elif isinstance(last_error, (httpx.ConnectError, httpx.RemoteProtocolError)):
        raise AIError(f"Connection failed after retries: {last_error}")
    raise AIError(f"API error after {retries} retries: {last_error}")


def _call_ai_once(endpoint: str, api_key: str, model: str, provider: str,
                  system_prompt: str, user_prompt: str,
                  max_tokens: int, temperature: float, timeout_sec: float) -> dict:
    """Single AI call without retry logic."""
    start_time = time.time()
    timeout = httpx.Timeout(timeout_sec, connect=15.0)

    if provider == "anthropic":
        headers, body = _build_anthropic_request(model, system_prompt, user_prompt, max_tokens, temperature, api_key)
        url = f"{endpoint}/messages"
    else:
        headers, body = _build_openai_request(model, system_prompt, user_prompt, max_tokens, temperature, api_key)
        url = f"{endpoint}/chat/completions"

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


def _raise_http_error(e: httpx.HTTPStatusError, model: str):
    """Map HTTP status codes to user-friendly AIError messages."""
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
