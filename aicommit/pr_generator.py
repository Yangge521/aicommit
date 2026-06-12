"""PR description generator for aicommit."""

from .ai import AIError, generate_commit_message
from .git_utils import (
    GitError,
    get_branch_name,
    get_recent_commits,
    run_git,
)


def get_pr_diff(base_branch: str = "main") -> str:
    """Get diff between current branch and base branch for PR context."""
    try:
        stat = run_git(["diff", f"{base_branch}...HEAD", "--stat"])
        diff = run_git(["diff", f"{base_branch}...HEAD", "--unified=3"])
    except GitError:
        # Try origin/base
        try:
            stat = run_git(["diff", f"origin/{base_branch}...HEAD", "--stat"])
            diff = run_git(["diff", f"origin/{base_branch}...HEAD", "--unified=3"])
        except GitError:
            raise GitError(
                f"Could not find base branch '{base_branch}' or 'origin/{base_branch}'.\n"
                "Specify the base branch with: `aicommit --pr-base main`"
            )

    full_diff = stat + "\n\n" + diff
    lines = full_diff.split("\n")
    if len(lines) > 300:
        full_diff = "\n".join(lines[:300])
        full_diff += f"\n\n... (truncated, {len(lines) - 300} more lines)"
    return full_diff


def get_commits_summary(base_branch: str = "main") -> str:
    """Get list of commits between base and HEAD."""
    try:
        commits = run_git(["log", f"{base_branch}..HEAD", "--oneline", "--no-merges"])
        return commits if commits else "(no commits found)"
    except GitError:
        return "(could not determine commits)"


PR_PROMPT_TEMPLATE = """Generate a pull request description for the following changes.

## Diff:
{diff}

## Commits in this PR:
{commits}

## Branch: {branch}

## Instructions:
Write a comprehensive PR description with these sections:
1. **Summary** — What does this PR do? (1-2 sentences)
2. **Changes** — Bullet list of key changes
3. **Testing** — How was this tested?
4. **Screenshots** (if applicable) — Note if visual changes exist

Keep it concise and professional. Do NOT include the section headers in code blocks.\
Write in {language}."""


def generate_pr_description(
    base_branch: str = "main",
    language: str = "auto",
    hint: str = "",
) -> str:
    """Generate a pull request description."""
    diff = get_pr_diff(base_branch)
    commits = get_commits_summary(base_branch)
    branch = get_branch_name()

    prompt = PR_PROMPT_TEMPLATE.format(
        diff=diff,
        commits=commits,
        branch=branch,
        language="English" if language == "auto" else language,
    )

    if hint:
        prompt += f'\n\nAdditional context: "{hint}"'

    # Reuse the AI call infrastructure
    from .config import load_config

    config = load_config()
    if not config["api"]["key"]:
        raise AIError("No API key configured. Run `aicommit --config` to set up.")

    import time
    import httpx

    endpoint = config["api"]["endpoint"].rstrip("/")
    start_time = time.time()
    timeout = httpx.Timeout(90.0, connect=15.0)

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
                        {"role": "system", "content": "You are a professional software engineer writing clear, concise PR descriptions."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 1500,
                },
            )
            response.raise_for_status()
            data = response.json()

            if "choices" not in data or not data["choices"]:
                raise AIError("Empty response from AI provider")

            message = data["choices"][0]["message"]["content"].strip()

            elapsed_ms = (time.time() - start_time) * 1000

            # Show stats
            from .render import console
            usage = data.get("usage", {})
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
        raise AIError(f"Failed to generate PR description: {e}")
