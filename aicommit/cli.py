"""CLI entry point for aicommit."""

import sys
from pathlib import Path

import click
from rich.panel import Panel
from rich.prompt import Confirm

from .ai import AIError, generate_commit_message
from .config import (
    load_config, save_config, setup_wizard, reset_config,
)
from .conventional import (
    auto_fix_conventional,
    conventional_to_emoji,
    validate_conventional,
)
from .git_utils import (
    GitError,
    amend_commit,
    commit,
    detect_breaking_changes,
    detect_scope,
    get_branch_name,
    get_last_commit_diff,
    get_last_commit_message,
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
    show_reset_done,
    show_stats,
    show_success,
    show_warning,
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
    "--scope",
    default=None,
    help="Override auto-detected scope (e.g., 'auth', 'api')",
)
@click.option(
    "--signoff", "--sign",
    is_flag=True,
    help="Add Signed-off-by trailer to commit",
)
@click.option(
    "--no-verify", "-n",
    is_flag=True,
    help="Skip pre-commit and commit-msg hooks",
)
@click.option(
    "--last",
    is_flag=True,
    help="Regenerate message for the most recent commit (requires --amend)",
)
@click.option(
    "--amend",
    is_flag=True,
    help="Amend the last commit with the generated message",
)
@click.option(
    "-t", "--template",
    type=click.Path(exists=True),
    default=None,
    help="Custom prompt template file (Python format string)",
)
@click.option(
    "--config",
    "run_config",
    is_flag=True,
    help="Open configuration wizard",
)
@click.option(
    "--reset-config",
    is_flag=True,
    help="Reset all configuration to defaults",
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
@click.option(
    "--pr",
    is_flag=True,
    help="Generate a pull request description from branch diff",
)
@click.option(
    "--pr-base",
    default="main",
    help="Base branch for PR diff (default: main)",
)
@click.option(
    "--validate",
    is_flag=True,
    help="Validate generated message against Conventional Commits spec",
)
@click.option(
    "--auto-fix",
    is_flag=True,
    help="Auto-fix conventional commit format if needed",
)
@click.option(
    "--completion",
    type=click.Choice(["bash", "zsh", "fish", "powershell"]),
    default=None,
    help="Generate shell completion script",
)
@click.version_option(version="1.2.0", prog_name="aicommit")
def main(style, auto_yes, dry_run, message, edit, scope, signoff, no_verify,
         last, amend, template, run_config, reset_config_flag, status,
         hook_file, install_hook_flag, uninstall_hook_flag,
         pr, pr_base, validate, auto_fix, completion):
    """AI-powered git commit message generator.

    Run `aicommit` in any git repo with staged changes.
    The AI will analyze your diff and generate a meaningful commit message.

    \b
    Examples:
      aicommit                       # Generate and commit with confirmation
      aicommit -y                    # Skip confirmation
      aicommit -s emoji              # Use emoji style
      aicommit --dry-run             # Preview without committing
      aicommit -m "urgent fix"       # Provide context hint
      aicommit -e                    # Edit message before committing
      aicommit --scope auth          # Set scope manually
      aicommit --signoff             # Add Signed-off-by
      aicommit --last --amend        # Regenerate last commit message
      aicommit --config              # Setup API key and preferences
      aicommit --reset-config        # Reset to defaults
      aicommit --install-hook        # Install as git hook
    """
    # ── Hook mode ──────────────────────────────────────────
    if hook_file:
        _run_hook_mode(hook_file)
        return

    # ── Completion mode ────────────────────────────────────
    if completion:
        _print_completion(completion)
        return

    # ── PR mode ────────────────────────────────────────────
    if pr:
        _run_pr_mode(pr_base, message)
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

    # ── Config/Reset modes ─────────────────────────────────
    if reset_config_flag:
        reset_config()
        console.print("[green]✓ Configuration reset to defaults.[/green]")
        return

    if run_config:
        config = setup_wizard()
        show_config_status(config)
        return

    if status:
        config = load_config()
        show_config_status(config)
        return

    # ── Validate environment ───────────────────────────────
    if not is_git_repo():
        console.print("[red]✗ Not a git repository. Run this inside a git repo.[/red]")
        sys.exit(1)

    is_amend_mode = amend or last

    if is_amend_mode:
        # Amend/Last mode — uses the most recent commit's diff
        if last and not amend:
            console.print("[yellow]ℹ --last requires --amend. Enabling amend mode.[/yellow]")
        if not has_staged_changes():
            show_warning("No staged changes. Using last commit's changes for regeneration.")
    else:
        if not has_staged_changes():
            console.print("[yellow]ℹ No staged changes. Use `git add` first.[/yellow]")
            console.print("[dim]Tip: use `aicommit --last --amend` to rewrite the last commit message.[/dim]")
            sys.exit(0)

    # ── Load config ────────────────────────────────────────
    config = load_config()
    if not config["api"]["key"]:
        console.print("[yellow]⚠ First time? Let's set up your AI provider.[/yellow]")
        config = setup_wizard()
        if not config["api"]["key"]:
            console.print("[red]✗ API key required. Run `aicommit --config` to set up.[/red]")
            sys.exit(1)

    # ── Load custom template ───────────────────────────────
    custom_template = None
    if template:
        try:
            custom_template = Path(template).read_text(encoding="utf-8")
            console.print(f"[dim]Using custom template: {template}[/dim]")
        except Exception as e:
            console.print(f"[red]✗ Failed to read template file: {e}[/red]")
            sys.exit(1)

    # ── Gather git context ─────────────────────────────────
    try:
        repo = get_repo_name()
        branch = get_branch_name()
        recent = get_recent_commits(5)

        if is_amend_mode:
            files = []
            diff = get_last_commit_diff(max_lines=config["commit"]["max_diff_lines"])
            stats = ""
            old_message = get_last_commit_message()
            console.print(f"[dim]Amending: {old_message.split(chr(10))[0]}[/dim]")
            scope = scope or None
            branch_type = infer_type_from_branch(branch)
            breaking = detect_breaking_changes(diff)
        else:
            files = get_staged_files()
            diff = get_staged_diff(
                max_lines=config["commit"]["max_diff_lines"],
                skip_noise=True,
            )
            stats = get_staged_stats()
            scope = scope or detect_scope(files)
            branch_type = infer_type_from_branch(branch)
            breaking = detect_breaking_changes(diff)
            file_list = "\n".join(f"  - {f}" for f in files[:30])
            if len(files) > 30:
                file_list += f"\n  ... and {len(files) - 30} more files"

        # Build hints for AI
        branch_hint = ""
        if branch_type:
            branch_hint = (
                f"Branch name '{branch}' suggests this is a '{branch_type}' type change."
            )
            if scope:
                branch_hint += f" Use scope: {scope}."

        breaking_hint = ""
        if breaking:
            breaking_hint = (
                "⚠ This diff contains breaking changes! "
                "Use '!' after type/scope (e.g., feat(api)!: ...) "
                "and add BREAKING CHANGE: footer if using conventional style."
            )

        file_list_str = ""
        if not is_amend_mode:
            file_list_str = file_list

        # Show summary
        show_diff_summary(
            files if not is_amend_mode else [],
            stats,
            scope=scope or "",
            branch_type=branch_type or "",
            breaking=breaking,
        )
        console.print(
            f"[dim]Repo: {repo} | Branch: {branch}"
            f"{' | Mode: amend' if is_amend_mode else ''}[/dim]"
        )

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
                file_list=file_list_str,
                template=custom_template,
            )
            progress.remove_task(task)

        # ── Show result ─────────────────────────────────────
        commit_msg = result.message

        # ── Conventional validation ─────────────────────────
        if commit_style == "conventional":
            is_valid, err = validate_conventional(commit_msg)
            if validate and not is_valid:
                console.print(f"[yellow]⚠ Validation: {err}[/yellow]")
            if auto_fix and not is_valid:
                fixed = auto_fix_conventional(commit_msg)
                if fixed != commit_msg:
                    console.print(f"[yellow]🔧 Auto-fixed to conventional format[/yellow]")
                    show_message_preview(fixed, commit_style, scope=scope or "")
                    if not auto_yes and not config["commit"]["auto_confirm"]:
                        if Confirm.ask("[bold]Use fixed message?[/bold]", default=True):
                            commit_msg = fixed
                    else:
                        commit_msg = fixed

        show_message_preview(commit_msg, commit_style, scope=scope or "")
        show_stats(result.tokens_in, result.tokens_out, result.time_ms, result.model)

        # ── Edit mode ───────────────────────────────────────
        commit_msg = commit_msg
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

        # ── Confirm and execute ─────────────────────────────
        do_signoff = signoff or config["commit"].get("signoff", False)
        do_no_verify = no_verify or config["commit"].get("no_verify", False)

        if auto_yes or config["commit"]["auto_confirm"] or confirm_commit(commit_msg):
            if is_amend_mode:
                amend_commit(commit_msg, signoff=do_signoff, no_verify=do_no_verify)
                console.print(f"\n[green bold]✓ Amended![/green bold] [dim]{commit_msg.split(chr(10))[0]}[/dim]\n")
            else:
                commit(commit_msg, signoff=do_signoff, no_verify=do_no_verify)
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


