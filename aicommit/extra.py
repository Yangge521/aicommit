"""Changelog and squash commit message generation."""

import time

import httpx

from .ai import AIError
from .config import load_config
from .git_utils import GitError, get_branch_name, get_recent_commits, run_git

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
    config = load_config()
    if not config["api"]["key"]:
        raise AIError("No API key configured.")

    # Get commits
    try:
        commit_msgs = get_recent_commits(num_commits)
    except GitError:
        raise GitError("Could not read commit history.")

    if not commit_msgs:
        raise GitError("No commits found.")

    # Get combined diff
    try:
        diff = run_git(["diff", f"HEAD~{num_commits}..HEAD", "--unified=3"])
    except GitError:
        # Try with fewer commits
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
        commits=commits_text,
        diff=diff,
        style_instruction=style_map.get(style, style_map["conventional"]),
        language="English" if language == "auto" else language,
    )

    if hint:
        prompt += f'\n\nContext: "{hint}"'

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
                        {"role": "system", "content": "You write clean, descriptive git commit messages."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 500,
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
        raise AIError(f"API error ({e.response.status_code})")
    except Exception as e:
        raise AIError(f"Squash generation failed: {e}")


# ── Changelog generation ────────────────────────────


CHANGELOG_PROMPT = """Generate a changelog entry from these git commits.

## Repository: {repo}
## Version: {version}
## Commits since last release:
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
        # Get last tag
        last_tag = ""
        if not version:
            tags = run_git(["tag", "--sort=-creatordate"])
            if tags:
                last_tag = tags.split("\n")[0].strip()
        else:
            last_tag = version

        commits = get_recent_commits(30)
        return "\n".join(f"  • {c}" for c in commits)
    except GitError:
        return "(could not retrieve commits)"


def generate_changelog(
    version: str = "",
    language: str = "auto",
    hint: str = "",
) -> str:
    """Generate a changelog entry from commits."""
    config = load_config()
    if not config["api"]["key"]:
        raise AIError("No API key configured.")

    from .git_utils import get_repo_name

    repo = get_repo_name()
    commits_text = get_commits_since_tag(version)
    ver = version or "next"

    prompt = CHANGELOG_PROMPT.format(
        repo=repo,
        version=ver,
        commits=commits_text,
        language="English" if language == "auto" else language,
    )

    if hint:
        prompt += f'\n\nFocus on: "{hint}"'

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
                        {"role": "system", "content": "You write professional changelogs following Keep a Changelog format."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.5,
                    "max_tokens": 1500,
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
        raise AIError(f"API error ({e.response.status_code})")
    except Exception as e:
        raise AIError(f"Changelog generation failed: {e}")
