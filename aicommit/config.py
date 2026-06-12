"""Configuration management for aicommit."""

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.text import Text

console = Console()

CONFIG_DIR = Path.home() / ".aicommit"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = {
    "api": {
        "endpoint": "https://api.deepseek.com/v1",
        "key": "",
        "model": "deepseek-chat",
    },
    "commit": {
        "style": "conventional",
        "language": "auto",
        "max_diff_lines": 200,
        "auto_confirm": False,
        "signoff": False,
        "no_verify": False,
    },
}


def load_config() -> dict:
    """Load config from file, overriding with environment variables.

    Environment variables (highest priority):
      AICOMMIT_API_KEY       → api.key
      AICOMMIT_ENDPOINT      → api.endpoint
      AICOMMIT_MODEL         → api.model
      AICOMMIT_STYLE         → commit.style
      AICOMMIT_LANGUAGE      → commit.language
      AICOMMIT_MAX_DIFF_LINES → commit.max_diff_lines
    """
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "rb") as f:
                loaded = tomllib.load(f)
            config = DEFAULT_CONFIG.copy()
            _deep_merge(config, loaded)
        except Exception:
            console.print("[yellow]⚠ Config file corrupted, using defaults[/yellow]")
            config = DEFAULT_CONFIG.copy()
    else:
        config = DEFAULT_CONFIG.copy()

    # Override with environment variables
    env_map = {
        "api": {
            "AICOMMIT_API_KEY": ("key", str),
            "AICOMMIT_ENDPOINT": ("endpoint", str),
            "AICOMMIT_MODEL": ("model", str),
        },
        "commit": {
            "AICOMMIT_STYLE": ("style", str),
            "AICOMMIT_LANGUAGE": ("language", str),
            "AICOMMIT_MAX_DIFF_LINES": ("max_diff_lines", int),
        },
    }
    for section, vars in env_map.items():
        for env_key, (config_key, cast) in vars.items():
            val = os.environ.get(env_key)
            if val is not None:
                config[section][config_key] = cast(val)

    return config


def save_config(config: dict) -> None:
    """Save config to file using proper TOML format."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "# aicommit configuration",
        "# Run `aicommit --config` to reconfigure interactively.",
        "",
        "[api]",
        f'endpoint = "{_escape_toml_str(config["api"]["endpoint"])}"',
        f'key = "{_escape_toml_str(config["api"]["key"])}"',
        f'model = "{_escape_toml_str(config["api"]["model"])}"',
        "",
        "[commit]",
        f'style = "{_escape_toml_str(config["commit"]["style"])}"',
        f'language = "{_escape_toml_str(config["commit"]["language"])}"',
        f"max_diff_lines = {config['commit']['max_diff_lines']}",
        f"auto_confirm = {str(config['commit']['auto_confirm']).lower()}",
        f"signoff = {str(config['commit'].get('signoff', False)).lower()}",
        f"no_verify = {str(config['commit'].get('no_verify', False)).lower()}",
        "",
    ]
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _escape_toml_str(s: str) -> str:
    """Escape a string for safe TOML embedding."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def reset_config() -> None:
    """Reset configuration to defaults."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    save_config(DEFAULT_CONFIG.copy())


def setup_wizard() -> dict:
    """Interactive setup wizard for first-time users."""
    console.print()
    console.print(
        Panel.fit(
            Text("🚀 Welcome to aicommit!\n\n"
                 "Let's set up your AI provider in 3 steps.\n"
                 "Press Enter to accept defaults.",
                 style="bold cyan"),
            title="First Time Setup",
            border_style="cyan",
        )
    )

    config = DEFAULT_CONFIG.copy()

    # Step 1: API Provider
    console.print("\n[bold]Step 1/3: Choose AI Provider[/bold]")
    console.print("  1. DeepSeek (free tier, recommended)")
    console.print("  2. OpenAI")
    console.print("  3. Custom (any OpenAI-compatible API)")
    choice = Prompt.ask("  Your choice", choices=["1", "2", "3"], default="1")

    if choice == "1":
        config["api"]["endpoint"] = "https://api.deepseek.com/v1"
        config["api"]["model"] = "deepseek-chat"
    elif choice == "2":
        config["api"]["endpoint"] = "https://api.openai.com/v1"
        config["api"]["model"] = "gpt-4o-mini"
    else:
        config["api"]["endpoint"] = Prompt.ask(
            "  API endpoint URL", default="https://api.deepseek.com/v1"
        )
        config["api"]["model"] = Prompt.ask("  Model name", default="deepseek-chat")

    # Step 2: API Key
    console.print(f"\n[bold]Step 2/3: API Key[/bold]")
    console.print(f"  💡 Get a free DeepSeek key: https://platform.deepseek.com/api_keys")
    key = Prompt.ask("  Your API key", password=True)
    if key:
        config["api"]["key"] = key
    else:
        console.print("  [yellow]⚠ No key provided. You can add it later with: aicommit --config[/yellow]")

    # Step 3: Commit style
    console.print(f"\n[bold]Step 3/3: Commit Style[/bold]")
    console.print("  1. [green]conventional[/green] — feat: add login page (industry standard)")
    console.print("  2. [yellow]emoji[/yellow]       — ✨ Add login page (fun & expressive)")
    console.print("  3. [dim]simple[/dim]       — Add login page (short & sweet)")
    console.print("  4. [blue]detailed[/blue]     — Multi-line with bullet points")
    style_choice = Prompt.ask("  Your style", choices=["1", "2", "3", "4"], default="1")
    config["commit"]["style"] = ["conventional", "emoji", "simple", "detailed"][int(style_choice) - 1]

    save_config(config)
    console.print("\n[green]✓ Setup complete! Run `aicommit` in any git repo to get started.[/green]\n")
    return config


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