def _print_completion(shell: str):
    """Print shell completion script to stdout."""
    # Build completion script using Click's auto-completion infrastructure
    # User should run: eval "$(aicommit --completion bash)"
    prog = "aicommit"

    if shell == "bash":
        print(f'''# aicommit bash completion
_aicommit_completion() {{
    local IFS=$'\\n'
    COMPREPLY=()
    local cur="${{COMP_WORDS[COMP_CWORD]}}"
    if [[ $cur == -* ]]; then
        COMPREPLY=( $(compgen -W "-s --style -y --yes --dry-run -m --message -e --edit --scope \\
            --signoff --sign --no-verify -n --last --amend -t --template \\
            --config --reset-config --status --install-hook --uninstall-hook \\
            --pr --pr-base --validate --auto-fix --completion --help --version" -- "$cur") )
    fi
    return 0
}}
complete -F _aicommit_completion {prog}''')
    elif shell == "zsh":
        print(f'''#compdef {prog}
_aicommit() {{
    local -a opts
    opts=(
        '-s[Commit message style]:style:(conventional emoji simple detailed)'
        '-y[Skip confirmation]'
        '--dry-run[Preview without committing]'
        '-m[Additional context hint]:hint:'
        '-e[Edit before committing]'
        '--scope[Override scope]:scope:'
        '--signoff[Add Signed-off-by]'
        '--no-verify[Skip pre-commit hooks]'
        '--last[Regenerate last commit message]'
        '--amend[Amend last commit]'
        '-t[Custom template file]:file:_files'
        '--config[Open config wizard]'
        '--reset-config[Reset to defaults]'
        '--status[Show current config]'
        '--install-hook[Install git hook]'
        '--uninstall-hook[Remove git hook]'
        '--pr[Generate PR description]'
        '--pr-base[Base branch for PR]:branch:'
        '--validate[Validate conventional format]'
        '--auto-fix[Auto-fix conventional format]'
        '--completion[Shell completion]:shell:(bash zsh fish powershell)'
        '--help[Show help]'
        '--version[Show version]'
    )
    _describe 'command' opts
}}
compdef _aicommit {prog}''')
    elif shell == "fish":
        print(f'''# aicommit fish completion
complete -c {prog} -s s -l style -x -a "conventional emoji simple detailed" -d "Commit message style"
complete -c {prog} -s y -l yes -d "Skip confirmation and commit immediately"
complete -c {prog} -l dry-run -d "Show generated message without committing"
complete -c {prog} -s m -l message -x -d "Additional context/hint for the AI"
complete -c {prog} -s e -l edit -d "Open generated message in EDITOR before committing"
complete -c {prog} -l scope -x -d "Override auto-detected scope"
complete -c {prog} -l signoff -l sign -d "Add Signed-off-by trailer to commit"
complete -c {prog} -s n -l no-verify -d "Skip pre-commit and commit-msg hooks"
complete -c {prog} -l last -d "Regenerate message for the most recent commit"
complete -c {prog} -l amend -d "Amend the last commit"
complete -c {prog} -s t -l template -r -d "Custom prompt template file"
complete -c {prog} -l config -d "Open configuration wizard"
complete -c {prog} -l reset-config -d "Reset all configuration to defaults"
complete -c {prog} -l status -d "Show current configuration"
complete -c {prog} -l install-hook -d "Install as git prepare-commit-msg hook"
complete -c {prog} -l uninstall-hook -d "Remove aicommit git hook"
complete -c {prog} -l pr -d "Generate a pull request description"
complete -c {prog} -l pr-base -x -d "Base branch for PR diff"
complete -c {prog} -l validate -d "Validate generated message against Conventional Commits"
complete -c {prog} -l auto-fix -d "Auto-fix conventional commit format"
complete -c {prog} -l completion -x -a "bash zsh fish powershell" -d "Generate shell completion script"
complete -c {prog} -l help -d "Show help"
complete -c {prog} -l version -d "Show version"''')
    elif shell == "powershell":
        print(f'''# aicommit PowerShell completion
Register-ArgumentCompleter -Native -CommandName {prog} -ScriptBlock {{
    param($wordToComplete, $commandAst, $cursorPosition)
    $opts = @(
        '-s', '-y', '--dry-run', '-m', '-e', '--scope', '--signoff', '--sign',
        '--no-verify', '-n', '--last', '--amend', '-t', '--template',
        '--config', '--reset-config', '--status',
        '--install-hook', '--uninstall-hook', '--pr', '--pr-base',
        '--validate', '--auto-fix', '--completion', '--help', '--version'
    )
    $opts | Where-Object {{ $_ -like "$wordToComplete*" }}
}}''')
    else:
        console.print(f"[red]Unknown shell: {shell}[/red]")
        sys.exit(1)


