"""Git operations for aicommit."""

import platform
import subprocess
from collections import Counter
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
            creationflags=0x08000000 if platform.system() == "Windows" else 0,
        )
        if result.returncode != 0:
            raise GitError(result.stderr.strip() or result.stdout.strip())
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


_NOISE_PATTERNS = [
    ".lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Gemfile.lock", "Cargo.lock", "composer.lock",
    ".min.js", ".min.css", ".map", ".pyc", ".pyo",
    ".sum", "go.sum", ".mod",
    "dist/", "build/", ".next/", "node_modules/",
    ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff",
    ".generated.", "autogen", ".pb.go", ".pb.cc",
]


def is_noise_file(filepath: str) -> bool:
    """Check if a file is likely noise (lockfiles, generated, binaries)."""
    lower = filepath.lower()
    for pat in _NOISE_PATTERNS:
        if pat in lower:
            return True
    return False


def get_staged_diff(max_lines: int = 200, skip_noise: bool = True) -> str:
    """Get the git diff of staged changes, with smart filtering and truncation.

    Args:
        max_lines: Maximum lines of diff to return (truncates smartly)
        skip_noise: If True, skip lockfiles, generated files, etc.
    """
    all_files = get_staged_files()

    if skip_noise:
        meaningful = [f for f in all_files if not is_noise_file(f)]
    else:
        meaningful = list(all_files)

    if not meaningful:
        # All files are noise — fall back to all files
        meaningful = list(all_files)

    # Get diff stat for meaningful files only
    stat = run_git(["diff", "--cached", "--stat", "--"] + meaningful)

    # Get actual diff
    diff = run_git(["diff", "--cached", "--unified=3", "--"] + meaningful)

    # Check diff size and warn if very large
    total_lines = diff.count("\n")
    if total_lines > 500:
        # For very large diffs, only keep the stat + first 200 lines of diff
        # to give AI enough context without overwhelming
        diff = "\n".join(diff.split("\n")[:200])
        diff += f"\n\n... ({total_lines - 200} more diff lines truncated for brevity)"

    # Build full diff with stat header
    full_diff = stat + "\n\n" + diff

    # Final truncation safety net
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
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
            creationflags=0x08000000 if platform.system() == "Windows" else 0,
        )
        return result.returncode != 0
    except FileNotFoundError:
        raise GitError("Git is not installed or not in PATH")


def get_last_commit_diff(max_lines: int = 200) -> str:
    """Get the diff of the most recent commit (for --last mode)."""
    try:
        stat = run_git(["show", "--stat", "HEAD"])
        diff = run_git(["show", "--unified=3", "HEAD"])
    except GitError:
        raise GitError("No previous commit found. This is the initial commit.")

    full_diff = stat + "\n\n" + diff
    lines = full_diff.split("\n")
    if len(lines) > max_lines:
        full_diff = "\n".join(lines[:max_lines])
        full_diff += f"\n\n... (truncated, {len(lines) - max_lines} more lines)"
    return full_diff


def get_last_commit_message() -> str:
    """Get the most recent commit message."""
    return run_git(["log", "-1", "--format=%B"])


def detect_scope(files: list[str]) -> Optional[str]:
    """Auto-detect commit scope from changed file paths.

    e.g., src/auth/login.ts + src/auth/logout.ts → 'auth'
          docs/api.md → 'docs'
          package.json + yarn.lock → None (too broad)
    """
    if not files:
        return None

    # Filter noise files for scope detection
    meaningful = [f for f in files if not is_noise_file(f)]
    if not meaningful:
        meaningful = files

    dirs = []
    for f in meaningful:
        parts = Path(f).parts
        if len(parts) >= 2:
            skip_dirs = {"src", "lib", "app", "packages", "internal", "pkg", "cmd"}
            for p in parts[:-1]:
                if p.lower() not in skip_dirs and not p.startswith("."):
                    dirs.append(p.lower())
                    break
            else:
                dirs.append(parts[0].lower())
        else:
            # Single file at root
            stem = Path(f).stem.lower()
            if stem not in ("readme", "license", "changelog"):
                dirs.append(stem)

    if not dirs:
        return None

    counter = Counter(dirs)
    most_common = counter.most_common(1)[0]

    if most_common[1] >= 2 and most_common[1] / len(dirs) > 0.5:
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

    feat/xxx → feat, fix/xxx → fix, chore/xxx → chore, etc.
    """
    branch_lower = branch.lower()
    type_prefixes = {
        "feat/": "feat", "feature/": "feat",
        "fix/": "fix", "bugfix/": "fix", "hotfix/": "fix",
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


def commit(message: str, signoff: bool = False, no_verify: bool = False) -> bool:
    """Create a commit with the given message."""
    try:
        args = ["commit", "-m", message]
        if signoff:
            args.insert(1, "--signoff")
        if no_verify:
            args.insert(1, "--no-verify")
        run_git(args)
        return True
    except GitError as e:
        raise GitError(f"Commit failed: {e}")


def amend_commit(message: str, signoff: bool = False, no_verify: bool = False) -> bool:
    """Amend the last commit with a new message."""
    try:
        args = ["commit", "--amend", "-m", message]
        if signoff:
            args.insert(1, "--signoff")
        if no_verify:
            args.insert(1, "--no-verify")
        run_git(args)
        return True
    except GitError as e:
        raise GitError(f"Amend failed: {e}")


def install_hook() -> str:
    """Install aicommit as a prepare-commit-msg hook.
    Creates a shell script on Unix, batch file on Windows.
    """
    git_dir = run_git(["rev-parse", "--git-dir"])
    hook_path = Path(git_dir) / "hooks" / "prepare-commit-msg"

    if hook_path.exists():
        content = hook_path.read_text(encoding="utf-8")
        if "aicommit" in content:
            raise GitError("aicommit hook is already installed.")
        raise GitError(
            f"A prepare-commit-msg hook already exists at {hook_path}.\n"
            f'Remove it first or manually add `aicommit --hook "%1"` to it.'
        )

    hook_path.parent.mkdir(parents=True, exist_ok=True)

    if platform.system() == "Windows":
        hook_script = _windows_hook_script()
    else:
        hook_script = _unix_hook_script()

    hook_path.write_text(hook_script, encoding="utf-8")
    try:
        hook_path.chmod(0o755)
    except Exception:
        pass

    return str(hook_path)


def _unix_hook_script() -> str:
    """Generate Unix shell hook script."""
    return """#!/bin/sh
# Generated by aicommit — AI-powered commit messages
COMMIT_MSG_FILE="$1"
COMMIT_SOURCE="$2"

case "$COMMIT_SOURCE" in
    message|template|commit) ;;
    merge|squash) exit 0 ;;
    *) exit 0 ;;
esac

if ! git diff --cached --quiet 2>/dev/null; then
    aicommit --hook "$COMMIT_MSG_FILE" 2>/dev/null
fi
exit 0
"""


def _windows_hook_script() -> str:
    """Generate Windows batch hook script."""
    return """@echo off
REM Generated by aicommit — AI-powered commit messages
set COMMIT_MSG_FILE=%1
set COMMIT_SOURCE=%2

if "%COMMIT_SOURCE%"=="message" goto :run
if "%COMMIT_SOURCE%"=="template" goto :run
if "%COMMIT_SOURCE%"=="commit" goto :run
exit /b 0

:run
git diff --cached --quiet 2>nul
if errorlevel 1 (
    aicommit --hook "%COMMIT_MSG_FILE%" 2>nul
)
exit /b 0
"""


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
