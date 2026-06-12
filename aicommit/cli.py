"""CLI entry point for aicommit."""

import sys
from pathlib import Path

import click

from .ai import AIError, generate_commit_message
from .config import load_config, save_config, setup_wizard
from .git_utils import (
    GitError,
    commit,
    detect_breaking_changes,
    detect_scope,
    get_branch_name,
    get_recent_commits,
    get_repo_name,
    get_staged_diff,
    get_staged_files,
    get_staged_stats,
    has_staged_changes,
    infer_type_from_branch,
    install_hook,
    is_git_repo,
    uninstall_hook,
)
from .render import (
    confirm_commit,
    console,
    show_config_status,
    show_diff_summary,
    show_dry_run,
    show_generating,
    show_hook_installed,
    show_hook_uninstalled,
    show_message_preview,
    show_stats,
    show_success,
)


@click.command()
@click.option(
    "-s", "--style",
    type=click.Choice(["conventional", "emoji", "simple", "detailed"]),
    help="Commit message style",
)
@click.option(
    "-y", "--yes", "auto_yes",
    is_flag=True,
    help="Skip confirmation and commit immediately",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show generated message without committing",
)
@click.option(
    "-m", "--message",
    help="Additional context/hint for the AI",
)
@click.option(
    "-e", "--edit",
    is_flag=True,
    help="Open generated message in $EDITOR before committing",
)
@click.option(
    "--config",
    "run_config",
    is_flag=True,
    help="Open configuration wizard",
)
@click.option(
    "--status",
    is_flag=True,
    help="Show current configuration",
)
@click.option(
    "--hook",
    "hook_file",
    default=None,
    help="Internal: used by git prepare-commit-msg hook",
    hidden=True,
)
@click.option(
    "--install-hook",
    is_flag=True,
    help="Install as git prepare-commit-msg hook",
)
@click.option(
    "--uninstall-hook",
    is_flag=True,
    help="Remove aicommit git hook",
)
@click.version_option(version="1.1.0", prog_name="aicommit")
def main(style, auto_yes, dry_run, message, edit, run_config, status,
         hook_file, install_hook_flag, uninstall_hook_flag):
    """AI-powered git commit message generator.

    Run `aicommit` in any git repo with staged changes.
    The AI will analyze your diff and generate a meaningful commit message.

    \b
    Examples:
      aicommit                    # Generate and commit with confirmation
      aicommit -y                 # Skip confirmation
      aicommit -s emoji           # Use emoji style
      aicommit --dry-run          # Preview without committing
      aicommit -m "urgent fix"    # Provide context hint
      aicommit -e                 # Edit message before committing
      aicommit --config           # Setup API key and preferences
      aicommit --install-hook     # Install as git hook
    """
    # ── Hook mode ──────────────────────────────────────────
    if hook_file:
        _run_hook_mode(hook_file)
        return

    # ── Install/Uninstall hook ─────────────────────────────
    if install_hook_flag:
        try:
            path = install_hook()
            show_hook_installed(path)
        except GitError as e:
            console.print(f"[red]✗ {e}[/red]")
            sys.exit(1)
        return

    if uninstall_hook_flag:
        try:
            path = uninstall_hook()
            show_hook_uninstalled(path)
        except GitError as e:
            console.print(f"[red]✗ {e}[/red]")
            sys.exit(1)
        return

    # ── Config mode ────────────────────────────────────────
    if run_config:
        config = setup_wizard()
        show_config_status(config)
        return

    # ── Status mode ────────────────────────────────────────
    if status:
        config = load_config()
        show_config_status(config)
        return

    # ── Validate environment ───────────────────────────────
    if not is_git_repo():
        console.print("[red]✗ Not a git repository. Run this inside a git repo.[/red]")
        sys.exit(1)

    if not has_staged_changes():
        console.print("[yellow]ℹ No staged changes. Use `git add` first.[/yellow]")
        sys.exit(0)

    # ── Load config ────────────────────────────────────────
    config = load_config()
    if not config["api"]["key"] and not run_config:
        console.print("[yellow]⚠ First time? Let's set up your AI provider.[/yellow]")
        config = setup_wizard()
        if not config["api"]["key"]:
            console.print("[red]✗ API key required. Run `aicommit --config` to set up.[/red]")
            sys.exit(1)

    # ── Gather git context ─────────────────────────────────
    try:
        repo = get_repo_name()
        branch = get_branch_name()
        files = get_staged_files()
        diff = get_staged_diff(max_lines=config["commit"]["max_diff_lines"])
        stats = get_staged_stats()
        recent = get_recent_commits(5)

        # Smart analysis
        scope = detect_scope(files)
        branch_type = infer_type_from_branch(branch)
        breaking = detect_breaking_changes(diff)

        # Build hints for AI
        branch_hint = ""
        if branch_type:
            branch_hint = f"Branch name '{branch}' suggests this is a '{branch_type}' type change."
            # If branch type conflicts with scope, note it
            if scope and branch_type in ("docs", "test", "ci"):
                branch_hint += f" Scope: {scope}"

        breaking_hint = ""
        if breaking:
            breaking_hint = (
                "⚠ This diff contains breaking changes! "
                "Use '!' after type/scope (e.g., feat(api)!: ...) "
                "and add BREAKING CHANGE: footer if using conventional style."
            )

        file_list = "\n".join(f"  - {f}" for f in files[:30])
        if len(files) > 30:
            file_list += f"\n  ... and {len(files) - 30} more files"

        # Show summary
        show_diff_summary(files, stats, scope=scope or "",
                          branch_type=branch_type or "",
                          breaking=breaking)
        console.print(f"[dim]Repo: {repo} | Branch: {branch}[/dim]")

        # Determine style
        commit_style = style or config["commit"]["style"]
        language = config["commit"]["language"]

        # ── Generate message ────────────────────────────────
        with show_generating() as progress:
            task = progress.add_task("", total=None)
            result = generate_commit_message(
                diff=diff,
                style=commit_style,
                language=language,
                recent_commits=recent,
                hint=message,
                branch_hint=branch_hint,
                breaking_hint=breaking_hint,
                file_list=file_list,
            )
            progress.remove_task(task)

        # ── Show result ─────────────────────────────────────
        show_message_preview(result.message, commit_style, scope=scope or "")
        show_stats(result.tokens_in, result.tokens_out, result.time_ms, result.model)

        # ── Edit mode ───────────────────────────────────────
        commit_msg = result.message
        if edit:
            edited = click.edit(commit_msg)
            if edited is not None:
                commit_msg = edited.strip()
                if not commit_msg:
                    console.print("[yellow]Message was empty, commit cancelled.[/yellow]")
                    return

        # ── Dry run ─────────────────────────────────────────
        if dry_run:
            show_dry_run(commit_msg)
            return

        # ── Confirm and commit ──────────────────────────────
        if auto_yes or config["commit"]["auto_confirm"] or confirm_commit(commit_msg):
            commit(commit_msg)
            show_success(commit_msg)
        else:
            console.print("\n[yellow]Commit cancelled.[/yellow]")

    except GitError as e:
        console.print(f"[red]✗ Git error: {e}[/red]")
        sys.exit(1)
    except AIError as e:
        console.print(f"[red]✗ AI error: {e}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user.[/yellow]")
        sys.exit(0)


