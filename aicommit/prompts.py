"""Prompt templates for different commit styles."""

SYSTEM_PROMPT = """You are a commit message generator. Your job is to write clear, informative git commit messages based on code diffs.

Rules:
- Write in {language} (auto-detect means: respond in the same language as the code changes)
- Focus on WHAT changed and WHY, not how
- Never include explanations, apologies, or meta-commentary
- Return ONLY the commit message, nothing else
- Keep it concise but descriptive
- Look at recent commits for style consistency
- For bug fixes, mention what was broken and how it's fixed
- For refactors, note what was simplified and why"""

CONVENTIONAL_PROMPT = """Generate a conventional commit message for these staged changes.

Format: <type>[optional scope]: <description>

Types:
- feat: new feature
- fix: bug fix
- docs: documentation only
- style: formatting, missing semicolons, etc
- refactor: code change that neither fixes a bug nor adds a feature
- perf: performance improvement
- test: adding or correcting tests
- chore: build process, tooling, dependencies
- ci: CI/CD changes
- revert: reverts a previous commit

{branch_hint}
{breaking_hint}

The description should:
- Use imperative mood ("add" not "added" or "adds")
- Not capitalize the first letter
- No period at the end
- Be 50-72 characters max

If changes span multiple concerns, use the most impactful type.
{recent_commits}

File paths changed:
{file_list}

Staged changes:
{diff}

Return ONLY the commit message, nothing else."""

EMOJI_PROMPT = """Generate a gitmoji-style commit message for these staged changes.

Format: <emoji> <description>

Common emojis:
- ✨ feat: new feature
- 🐛 fix: bug fix
- 📝 docs: documentation
- 💄 style: UI/style changes
- ♻️ refactor: code refactoring
- ⚡ perf: performance improvement
- ✅ test: tests
- 🔧 chore: tooling/config
- 🚀 ci: CI/CD
- 🎨 format: code formatting
- 🔒 security: security fixes
- 🗑️ remove: deleting code/files
- 🚚 move: moving/renaming files
- 🏗️ build: build system changes
- 💥 breaking: breaking changes
- ⏪ revert: reverting changes

Pick the most appropriate emoji. Description should be short and clear.
{branch_hint}
{breaking_hint}
{recent_commits}

File paths changed:
{file_list}

Staged changes:
{diff}

Return ONLY the commit message (emoji + description), nothing else."""

SIMPLE_PROMPT = """Generate a short, clear commit message for these staged changes.

Keep it under 72 characters. Use imperative mood. One line only.
{recent_commits}
{branch_hint}
{breaking_hint}

File paths changed:
{file_list}

Staged changes:
{diff}

Return ONLY the commit message, nothing else."""

DETAILED_PROMPT = """Generate a detailed commit message for these staged changes.

Format:
<summary line, max 72 chars>
<blank line>
<bullet points explaining key changes>

Guidelines:
- Summary should be concise and imperative
- Each bullet should explain one logical change
- Mention affected files/modules if relevant
- Highlight any breaking changes or important notes
{recent_commits}
{branch_hint}

File paths changed:
{file_list}

Staged changes:
{diff}

Return ONLY the commit message, nothing else."""

STYLE_PROMPTS = {
    "conventional": CONVENTIONAL_PROMPT,
    "emoji": EMOJI_PROMPT,
    "simple": SIMPLE_PROMPT,
    "detailed": DETAILED_PROMPT,
}
