"""PR description generator for aicommit."""

from .ai_client import AIError, call_ai
from .git_utils import (
    GitError,
    get_branch_name,
    get_repo_name,
    run_git,
)


def get_pr_diff(base_branch: str = "main") -> str:
    """Get diff between current branch and base branch for PR context."""
    try:
        stat = run_git(["diff", f"{base_branch}...HEAD", "--stat"])
        diff = run_git(["diff", f"{base_branch}...HEAD", "--unified=3"])
    except GitError:
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


PR_PROMPT = """Generate a pull request description for the following changes.

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

Keep it concise and professional. Write in {language}."""


def generate_pr_description(
    base_branch: str = "main",
    language: str = "auto",
    hint: str = "",
) -> str:
    """Generate a pull request description."""
    diff = get_pr_diff(base_branch)
    commits = get_commits_summary(base_branch)
    branch = get_branch_name()

    prompt = PR_PROMPT.format(
        diff=diff, commits=commits, branch=branch,
        language="English" if language == "auto" else language,
    )

    if hint:
        prompt += f'\n\nAdditional context: "{hint}"'

    result = call_ai(
        system_prompt="You are a professional software engineer writing clear, concise PR descriptions.",
        user_prompt=prompt,
        max_tokens=1500,
        temperature=0.4,
        timeout_sec=90.0,
    )

    from .render import console
    console.print(
        f"[dim]Model: {result['model']} | "
        f"Tokens: {result['prompt_tokens']}→{result['completion_tokens']} | "
        f"Time: {result['time_ms']:.0f}ms[/dim]"
    )
    return result["content"]
