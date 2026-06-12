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
    template: Optional[str] = None,
    max_tokens_override: Optional[int] = None,
) -> AIResult:
    """Generate a commit message using the configured AI provider.

    Args:
        diff: Git diff content
        style: Commit style (conventional, emoji, simple, detailed)
        language: Output language hint
        recent_commits: Recent commit messages for style matching
        hint: User-provided additional context
        branch_hint: Auto-detected branch type hint
        breaking_hint: Breaking change warning
        file_list: List of changed files
        template: Custom prompt template (overrides style prompts)

    Returns:
        AIResult with generated message and metadata.
    """
    config = load_config()

    endpoint = config["api"]["endpoint"].rstrip("/")
    api_key = config["api"]["key"]
    model = config["api"]["model"]

    if not api_key:
        raise AIError(
            "No API key configured. Run `aicommit --config` to set up."
        )

    # Build system prompt
    system = SYSTEM_PROMPT.format(language=language)

    # Build user prompt
    if template:
        # Use custom template
        user_prompt = template.format(
            diff=diff,
            style=style,
            branch_hint=branch_hint,
            breaking_hint=breaking_hint,
            file_list=file_list,
        )
    else:
        recent_text = ""
        if recent_commits:
            recent_text = "Recent commits (match this style):\n"
            for c in recent_commits:
                recent_text += f"  - {c}\n"

        prompt_template = STYLE_PROMPTS.get(style, STYLE_PROMPTS["conventional"])
        user_prompt = prompt_template.format(
            diff=diff,
            recent_commits=recent_text,
            branch_hint=branch_hint,
            breaking_hint=breaking_hint,
            file_list=file_list,
        )

    if hint:
        user_prompt += f'\n\nAdditional context from user: "{hint}"'

    # Make API call with proper timeout
    start_time = time.time()
    timeout = httpx.Timeout(60.0, connect=15.0)
    max_tok = max_tokens_override if max_tokens_override is not None else 500

    try:
        with httpx.Client(timeout=timeout) as client:
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
                    "max_tokens": max_tok,
                },
            )
            response.raise_for_status()
            data = response.json()

            elapsed_ms = (time.time() - start_time) * 1000

            if "choices" not in data or not data["choices"]:
                raise AIError("Empty response from AI provider")

            message = data["choices"][0]["message"]["content"].strip()

            # Clean up markdown code block wrapping
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
        status = e.response.status_code
        if status == 401:
            raise AIError("Invalid API key. Run `aicommit --config` to update.")
        elif status == 429:
            raise AIError("API rate limit exceeded. Please try again later.")
        elif status == 404:
            raise AIError(
                f"Model '{model}' not found at {endpoint}. Check your configuration."
            )
        elif status >= 500:
            raise AIError(f"API server error ({status}). The provider may be down.")
        else:
            body = e.response.text[:300]
            raise AIError(f"API error ({status}): {body}")
    except httpx.ConnectError:
        raise AIError(
            f"Could not connect to {endpoint}. Check your network and endpoint URL."
        )
    except httpx.TimeoutException:
        raise AIError("Request timed out. The AI provider may be slow or unreachable.")
    except httpx.RequestError as e:
        raise AIError(f"Connection failed: {e}")
