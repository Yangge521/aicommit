"""CLI entry point for aicommit."""

import sys

import click

from .ai import AIError, generate_commit_message
from .config import load_config, save_config, setup_wizard
from .git_utils import (
    GitError,
    commit,
    get_branch_name,
    get_recent_commits,
    get_repo_name,
    get_staged_diff,
    get_staged_files,
    has_staged_changes,
    is_git_repo,
)
from .render import (
    confirm_commit,
    console,
    show_config_status,
    show_diff_summary,
    show_dry_run,
    show_generating,
    show_message_preview,
    show_success,
    show_welcome,
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
@click.version_option(version="1.0.0", prog_name="aicommit")
def main(style, auto_yes, dry_run, message, run_config, status):
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
      aicommit --config           # Setup API key and preferences
    """
    # Config mode
    if run_config:
        config = setup_wizard()
        show_config_status(config)
        return

    # Status mode
    if status:
        config = load_config()
        show_config_status(config)
        return

    # Validate environment
    if not is_git_repo():
        console.print("[red]✗ Not a git repository. Run this inside a git repo.[/red]")
        sys.exit(1)

    if not has_staged_changes():
        console.print("[yellow]ℹ No staged changes. Use `git add` first.[/yellow]")
        sys.exit(0)

    # Load config, setup if first time
    config = load_config()
    if not config["api"]["key"] and not run_config:
        console.print("[yellow]⚠ First time? Let's set up your AI provider.[/yellow]")
        config = setup_wizard()
        if not config["api"]["key"]:
            console.print("[red]✗ API key required. Run `aicommit --config` to set up.[/red]")
            sys.exit(1)

    # Determine style
    commit_style = style or config["commit"]["style"]
    max_diff = config["commit"]["max_diff_lines"]
    language = config["commit"]["language"]

    try:
        # Gather git context
        repo = get_repo_name()
        branch = get_branch_name()
        files = get_staged_files()
        diff = get_staged_diff(max_lines=max_diff)
        recent = get_recent_commits(5)

        show_diff_summary(files, len(diff))
        console.print(f"[dim]Repo: {repo} | Branch: {branch} | Style: {commit_style}[/dim]")

        # Generate message with animation
        with show_generating() as progress:
            task = progress.add_task("", total=None)
            commit_msg = generate_commit_message(
                diff=diff,
                style=commit_style,
                language=language,
                recent_commits=recent,
                hint=message,
            )
            progress.remove_task(task)

        # Show preview
        show_message_preview(commit_msg, commit_style)

        # Dry run
        if dry_run:
            show_dry_run(commit_msg)
            return

        # Confirm and commit
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


if __name__ == "__main__":
    main()
