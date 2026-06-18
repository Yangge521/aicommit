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
    get_commit_diff,
    get_commit_files,
    get_commits_in_range,
    get_last_commit_message,
    get_repo_name,
    get_staged_diff,
    get_staged_files,
    get_staged_stats,
    has_staged_changes,
    infer_type_from_branch,
    install_hook,
    is_git_repo,
    run_git,
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
@click.option("--reset-config", "reset_config_flag", is_flag=True, help="Reset config to defaults")
@click.option("--install-hook", "install_hook_flag", is_flag=True, help="Install aicommit as git prepare-commit-msg hook")
@click.option("--uninstall-hook", "uninstall_hook_flag", is_flag=True, help="Remove aicommit git hook")
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
@click.option("--retry", "retry_last", is_flag=True,
              help="Regenerate the last commit message (re-run AI with same diff)")
@click.option("--group-by", "group_by",
              type=click.Choice(["dir", "type", "ext"]),
              default=None,
              help="Group staged changes and generate separate commits per group")
@click.option("--install-alias", "install_alias", is_flag=True,
              help="Install git aliases (git ci, git review, git squash)")
@click.option("--uninstall-alias", "uninstall_alias", is_flag=True,
              help="Remove aicommit git aliases")
@click.option("--body-file", "body_file", default=None, metavar="FILE",
              help="Read additional body content from file and append to commit message")
@click.option("--push", "auto_push", is_flag=True,
              help="Push to remote after committing")
@click.option("--language", "language_override", default=None,
              help="Override output language for this run (e.g. en, zh, ja)")
@click.option("--emoji-pair", "emoji_pair", is_flag=True,
              help="Use conventional format with emoji prefix (e.g. ✨ feat: add feature)")
@click.option("--rebase", "rebase_mode", is_flag=True,
              help="Interactive rebase: regenerate messages for commits since base")
@click.option("--rebase-base", default=None, metavar="BRANCH",
              help="Base branch/commit for --rebase (default: auto-detect from remote)")
