# aicommit

> 🚀 **AI writes your git commit messages. You ship code.**

[![PyPI](https://img.shields.io/badge/pypi-v1.5.0-blue)](https://pypi.org/project/aicommit/)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-48%20passed-brightgreen)](.)

Stop staring at your terminal wondering what commit message to write. **aicommit** reads your staged changes, understands your code, and generates the perfect commit message — in any style you want.

## ✨ Features

- 🧠 **AI-Powered** — Uses DeepSeek, OpenAI, Anthropic, Ollama, or any compatible API
- 🎨 **4 Commit Styles** — Conventional Commits, Gitmoji, Simple, Detailed
- 🎯 **Smart Context** — Auto-detects scope, branch type, breaking changes, monorepo packages
- 🔍 **Branch-Aware** — Infers commit type from branch name (feat/xxx, fix/xxx)
- 💥 **Breaking Change Detection** — Flags breaking changes with `!`
- 📦 **Monorepo Support** — Detects package from directory structure
- 🌐 **Multi-Provider** — DeepSeek, OpenAI, Anthropic, Ollama, custom endpoints
- 🔎 **Code Review** — AI code review of staged changes
- 📋 **PR Description** — Generate pull request descriptions from branch diffs
- 📦 **Squash Messages** — Generate consolidated messages from commits
- 📝 **Changelog Generation** — Auto-generate changelog entries
- ⚙️ **Config Management** — Set/get config via CLI (`--set`, `--get`)
- 🚫 **.aicommitignore** — Per-project file/diff ignore patterns
- ✅ **Conventional Validation** — Validate and auto-fix conventional commits
- 🔄 **AI Retry** — Exponential backoff on API failures
- 🔤 **Shell Completions** — bash, zsh, fish, PowerShell
- 🪝 **Git Hook** — Install as prepare-commit-msg hook
- 📋 **Clipboard** — Auto-copy with `--copy`
- 🌍 **CI/CD Ready** — GitHub Action included, AICOMMIT_* env vars
- ✏️ **Edit Mode** — Edit message in $EDITOR before commit
- ⚡ **Auto-Stage** — `--stage` to auto-add files
- 🖥️ **Beautiful CLI** — Rich output with token stats and progress

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
# 1. Setup (one-time, 2 steps)
aicommit --init

# 2. Stage + generate + commit in one go
aicommit --stage -y

# Or step-by-step
git add .
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

## 🧠 Smart Context Analysis

aicommit doesn't just read your diff — it understands the context:

- **Scope Detection**: `src/auth/login.ts` + `src/auth/logout.ts` → scope: `auth`
- **Branch Inference**: Branch `feat/oauth-login` → type: `feat`
- **Breaking Changes**: Detects deprecated APIs, signature changes → adds `!` flag
- **Style Matching**: Learns from your last 5 commit messages
- **File Context**: Understands which files changed and why it matters

```bash
$ aicommit
Staged: 3 file(s) → scope: auth → branch suggests: feat ⚠ BREAKING CHANGE DETECTED
Repo: aicommit | Branch: feat/oauth-login

┌─ Generated Message (📐 Conventional) ──┐
│ feat(auth)!: add OAuth2 login flow     │
│                                        │
│ BREAKING CHANGE: removed legacy token  │
│ endpoint in favor of OAuth2            │
└────────────────────────────────────────┘
Model: deepseek-chat | Tokens: 420→68 | Time: 820ms

Commit with this message? [y/N]:
```

## 📖 Usage

```bash
# Quick setup (configure git + AI provider)
aicommit --init

# Stage, generate, and commit in one command
aicommit --stage -y

# Basic usage
aicommit                    # Generate and confirm

# Skip confirmation
aicommit -y

# Preview without committing
aicommit --dry-run

# Provide additional context
aicommit -m "fixing race condition in websocket handler"

# Use a specific style
aicommit -s conventional

# Edit generated message before committing
aicommit -e

# Copy generated message to clipboard
aicommit --copy

# Override token limit
aicommit --max-tokens 1000

# Install as git hook (auto-suggests on every commit)
aicommit --install-hook

# Remove the git hook
aicommit --uninstall-hook

# Reconfigure
aicommit --config
```

### ⚙️ Configuration Management

```bash
# Show full configuration
aicommit --config

# Get a specific value
aicommit --get api.model

# Set a value
aicommit --set api.model=gpt-4

# Reset to defaults
aicommit --reset-config
```

### 🚫 .aicommitignore

Create `.aicommitignore` in your repo root to exclude files from AI analysis:

```gitignore
# .aicommitignore
*.lock
*.log
dist/*
secrets.env
generated/*
```

Patterns use the same glob syntax as `.gitignore` and are merged with built-in noise filtering.

### 🔎 Code Review

```bash
# Review staged changes before committing
aicommit --review

# Review with severity filter
aicommit --review --severity high

# Focus on specific area
aicommit --review -m "SQL injection risks"
```

### 📋 PR Description

```bash
# Generate PR description from branch diff
aicommit --pr

# Specify base branch
aicommit --pr --pr-base develop

# Add context
aicommit --pr -m "async refactor, focus on error handling"
```

### 📦 Squash & Changelog

```bash
# Generate squash message from last 5 commits
aicommit --squash 5

# Generate changelog entry
aicommit --changelog

# With version tag
aicommit --changelog --version-tag v1.3.0
```

### ✅ Conventional Validation

```bash
# Validate conventional format
aicommit --validate

# Auto-fix format if needed
aicommit --auto-fix
```

### 🔤 Shell Completions

```bash
# Generate for your shell
aicommit --completion bash > ~/.aicommit-completion.bash
aicommit --completion zsh > ~/.aicommit-completion.zsh
aicommit --completion fish > ~/.config/fish/completions/aicommit.fish
aicommit --completion powershell
```

### 🌍 CI/CD & GitHub Actions

All config can be overridden via environment variables:

```bash
export AICOMMIT_API_KEY="sk-xxx"
export AICOMMIT_MODEL="gpt-4o"
export AICOMMIT_STYLE="conventional"
export AICOMMIT_PROVIDER="openai"
export AICOMMIT_TEMPERATURE="0.3"
```

GitHub Action available — see [action.yml](action.yml):

```yaml
- uses: Yangge521/aicommit@master
  with:
    api_key: ${{ secrets.AICOMMIT_API_KEY }}
    style: conventional
    stage: true
```

## 🪝 Git Hook Integration

Install aicommit as a `prepare-commit-msg` hook and get AI suggestions automatically on every `git commit`:

```bash
aicommit --install-hook
```

Now when you run `git commit`, the editor will be pre-filled with an AI-generated message. You can edit it or accept it as-is.

```bash
git add .
git commit
# → Editor opens with AI suggestion pre-filled!
```

Remove anytime:

```bash
aicommit --uninstall-hook
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
- **Accurate** — Based on actual diff analysis, not guessing
- **Consistent** — Follows your team's conventions automatically
- **Context-Aware** — Scope detection, branch inference, breaking change awareness
- **Fast** — Generated in under a second
- **Customizable** — Your style, your rules, your model

## 🧪 Development

```bash
git clone https://github.com/Ghy/aicommit.git
cd aicommit
pip install -e ".[dev]"
pytest
```

## 📝 License

MIT © Ghy

---

<p align="center">
  <sub>Built with ❤️ for developers who'd rather write code than commit messages</sub>
</p>