def _run_hook_mode(commit_msg_file: str):
    """Run in git hook mode — write AI message to commit msg file."""
    try:
        if not has_staged_changes():
            return  # Nothing to do

        config = load_config()
        if not config["api"]["key"]:
            return  # Not configured yet

        files = get_staged_files()
        diff = get_staged_diff(max_lines=config["commit"]["max_diff_lines"])
        recent = get_recent_commits(3)
        branch = get_branch_name()
        scope = detect_scope(files)
        branch_type = infer_type_from_branch(branch)
        breaking = detect_breaking_changes(diff)

        branch_hint = ""
        if branch_type:
            branch_hint = f"Branch '{branch}' suggests '{branch_type}' type."

        breaking_hint = ""
        if breaking:
            breaking_hint = "⚠ Contains breaking changes."

        file_list = "\n".join(f"  - {f}" for f in files[:20])

        result = generate_commit_message(
            diff=diff,
            style=config["commit"]["style"],
            language=config["commit"]["language"],
            recent_commits=recent,
            branch_hint=branch_hint,
            breaking_hint=breaking_hint,
            file_list=file_list,
        )

        # Write suggestion to commit message file
        msg_path = Path(commit_msg_file)
        current = msg_path.read_text(encoding="utf-8") if msg_path.exists() else ""

        if current.strip():
            # Don't overwrite existing message
            return

        msg_path.write_text(result.message + "\n", encoding="utf-8")

    except Exception:
        # Hook should never block a commit
        pass


if __name__ == "__main__":
    main()