@click.option("--rebase-all", is_flag=True,
              help="With --rebase: reword ALL commits without prompting")
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
    retry_last, group_by, install_alias, uninstall_alias, body_file,
    auto_push, language_override, emoji_pair,
    rebase_mode, rebase_base, rebase_all,
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
    if install_alias:
        _run_install_alias()
        return
    if uninstall_alias:
        _run_uninstall_alias()
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

    # ── Interactive Rebase ───────────────────────────
    if rebase_mode:
        _run_rebase_mode(rebase_base, rebase_all, style, language_override, hint, auto_yes)
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
    language = language_override or config["commit"]["language"]

    # Handle --last (generate message for existing commit)
    if last:
        _run_last_mode(commit_style, language, hint, amend, signoff, no_verify, copy, output_file, msg_template_name)
        return

    # Handle --retry (regenerate from last commit diff)
    if retry_last:
        _run_retry_mode(commit_style, language, hint, signoff, no_verify, copy, output_file, msg_template_name, editor_cmd_override)
        return

    # Normal commit flow
    if not has_staged_changes():
        console.print("[yellow]ℹ No staged changes. Run `git add <files>` first, or use `-a` to auto-stage.[/yellow]")
        sys.exit(0)

    # Handle --group-by: split staged changes and generate separate commits
    if group_by:
        _run_group_by_mode(group_by, commit_style, language, hint, signoff, no_verify, auto_yes, output_file)
        return

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
                        file_list="\n".join(f"- {f}" for f in files),
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

        # Apply emoji-pair mode: prepend emoji to conventional message
        if emoji_pair and commit_style == "conventional":
            from .conventional import parse_conventional, EMOJI_MAP
            parsed = parse_conventional(final_msg)
            if parsed and parsed["type"] in EMOJI_MAP:
                final_msg = f"{EMOJI_MAP[parsed['type']]} {final_msg}"

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

        # Append body from file
        if body_file:
            try:
                body_content = Path(body_file).read_text(encoding="utf-8").strip()
                if body_content:
                    final_msg += f"\n\n{body_content}"
                    console.print(f"[dim]📎 Appended body from {body_file}[/dim]")
            except FileNotFoundError:
                console.print(f"[red]✗ Body file not found: {body_file}[/red]")
                sys.exit(1)

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

            # Auto-push if requested
            if auto_push:
                push_out = sp.run(
                    ["git", "push"],
                    capture_output=True, text=True,
                    creationflags=0x08000000,
                )
                if push_out.returncode != 0:
                    console.print(f"[yellow]⚠ git push failed:[/yellow]\n{push_out.stderr}")
                else:
                    console.print(f"[green]✓ Pushed to remote[/green]")
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
        # Try HEAD~1 first; fallback to showing HEAD for initial commits
        diff = sp.run(
            ["git", "diff", "HEAD~1", "--unified=3"],
            capture_output=True, text=True,
            creationflags=0x08000000,
        )
        if diff.returncode != 0:
            diff = sp.run(
                ["git", "show", "--unified=3", "HEAD"],
                capture_output=True, text=True,
                creationflags=0x08000000,
            )
            if diff.returncode != 0:
                console.print("[red]✗ Could not get last commit diff.[/red]")
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
                    file_list="",
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
            config = load_config()
            if signoff or config["commit"].get("signoff"):
                amend_args.append("--signoff")
            if no_verify or config["commit"].get("no_verify"):
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

    language = language_override or config["commit"]["language"]

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
    language = language or config["commit"]["language"]

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
    language = language or config["commit"]["language"]

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
        amend_result = sp.run(
            ["git", "commit", "--amend", "-m", fixed],
            capture_output=True, text=True,
            creationflags=0x08000000,
        )
        if amend_result.returncode != 0:
            console.print(f"[red]✗ git commit --amend failed:[/red]\n{amend_result.stderr}")
            sys.exit(1)
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
    import shlex

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

        sp.run([*shlex.split(editor), tmp_path], check=False)

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
            file_list="\n".join(f"- {f}" for f in get_staged_files()),
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
                    file_list="\n".join(f"- {f}" for f in (kwargs.get("files") or [])),
                    template=kwargs.get("custom_template"),
                    max_tokens_override=kwargs.get("max_tokens_override"),
                    temperature_override=kwargs.get("temperature_override", 0.3) + i * 0.1,
                )
                options.append(r)
            except (GitErr, AIErr) as e:
                progress.remove_task(task)
                if i == 0:
                    console.print(f"[red]✗ {e}[/red]")
                    sys.exit(1)
            progress.remove_task(task)

    if not options:
        console.print("[red]✗ Could not generate any commit messages.[/red]")
        sys.exit(1)

    console.print()
    for i, opt in enumerate(options, 1):
        letter = ["a", "b", "c"][i - 1]
        console.print(f"  [bold cyan]{letter})[/bold cyan] {opt.message}")

    valid_choices = ["a", "b", "c"][:len(options)]
    console.print()
    choice = Prompt.ask("[bold]Pick one[/bold]", choices=valid_choices, default=valid_choices[0])
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
    table.add_row("commit", "auto_confirm", str(commit.get("auto_confirm", False)))
    table.add_row("commit", "signoff", str(commit.get("signoff", False)))
    table.add_row("commit", "no_verify", str(commit.get("no_verify", False)))

    # Templates section
    templates = config.get("templates", {})
    if templates:
        for i, (name, fmt) in enumerate(templates.items()):
            section = "templates" if i == 0 else ""
            table.add_row(section, name, fmt[:60] + ("..." if len(fmt) > 60 else ""))

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
        # Split at first whitespace: emoji (possibly multi-codepoint) + rest
        # Works for single emoji (✨), ZWJ sequences (👨‍💻), flag sequences (🇨🇳)
        m = re.match(r'^(\S+)\s+(.*)$', header)
        if m:
            result["emoji"] = m.group(1)
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
    # Clean up empty parentheses, dangling colons, and extra spaces from empty replacements
    result = _re.sub(r'\(\)', '', result)           # "type()" → "type"
    result = _re.sub(r':\s*:', ':', result)         # ":: desc" → ": desc"
    result = _re.sub(r'  +', ' ', result)           # collapse multiple spaces
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


