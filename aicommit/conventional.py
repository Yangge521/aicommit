"""Conventional commit validation and auto-fix."""

import re
from typing import Optional, Tuple

# Conventional Commit spec: https://www.conventionalcommits.org/en/v1.0.0/
# Pattern: type(scope)!: description
# Types from: https://github.com/angular/angular/blob/main/CONTRIBUTING.md#type
ALLOWED_TYPES = {
    "feat", "fix", "docs", "style", "refactor", "perf",
    "test", "build", "ci", "chore", "revert",
}

CONVENTIONAL_PATTERN = re.compile(
    r"^(?P<type>\w+)(\((?P<scope>[^)]*)\))?(?P<breaking>!)?: (?P<description>.+)$"
)

FOOTER_PATTERN = re.compile(
    r"^(?P<token>BREAKING[\s-]CHANGE|Co-authored-by|Reviewed-by|Signed-off-by|Acked-by|Refs|Closes|Fixes):\s",
    re.IGNORECASE,
)


def parse_conventional(message: str) -> Optional[dict]:
    """Parse a conventional commit message into its components.

    Returns dict with type, scope, breaking, description, body, footers
    or None if message doesn't follow the convention.
    """
    lines = message.strip().split("\n")
    subject = lines[0]

    match = CONVENTIONAL_PATTERN.match(subject)
    if not match:
        return None

    body_lines = []
    footers = {}
    in_body = False

    for line in lines[1:]:
        footer_match = FOOTER_PATTERN.match(line)
        if footer_match and in_body:
            token = footer_match.group("token")
            value = line[footer_match.end():].strip()
            footers[token] = value
        elif line.strip():
            in_body = True
            body_lines.append(line.strip())

    return {
        "type": match.group("type"),
        "scope": match.group("scope"),
        "breaking": match.group("breaking") == "!" or "BREAKING CHANGE" in message,
        "description": match.group("description"),
        "body": "\n".join(body_lines) if body_lines else None,
        "footers": footers,
    }


def validate_conventional(message: str) -> Tuple[bool, Optional[str]]:
    """Validate a conventional commit message.

    Returns (is_valid, error_message).
    """
    parsed = parse_conventional(message)
    if not parsed:
        return False, "Message does not follow conventional commit format: type(scope): description"

    if parsed["type"] not in ALLOWED_TYPES:
        return False, (
            f"Invalid type '{parsed['type']}'. "
            f"Allowed types: {', '.join(sorted(ALLOWED_TYPES))}"
        )

    desc = parsed["description"]
    if len(desc) > 72:
        return False, f"Description too long ({len(desc)} chars). Should be ≤72 chars."

    if not desc:
        return False, "Description is empty."

    return True, None


def auto_fix_conventional(message: str, default_type: str = "chore") -> str:
    """Try to auto-fix a non-conventional message into conventional format.

    Heuristics:
    - Add default type prefix if missing
    - Lowercase the first word of description
    - Ensure there's a space after colon
    """
    parsed = parse_conventional(message)
    if parsed and parsed["type"] in ALLOWED_TYPES:
        return message  # Already valid

    # Try to fix: prepend type if it looks like a plain description
    lines = message.strip().split("\n")
    first_line = lines[0]

    # If it already starts with a known type but has wrong format
    for t in sorted(ALLOWED_TYPES, key=len, reverse=True):
        if first_line.lower().startswith(t + ":"):
            # Close — just need proper formatting
            rest = first_line[len(t) + 1:].strip()
            return f"{t}: {rest}" + ("\n" + "\n".join(lines[1:]) if len(lines) > 1 else "")

    # Prepend default type
    first_lower = first_line[0].lower() + first_line[1:] if first_line else first_line
    fixed = f"{default_type}: {first_lower}"
    if len(lines) > 1:
        fixed += "\n" + "\n".join(lines[1:])
    return fixed


EMOJI_MAP = {
    "feat": "✨",
    "fix": "🐛",
    "docs": "📝",
    "style": "💄",
    "refactor": "♻️",
    "perf": "⚡",
    "test": "✅",
    "build": "📦",
    "ci": "👷",
    "chore": "🔧",
    "revert": "⏪",
}


def conventional_to_emoji(message: str) -> str:
    """Convert a conventional commit to emoji style."""
    parsed = parse_conventional(message)
    if not parsed:
        return message

    emoji = EMOJI_MAP.get(parsed["type"], "💡")
    result = f"{emoji} {parsed['description']}"
    if parsed["body"]:
        result += "\n\n" + parsed["body"]
    return result
