"""AI commit message generation — uses shared ai_client."""

from dataclasses import dataclass
from typing import Optional

from .ai_client import AIError, call_ai  # noqa: F401 — re-export
from .config import load_config
from .prompts import STYLE_PROMPTS, SYSTEM_PROMPT


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
    temperature_override: Optional[float] = None,
) -> AIResult:
    """Generate a commit message using the configured AI provider."""
    config = load_config()

    system = SYSTEM_PROMPT.format(language=language)

    # Build user prompt
    if template:
        user_prompt = template.format(
            diff=diff, style=style,
            branch_hint=branch_hint, breaking_hint=breaking_hint, file_list=file_list,
        )
    else:
        recent_text = ""
        if recent_commits:
            recent_text = "Recent commits (match this style):\n"
            for c in recent_commits:
                recent_text += f"  - {c}\n"

        prompt_template = STYLE_PROMPTS.get(style, STYLE_PROMPTS["conventional"])
        user_prompt = prompt_template.format(
            diff=diff, recent_commits=recent_text,
            branch_hint=branch_hint, breaking_hint=breaking_hint, file_list=file_list,
        )

    if hint:
        user_prompt += f'\n\nAdditional context from user: "{hint}"'

    max_tok = max_tokens_override if max_tokens_override is not None else 500
    temp = temperature_override if temperature_override is not None else config["api"].get("temperature", 0.3)

    result = call_ai(
        system_prompt=system,
        user_prompt=user_prompt,
        max_tokens=max_tok,
        temperature=temp,
    )

    message = result["content"]
    # Clean up markdown code block wrapping
    if message.startswith("```"):
        lines = message.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        message = "\n".join(lines).strip()

    return AIResult(
        message=message,
        model=result["model"],
        tokens_in=result["prompt_tokens"],
        tokens_out=result["completion_tokens"],
        time_ms=result["time_ms"],
    )
