"""Configuration management for aicommit."""

import datetime
import json
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
HISTORY_FILE = CONFIG_DIR / "history.jsonl"

DEFAULT_CONFIG = {
    "api": {
        "endpoint": "https://api.deepseek.com/v1",
        "key": "",
        "model": "deepseek-chat",
        "provider": "openai",
        "temperature": 0.3,
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
      AICOMMIT_PROVIDER      → api.provider
      AICOMMIT_TEMPERATURE   → api.temperature
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
            "AICOMMIT_PROVIDER": ("provider", str),
            "AICOMMIT_TEMPERATURE": ("temperature", float),
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
        f'provider = "{_escape_toml_str(config["api"].get("provider", "openai"))}"',
        f'endpoint = "{_escape_toml_str(config["api"]["endpoint"])}"',
        f'key = "{_escape_toml_str(config["api"]["key"])}"',
        f'model = "{_escape_toml_str(config["api"]["model"])}"',
        f"temperature = {config['api'].get('temperature', 0.3)}",
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


def save_history(entry: dict) -> None:
    """Append a commit history entry as JSON lines."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    entry["timestamp"] = datetime.datetime.now().isoformat()
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_history(limit: int = 50) -> list[dict]:
    """Load recent commit history entries."""
    if not HISTORY_FILE.exists():
        return []
    entries = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries[-limit:]


def setup_wizard() -> dict:
    """Interactive setup wizard for first-time users."""
    console.print()
    console.print(
        Panel.fit(
            Text("🚀 Welcome to aicommit!\n\n"
                 "Let's set up your AI provider in 4 steps.\n"
                 "Press Enter to accept defaults.",
                 style="bold cyan"),
            title="First Time Setup",
            border_style="cyan",
        )
    )

    config = DEFAULT_CONFIG.copy()

    # Step 1: API Provider
    console.print("\n[bold]Step 1/4: Choose AI Provider[/bold]")
    console.print("  1. DeepSeek (free tier, recommended)")
    console.print("  2. OpenAI")
    console.print("  3. Anthropic Claude")
    console.print("  4. Ollama (local)")
    console.print("  5. Custom (OpenAI-compatible)")
    choice = Prompt.ask("  Your choice", choices=["1","2","3","4","5"], default="1")

    if choice == "1":
        config["api"]["provider"] = "openai"
        config["api"]["endpoint"] = "https://api.deepseek.com/v1"
        config["api"]["model"] = "deepseek-chat"
    elif choice == "2":
        config["api"]["provider"] = "openai"
        config["api"]["endpoint"] = "https://api.openai.com/v1"
        config["api"]["model"] = "gpt-4o-mini"
    elif choice == "3":
        config["api"]["provider"] = "anthropic"
        config["api"]["endpoint"] = "https://api.anthropic.com/v1"
        config["api"]["model"] = "claude-3-5-haiku-latest"
    elif choice == "4":
        config["api"]["provider"] = "openai"
        config["api"]["endpoint"] = "http://localhost:11434/v1"
        config["api"]["model"] = "llama3.2"
    else:
        config["api"]["provider"] = "openai"
        config["api"]["endpoint"] = Prompt.ask(
            "  API endpoint URL", default="https://api.deepseek.com/v1"
        )
        config["api"]["model"] = Prompt.ask("  Model name", default="deepseek-chat")

    # Step 2: API Key
    console.print(f"\n[bold]Step 2/4: API Key[/bold]")
    key = Prompt.ask("  Your API key", password=True)
    if key:
        config["api"]["key"] = key
    else:
        console.print("  [yellow]⚠ No key provided. You can add it later with: aicommit --config[/yellow]")

    # Step 3: Commit style
    console.print(f"\n[bold]Step 3/4: Commit Style[/bold]")
    console.print("  1. [green]conventional[/green] — feat: add login page (industry standard)")
    console.print("  2. [yellow]emoji[/yellow]       — ✨ Add login page (fun & expressive)")
    console.print("  3. [dim]simple[/dim]       — Add login page (short & sweet)")
    console.print("  4. [blue]detailed[/blue]     — Multi-line with bullet points")
    style_choice = Prompt.ask("  Your style", choices=["1","2","3","4"], default="1")
    config["commit"]["style"] = ["conventional", "emoji", "simple", "detailed"][int(style_choice)-1]

    # Step 4: Temperature
    console.print(f"\n[bold]Step 4/4: Creativity[/bold]")
    console.print("  Lower (0.1-0.3) = more predictable, Higher (0.5-0.8) = more creative")
    temp = Prompt.ask("  Temperature", default="0.3")
    try:
        config["api"]["temperature"] = float(temp)
    except ValueError:
        config["api"]["temperature"] = 0.3

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
