"""Rich terminal rendering utilities."""

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.text import Text

console = Console()


def show_welcome():
    """Show welcome banner."""
    console.print()


def show_config_status(config: dict):
    """Show current configuration status."""
    has_key = bool(config["api"]["key"])
    key_status = "[green]✓ configured[/green]" if has_key else "[red]✗ missing[/red]"
    endpoint = config["api"]["endpoint"]
    model = config["api"]["model"]
    style = config["commit"]["style"]

    console.print(
        Panel(
            f"  Provider: [bold]{endpoint}[/bold]\n"
            f"  Model:    [bold]{model}[/bold]\n"
            f"  API Key:  {key_status}\n"
            f"  Style:    [bold]{style}[/bold]",
            title="[bold]Config[/bold]",
            border_style="blue",
            padding=(1, 2),
        )
    )


def show_generating():
    """Return a progress context for generation animation."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]AI is crafting your commit message...[/bold cyan]"),
        console=console,
        transient=True,
    )


def show_message_preview(message: str, style_name: str):
    """Show the generated commit message with syntax highlighting."""
    console.print()
    console.print(
        Panel(
            message,
            title=f"[bold]Generated Message ({style_name} style)[/bold]",
            border_style="green",
            padding=(1, 2),
        )
    )


def show_success(message: str):
    """Show commit success."""
    first_line = message.split("\n")[0]
    console.print(f"\n[green bold]✓ Committed![/green bold] [dim]{first_line}[/dim]\n")


def show_dry_run(message: str):
    """Show dry run notice."""
    console.print("\n[yellow]ℹ Dry run — nothing was committed.[/yellow]\n")


def show_diff_summary(files: list[str], diff_size: int):
    """Show summary of staged changes."""
    console.print(
        f"[dim]Staged: {len(files)} file(s), {diff_size} chars of diff[/dim]"
    )


def confirm_commit(message: str) -> bool:
    """Ask user to confirm the commit."""
    console.print()
    return Confirm.ask(
        "[bold]Commit with this message?[/bold]",
        default=True,
    )
