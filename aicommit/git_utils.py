"""Git operations for aicommit."""

import subprocess
from pathlib import Path
from typing import Optional


class GitError(Exception):
    """Raised when git operations fail."""
    pass


def run_git(args: list[str], cwd: Optional[Path] = None) -> str:
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


def is_git_repo(path: Optional[Path] = None) -> bool:
    """Check if path is inside a git repository."""
    try:
        run_git(["rev-parse", "--git-dir"], cwd=path)
        return True
    except GitError:
        return False


def get_staged_diff(max_lines: int = 200) -> str:
    """Get the git diff of staged changes, truncated."""
    try:
        # Get diffstat first for summary
        stat = run_git(["diff", "--cached", "--stat"])
        # Get actual diff
        diff = run_git(["diff", "--cached", "--unified=3"])
    except GitError:
        raise GitError("No staged changes found. Use `git add` first.")

    # Build full diff with stat header
    full_diff = stat + "\n\n" + diff

    # Truncate if too long
    lines = full_diff.split("\n")
    if len(lines) > max_lines:
        full_diff = "\n".join(lines[:max_lines])
        full_diff += f"\n\n... (truncated, {len(lines) - max_lines} more lines)"
    return full_diff


def get_staged_files() -> list[str]:
    """Get list of staged files."""
    result = run_git(["diff", "--cached", "--name-only"])
    return [f for f in result.split("\n") if f]


def get_staged_stats() -> str:
    """Get detailed stats of staged changes."""
    return run_git(["diff", "--cached", "--stat"])


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
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name
    except GitError:
        return Path.cwd().name


def has_staged_changes() -> bool:
    """Check if there are staged changes."""
    try:
        run_git(["diff", "--cached", "--quiet"])
        return False  # Exit 0 means no changes
    except GitError:
        return True  # Exit 1 means there are changes


def detect_scope(files: list[str]) -> Optional[str]:
    """Auto-detect commit scope from changed file paths.

    e.g., src/auth/login.ts + src/auth/logout.ts → 'auth'
          docs/api.md → 'docs'
          package.json + yarn.lock → None (too broad)
    """
    if not files:
        return None

    # Extract top-level or common directory patterns
    dirs = []
    for f in files:
        parts = Path(f).parts
        if len(parts) >= 2:
            # Skip common root dirs like src/, lib/, app/
            skip_dirs = {"src", "lib", "app", "packages", "internal", "pkg", "cmd"}
            for p in parts[:-1]:
                if p.lower() not in skip_dirs and not p.startswith("."):
                    dirs.append(p.lower())
                    break
            else:
                dirs.append(parts[0].lower())

    if not dirs:
        return None

    # Find most common directory
    from collections import Counter
    counter = Counter(dirs)
    most_common = counter.most_common(1)[0]

    # Only suggest scope if it appears in >50% of files (or at least 2 files)
    if most_common[1] >= 2 or most_common[1] / len(files) > 0.5:
        return most_common[0]
    return None


def detect_breaking_changes(diff: str) -> bool:
    """Detect if diff contains potential breaking changes."""
    breaking_keywords = [
        "breaking change",
        "BREAKING CHANGE",
        "breaking-change",
        "deprecated",
        "DEPRECATED",
        "remove deprecat",
        "backward incompat",
        "backwards incompat",
        "api break",
        "API break",
        "interface change",
        "signature change",
    ]
    diff_lower = diff.lower()
    return any(kw.lower() in diff_lower for kw in breaking_keywords)


def infer_type_from_branch(branch: str) -> Optional[str]:
    """Infer commit type from branch name convention.

    feat/xxx → feat
    fix/xxx → fix
    chore/xxx → chore
    docs/xxx → docs
    refactor/xxx → refactor
    """
    branch_lower = branch.lower()
    type_prefixes = {
        "feat/": "feat",
        "feature/": "feat",
        "fix/": "fix",
        "bugfix/": "fix",
        "hotfix/": "fix",
        "chore/": "chore",
        "docs/": "docs",
        "refactor/": "refactor",
        "perf/": "perf",
        "test/": "test",
        "ci/": "ci",
        "revert/": "revert",
        "style/": "style",
    }
    for prefix, ctype in type_prefixes.items():
        if branch_lower.startswith(prefix):
            return ctype
    return None


def commit(message: str) -> bool:
    """Create a commit with the given message."""
    try:
        run_git(["commit", "-m", message])
        return True
    except GitError as e:
        raise GitError(f"Commit failed: {e}")


def install_hook() -> str:
    """Install aicommit as a prepare-commit-msg hook."""
    git_dir = run_git(["rev-parse", "--git-dir"])
    hook_path = Path(git_dir) / "hooks" / "prepare-commit-msg"

    if hook_path.exists():
        # Check if it's already our hook
        content = hook_path.read_text(encoding="utf-8")
        if "aicommit" in content:
            raise GitError("aicommit hook is already installed.")
        raise GitError(
            f"A prepare-commit-msg hook already exists at {hook_path}.\n"
            "Remove it first or manually add `aicommit --hook \"$1\"` to it."
        )

    hook_script = f'''#!/bin/sh
# Generated by aicommit — AI-powered commit messages
# This hook runs before the commit message editor opens.
# It generates an AI suggestion in the commit message buffer.

COMMIT_MSG_FILE="$1"
COMMIT_SOURCE="$2"

# Only run for new commits, not merges/amends/squashes
case "$COMMIT_SOURCE" in
    message|template|commit) ;;
    merge|squash) exit 0 ;;
    *) exit 0 ;;
esac

# Check if there are staged changes
if ! git diff --cached --quiet 2>/dev/null; then
    # Has staged changes — run aicommit
    aicommit --hook "$COMMIT_MSG_FILE" 2>/dev/null
fi

exit 0
'''

    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(hook_script, encoding="utf-8")
    # Make executable on Unix
    try:
        hook_path.chmod(0o755)
    except Exception:
        pass

    return str(hook_path)


def uninstall_hook() -> str:
    """Remove the aicommit prepare-commit-msg hook."""
    git_dir = run_git(["rev-parse", "--git-dir"])
    hook_path = Path(git_dir) / "hooks" / "prepare-commit-msg"

    if not hook_path.exists():
        raise GitError("No prepare-commit-msg hook found.")

    content = hook_path.read_text(encoding="utf-8")
    if "aicommit" not in content:
        raise GitError("The existing hook is not an aicommit hook.")

    hook_path.unlink()
    return str(hook_path)
