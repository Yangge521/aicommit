"""Tests for aicommit."""

import os
import tempfile
from pathlib import Path


class TestImport:
    def test_version(self):
        import aicommit
        assert aicommit.__version__ == "1.1.0"


class TestConfig:
    def test_defaults(self):
        from aicommit.config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["commit"]["style"] == "conventional"
        assert DEFAULT_CONFIG["commit"]["max_diff_lines"] == 200
        assert DEFAULT_CONFIG["api"]["model"] == "deepseek-chat"

    def test_deep_merge(self):
        from aicommit.config import _deep_merge
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        override = {"a": {"b": 10}}
        _deep_merge(base, override)
        assert base["a"]["b"] == 10
        assert base["a"]["c"] == 2
        assert base["d"] == 3


class TestPrompts:
    def test_all_styles_exist(self):
        from aicommit.prompts import STYLE_PROMPTS
        assert set(STYLE_PROMPTS.keys()) == {"conventional", "emoji", "simple", "detailed"}

    def test_conventional_format(self):
        from aicommit.prompts import CONVENTIONAL_PROMPT
        msg = CONVENTIONAL_PROMPT.format(
            diff="test diff", recent_commits="",
            branch_hint="", breaking_hint="", file_list="- test.py"
        )
        assert "conventional commit" in msg.lower()
        assert "test diff" in msg

    def test_emoji_format(self):
        from aicommit.prompts import EMOJI_PROMPT
        msg = EMOJI_PROMPT.format(
            diff="test", branch_hint="", file_list="- test.py"
        )
        assert "gitmoji" in msg.lower()


class TestGitUtils:
    def test_not_a_repo(self):
        from aicommit.git_utils import is_git_repo
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                assert not is_git_repo()
            finally:
                os.chdir(os.path.expanduser("~"))

    def test_detect_scope_single_dir(self):
        from aicommit.git_utils import detect_scope
        files = ["src/auth/login.ts", "src/auth/logout.ts"]
        assert detect_scope(files) == "auth"

    def test_detect_scope_mixed(self):
        from aicommit.git_utils import detect_scope
        files = ["src/auth/login.ts", "docs/api.md", "README.md"]
        # No clear majority
        result = detect_scope(files)
        assert result is None or result in ("auth", "docs")

    def test_detect_scope_nested(self):
        from aicommit.git_utils import detect_scope
        files = [
            "src/components/Button.tsx",
            "src/components/Input.tsx",
            "src/components/Modal.tsx",
        ]
        assert detect_scope(files) == "components"

    def test_detect_breaking_changes(self):
        from aicommit.git_utils import detect_breaking_changes
        assert detect_breaking_changes("BREAKING CHANGE: removed old API")
        assert detect_breaking_changes("this is a breaking change in the interface")
        assert not detect_breaking_changes("add new feature")

    def test_infer_type_from_branch(self):
        from aicommit.git_utils import infer_type_from_branch
        assert infer_type_from_branch("feat/oauth-login") == "feat"
        assert infer_type_from_branch("fix/login-bug") == "fix"
        assert infer_type_from_branch("chore/update-deps") == "chore"
        assert infer_type_from_branch("random-branch") is None

    def test_has_staged_changes_empty(self):
        from aicommit.git_utils import has_staged_changes
        # In a git repo (aicommit dir), check with no staged changes
        result = has_staged_changes()
        assert isinstance(result, bool)


class TestAI:
    def test_ai_result_dataclass(self):
        from aicommit.ai import AIResult
        r = AIResult(message="test", model="gpt-4", tokens_in=10, tokens_out=5, time_ms=100)
        assert r.message == "test"
        assert r.model == "gpt-4"
        assert r.tokens_in == 10
