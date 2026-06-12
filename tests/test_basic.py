"""Tests for aicommit."""

import os
import tempfile
from pathlib import Path


class TestImport:
    def test_version(self):
        import aicommit
        assert aicommit.__version__ == "1.2.0"


class TestConfig:
    def test_defaults(self):
        from aicommit.config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["commit"]["style"] == "conventional"
        assert DEFAULT_CONFIG["commit"]["max_diff_lines"] == 200
        assert DEFAULT_CONFIG["api"]["model"] == "deepseek-chat"
        assert "signoff" in DEFAULT_CONFIG["commit"]
        assert "no_verify" in DEFAULT_CONFIG["commit"]

    def test_deep_merge(self):
        from aicommit.config import _deep_merge
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        override = {"a": {"b": 10}}
        _deep_merge(base, override)
        assert base["a"]["b"] == 10
        assert base["a"]["c"] == 2
        assert base["d"] == 3

    def test_escape_toml_str(self):
        from aicommit.config import _escape_toml_str
        assert _escape_toml_str('hello') == 'hello'
        assert _escape_toml_str('has"quote') == 'has\\"quote'
        assert _escape_toml_str('has\\back') == 'has\\\\back'

    def test_save_load_roundtrip(self):
        """Test that config survives save → load roundtrip."""
        from aicommit.config import DEFAULT_CONFIG, save_config, load_config
        import copy
        config = copy.deepcopy(DEFAULT_CONFIG)
        config["api"]["key"] = "sk-test-key-with-special-chars"
        config["commit"]["style"] = "emoji"
        config["commit"]["signoff"] = True
        save_config(config)
        loaded = load_config()
        assert loaded["api"]["key"] == "sk-test-key-with-special-chars"
        assert loaded["commit"]["style"] == "emoji"
        assert loaded["commit"]["signoff"] is True
        assert loaded["commit"]["no_verify"] is False


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
        assert "conventional" in msg.lower()
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
            original = os.getcwd()
            try:
                os.chdir(tmp)
                assert not is_git_repo()
            finally:
                os.chdir(original)

    def test_is_noise_file(self):
        from aicommit.git_utils import is_noise_file
        assert is_noise_file("package-lock.json")
        assert is_noise_file("yarn.lock")
        assert is_noise_file("dist/bundle.js")
        assert is_noise_file("src/app.min.js")
        assert not is_noise_file("src/auth/login.ts")
        assert not is_noise_file("README.md")
        assert not is_noise_file("pyproject.toml")

    def test_detect_scope_single_dir(self):
        from aicommit.git_utils import detect_scope
        files = ["src/auth/login.ts", "src/auth/logout.ts"]
        assert detect_scope(files) == "auth"

    def test_detect_scope_mixed(self):
        from aicommit.git_utils import detect_scope
        files = ["src/auth/login.ts", "docs/api.md", "README.md"]
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

    def test_detect_scope_single_file(self):
        from aicommit.git_utils import detect_scope
        assert detect_scope(["src/utils/helpers.py"]) is None

    def test_detect_breaking_changes(self):
        from aicommit.git_utils import detect_breaking_changes
        assert detect_breaking_changes("BREAKING CHANGE: removed old API")
        assert detect_breaking_changes("this is a breaking change")
        assert detect_breaking_changes("deprecated function removed")
        assert not detect_breaking_changes("add new feature")
        assert not detect_breaking_changes("fix typo in comment")

    def test_infer_type_from_branch(self):
        from aicommit.git_utils import infer_type_from_branch
        assert infer_type_from_branch("feat/oauth-login") == "feat"
        assert infer_type_from_branch("feature/new-ui") == "feat"
        assert infer_type_from_branch("fix/login-bug") == "fix"
        assert infer_type_from_branch("bugfix/crash") == "fix"
        assert infer_type_from_branch("hotfix/urgent") == "fix"
        assert infer_type_from_branch("chore/update-deps") == "chore"
        assert infer_type_from_branch("docs/api-ref") == "docs"
        assert infer_type_from_branch("refactor/cleanup") == "refactor"
        assert infer_type_from_branch("random-branch") is None
        assert infer_type_from_branch("main") is None

    def test_has_staged_changes_empty(self):
        from aicommit.git_utils import has_staged_changes
        result = has_staged_changes()
        assert isinstance(result, bool)


class TestAI:
    def test_ai_result_dataclass(self):
        from aicommit.ai import AIResult
        r = AIResult(message="test", model="gpt-4", tokens_in=10, tokens_out=5, time_ms=100)
        assert r.message == "test"
        assert r.model == "gpt-4"
        assert r.tokens_in == 10
        assert r.tokens_out == 5
        assert r.time_ms == 100

    def test_ai_error_types(self):
        from aicommit.ai import AIError
        e = AIError("No API key configured")
        assert "API key" in str(e)


class TestConventional:
    def test_parse_valid(self):
        from aicommit.conventional import parse_conventional
        result = parse_conventional("feat(auth): add OAuth2 login")
        assert result is not None
        assert result["type"] == "feat"
        assert result["scope"] == "auth"
        assert result["breaking"] is False
        assert result["description"] == "add OAuth2 login"

    def test_parse_breaking(self):
        from aicommit.conventional import parse_conventional
        result = parse_conventional("feat(api)!: remove legacy endpoint")
        assert result is not None
        assert result["breaking"] is True

    def test_parse_no_scope(self):
        from aicommit.conventional import parse_conventional
        result = parse_conventional("fix: correct typo in README")
        assert result is not None
        assert result["type"] == "fix"
        assert result["scope"] is None

    def test_parse_invalid(self):
        from aicommit.conventional import parse_conventional
        assert parse_conventional("just a random message") is None
        assert parse_conventional("") is None

    def test_validate_valid(self):
        from aicommit.conventional import validate_conventional
        valid, err = validate_conventional("feat(auth): add login")
        assert valid is True
        assert err is None

    def test_validate_bad_type(self):
        from aicommit.conventional import validate_conventional
        valid, err = validate_conventional("hack(auth): do stuff")
        assert valid is False
        assert "hack" in err

    def test_validate_no_description(self):
        from aicommit.conventional import validate_conventional
        valid, err = validate_conventional("feat: ")
        assert valid is False

    def test_auto_fix_add_type(self):
        from aicommit.conventional import auto_fix_conventional
        fixed = auto_fix_conventional("Add login page", default_type="feat")
        assert fixed == "feat: add login page"

    def test_auto_fix_already_valid(self):
        from aicommit.conventional import auto_fix_conventional
        msg = "feat(auth): add login"
        assert auto_fix_conventional(msg) == msg

    def test_conventional_to_emoji(self):
        from aicommit.conventional import conventional_to_emoji
        result = conventional_to_emoji("fix: correct typo")
        assert result == "🐛 correct typo"

    def test_emoji_map_complete(self):
        from aicommit.conventional import EMOJI_MAP, ALLOWED_TYPES
        for t in ALLOWED_TYPES:
            assert t in EMOJI_MAP, f"Missing emoji for type: {t}"
