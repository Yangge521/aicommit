"""Rich terminal rendering utilities."""

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from .config import load_config

console = Console()


def show_config_status(config: dict):
    """Show current configuration status."""
    has_key = bool(config["api"]["key"])
    key_status = "[green]✓ configured[/green]" if has_key else "[red]✗ missing[/red]"
    endpoint = config["api"]["endpoint"]
    model = config["api"]["model"]
    style = config["commit"]["style"]
    language = config["commit"]["language"]
    auto = "[green]yes[/green]" if config["commit"]["auto_confirm"] else "[dim]no[/dim]"
    signoff = "[green]yes[/green]" if config["commit"].get("signoff") else "[dim]no[/dim]"
    no_verify = "[green]yes[/green]" if config["commit"].get("no_verify") else "[dim]no[/dim]"

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Provider:", f"[bold]{endpoint}[/bold]")
    table.add_row("Model:", f"[bold]{model}[/bold]")
    table.add_row("API Key:", key_status)
    table.add_row("Style:", f"[bold]{style}[/bold]")
    table.add_row("Language:", f"[bold]{language}[/bold]")
    table.add_row("Auto-confirm:", auto)
    table.add_row("Signoff:", signoff)
    table.add_row("No-verify:", no_verify)

    console.print(
        Panel(table, title="[bold]Configuration[/bold]", border_style="blue")
    )


def show_generating():
    """Return a progress context for generation animation."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]AI is crafting your commit message...[/bold cyan]"),
        console=console,
        transient=True,
    )


def show_message_preview(message: str, style_name: str, scope: str = ""):
    """Show the generated commit message with metadata."""
    console.print()
    style_label = {
        "conventional": "📐 Conventional",
        "emoji": "😄 Gitmoji",
        "simple": "📝 Simple",
        "detailed": "📋 Detailed",
    }.get(style_name, style_name)

    title = f"[bold]{style_label}[/bold]"
    if scope:
        title += f" [dim](scope: {scope})[/dim]"

    console.print(
        Panel(
            message,
            title=title,
            border_style="green",
            padding=(1, 2),
        )
    )


def show_stats(tokens_in: int, tokens_out: int, time_ms: float, model: str):
    """Show token usage and timing stats."""
    console.print(
        f"[dim]Model: {model} | "
        f"Tokens: {tokens_in}→{tokens_out} | "
        f"Time: {time_ms:.0f}ms[/dim]"
    )


def show_success(message: str):
    """Show commit success."""
    first_line = message.split("\n")[0]
    console.print(f"\n[green bold]✓ Committed![/green bold] [dim]{first_line}[/dim]")
    console.print()


def show_dry_run(message: str):
    """Show dry run notice."""
    console.print("\n[yellow]ℹ Dry run — nothing was committed.[/yellow]")
    console.print()


def show_diff_summary(files: list[str], stats: str, scope: str = "",
                      branch_type: str = "", breaking: bool = False):
    """Show summary of staged changes."""
    if files:
        console.print(f"[dim]Staged: {len(files)} file(s)[/dim]", end="")
    else:
        console.print(f"[dim]Analyzing last commit[/dim]", end="")

    if scope:
        console.print(f" [cyan]→ scope: {scope}[/cyan]", end="")

    if branch_type:
        console.print(f" [yellow]→ branch suggests: {branch_type}[/yellow]", end="")

    if breaking:
        console.print(f" [red bold]⚠ BREAKING CHANGE DETECTED[/red bold]", end="")

    console.print()

    if stats:
        for line in stats.strip().split("\n")[:5]:
            console.print(f"  [dim]{line}[/dim]")


def show_warning(msg: str):
    """Show a warning message."""
    console.print(f"[yellow]⚠ {msg}[/yellow]")


def confirm_commit(message: str) -> bool:
    """Ask user to confirm the commit."""
    console.print()
    return Confirm.ask(
        "[bold]Commit with this message?[/bold]",
        default=True,
    )


def show_hook_installed(path: str):
    """Show hook installation success."""
    console.print(
        Panel(
            f"Hook installed at: [bold]{path}[/bold]\n\n"
            "Now every `git commit` will automatically\n"
            "pre-fill the commit message with an AI suggestion.\n\n"
            "Run [bold]aicommit --uninstall-hook[/bold] to remove.",
            title="[green bold]✓ Git Hook Installed[/green bold]",
            border_style="green",
        )
    )


def show_hook_uninstalled(path: str):
    """Show hook removal success."""
    console.print(f"\n[green]✓ Hook removed from {path}[/green]\n")


def show_reset_done():
    """Show config reset confirmation."""
    console.print("[green]✓ Configuration reset to defaults.[/green]")


def show_status():
    """Alias for show_config_status — used by --status flag."""
    show_config_status(load_config())