def _run_retry_mode(style: str, language: str, hint: str, signoff: bool, no_verify: bool,
                    copy: bool, output_file: str = None, msg_template_name: str = None,
                    editor_cmd: str = None):
    """Retry: regenerate message for the last commit using its diff."""
    config = load_config()
    if not config["api"]["key"]:
        console.print("[red]✗ No API key configured.[/red]")
        sys.exit(1)

    try:
        # Try HEAD~1 first; fallback to showing HEAD for initial commits
        diff_result = sp.run(
            ["git", "diff", "HEAD~1", "--unified=3"],
            capture_output=True, text=True,
            creationflags=0x08000000,
        )
        if diff_result.returncode != 0:
            diff_result = sp.run(
                ["git", "show", "--unified=3", "HEAD"],
                capture_output=True, text=True,
                creationflags=0x08000000,
            )
            if diff_result.returncode != 0:
                console.print("[red]✗ Could not get last commit diff.[/red]")
                sys.exit(1)

        diff_text = diff_result.stdout
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
                    hint=hint or "Improve this commit message",
                    branch_hint=f"Branch: {branch}, type: {branch_type}" if branch_type else "",
                    file_list="",
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
                final_msg = _apply_message_template(final_msg, tmpl, style, branch=get_branch_name())
                console.print(f"[dim]📋 Template '{msg_template_name}' applied[/dim]")
            else:
                console.print(f"[yellow]⚠ Template '{msg_template_name}' not found.[/yellow]")

        console.print(
            Panel(
                final_msg,
                title="[bold]🔄 Retried Message[/bold]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
        console.print(
            f"[dim]Model: {result.model} | "
            f"Tokens: {result.tokens_in}→{result.tokens_out} | "
            f"Time: {result.time_ms:.0f}ms[/dim]"
        )

        if copy:
            _copy_to_clipboard(final_msg)
        if output_file:
            _save_to_file(final_msg, output_file)

        # Auto-amend the last commit
        ok = Confirm.ask("[bold]Amend last commit with this message?[/bold]", default=True)
        if not ok:
            console.print("[dim]Message generated but not applied. Use --copy or --output to save it.[/dim]")
            return

        amend_args = ["commit", "--amend", "-m", final_msg]
        config_signoff = load_config()["commit"].get("signoff", False)
        config_no_verify = load_config()["commit"].get("no_verify", False)
        if signoff or config_signoff:
            amend_args.append("--signoff")
        if no_verify or config_no_verify:
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

        save_history({
            "repo": get_repo_name(),
            "branch": branch,
            "style": style,
            "message": final_msg,
            "model": result.model,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "time_ms": result.time_ms,
        })

    except Exception as e:
        console.print(f"[red]✗ {e}[/red]")
        sys.exit(1)


def _run_group_by_mode(group_by: str, style: str, language: str, hint: str,
                      signoff: bool, no_verify: bool, auto_yes: bool,
                      output_file: str = None):
    """Group staged changes by dir/type/ext and generate separate commits per group."""
    from collections import defaultdict
    config = load_config()
    if not config["api"]["key"]:
        console.print("[red]✗ No API key configured.[/red]")
        sys.exit(1)

    files = get_staged_files()
    if not files:
        console.print("[yellow]ℹ No staged changes.[/yellow]")
        sys.exit(0)

    # Group files
    groups = defaultdict(list)
    for f in files:
        p = Path(f)
        if group_by == "dir":
            key = p.parts[0] if len(p.parts) > 1 else "(root)"
        elif group_by == "type":
            # Infer type from file path/name
            name_lower = p.name.lower()
            if any(kw in name_lower for kw in ["test", "spec", ".test.", ".spec."]):
                key = "test"
            elif any(kw in str(p) for kw in ["doc", "readme", "changelog", ".md"]):
                key = "docs"
            elif any(kw in str(p) for kw in ["config", "settings", ".toml", ".yaml", ".json"]):
                key = "config"
            elif any(kw in str(p) for kw in ["style", ".css", ".scss", ".less"]):
                key = "style"
            else:
                key = "src"
        elif group_by == "ext":
            key = p.suffix if p.suffix else "(no ext)"
        else:
            key = "(unknown)"
        groups[key].append(f)

    if len(groups) <= 1:
        console.print(f"[yellow]ℹ Only 1 group found. Use regular aicommit instead of --group-by.[/yellow]")
        return

    console.print(f"[bold]📂 Found {len(groups)} groups:[/bold]")
    for key, group_files in sorted(groups.items()):
        console.print(f"  [cyan]{key}[/cyan]: {', '.join(group_files)}")
    console.print()

    # Process each group
    commit_style = style or config["commit"]["style"]
    for key, group_files in sorted(groups.items()):
        console.print(f"[bold cyan]── Group: {key} ({len(group_files)} files) ──[/bold cyan]")

        # Get diff for just these files
        diff = run_git(["diff", "--cached", "--unified=3", "--"] + group_files)
        if not diff.strip():
            console.print(f"  [dim]No meaningful diff, skipping[/dim]")
            continue

        # Limit diff size
        diff_lines = diff.split("\n")
        if len(diff_lines) > 200:
            diff = "\n".join(diff_lines[:200]) + f"\n... ({len(diff_lines)-200} more lines)"

        branch = get_branch_name()
        branch_type = infer_type_from_branch(branch)

        try:
            with show_generating() as progress:
                task = progress.add_task(f"Group: {key}", total=None)
                result = generate_commit_message(
                    diff=diff, style=commit_style, language=language,
                    hint=hint or f"Changes in {key}",
                    branch_hint=f"Branch: {branch}" if branch else "",
                    file_list="\n".join(f"- {f}" for f in group_files),
                    max_tokens_override=300,
                )
                progress.remove_task(task)
        except (GitErr, AIErr) as e:
            console.print(f"  [red]✗ Failed: {e}[/red]")
            continue

        console.print(
            Panel(
                result.message,
                title=f"[bold]📦 {key}[/bold]",
                border_style="green",
                padding=(0, 1),
            )
        )

        if not auto_yes:
            ok = Confirm.ask(f"[bold]Commit group '{key}'?[/bold]", default=True)
            if not ok:
                console.print(f"  [dim]Skipping {key}[/dim]")
                continue

        # Commit just these files
        commit_args = ["commit", "-m", result.message, "--"] + group_files
        if signoff:
            commit_args.insert(1, "--signoff")
        if no_verify:
            commit_args.insert(1, "--no-verify")

        # First unstage everything, then stage only this group
        # Use git rm --cached for initial commits (no HEAD), git reset otherwise
        reset_result = sp.run(["git", "reset", "HEAD", "--"], capture_output=True, creationflags=0x08000000)
        if reset_result.returncode != 0:
            # Initial commit: no HEAD to reset from, unstage individually
            # Only unstage files that are NOT in this group and are still staged
            currently_staged = sp.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True, text=True, creationflags=0x08000000,
            )
            staged_list = [f for f in currently_staged.stdout.strip().split("\n") if f]
            for staged_file in staged_list:
                if staged_file not in group_files:
                    sp.run(["git", "rm", "--cached", staged_file], capture_output=True, creationflags=0x08000000)
        sp.run(["git", "add", "--"] + group_files, capture_output=True, creationflags=0x08000000)

        out = sp.run(
            ["git"] + commit_args,
            capture_output=True, text=True,
            creationflags=0x08000000,
        )
        if out.returncode != 0:
            console.print(f"  [red]✗ Commit failed: {out.stderr}[/red]")
            # Re-stage only this group's files on failure
            sp.run(["git", "add", "--"] + group_files, capture_output=True, creationflags=0x08000000)
            continue
        console.print(f"  [green]✓ Committed {key}[/green]")

        save_history({
            "repo": get_repo_name(),
            "branch": branch,
            "style": commit_style,
            "message": result.message,
            "model": result.model,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "time_ms": result.time_ms,
        })

    # Re-stage any remaining files
    remaining = sp.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True,
        creationflags=0x08000000,
    )
    if not remaining.stdout.strip():
        console.print("\n[green]✓ All groups committed successfully.[/green]")
    else:
        console.print("\n[yellow]⚠ Some files remain staged. Run `aicommit` again or `git reset`.[/yellow]")


