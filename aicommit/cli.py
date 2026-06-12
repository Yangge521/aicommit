"""Command-line interface for aicommit."""

import os
import platform
import subprocess as sp
import sys
import tempfile
from pathlib import Path

import click
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .__init__ import __version__
from .ai import AIError as AIErr, AIResult, generate_commit_message
from .config import (
    CONFIG_FILE,
    TEMPLATE_VARIABLES,
    delete_message_template,
    get_config_value,
    get_message_template,
    list_message_templates,
    load_config,
    load_history,
    reset_config,
    save_config,
    save_history,
    save_message_template,
    set_config_value,
    setup_wizard,
)
from .conventional import auto_fix_conventional, validate_conventional
from .extra import generate_changelog, generate_squash_message
from .git_utils import (
    GitError as GitErr,
    detect_breaking_changes,
    detect_monorepo_package,
    detect_scope,
    get_branch_name,
    get_last_commit_message,
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
from .pr_generator import generate_pr_description
from .render import console, show_diff_summary, show_generating


# ── Main CLI ──────────────────────────────────────────

@click.command()
@click.version_option(__version__, "--version", "-V", message="aicommit v%(version)s")
@click.option("--style", "-s", default=None,
              type=click.Choice(["conventional", "emoji", "simple", "detailed"]),
              help="Commit message style")
@click.option("--message", "-m", "hint", default=None, help="Additional context for the AI")
@click.option("--dry-run", "-d", is_flag=True, help="Preview message without committing")
@click.option("--yes", "-y", "auto_yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--edit", "-e", is_flag=True, help="Open generated message in editor before committing")
@click.option("--scope", default=None, help="Override detected scope")
@click.option("--signoff", is_flag=True, help="Add Signed-off-by trailer")
@click.option("--no-verify", is_flag=True, help="Bypass pre-commit and commit-msg hooks")
@click.option("--last", is_flag=True, help="Generate message for last commit (useful with --amend)")
@click.option("--amend", is_flag=True, help="Amend the last commit with generated message")
@click.option("--template", "-t", "template_file", default=None, help="Custom prompt template file")
@click.option("--stage", "-a", "auto_stage", is_flag=True, help="Auto-stage all modified files before commit")
@click.option("--co-author", "co_author", multiple=True, default=None, help="Add Co-authored-by trailer (repeatable)")
@click.option("--issue", "issue_ref", default=None, help="Link to issue (e.g. #42 or JIRA-123)")
@click.option("--choose", "-c", "choose_mode", is_flag=True, help="Generate 3 options and pick one interactively")
@click.option("--init", "init_mode", is_flag=True, help="One-command setup: configure git + AI provider")
@click.option("--config", "config_mode", is_flag=True, help="Show current configuration")
@click.option("--set", "-S", "set_config", default=None, metavar="KEY=VALUE", 
              help="Set config value (e.g. --set api.model=gpt-4)")
@click.option("--get", "-G", "get_config", default=None, metavar="KEY",
              help="Get config value (e.g. --get api.model)")
@click.option("--diff", "show_diff", is_flag=True, help="Preview staged diff before generating")
@click.option("--stats", "show_stats", is_flag=True, help="Show usage statistics dashboard")
@click.option("--temperature", type=float, default=None, help="Override AI temperature (0.0-1.0)")
@click.option("--max-tokens", type=int, default=None, help="Max tokens for AI response")
@click.option("--provider", "provider_override", default=None,
              type=click.Choice(["openai", "anthropic", "ollama", "deepseek"]),
              help="Override AI provider for this run")
@click.option("--reset-config", is_flag=True, help="Reset config to defaults")
@click.option("--install-hook", is_flag=True, help="Install aicommit as git prepare-commit-msg hook")
@click.option("--uninstall-hook", is_flag=True, help="Remove aicommit git hook")
@click.option("--review", is_flag=True, help="AI code review of staged changes")
@click.option("--severity", default="all",
              type=click.Choice(["all", "high", "medium", "low"]),
              help="Filter review results by severity")
@click.option("--pr", "generate_pr", is_flag=True, help="Generate pull request description")
@click.option("--pr-base", default="main", help="Base branch for PR diff")
@click.option("--squash", "squash_n", type=int, default=None, metavar="N",
              help="Generate squash message from last N commits")
@click.option("--changelog", is_flag=True, help="Generate changelog from commit history")
@click.option("--version-tag", default=None, help="Version tag for changelog")
@click.option("--validate", is_flag=True, help="Validate last commit follows conventional format")
@click.option("--auto-fix", is_flag=True, help="Auto-fix last commit to follow conventional format")
@click.option("--completion", "shell", default=None,
              type=click.Choice(["bash", "zsh", "fish", "powershell"]),
              help="Generate shell completion script")
@click.option("--copy", is_flag=True, help="Copy generated message to clipboard")
@click.option("--log", "show_log", is_flag=True, help="Show recent aicommit message history")
@click.option("--log-repo", default=None, help="Filter log by repository name")
@click.option("--log-style", default=None,
              type=click.Choice(["conventional", "emoji", "simple", "detailed"]),
              help="Filter log by commit style")
@click.option("--output", "-o", "output_file", default=None, help="Save generated message to a file")
@click.option("--hook", "hook_file", default=None, hidden=True, help="Internal: used by git hook")
@click.option("--msg-template", "msg_template_name", default=None, help="Apply a named message template to format output")
@click.option("--msg-template-save", "msg_template_save", default=None, metavar="NAME=FORMAT",
              help='Save a message template (e.g. --msg-template-save myfmt="{type}({scope}): {description}")')
@click.option("--msg-template-list", "msg_template_list", is_flag=True, help="List saved message templates")
@click.option("--msg-template-delete", "msg_template_delete", default=None, metavar="NAME",
              help="Delete a saved message template")
@click.option("--editor-cmd", "editor_cmd_override", default=None, metavar="EDITOR",
              help="Editor command to use with -e (e.g. --editor-cmd vim)")
def main(
    style, hint, dry_run, auto_yes, edit, scope, signoff, no_verify,
    last, amend, template_file, auto_stage, co_author, issue_ref, choose_mode,
    init_mode, config_mode, set_config, get_config, show_diff, show_stats,
    temperature, max_tokens, provider_override,
    reset_config_flag,
    install_hook_flag, uninstall_hook_flag,
    review, severity, generate_pr, pr_base,
    squash_n, changelog, version_tag,
    validate, auto_fix,
    shell, copy, show_log, log_repo, log_style, output_file, hook_file,
    msg_template_name, msg_template_save, msg_template_list, msg_template_delete,
    editor_cmd_override,
):
    """AI-powered git commit message generator.

    Stage your changes with `git add`, then run `aicommit` to generate the
    perfect commit message.
    """

    # ── Meta commands (no git repo required) ──────────
    if set_config:
        if "=" not in set_config:
            console.print("[red]✗ Use format: --set KEY=VALUE (e.g., --set api.model=gpt-4)[/red]")
            return
        k, v = set_config.split("=", 1)
        try:
            set_config_value(k.strip(), v.strip())
            console.print(f"[green]✓ Set {k.strip()} = {v.strip()}[/green]")
        except ValueError as e:
            console.print(f"[red]✗ {e}[/red]")
        return
    if get_config:
        try:
            val = get_config_value(get_config.strip())
            console.print(f"[cyan]{get_config.strip()}[/cyan] = [bold]{val}[/bold]")
        except ValueError as e:
            console.print(f"[red]✗ {e}[/red]")
        return
    if reset_config_flag:
        reset_config()
        console.print("[green]✓ Config reset to defaults[/green]")
        return
    if shell:
        _print_completion(shell)
        return
    if show_log:
        _run_log(log_repo, log_style)
        return
    if init_mode:
        _run_init()
        return
    if config_mode:
        _run_config_show()
        return
    if show_diff:
        _run_diff_preview()
        return
    if show_stats:
        _run_stats()
        return
    if hook_file:
        _run_hook_mode(hook_file)
        return
    if msg_template_list:
        _run_template_list()
        return
    if msg_template_save:
        _run_template_save(msg_template_save)
        return
    if msg_template_delete:
        _run_template_delete(msg_template_delete)
        return

    # ── Sub-commands that need a git repo ────────────
    if install_hook_flag:
        install_hook()
        return
    if uninstall_hook_flag:
        uninstall_hook()
        return
    if generate_pr:
        _run_pr_mode(pr_base, hint, output_file)
        return
    if squash_n:
        _run_squash_mode(squash_n, style, hint, output_file)
        return
    if changelog:
        _run_changelog_mode(version_tag, hint, output_file)
        return
    if review:
        _run_review_mode(severity, hint, output_file)
        return
    if validate:
        _run_validate()
        return
    if auto_fix:
        _run_auto_fix()
        return

    # ── Commit generation ───────────────────────────

    if not is_git_repo():
        console.print("[red]✗ Not a git repository.[/red]")
        sys.exit(1)

    # Auto-stage
    if auto_stage:
        _auto_stage_changes()

    if amend and not last:
        console.print("[yellow]ℹ --amend is usually used with --last (last commit amend).[/yellow]")

    config = load_config()

    # Apply runtime provider override
    if provider_override:
        _apply_provider_override(config, provider_override)

    # First-run setup
    if not config["api"]["key"]:
        console.print("[yellow]⚠ First time? Let's set up your AI provider.[/yellow]")
        config = setup_wizard()
        if not config["api"]["key"]:
            console.print("[red]✗ API key required to use aicommit.[/red]")
            sys.exit(1)
        # Reload after setup
        config = load_config()

    commit_style = style or config["commit"]["style"]
    language = config["commit"]["language"]

    # Handle --last (generate message for existing commit)
    if last:
        _run_last_mode(commit_style, language, hint, amend, signoff, no_verify, copy, output_file, msg_template_name)
        return

    # Normal commit flow
    if not has_staged_changes():
        console.print("[yellow]ℹ No staged changes. Run `git add <files>` first, or use `-a` to auto-stage.[/yellow]")
        sys.exit(0)

    # Template
    custom_template = None
    if template_file:
        try:
            custom_template = Path(template_file).read_text(encoding="utf-8")
            custom_template = _expand_template_vars(custom_template,
                branch=get_branch_name(), scope=scope or detect_scope(get_staged_files()),
            )
        except FileNotFoundError:
            console.print(f"[red]✗ Template file not found: {template_file}[/red]")
            sys.exit(1)

    try:
        # Gather context
        diff = get_staged_diff(
            max_lines=config["commit"]["max_diff_lines"],
            skip_noise=True,
        )
        files = get_staged_files()
        stats = get_staged_stats()
        branch = get_branch_name()
        repo = get_repo_name()
        detected_scope = scope or detect_scope(files) or detect_monorepo_package(files)
        branch_type = infer_type_from_branch(branch)
        breaking = detect_breaking_changes(diff)

        show_diff_summary(files, stats, scope=detected_scope, branch_type=branch_type, breaking=breaking)

        temp_override = temperature if temperature is not None else config["api"].get("temperature", 0.3)

        # Choose mode: generate 3 options for user to pick
        if choose_mode:
            result = _choose_commit_message(
                diff=diff, style=commit_style, language=language,
                hint=hint, branch_type=branch_type, branch=branch,
                breaking=breaking, files=files, custom_template=custom_template,
                max_tokens_override=max_tokens, temperature_override=temp_override,
            )
        else:
            with show_generating() as progress:
                task = progress.add_task("", total=None)
                try:
                    result = generate_commit_message(
                        diff=diff,
                        style=commit_style,
                        language=language,
                        hint=hint,
                        branch_hint=f"Branch: {branch}, type: {branch_type}" if branch_type else "",
                        breaking_hint="BREAKING CHANGE DETECTED" if breaking else "",
                        file_list=files,
                        template=custom_template,
                        max_tokens_override=max_tokens,
                        temperature_override=temp_override,
                    )
                except (GitErr, AIErr) as e:
                    progress.remove_task(task)
                    console.print(f"[red]✗ {e}[/red]")
                    sys.exit(1)
                progress.remove_task(task)

        console.print()
        console.print(
            Panel(
                result.message,
                title=f"[bold]{'📐' if commit_style == 'conventional' else '🎨' if commit_style == 'emoji' else '📝'} Generated Message ({commit_style.title()})[/bold]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
        console.print(
            f"[dim]Model: {result.model} | "
            f"Tokens: {result.tokens_in}→{result.tokens_out} | "
            f"Time: {result.time_ms:.0f}ms | "
            f"Temp: {temp_override}[/dim]"
        )

        # Copy to clipboard
        if copy:
            _copy_to_clipboard(result.message)

        # Save to file
        if output_file:
            _save_to_file(result.message, output_file)

        # Dry run
        if dry_run:
            console.print("\n[dim]Dry run — not committing.[/dim]")
            return

        # Confirmation
        if not auto_yes:
            console.print()
            ok = Confirm.ask("[bold]Commit with this message?[/bold]", default=True)
            if not ok:
                console.print("[dim]Aborted.[/dim]")
                return

        # Edit
        final_msg = result.message

        # Apply message template if specified
        if msg_template_name:
            tmpl = get_message_template(msg_template_name)
            if tmpl:
                final_msg = _apply_message_template(
                    final_msg, tmpl, commit_style,
                    branch=get_branch_name(),
                )
                console.print(f"[dim]📋 Template '{msg_template_name}' applied[/dim]")
            else:
                console.print(f"[yellow]⚠ Template '{msg_template_name}' not found. Use --msg-template-list to see saved templates.[/yellow]")

        # Body wrapping for detailed style
        if commit_style == "detailed" and "\n\n" in final_msg:
            from .conventional import wrap_body
            final_msg = wrap_body(final_msg)

        if edit:
            final_msg = _edit_message(final_msg, editor_cmd_override)

        # Add co-author trailers
        for author in co_author:
            final_msg += f"\nCo-authored-by: {author}"
        # Add issue reference
        if issue_ref:
            final_msg += f"\nRefs: {issue_ref}"

        # Commit
        commit_args = ["commit", "-m", final_msg]
        if signoff or config["commit"].get("signoff"):
            commit_args.append("--signoff")
        if no_verify or config["commit"].get("no_verify"):
            commit_args.append("--no-verify")

        try:
            out = sp.run(
                ["git"] + commit_args,
                capture_output=True, text=True,
                creationflags=0x08000000,
            )
            if out.returncode != 0:
                console.print(f"[red]✗ git commit failed:[/red]\n{out.stderr}")
                sys.exit(1)
            console.print(f"[green]{out.stdout.strip()}[/green]")

            # Save history
            save_history({
                "repo": repo,
                "branch": branch,
                "style": commit_style,
                "message": final_msg,
                "model": result.model,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "time_ms": result.time_ms,
            })
        except Exception as e:
            console.print(f"[red]✗ {e}[/red]")
            sys.exit(1)

    except GitErr as e:
        console.print(f"[red]✗ Git error: {e}[/red]")
        sys.exit(1)


# ── Sub-command helpers ──────────────────────────────

def _auto_stage_changes():
    """Run `git add -A` to stage all changes."""
    try:
        sp.run(
            ["git", "add", "-A"],
            capture_output=True, text=True,
            creationflags=0x08000000,
        )
        console.print("[dim]📎 Auto-staged all changes[/dim]")
    except Exception as e:
        console.print(f"[red]✗ Auto-stage failed: {e}[/red]")
        sys.exit(1)


def _run_last_mode(style: str, language: str, hint: str, amend: bool, signoff: bool, no_verify: bool, copy: bool, output_file: str = None, msg_template_name: str = None):
    """Generate message for last commit (amend)."""
    config = load_config()
    if not config["api"]["key"]:
        console.print("[red]✗ No API key configured.[/red]")
        sys.exit(1)

    try:
        diff = sp.run(
            ["git", "diff", "HEAD~1", "--unified=3"],
            capture_output=True, text=True,
            creationflags=0x08000000,
        )
        if diff.returncode != 0:
            console.print("[red]✗ Could not get last commit diff (need at least 2 commits).[/red]")
            sys.exit(1)

        diff_text = diff.stdout
        diff_lines = diff_text.split("\n")
        if len(diff_lines) > 300:
            diff_text = "\n".join(diff_lines[:300]) + f"\n... ({len(diff_lines)-300} more lines)"

        branch = get_branch_name()
        branch_type = infer_type_from_branch(branch)

        with show_generating() as progress:
            task = progress.add_task("", total=None)
            try:
                result = generate_commit_message(
                    diff=diff_text, style=style, language=language,
                    hint=hint or "Rewrite commit message for these changes",
                    branch_hint=f"Branch: {branch}, type: {branch_type}" if branch_type else "",
                    max_tokens_override=500,
                )
            except (GitErr, AIErr) as e:
                progress.remove_task(task)
                console.print(f"[red]✗ {e}[/red]")
                sys.exit(1)
            progress.remove_task(task)

        console.print()

        # Apply message template if specified
        final_msg = result.message
        if msg_template_name:
            tmpl = get_message_template(msg_template_name)
            if tmpl:
                final_msg = _apply_message_template(
                    final_msg, tmpl, style,
                    branch=get_branch_name(),
                )
                console.print(f"[dim]📋 Template '{msg_template_name}' applied[/dim]")
            else:
                console.print(f"[yellow]⚠ Template '{msg_template_name}' not found.[/yellow]")

        console.print(
            Panel(
                final_msg,
                title="[bold]📝 Amended Message[/bold]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

        if copy:
            _copy_to_clipboard(final_msg)

        if output_file:
            _save_to_file(final_msg, output_file)

        if amend:
            amend_args = ["commit", "--amend", "-m", final_msg]
            if signoff:
                amend_args.append("--signoff")
            if no_verify:
                amend_args.append("--no-verify")
            out = sp.run(
                ["git"] + amend_args,
                capture_output=True, text=True,
                creationflags=0x08000000,
            )
            if out.returncode != 0:
                console.print(f"[red]✗ git commit --amend failed:[/red]\n{out.stderr}")
                sys.exit(1)
            console.print(f"[green]{out.stdout.strip()}[/green]")

    except Exception as e:
        console.print(f"[red]✗ {e}[/red]")
        sys.exit(1)


def _run_pr_mode(base_branch: str, hint: str, output_file: str = None):
    """Generate a pull request description."""
    if not is_git_repo():
        console.print("[red]✗ Not a git repository.[/red]")
        sys.exit(1)

    config = load_config()
    if not config["api"]["key"]:
        console.print("[yellow]⚠ First time? Let's set up your AI provider.[/yellow]")
        config = setup_wizard()
        if not config["api"]["key"]:
            console.print("[red]✗ API key required.[/red]")
            sys.exit(1)

    language = config["commit"]["language"]

    with show_generating() as progress:
        task = progress.add_task("", total=None)
        try:
            msg = generate_pr_description(base_branch, language, hint)
        except (GitErr, AIErr) as e:
            progress.remove_task(task)
            console.print(f"[red]✗ {e}[/red]")
            sys.exit(1)
        progress.remove_task(task)

    console.print()
    console.print(
        Panel(
            msg,
            title="[bold]📋 PR Description[/bold]",
            border_style="magenta",
            padding=(1, 2),
        )
    )

    if output_file:
        _save_to_file(msg, output_file)


def _run_squash_mode(num_commits: int, style: str, hint: str, output_file: str = None):
    """Generate a squash commit message."""
    if not is_git_repo():
        console.print("[red]✗ Not a git repository.[/red]")
        sys.exit(1)

    config = load_config()
    commit_style = style or config["commit"]["style"]
    language = config["commit"]["language"]

    with show_generating() as progress:
        task = progress.add_task("", total=None)
        try:
            msg = generate_squash_message(num_commits, commit_style, language, hint)
        except (GitErr, AIErr) as e:
            progress.remove_task(task)
            console.print(f"[red]✗ {e}[/red]")
            sys.exit(1)
        progress.remove_task(task)

    console.print()
    console.print(
        Panel(
            msg,
            title=f"[bold]📦 Squash Message ({num_commits} commits)[/bold]",
            border_style="green",
            padding=(1, 2),
        )
    )

    if output_file:
        _save_to_file(msg, output_file)


def _run_changelog_mode(version: str, hint: str, output_file: str = None):
    """Generate a changelog entry."""
    if not is_git_repo():
        console.print("[red]✗ Not a git repository.[/red]")
        sys.exit(1)

    config = load_config()
    language = config["commit"]["language"]

    with show_generating() as progress:
        task = progress.add_task("", total=None)
        try:
            msg = generate_changelog(version, language, hint)
        except AIErr as e:
            progress.remove_task(task)
            console.print(f"[red]✗ {e}[/red]")
            sys.exit(1)
        progress.remove_task(task)

    console.print()
    console.print(
        Panel(
            msg,
            title=f"[bold]📝 Changelog{' v'+version if version else ''}[/bold]",
            border_style="blue",
            padding=(1, 2),
        )
    )

    if output_file:
        _save_to_file(msg, output_file)


def _run_review_mode(severity: str, hint: str, output_file: str = None):
    """Run AI code review on staged changes."""
    from .review import analyze_diff

    if not is_git_repo():
        console.print("[red]✗ Not a git repository.[/red]")
        sys.exit(1)

    if not has_staged_changes():
        console.print("[yellow]ℹ No staged changes. Stage files with `git add` first.[/yellow]")
        sys.exit(0)

    config = load_config()
    if not config["api"]["key"]:
        console.print("[yellow]⚠ First time? Let's set up your AI provider.[/yellow]")
        config = setup_wizard()
        if not config["api"]["key"]:
            console.print("[red]✗ API key required.[/red]")
            sys.exit(1)

    try:
        files = get_staged_files()
        diff = get_staged_diff(max_lines=config["commit"]["max_diff_lines"], skip_noise=True)
        stats = get_staged_stats()

        show_diff_summary(files, stats, scope="review", branch_type="", breaking=False)

        console.print("\n[bold cyan]🔍 AI Code Review[/bold cyan]")
        console.print("[dim]Analyzing staged changes...[/dim]\n")

        with show_generating() as progress:
            task = progress.add_task("", total=None)
            result = analyze_diff(diff, severity, hint)
            progress.remove_task(task)

        console.print()
        console.print(
            Panel(
                result,
                title="[bold]🔍 Review Results[/bold]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

        if output_file:
            _save_to_file(result, output_file)
    except (GitErr, AIErr) as e:
        console.print(f"[red]✗ {e}[/red]")
        sys.exit(1)


def _run_validate():
    """Validate last commit follows conventional format."""
    if not is_git_repo():
        console.print("[red]✗ Not a git repository.[/red]")
        sys.exit(1)
    msg = get_last_commit_message()
    if not msg:
        console.print("[red]✗ No commits found.[/red]")
        sys.exit(1)
    valid, error = validate_conventional(msg)
    if valid:
        console.print(f"[green]✓ Conventional commit format is valid.[/green]")
    else:
        console.print(f"[red]✗ {error}[/red]")
        console.print(f"[dim]Run `aicommit --auto-fix` to fix it automatically.[/dim]")


def _run_auto_fix():
    """Auto-fix last commit message to follow conventional format."""
    if not is_git_repo():
        console.print("[red]✗ Not a git repository.[/red]")
        sys.exit(1)
    msg = get_last_commit_message()
    if not msg:
        console.print("[red]✗ No commits found.[/red]")
        sys.exit(1)
    try:
        fixed = auto_fix_conventional(msg)
        console.print(f"[green]✓ Fixed message:[/green]")
        console.print(f"  [dim]Old:[/dim] {msg}")
        console.print(f"  [dim]New:[/dim] {fixed}")
        sp.run(
            ["git", "commit", "--amend", "-m", fixed],
            capture_output=True, text=True,
            creationflags=0x08000000,
        )
        console.print("[green]✓ Last commit message updated.[/green]")
    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        sys.exit(1)


def _run_log(repo_filter: str = None, style_filter: str = None):
    """Show recent aicommit message history with optional filtering."""
    entries = load_history(50)
    if not entries:
        console.print("[dim]No history yet. Generate some commits first![/dim]")
        return

    # Apply filters
    if repo_filter:
        entries = [e for e in entries if e.get("repo", "") and repo_filter.lower() in e["repo"].lower()]
    if style_filter:
        entries = [e for e in entries if e.get("style") == style_filter]

    if not entries:
        console.print("[dim]No matching entries found.[/dim]")
        return

    console.print()
    filter_desc = ""
    if repo_filter:
        filter_desc += f" repo={repo_filter}"
    if style_filter:
        filter_desc += f" style={style_filter}"
    console.print(f"[bold]📜 aicommit History[/bold] ([dim]{len(entries)} entries[/dim]{filter_desc})")
    console.print("─" * 60)

    for entry in reversed(entries[-30:]):
        when = entry.get("timestamp", "")[:19].replace("T", " ")
        repo = entry.get("repo", "?")
        branch = entry.get("branch", "?")
        style = entry.get("style", "?")
        msg = entry.get("message", "?").split("\n")[0][:80]
        model = entry.get("model", "?")
        tok = f"→{entry.get('tokens_out', 0)}"
        console.print(
            f"[dim]{when}[/dim]  [cyan]{repo}[/cyan]/[dim]{branch}[/dim]  "
            f"[green]{msg}[/green]  "
            f"[dim]{style} | {model} | {tok} tok[/dim]"
        )

    console.print("─" * 60)
    console.print(f"[dim]History file: ~/.aicommit/history.jsonl[/dim]")


def _edit_message(message: str, editor_cmd: str | None = None) -> str:
    """Open message in $EDITOR for user editing.

    Args:
        message: The commit message to edit.
        editor_cmd: Override editor command (e.g. 'vim', 'code --wait').
    """
    if editor_cmd:
        editor = editor_cmd
    else:
        editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "notepad" if platform.system() == "Windows" else "vim"))

    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="aicommit_", text=True)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(message)
            f.write("\n\n# Edit the commit message above.")
            f.write("\n# Lines starting with # will be ignored.\n")

        sp.run([editor, tmp_path], check=False)

        with open(tmp_path, "r", encoding="utf-8") as f:
            edited = f.read()

        # Strip comment lines
        lines = [
            line for line in edited.split("\n")
            if not line.strip().startswith("#")
        ]
        result = "\n".join(lines).strip()
        return result if result else message
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _copy_to_clipboard(text: str):
    """Copy text to clipboard."""
    import shutil

    try:
        import pyperclip
        pyperclip.copy(text)
        console.print("[dim]📋 Copied to clipboard[/dim]")
        return
    except ImportError:
        pass

    try:
        if platform.system() == "Windows":
            sp.run(["clip"], input=text, text=True, creationflags=0x08000000)
        elif platform.system() == "Darwin":
            sp.run(["pbcopy"], input=text, text=True)
        elif shutil.which("xclip"):
            sp.run(["xclip", "-selection", "clipboard"], input=text, text=True)
        elif shutil.which("xsel"):
            sp.run(["xsel", "--clipboard", "--input"], input=text, text=True)
        else:
            return
        console.print("[dim]📋 Copied to clipboard[/dim]")
    except Exception:
        pass


def _print_completion(shell: str):
    """Print shell completion script to stdout."""
    if shell == "bash":
        print('eval "$(_AICOMMIT_COMPLETE=bash_source aicommit)"')
    elif shell == "zsh":
        print('eval "$(_AICOMMIT_COMPLETE=zsh_source aicommit)"')
    elif shell == "fish":
        print("aicommit --completion fish | source")
    elif shell == "powershell":
        print("Register-ArgumentCompleter -Native -CommandName aicommit -ScriptBlock {")
        print("    param($wordToComplete, $commandAst, $cursorPosition)")
        print("    $env:_AICOMMIT_COMPLETE = 'powershell_complete'")
        print("    aicommit | ForEach-Object { [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }")
        print("}")

def _run_hook_mode(commit_msg_file: str):
    """Hook mode: generate message and write it to the commit message file.
    
    Called by the prepare-commit-msg git hook. Writes the AI-generated
    message into the given file so git uses it as the pre-filled message.
    """
    if not has_staged_changes():
        return  # Nothing to analyze

    config = load_config()
    if not config["api"]["key"]:
        return  # Not configured

    try:
        diff = get_staged_diff(max_lines=config["commit"]["max_diff_lines"], skip_noise=True)
        if not diff.strip():
            return

        result = generate_commit_message(
            diff=diff,
            style=config["commit"]["style"],
            language=config["commit"]["language"],
        )

        # Write the message to the commit file
        with open(commit_msg_file, "w", encoding="utf-8") as f:
            f.write(result.message)

        save_history({
            "repo": get_repo_name(),
            "branch": get_branch_name(),
            "style": config["commit"]["style"],
            "message": result.message,
            "model": result.model,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "time_ms": result.time_ms,
        })
    except Exception:
        pass  # Hook should never block the commit


def _choose_commit_message(**kwargs) -> AIResult:
    """Generate 3 commit message candidates and let user pick one."""
    from rich.prompt import Prompt

    options: list[AIResult] = []
    for i in range(3):
        with show_generating() as progress:
            task = progress.add_task(f"Option {i+1}/3", total=None)
            try:
                r = generate_commit_message(
                    diff=kwargs["diff"],
                    style=kwargs["style"],
                    language=kwargs["language"],
                    hint=kwargs.get("hint"),
                    branch_hint=kwargs.get("branch_hint") or "",
                    breaking_hint=kwargs.get("breaking_hint") or "",
                    file_list=kwargs.get("files"),
                    template=kwargs.get("custom_template"),
                    max_tokens_override=kwargs.get("max_tokens_override"),
                    temperature_override=kwargs.get("temperature_override", 0.3) + i * 0.15,
                )
                options.append(r)
            except (GitErr, AIErr) as e:
                progress.remove_task(task)
                if i == 0:
                    console.print(f"[red]✗ {e}[/red]")
                    sys.exit(1)
            progress.remove_task(task)

    console.print()
    for i, opt in enumerate(options, 1):
        letter = ["a", "b", "c"][i - 1]
        console.print(f"  [bold cyan]{letter})[/bold cyan] {opt.message}")

    console.print()
    choice = Prompt.ask("[bold]Pick one[/bold]", choices=["a", "b", "c"], default="a")
    idx = {"a": 0, "b": 1, "c": 2}[choice]
    return options[idx]


def _run_init():
    """One-command setup: configure git + AI provider."""
    console.print(Panel(
        "[bold]🚀 aicommit — First-Time Setup[/bold]\n\n"
        "This will configure git and your AI provider.",
        border_style="cyan",
    ))

    # Git config
    try:
        name = sp.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
        email = sp.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
        if not name or not email:
            console.print("[yellow]⚠ Git user not fully configured.[/yellow]")
            if not name:
                n = Prompt.ask("  Git user.name")
                sp.run(["git", "config", "--global", "user.name", n])
            if not email:
                e = Prompt.ask("  Git user.email")
                sp.run(["git", "config", "--global", "user.email", e])
            console.print("[green]✓ Git user configured[/green]")
        else:
            console.print(f"[dim]Git user: {name} <{email}>[/dim]")
    except Exception:
        pass

    # AI provider setup
    config = setup_wizard()
    if config["api"]["key"]:
        console.print("[green]✓ AI provider configured[/green]")
        console.print("\n[bold]All set! Try:[/bold] [cyan]aicommit[/cyan]")
    else:
        console.print("[red]✗ Setup incomplete — API key required.[/red]")


def _run_stats():
    """Show usage statistics dashboard."""
    entries = load_history(limit=500)
    if not entries:
        console.print("[dim]No history yet. Run aicommit to generate your first commit message.[/dim]")
        return

    from collections import Counter
    from datetime import datetime

    styles = Counter(e.get("style", "?") for e in entries)
    repos = Counter(e.get("repo", "?") for e in entries)
    models = Counter(e.get("model", "?") for e in entries)
    total_tokens_in = sum(e.get("tokens_in", 0) for e in entries)
    total_tokens_out = sum(e.get("tokens_out", 0) for e in entries)
    total_time_ms = sum(e.get("time_ms", 0) for e in entries)
    
    # Date range
    timestamps = [e.get("timestamp", "")[:10] for e in entries if e.get("timestamp")]
    date_range = f"{timestamps[-1]} → {timestamps[0]}" if len(timestamps) >= 2 else (timestamps[0] if timestamps else "N/A")
    
    # Per-repo breakdown
    total_commits = len(entries)

    table = Table(title="📊 aicommit Usage Stats", border_style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Total commits", str(total_commits))
    table.add_row("Date range", date_range)
    table.add_row("Total tokens (in/out)", f"{total_tokens_in:,} / {total_tokens_out:,}")
    table.add_row("Total AI time", f"{total_time_ms/1000:.1f}s")
    table.add_row("Avg tokens/commit", f"{(total_tokens_in + total_tokens_out) // max(len(entries), 1):,}")
    table.add_row("Avg time/commit", f"{total_time_ms / max(len(entries), 1):.0f}ms")
    table.add_row("Top style", styles.most_common(1)[0][0] if styles else "N/A")
    table.add_row("Top model", models.most_common(1)[0][0] if models else "N/A")

    console.print()
    console.print(table)

    # Per-repo breakdown
    if len(repos) > 1:
        console.print()
        repo_table = Table(title="📁 Per-Repo Breakdown", border_style="green")
        repo_table.add_column("Repository")
        repo_table.add_column("Commits", justify="right")
        repo_table.add_column("Share")
        for repo, count in repos.most_common(10):
            pct = count / total_commits * 100
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            repo_table.add_row(repo, str(count), f"{bar} {pct:.0f}%")
        console.print(repo_table)

    # Model breakdown
    if len(models) > 1:
        console.print()
        model_table = Table(title="🤖 Models Used", border_style="yellow")
        model_table.add_column("Model")
        model_table.add_column("Calls", justify="right")
        model_table.add_column("Avg Time")
        model_table.add_column("Avg Tokens")
        for model, count in models.most_common():
            model_entries = [e for e in entries if e.get("model") == model]
            avg_time = sum(e.get("time_ms", 0) for e in model_entries) / len(model_entries)
            avg_tok = sum(e.get("tokens_in", 0) + e.get("tokens_out", 0) for e in model_entries) / len(model_entries)
            model_table.add_row(model, str(count), f"{avg_time:.0f}ms", f"{avg_tok:.0f}")
        console.print(model_table)

    console.print()
    console.print("[dim]Use `aicommit log` to see recent messages.[/dim]")


def _expand_template_vars(template: str, **values) -> str:
    """Expand {key} placeholders in a custom template."""
    result = template
    for key, val in values.items():
        result = result.replace(f"{{{key}}}", str(val) if val else "")
    return result


def _run_config_show():
    """Show current configuration."""
    config = load_config()
    console.print(Panel("🔧 [bold]aicommit Configuration[/bold]", border_style="cyan"))

    table = Table(border_style="dim")
    table.add_column("Section", style="bold cyan")
    table.add_column("Key")
    table.add_column("Value")

    api = config["api"]
    commit = config["commit"]

    table.add_row("api", "provider", api.get("provider", "openai"))
    table.add_row("api", "model", api.get("model", ""))
    table.add_row("api", "endpoint", api.get("endpoint", ""))
    table.add_row("api", "key", (api["key"][:6] + "..." + api["key"][-4:]) if len(api.get("key", "")) > 10 else (api["key"] or "(not set)"))
    table.add_row("api", "temperature", str(api.get("temperature", 0.3)))
    table.add_row("commit", "style", commit.get("style", "conventional"))
    table.add_row("commit", "language", commit.get("language", "en"))
    table.add_row("commit", "max_diff_lines", str(commit.get("max_diff_lines", 200)))
    table.add_row("commit", "signoff", str(commit.get("signoff", False)))
    table.add_row("commit", "no_verify", str(commit.get("no_verify", False)))

    console.print(table)


def _run_diff_preview():
    """Preview staged diff without generating a message."""
    if not is_git_repo():
        console.print("[red]✗ Not a git repository.[/red]")
        return
    if not has_staged_changes():
        console.print("[yellow]ℹ No staged changes.[/yellow]")
        return

    config = load_config()
    diff = get_staged_diff(max_lines=config["commit"]["max_diff_lines"], skip_noise=True)
    files = get_staged_files()
    stats = get_staged_stats()
    scope = detect_scope(files)
    branch = get_branch_name()
    branch_type = infer_type_from_branch(branch)
    breaking = detect_breaking_changes(diff)

    show_diff_summary(files, stats, scope=scope, branch_type=branch_type, breaking=breaking)
    console.print()
    console.print(Panel(diff or "(empty diff)", title="📋 Staged Diff", border_style="dim"))


def _apply_provider_override(config: dict, provider: str):
    """Apply a runtime provider override to the config."""
    provider_map = {
        "deepseek": ("openai", "https://api.deepseek.com/v1", "deepseek-chat"),
        "openai": ("openai", "https://api.openai.com/v1", "gpt-4o-mini"),
        "anthropic": ("anthropic", "https://api.anthropic.com/v1", "claude-3-5-haiku-latest"),
        "ollama": ("openai", "http://localhost:11434/v1", "llama3.2"),
    }
    if provider in provider_map:
        prov, endpoint, model = provider_map[provider]
        config["api"]["provider"] = prov
        config["api"]["endpoint"] = endpoint
        config["api"]["model"] = model
        console.print(f"[dim]🔌 Provider override: {provider} ({model})[/dim]")


def _save_to_file(content: str, filepath: str):
    """Save message content to a file."""
    try:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        console.print(f"[dim]💾 Saved to {p.absolute()}[/dim]")
    except Exception as e:
        console.print(f"[red]✗ Failed to save: {e}[/red]")


def _parse_commit_message(message: str, style: str) -> dict:
    """Parse a commit message into components based on style.

    Returns dict with keys: type, scope, description, body, emoji, breaking.
    """
    import re

    result = {
        "type": "",
        "scope": "",
        "description": "",
        "body": "",
        "emoji": "",
        "breaking": "",
    }

    # Split header and body
    parts = message.split("\n\n", 1)
    header = parts[0].strip()
    body = parts[1].strip() if len(parts) > 1 else ""
    result["body"] = body

    if style == "conventional":
        # Parse: type(scope)!: description
        m = re.match(r'^(\w+)(?:\(([^)]*)\))?(!)?\s*:\s*(.*)$', header)
        if m:
            result["type"] = m.group(1) or ""
            result["scope"] = m.group(2) or ""
            result["breaking"] = m.group(3) or ""
            result["description"] = m.group(4).strip() or ""
        else:
            result["description"] = header
    elif style == "emoji":
        # Parse: emoji description
        m = re.match(r'^([^\w\s]\s*)(.*)$', header)
        if m:
            result["emoji"] = m.group(1).strip()
            result["description"] = m.group(2).strip()
        else:
            result["description"] = header
    elif style in ("simple", "detailed"):
        # Just description + body
        result["description"] = header
    else:
        result["description"] = header

    return result


def _apply_message_template(message: str, template_fmt: str, style: str, **extra_vars) -> str:
    """Apply a message template format to a parsed commit message.

    Template variables: {type}, {scope}, {description}, {body}, {emoji},
        {breaking}, {branch}.

    Args:
        message: The original AI-generated commit message.
        template_fmt: Template format string with {var} placeholders.
        style: The commit style used to generate the message.
        **extra_vars: Additional variables (branch, etc.).

    Returns:
        Formatted commit message.
    """
    import re as _re
    parsed = _parse_commit_message(message, style)
    # Merge extra vars (prefer extra over parsed)
    vars_dict = dict(parsed)
    vars_dict.update(extra_vars)
    vars_dict.setdefault("branch", "")

    result = template_fmt
    for key, val in vars_dict.items():
        result = result.replace(f"{{{key}}}", str(val) if val else "")
    # Clean up double spaces from empty replacements
    result = _re.sub(r'  +', ' ', result)
    return result.strip()


def _run_template_list():
    """List all saved message templates."""
    templates = list_message_templates()
    if not templates:
        console.print("[dim]No saved message templates.[/dim]")
        console.print()
        console.print("[dim]Create one with: aicommit --msg-template-save NAME=FORMAT[/dim]")
        console.print("\nAvailable variables:")
        for var, desc in TEMPLATE_VARIABLES.items():
            console.print(f"  [cyan]{var}[/cyan] - {desc}")
        return

    table = Table(title="📋 Saved Message Templates", border_style="dim")
    table.add_column("Name", style="bold cyan")
    table.add_column("Format")
    for name, fmt in templates.items():
        table.add_row(name, fmt)
    console.print(table)
    console.print()
    console.print("Apply with: [cyan]aicommit --msg-template NAME[/cyan]")


def _run_template_save(arg: str):
    """Save a named message template from NAME=FORMAT argument."""
    if "=" not in arg:
        console.print(
            "[red]✗ Use format: --msg-template-save NAME=FORMAT[/red]\n"
            'Example: [cyan]aicommit --msg-template-save myfmt="{type}({scope}): {description}"[/cyan]'
        )
        return
    name, fmt = arg.split("=", 1)
    name = name.strip()
    fmt = fmt.strip()

    if not name or not fmt:
        console.print("[red]✗ Both name and format are required.[/red]")
        return

    save_message_template(name, fmt)
    console.print(f"[green]✓ Template '{name}' saved.[/green]")
    console.print(f"  Format: [dim]{fmt}[/dim]")


def _run_template_delete(name: str):
    """Delete a named message template."""
    if delete_message_template(name):
        console.print(f"[green]✓ Template '{name}' deleted.[/green]")
    else:
        console.print(f"[yellow]⚠ Template '{name}' not found.[/yellow]")


if __name__ == "__main__":
    main()
