# aicommit

> 🚀 **AI writes your git commit messages. You ship code.**

[![PyPI](https://img.shields.io/badge/pypi-v1.0.0-blue)](https://pypi.org/project/aicommit/)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Stop staring at your terminal wondering what commit message to write. **aicommit** reads your staged changes, understands your code, and generates the perfect commit message — in any style you want.

<p align="center">
  <img src="https://raw.githubusercontent.com/Ghy/aicommit/main/demo.svg" width="700" alt="aicommit demo">
</p>

## ✨ Features

- 🧠 **AI-Powered** — Uses DeepSeek (free), OpenAI, or any OpenAI-compatible API
- 🎨 **4 Commit Styles** — Conventional Commits, Gitmoji, Simple, Detailed
- ⚡ **Zero Config** — Works out of the box with DeepSeek's free tier
- 🎯 **Context-Aware** — Analyzes your recent commits, branch name, and diff
- 💬 **Interactive** — Preview before committing, or auto-confirm with `-y`
- 🖥️ **Beautiful CLI** — Rich terminal output with progress animations
- 🔌 **Any LLM** — Works with OpenAI, DeepSeek, Ollama, Groq, and more

## 📦 Installation

```bash
pip install aicommit
```

Or with pipx (recommended for CLI tools):

```bash
pipx install aicommit
```

## 🚀 Quick Start

```bash
# 1. Setup (one-time)
aicommit --config

# 2. Stage your changes
git add .

# 3. Let AI write your commit
aicommit
```

That's it! The AI analyzes your diff and generates a commit message. Review and confirm, or use `-y` to skip confirmation.

## 🎨 Commit Styles

| Style | Example | Best For |
|-------|---------|----------|
| `conventional` (default) | `feat(auth): add OAuth2 login flow` | Teams, CI/CD, changelogs |
| `emoji` | `✨ Add OAuth2 login flow` | Personal projects, fun repos |
| `simple` | `Add OAuth2 login flow` | Quick commits |
| `detailed` | Multi-line with bullet points | Complex changes |

```bash
aicommit -s emoji      # Use emoji style
aicommit -s detailed   # Detailed with bullet points
aicommit -s simple     # Short and sweet
```

## 📖 Usage

```bash
# Basic usage
aicommit                # Generate and confirm

# Skip confirmation
aicommit -y

# Preview without committing
aicommit --dry-run

# Provide additional context
aicommit -m "fixing race condition in websocket handler"

# Use a specific style
aicommit -s conventional

# Reconfigure
aicommit --config

# Show current config
aicommit --status
```

## 🔧 Configuration

aicommit stores config at `~/.aicommit/config.toml`:

```toml
# API settings
endpoint = "https://api.deepseek.com/v1"
key = "sk-your-api-key"
model = "deepseek-chat"

# Commit preferences
style = "conventional"
language = "auto"
max_diff_lines = 200
auto_confirm = false
```

### Supported AI Providers

| Provider | Free Tier | Setup |
|----------|-----------|-------|
| **DeepSeek** | ✅ 500M tokens | [Get Key](https://platform.deepseek.com/api_keys) |
| OpenAI | ❌ Pay-as-you-go | [Get Key](https://platform.openai.com/api-keys) |
| Ollama (local) | ✅ Free | `endpoint="http://localhost:11434/v1"` |
| Groq | ✅ Free tier | [Get Key](https://console.groq.com/keys) |
| Any OpenAI-compatible | — | Set `endpoint` to your API |

### Using Local Models (Ollama)

```bash
# Start Ollama
ollama pull llama3.2

# Configure aicommit
aicommit --config
# → Choose "Custom"
# → Endpoint: http://localhost:11434/v1
# → Model: llama3.2
```

## 🤔 Why aicommit?

**The Problem:** Writing good commit messages is tedious. Most developers either write vague messages ("update", "fix") or spend too long crafting the perfect one.

**The Solution:** Let AI do it. aicommit understands your code changes and generates messages that are:
- **Accurate** — Based on actual diff analysis
- **Consistent** — Follows your team's conventions
- **Fast** — Generated in seconds
- **Customizable** — Your style, your rules

## 🧪 Development

```bash
git clone https://github.com/Ghy/aicommit.git
cd aicommit
pip install -e ".[dev]"
```

## 📝 License

MIT © Ghy

---

<p align="center">
  <sub>Built with ❤️ for developers who'd rather write code than commit messages</sub>
</p>