def _run_install_alias():
    """Install convenient git aliases for aicommit."""
    aliases = {
        "ci": "aicommit",
        "review": "aicommit --review",
        "squash": "aicommit --squash",
        "pr": "aicommit --pr",
        "changelog": "aicommit --changelog",
    }

    console.print(Panel(
        "[bold]🔧 Installing git aliases[/bold]\n\n"
        "This adds convenient shortcuts like `git ci` for `aicommit`.",
        border_style="cyan",
    ))

    installed = 0
    for alias, command in aliases.items():
        try:
            sp.run(
                ["git", "config", "--global", f"alias.{alias}", command],
                capture_output=True, text=True,
                creationflags=0x08000000,
            )
            console.print(f"  [green]✓[/green] git {alias} → {command}")
            installed += 1
        except Exception as e:
            console.print(f"  [red]✗ Failed to install 'git {alias}': {e}[/red]")

    if installed:
        console.print(f"\n[green]✓ {installed} aliases installed. Try: [bold]git ci[/bold][/green]")
    else:
        console.print("[red]✗ No aliases were installed.[/red]")


def _run_uninstall_alias():
    """Remove aicommit git aliases."""
    aliases = ["ci", "review", "squash", "pr", "changelog"]
    for alias in aliases:
        sp.run(
            ["git", "config", "--global", "--unset", f"alias.{alias}"],
            capture_output=True, creationflags=0x08000000,
        )
    console.print("[green]✓ aicommit git aliases removed.[/green]")


