"""AI API integration for commit message generation."""

import time
from dataclasses import dataclass
from typing import Optional

import httpx

from .config import load_config
from .prompts import STYLE_PROMPTS, SYSTEM_PROMPT


class AIError(Exception):
    """Raised when AI API calls fail."""
    pass


@dataclass
class AIResult:
    """Result from AI generation."""
    message: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    time_ms: float = 0


def generate_commit_message(
    diff: str,
    style: str = "conventional",
    language: str = "auto",
    recent_commits: Optional[list[str]] = None,
    hint: Optional[str] = None,
    branch_hint: str = "",
    breaking_hint: str = "",
    file_list: str = "",
) -> AIResult:
    """Generate a commit message using the configured AI provider.

    Returns AIResult with the message and metadata.
    """
    config = load_config()

    endpoint = config["api"]["endpoint"].rstrip("/")
    api_key = config["api"]["key"]
    model = config["api"]["model"]

    if not api_key:
        raise AIError(
            "No API key configured. Run `aicommit --config` to set up."
        )

    # Build recent commits context
    recent_text = ""
    if recent_commits:
        recent_text = "Recent commits (match this style):\n"
        for c in recent_commits:
            recent_text += f"  - {c}\n"

    # Get style prompt
    prompt_template = STYLE_PROMPTS.get(style, STYLE_PROMPTS["conventional"])
    user_prompt = prompt_template.format(
        diff=diff,
        recent_commits=recent_text,
        branch_hint=branch_hint,
        breaking_hint=breaking_hint,
        file_list=file_list,
    )

    if hint:
        user_prompt += f"\n\nAdditional context from user: \"{hint}\""

    system = SYSTEM_PROMPT.format(language=language)

    # Make API call
    start_time = time.time()

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{endpoint}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            data = response.json()

            elapsed_ms = (time.time() - start_time) * 1000

            if "choices" not in data or not data["choices"]:
                raise AIError("Empty response from AI provider")

            message = data["choices"][0]["message"]["content"].strip()

            # Remove markdown code block wrapping
            if message.startswith("```"):
                lines = message.split("\n")
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                message = "\n".join(lines).strip()

            # Extract token usage
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)

            return AIResult(
                message=message,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                time_ms=elapsed_ms,
            )

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise AIError("Invalid API key. Run `aicommit --config` to update.")
        elif e.response.status_code == 429:
            raise AIError("API rate limit exceeded. Please try again later.")
        elif e.response.status_code == 404:
            raise AIError(
                f"Model '{model}' not found at {endpoint}. Check your configuration."
            )
        else:
            raise AIError(f"API error ({e.response.status_code}): {e.response.text[:200]}")
    except httpx.RequestError as e:
        raise AIError(f"Connection failed: {e}")
