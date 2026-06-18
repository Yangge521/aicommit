"""AI commit message generation — uses shared ai_client."""

from dataclasses import dataclass
from typing import Optional

from .ai_client import AIError, call_ai  # noqa: F401 — re-export
from .config import load_config
from .prompts import STYLE_PROMPTS, SYSTEM_PROMPT
from .git_utils import chunk_diff, CHUNK_THRESHOLD


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
    """Generate a commit message using the configured AI provider.

    For large diffs (> CHUNK_THRESHOLD lines), automatically uses chunked
    context: generates per-chunk summaries first, then synthesises a final
    message from the summaries.
    """
    config = load_config()

    system = SYSTEM_PROMPT.format(language=language)

    # Check if diff is large enough to warrant chunking
    diff_lines = diff.count("\n") + 1
    use_chunking = diff_lines > CHUNK_THRESHOLD and not template

    if use_chunking:
        return _generate_chunked_message(
            diff=diff, style=style, language=language,
            recent_commits=recent_commits, hint=hint,
            branch_hint=branch_hint, breaking_hint=breaking_hint,
            file_list=file_list, max_tokens_override=max_tokens_override,
            temperature_override=temperature_override,
            config=config, system=system,
        )

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
    if not message or not message.strip():
        raise AIError("AI returned an empty response. Please try again.")

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


def _generate_chunked_message(
    diff: str, style: str, language: str,
    recent_commits: Optional[list[str]], hint: Optional[str],
    branch_hint: str, breaking_hint: str, file_list: str,
    max_tokens_override: Optional[int], temperature_override: Optional[float],
    config: dict, system: str,
) -> AIResult:
    """Generate commit message for large diffs using per-file chunking.

    Strategy:
    1. Split diff into per-file chunks.
    2. For each chunk, ask AI for a one-line summary.
    3. Feed all summaries + the stat into the final prompt.
    """
    chunks = chunk_diff(diff)

    # If chunking produced only 1 chunk, fall back to normal generation
    if len(chunks) <= 1:
        # Just truncate and proceed normally
        return _generate_simple(
            diff=diff[:8000], style=style, language=language,
            recent_commits=recent_commits, hint=hint,
            branch_hint=branch_hint, breaking_hint=breaking_hint,
            file_list=file_list, max_tokens_override=max_tokens_override,
            temperature_override=temperature_override,
            config=config, system=system,
        )

    # Step 1: Generate per-chunk summaries
    chunk_summaries: list[str] = []
    total_tokens_in = 0
    total_tokens_out = 0
    total_time_ms = 0.0
    model_used = ""

    summary_system = "You are a code analyst. For each diff chunk, provide a single-line summary of what changed. Be concise."

    for chunk in chunks:
        chunk_prompt = f"File: {chunk['file']}\n\nDiff:\n{chunk['diff']}\n\nOne-line summary of changes:"
        try:
            r = call_ai(
                system_prompt=summary_system,
                user_prompt=chunk_prompt,
                max_tokens=100,
                temperature=0.2,
            )
            summary = r["content"].strip()
            if summary:
                chunk_summaries.append(f"- [{chunk['file']}] {summary}")
            total_tokens_in += r["prompt_tokens"]
            total_tokens_out += r["completion_tokens"]
            total_time_ms += r["time_ms"]
            model_used = r["model"]
        except AIError:
            # If a chunk fails, add a basic summary
            chunk_summaries.append(f"- [{chunk['file']}] ({chunk['lines']} lines changed)")

    # Step 2: Build synthesis prompt
    recent_text = ""
    if recent_commits:
        recent_text = "Recent commits (match this style):\n"
        for c in recent_commits:
            recent_text += f"  - {c}\n"

    prompt_template = STYLE_PROMPTS.get(style, STYLE_PROMPTS["conventional"])

    # Build a condensed diff summary instead of the full diff
    condensed = "This is a large changeset spanning multiple files. Per-file summaries:\n\n"
    condensed += "\n".join(chunk_summaries)
    condensed += f"\n\nTotal: {len(chunks)} files changed, {diff.count(chr(10)) + 1} diff lines."

    user_prompt = prompt_template.format(
        diff=condensed, recent_commits=recent_text,
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

    total_tokens_in += result["prompt_tokens"]
    total_tokens_out += result["completion_tokens"]
    total_time_ms += result["time_ms"]
    model_used = result["model"]

    message = result["content"]
    if not message or not message.strip():
        raise AIError("AI returned an empty response. Please try again.")

    if message.startswith("```"):
        lines = message.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        message = "\n".join(lines).strip()

    return AIResult(
        message=message,
        model=model_used,
        tokens_in=total_tokens_in,
        tokens_out=total_tokens_out,
        time_ms=total_time_ms,
    )


def _generate_simple(
    diff: str, style: str, language: str,
    recent_commits: Optional[list[str]], hint: Optional[str],
    branch_hint: str, breaking_hint: str, file_list: str,
    max_tokens_override: Optional[int], temperature_override: Optional[float],
    config: dict, system: str,
) -> AIResult:
    """Fallback simple generation without chunking."""
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
    if not message or not message.strip():
        raise AIError("AI returned an empty response. Please try again.")

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
