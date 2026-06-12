"""AI code review for aicommit."""

from .ai_client import AIError, call_ai

REVIEW_PROMPT = """Analyze the following git diff for potential issues. Be thorough and practical.

## Instructions
Review the code changes for:
1. **Bugs** — Logic errors, edge cases, null/undefined issues
2. **Security** — Injection risks, exposed secrets, unsafe operations
3. **Performance** — N+1 queries, memory leaks, inefficient patterns
4. **Style** — Code consistency, naming, unused imports/variables
5. **Testing gaps** — What should be tested that isn't?

## Output Format
For each issue found, use:
- 🔴 **[Severity] File:line** — Description + suggestion

If no issues found, just say "✅ No significant issues detected."

## Diff
{diff}"""


def analyze_diff(diff: str, severity: str = "all", hint: str = "") -> str:
    """Analyze diff for code quality issues.

    Args:
        diff: Git diff to analyze
        severity: Minimum severity to report (all, high, medium, low)
        hint: Additional review focus area
    """
    prompt = REVIEW_PROMPT.format(diff=diff)

    if hint:
        prompt += f'\n\n## Additional Focus\nFocus especially on: {hint}'
    if severity != "all":
        prompt += f'\n\nReport only {severity} severity issues and above.'

    result = call_ai(
        system_prompt="You are a senior software engineer performing a thorough code review. Be specific, actionable, and fair. Cite line numbers when possible.",
        user_prompt=prompt,
        max_tokens=2000,
        temperature=0.2,
        timeout_sec=90.0,
    )

    from .render import console
    console.print(
        f"[dim]Model: {result['model']} | "
        f"Tokens: {result['prompt_tokens']}→{result['completion_tokens']} | "
        f"Time: {result['time_ms']:.0f}ms[/dim]"
    )
    return result["content"]
