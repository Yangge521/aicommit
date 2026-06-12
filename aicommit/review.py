"""AI code review for aicommit."""

import time

import httpx

from .ai import AIError
from .config import load_config

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


def analyze_diff(
    diff: str,
    severity: str = "all",
    hint: str = "",
) -> str:
    """Analyze diff for code quality issues.

    Args:
        diff: Git diff to analyze
        severity: Minimum severity to report (all, high, medium, low)
        hint: Additional review focus area
    """
    config = load_config()
    if not config["api"]["key"]:
        raise AIError("No API key configured. Run `aicommit --config` to set up.")

    endpoint = config["api"]["endpoint"].rstrip("/")
    start_time = time.time()
    timeout = httpx.Timeout(90.0, connect=15.0)

    prompt = REVIEW_PROMPT.format(diff=diff)

    if hint:
        prompt += f'\n\n## Additional Focus\nFocus especially on: {hint}'

    if severity != "all":
        prompt += f'\n\nReport only {severity} severity issues and above.'

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{endpoint}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config['api']['key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config["api"]["model"],
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a senior software engineer performing a thorough code review. Be specific, actionable, and fair. Cite line numbers from the diff when possible.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 2000,
                },
            )
            response.raise_for_status()
            data = response.json()

            if "choices" not in data or not data["choices"]:
                raise AIError("Empty response from AI provider")

            message = data["choices"][0]["message"]["content"].strip()

            elapsed_ms = (time.time() - start_time) * 1000
            usage = data.get("usage", {})

            from .render import console
            console.print(
                f"[dim]Model: {config['api']['model']} | "
                f"Tokens: {usage.get('prompt_tokens', 0)}→{usage.get('completion_tokens', 0)} | "
                f"Time: {elapsed_ms:.0f}ms[/dim]"
            )

            return message

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise AIError("Invalid API key.")
        raise AIError(f"API error ({e.response.status_code})")
    except Exception as e:
        raise AIError(f"Review failed: {e}")