def _run_rebase_mode(base: str, reword_all: bool, style: str, language_override: str, hint: str, auto_yes: bool):
    """Interactive rebase: regenerate commit messages for a range of commits.

    Flow:
    1. Determine base (auto-detect from remote tracking branch if not given).
    2. List commits from base..HEAD.
    3. For each commit, show current message and generate a new one.
    4. User picks which commits to reword (or --rebase-all for all).
    5. Apply reworded messages via sequential `git rebase -i`.
    """
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

    # Determine base commit
    if base:
        base_ref = base
    else:
        # Auto-detect from remote tracking branch
        try:
            upstream = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
            base_ref = upstream if upstream else None
        except GitErr:
            base_ref = None

        if not base_ref:
            # Fallback: use origin/main or origin/master
            for candidate in ["origin/main", "origin/master", "main", "master"]:
                try:
                    run_git(["rev-parse", "--verify", candidate])
                    base_ref = candidate
                    break
                except GitErr:
                    continue

        if not base_ref:
            console.print("[red]✗ Could not determine base. Use --rebase-base BRANCH.[/red]")
            sys.exit(1)

    # Get commits in range
    try:
        commits = get_commits_in_range(base_ref)
    except GitErr as e:
        console.print(f"[red]✗ Failed to get commits: {e}[/red]")
        sys.exit(1)

    if not commits:
        console.print(f"[yellow]ℹ No commits between {base_ref} and HEAD.[/yellow]")
        return

    commit_style = style or config["commit"]["style"]
    language = language_override or config["commit"]["language"]

    # Show commits
    console.print()
    console.print(f"[bold]🔄 Interactive Rebase: {base_ref}..HEAD[/bold]")
    console.print(f"[dim]{len(commits)} commits to review[/dim]\n")

    for i, c in enumerate(commits, 1):
        console.print(f"  [bold cyan]{i}.[/bold cyan] [dim]{c['hash'][:8]}[/dim] {c['subject']}")
    console.print()

    # Determine which commits to reword
    if reword_all:
        to_reword = list(range(len(commits)))
    else:
        to_reword = []
        for i, c in enumerate(commits):
            if auto_yes:
                to_reword.append(i)
                continue
            ok = Confirm.ask(f"Reword commit {i+1}? ({c['subject'][:50]})", default=False)
            if ok:
                to_reword.append(i)

    if not to_reword:
        console.print("[dim]No commits selected. Exiting.[/dim]")
        return

    console.print(f"\n[bold]Rewording {len(to_reword)} commits...[/bold]\n")

    # Generate new messages for each selected commit
    reworded: list[tuple[int, str]] = []  # (commit_index, new_message)
    for idx in to_reword:
        c = commits[idx]
        console.print(f"[bold cyan]── Commit {idx+1}/{len(commits)}: {c['hash'][:8]} ──[/bold cyan]")
        console.print(f"  [dim]Old:[/dim] {c['subject']}")

        try:
            diff = get_commit_diff(c["hash"])
            files = get_commit_files(c["hash"])
            branch_type = infer_type_from_branch(get_branch_name())
            breaking = detect_breaking_changes(diff)

            with show_generating() as progress:
                task = progress.add_task("Generating...", total=None)
                try:
                    result = generate_commit_message(
                        diff=diff, style=commit_style, language=language,
                        hint=hint or f"Reword commit: {c['subject']}",
                        branch_hint=f"Branch: {get_branch_name()}, type: {branch_type}" if branch_type else "",
                        breaking_hint="BREAKING CHANGE DETECTED" if breaking else "",
                        file_list="\n".join(f"- {f}" for f in files),
                        max_tokens_override=500,
                    )
                except (GitErr, AIErr) as e:
                    progress.remove_task(task)
                    console.print(f"  [red]✗ Failed: {e}[/red]")
                    continue
                progress.remove_task(task)

            console.print(f"  [green]New:[/green] {result.message}")
            console.print(f"  [dim]Model: {result.model} | Tokens: {result.tokens_in}→{result.tokens_out} | {result.time_ms:.0f}ms[/dim]")

            if not auto_yes and not reword_all:
                ok = Confirm.ask("  Use this message?", default=True)
                if not ok:
                    console.print("  [dim]Skipped.[/dim]")
                    continue

            reworded.append((idx, result.message))
            console.print()

        except GitErr as e:
            console.print(f"  [red]✗ {e}[/red]")
            continue

    if not reworded:
        console.print("[yellow]No commits were reworded.[/yellow]")
        return

    # Apply reworded messages via sequential git rebase
    # Strategy: use GIT_SEQUENCE_EDITOR + GIT_EDITOR to reword each commit
    console.print(f"[bold]Applying {len(reworded)} reworded messages...[/bold]\n")

    import tempfile
    import stat as stat_mod

    success_count = 0
    fail_count = 0

    # Process in reverse order (oldest commit first) to avoid hash changes affecting later commits
    for idx, new_msg in reversed(reworded):
        c = commits[idx]
        short_hash = c["hash"][:7]

        # Write the new message to a temp file
        msg_fd, msg_path = tempfile.mkstemp(suffix=".txt", prefix="aicommit_reword_", text=True)
        try:
            with os.fdopen(msg_fd, "w", encoding="utf-8") as f:
                f.write(new_msg)

            # Create a GIT_EDITOR that replaces the message with our file content
            if platform.system() == "Windows":
                # Windows: batch script that copies our message over the commit msg file
                editor_script = tempfile.mktemp(suffix=".bat", prefix="aicommit_editor_")
                with open(editor_script, "w", encoding="utf-8") as f:
                    f.write('@echo off\n')
                    f.write('copy /Y "' + msg_path + '" "%1" >nul\n')
                git_editor = 'cmd /c "' + editor_script + '"'
            else:
                # Unix: shell script that copies our message
                editor_script = tempfile.mktemp(suffix=".sh", prefix="aicommit_editor_")
                with open(editor_script, "w", encoding="utf-8") as f:
                    f.write('#!/bin/sh\n')
                    f.write('cp "' + msg_path + '" "$1"\n')
                st = os.stat(editor_script)
                os.chmod(editor_script, st.st_mode | stat_mod.S_IEXEC)
                git_editor = editor_script

            # Create a GIT_SEQUENCE_EDITOR that marks the target commit as 'reword'
            if platform.system() == "Windows":
                seq_script = tempfile.mktemp(suffix=".bat", prefix="aicommit_seq_")
                with open(seq_script, "w", encoding="utf-8") as f:
                    f.write('@echo off\n')
                    f.write('powershell -Command "(Get-Content \"%1\") -replace \"^pick (' + short_hash + ')\", \"reword $1\" | Set-Content \"%1\""')
                git_seq_editor = 'cmd /c "' + seq_script + '"'
            else:
                seq_script = tempfile.mktemp(suffix=".sh", prefix="aicommit_seq_")
                sed_expr = 's/^pick ' + short_hash + '/reword ' + short_hash + '/'
                with open(seq_script, "w", encoding="utf-8") as f:
                    f.write('#!/bin/sh\n')
                    f.write('sed -i \'' + sed_expr + '\' "$1"\n')
                st = os.stat(seq_script)
                os.chmod(seq_script, st.st_mode | stat_mod.S_IEXEC)
                git_seq_editor = seq_script

            env = dict(os.environ)
            env['GIT_SEQUENCE_EDITOR'] = git_seq_editor
            env['GIT_EDITOR'] = git_editor

            result = sp.run(
                ["git", "rebase", "-i", c["hash"] + "^"],
                capture_output=True, text=True,
                env=env,
                creationflags=0x08000000 if platform.system() == "Windows" else 0,
            )

            if result.returncode == 0:
                success_count += 1
                console.print(f"  [green]✓[/green] {short_hash} → {new_msg[:50]}")
            else:
                fail_count += 1
                console.print(f"  [red]✗[/red] {short_hash}: {result.stderr.strip()[:80]}")
                # Abort the rebase on failure
                sp.run(["git", "rebase", "--abort"],
                       capture_output=True, creationflags=0x08000000)
                break
        finally:
            # Cleanup temp files
            for p in [msg_path]:
                try:
                    os.unlink(p)
                except OSError:
                    pass
            for p_name in ['editor_script', 'seq_script']:
                if p_name in dir():
                    p_val = locals()[p_name]
                    try:
                        os.unlink(p_val)
                    except (OSError, NameError):
                        pass

    console.print()
    if success_count:
        console.print(f"[green]✓ Reworded {success_count} commits successfully.[/green]")
    if fail_count:
        console.print(f"[red]✗ {fail_count} commits failed.[/red]")


if __name__ == "__main__":
    main()

