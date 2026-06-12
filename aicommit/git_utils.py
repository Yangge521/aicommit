"""Git operations for aicommit."""

import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when git operations fail."""
    pass


def run_git(args: list[str], cwd: Path | None = None) -> str:
    """Run a git command and return stdout."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise GitError(result.stderr.strip())
        return result.stdout.strip()
    except FileNotFoundError:
        raise GitError("Git is not installed or not in PATH")


def is_git_repo(path: Path | None = None) -> bool:
    """Check if path is inside a git repository."""
    try:
        run_git(["rev-parse", "--git-dir"], cwd=path)
        return True
    except GitError:
        return False


def get_staged_diff(max_lines: int = 200) -> str:
    """Get the git diff of staged changes, truncated."""
    try:
        diff = run_git(["diff", "--cached", "--stat"])
        diff += "\n\n"
        diff += run_git(["diff", "--cached"])
    except GitError:
        raise GitError("No staged changes found. Use `git add` first.")

    # Truncate if too long
    lines = diff.split("\n")
    if len(lines) > max_lines:
        diff = "\n".join(lines[:max_lines])
        diff += f"\n... (truncated, {len(lines) - max_lines} more lines)"
    return diff


def get_staged_files() -> list[str]:
    """Get list of staged files."""
    return run_git(["diff", "--cached", "--name-only"]).split("\n")


def get_branch_name() -> str:
    """Get current branch name."""
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"])


def get_recent_commits(count: int = 5) -> list[str]:
    """Get recent commit messages for context."""
    try:
        messages = run_git(["log", f"-{count}", "--format=%s"])
        return [m for m in messages.split("\n") if m]
    except GitError:
        return []


def get_repo_name() -> str:
    """Get repository name from remote or directory."""
    try:
        url = run_git(["remote", "get-url", "origin"])
        # Extract repo name from URL
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name
    except GitError:
        return Path.cwd().name


def has_staged_changes() -> bool:
    """Check if there are staged changes."""
    try:
        result = run_git(["diff", "--cached", "--quiet"])
        return False  # Exit 0 means no changes
    except GitError:
        return True  # Exit 1 means there are changes


def commit(message: str) -> bool:
    """Create a commit with the given message."""
    try:
        run_git(["commit", "-m", message])
        return True
    except GitError as e:
        raise GitError(f"Commit failed: {e}")