def _run_pr_mode(base_branch: str, hint: str):
    """Generate a PR description."""
    from .pr_generator import generate_pr_description
    from .ai import AIError as AIErr
    from .git_utils import GitError as GitErr

    if not is_git_repo():
        console.print("[red]✗ Not a git repository.[/red]")
        sys.exit(1)

    with show_generating() as progress:
        task = progress.add_task("", total=None)
        try:
            description = generate_pr_description(base_branch, hint=hint)
        except (GitErr, AIErr) as e:
            progress.remove_task(task)
            console.print(f"[red]✗ {e}[/red]")
            sys.exit(1)
        progress.remove_task(task)

    console.print()
    console.print(
        Panel(
            description,
            title="[bold]📋 Pull Request Description[/bold]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print("\n[dim]Copy the description above to your PR.[/dim]")


def _run_hook_mode(commit_msg_file: str):
    """Run in git hook mode — write AI message to commit msg file."""
    try:
        if not has_staged_changes():
            return

        config = load_config()
        if not config["api"]["key"]:
            return

        files = get_staged_files()
        diff = get_staged_diff(
            max_lines=config["commit"]["max_diff_lines"],
            skip_noise=True,
        )
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

        msg_path = Path(commit_msg_file)
        current = msg_path.read_text(encoding="utf-8") if msg_path.exists() else ""

        if current.strip():
            return  # Don't overwrite existing message

        msg_path.write_text(result.message + "\n", encoding="utf-8")

    except Exception:
        # Hook should never block a commit
        pass


if __name__ == "__main__":
    main()
