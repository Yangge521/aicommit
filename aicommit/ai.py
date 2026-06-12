"""AI API integration for commit message generation."""

import httpx

from .config import load_config
from .prompts import STYLE_PROMPTS, SYSTEM_PROMPT


class AIError(Exception):
    """Raised when AI API calls fail."""
    pass


def generate_commit_message(
    diff: str,
    style: str = "conventional",
    language: str = "auto",
    recent_commits: list[str] | None = None,
    hint: str | None = None,
) -> str:
    """Generate a commit message using the configured AI provider."""
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
        recent_text = "Recent commit style reference:\n"
        for c in recent_commits:
            recent_text += f"  - {c}\n"

    # Get style prompt
    prompt_template = STYLE_PROMPTS.get(style, STYLE_PROMPTS["conventional"])
    user_prompt = prompt_template.format(
        diff=diff,
        recent_commits=recent_text,
    )

    if hint:
        user_prompt += f"\n\nAdditional context from user: {hint}"

    system = SYSTEM_PROMPT.format(language=language)

    # Make API call
    try:
        with httpx.Client(timeout=30.0) as client:
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

            if "choices" not in data or not data["choices"]:
                raise AIError("Empty response from AI provider")

            message = data["choices"][0]["message"]["content"].strip()
            # Remove any markdown code block wrapping
            if message.startswith("```"):
                lines = message.split("\n")
                message = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            return message

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
