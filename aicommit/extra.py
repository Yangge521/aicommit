"""Changelog and squash commit message generation."""

from .ai_client import AIError, call_ai
from .config import load_config
from .git_utils import GitError, get_recent_commits, run_git


# ── Squash message generation ─────────────────────────

SQUASH_PROMPT = """Generate a single, well-crafted commit message that summarizes all these commits:

## Recent Commits
{commits}

## Diff (all changes combined)
{diff}

## Instructions
Write a Single commit message that captures the essence of all these changes.
If it's a feature: use feat: prefix with scope if applicable.
If it's multiple fixes: use fix: with a summary.
If mixed: use the dominant change type.

{style_instruction}
Keep it under 72 characters for the subject line.
Write in {language}."""


def generate_squash_message(
    num_commits: int = 5,
    style: str = "conventional",
    language: str = "auto",
    hint: str = "",
) -> str:
    """Generate a single commit message summarizing the last N commits."""
    try:
        commit_msgs = get_recent_commits(num_commits)
    except GitError:
        raise GitError("Could not read commit history.")

    if not commit_msgs:
        raise GitError("No commits found.")

    try:
        diff = run_git(["diff", f"HEAD~{num_commits}..HEAD", "--unified=3"])
    except GitError:
        try:
            diff = run_git(["diff", "HEAD~1..HEAD", "--unified=3"])
            commit_msgs = get_recent_commits(1)
        except GitError:
            diff = "(unable to get diff for squash)"

    diff_lines = diff.split("\n")
    if len(diff_lines) > 300:
        diff = "\n".join(diff_lines[:300]) + f"\n... ({len(diff_lines)-300} more lines)"

    commits_text = "\n".join(f"  • {c}" for c in commit_msgs)

    style_map = {
        "conventional": "Use Conventional Commits format: type(scope): description",
        "emoji": "Use gitmoji convention: emoji description",
        "simple": "Keep it short and simple, one line",
        "detailed": "Include a subject line and bullet-point body",
    }

    prompt = SQUASH_PROMPT.format(
        commits=commits_text, diff=diff,
        style_instruction=style_map.get(style, style_map["conventional"]),
        language="English" if language == "auto" else language,
    )

    if hint:
        prompt += f'\n\nContext: "{hint}"'

    result = call_ai(
        system_prompt="You write clean, descriptive git commit messages.",
        user_prompt=prompt,
        max_tokens=500,
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


# ── Changelog generation ────────────────────────────

CHANGELOG_PROMPT = """Generate a changelog entry from these git commits.

## Repository: {repo}
## Version: {version}
## Commits:
{commits}

## Instructions
Write a markdown changelog entry following Keep a Changelog format (https://keepachangelog.com).
Group changes into: Added, Changed, Fixed, Removed, Deprecated, Security.
Each bullet should be a clear one-liner understandable by end users (not just commit messages).
If a category has no entries, skip it.

Write in {language}."""


def get_commits_since_tag(version: str = "") -> str:
    """Get formatted commit log since the last tag."""
    try:
        tags = run_git(["tag", "--sort=-creatordate"])
        tags_list = [t for t in tags.strip().split("\n") if t]

        if version and version in tags_list:
            # Commits since the specified tag
            commit_log = run_git(["log", f"{version}..HEAD", "--oneline", "--no-merges"])
        elif tags_list:
            # Commits since the most recent tag
            last_tag = tags_list[0]
            commit_log = run_git(["log", f"{last_tag}..HEAD", "--oneline", "--no-merges"])
        else:
            # No tags at all — fallback to last 30 commits
            commit_log = run_git(["log", "-30", "--oneline", "--no-merges"])
            if not commit_log.strip():
                return "(no commits found)"

        if not commit_log.strip():
            return "(no new commits since tag)"

        commits = commit_log.strip().split("\n")
        return "\n".join(f"  • {c}" for c in commits[:50])
    except GitError:
        return "(could not retrieve commits)"


def generate_changelog(
    version: str = "",
    language: str = "auto",
    hint: str = "",
) -> str:
    """Generate a changelog entry from commits."""
    from .git_utils import get_repo_name

    repo = get_repo_name()
    commits_text = get_commits_since_tag(version)
    ver = version or "next"

    prompt = CHANGELOG_PROMPT.format(
        repo=repo, version=ver, commits=commits_text,
        language="English" if language == "auto" else language,
    )

    if hint:
        prompt += f'\n\nFocus on: "{hint}"'

    result = call_ai(
        system_prompt="You write professional changelogs following Keep a Changelog format.",
        user_prompt=prompt,
        max_tokens=1500,
        temperature=0.5,
        timeout_sec=90.0,
    )

    from .render import console
    console.print(
        f"[dim]Model: {result['model']} | "
        f"Tokens: {result['prompt_tokens']}→{result['completion_tokens']} | "
        f"Time: {result['time_ms']:.0f}ms[/dim]"
    )
    return result["content"]
