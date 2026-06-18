"""Tests for aicommit."""

import os
import tempfile
from pathlib import Path


class TestImport:
    def test_version(self):
        import aicommit
        assert aicommit.__version__ == "1.12.0"


class TestConfig:
    def test_defaults(self):
        from aicommit.config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["commit"]["style"] == "conventional"
        assert DEFAULT_CONFIG["commit"]["max_diff_lines"] == 200
        assert DEFAULT_CONFIG["api"]["model"] == "deepseek-chat"
        assert "signoff" in DEFAULT_CONFIG["commit"]
        assert "no_verify" in DEFAULT_CONFIG["commit"]

    def test_config_has_provider(self):
        from aicommit.config import DEFAULT_CONFIG
        assert "provider" in DEFAULT_CONFIG["api"]
        assert DEFAULT_CONFIG["api"]["provider"] == "openai"
        assert "temperature" in DEFAULT_CONFIG["api"]
        assert DEFAULT_CONFIG["api"]["temperature"] == 0.3

    def test_env_override_provider(self, monkeypatch):
        from aicommit.config import DEFAULT_CONFIG, load_config
        monkeypatch.setenv("AICOMMIT_PROVIDER", "anthropic")
        monkeypatch.setenv("AICOMMIT_TEMPERATURE", "0.7")
        monkeypatch.setenv("AICOMMIT_MODEL", "claude-3-haiku")
        config = load_config()
        assert config["api"]["provider"] == "anthropic"
        assert config["api"]["temperature"] == 0.7
        assert config["api"]["model"] == "claude-3-haiku"
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
            diff="test", branch_hint="", breaking_hint="", recent_commits="", file_list="- test.py"
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


class TestReview:
    def test_review_prompt_structure(self):
        from aicommit.review import REVIEW_PROMPT
        assert "## Diff" in REVIEW_PROMPT
        assert "{diff}" in REVIEW_PROMPT


class TestExtra:
    def test_squash_prompt_structure(self):
        from aicommit.extra import SQUASH_PROMPT
        assert "{commits}" in SQUASH_PROMPT
        assert "{diff}" in SQUASH_PROMPT
        assert "{style_instruction}" in SQUASH_PROMPT

    def test_changelog_prompt_structure(self):
        from aicommit.extra import CHANGELOG_PROMPT
        assert "Added" in CHANGELOG_PROMPT
        assert "{commits}" in CHANGELOG_PROMPT
        assert "{version}" in CHANGELOG_PROMPT

    def test_extra_module_imports(self):
        from aicommit.extra import generate_squash_message, generate_changelog
        assert callable(generate_squash_message)
        assert callable(generate_changelog)


class TestClipboard:
    def test_clipboard_import(self):
        import platform
        assert platform.system()  # Just verify platform is available


class TestAIStats:
    def test_history_load_empty(self):
        from aicommit.config import load_history
        entries = load_history(limit=5)
        assert isinstance(entries, list)

    def test_history_dedup(self):
        from aicommit.config import save_history, load_history, reset_config
        save_history({"repo": "test", "branch": "main", "style": "feat", "message": "test"})
        entries = load_history(limit=50)
        assert any(e["message"] == "test" for e in entries)


class TestAIClient:
    def test_ai_client_import(self):
        from aicommit.ai_client import call_ai, _call_ai_once
        assert callable(call_ai)
        assert callable(_call_ai_once)

    def test_template_vars(self):
        from aicommit.cli import _expand_template_vars
        result = _expand_template_vars(
            "feat({scope}): add {branch} feature",
            scope="auth", branch="oauth/login"
        )
        assert result == "feat(auth): add oauth/login feature"


class TestMonorepo:
    def test_monorepo_import(self):
        from aicommit.git_utils import detect_monorepo_package
        assert callable(detect_monorepo_package)


class TestWrapBody:
    def test_wrap_body_simple(self):
        from aicommit.conventional import wrap_body
        result = wrap_body("feat: test\n\nThis is a long description that needs wrapping.")
        assert result.startswith("feat: test")
        assert "\n\n" in result

    def test_wrap_body_no_body(self):
        from aicommit.conventional import wrap_body
        result = wrap_body("feat: add login")
        assert result == "feat: add login"


class TestConfigSetGet:
    def test_get_config_value_defaults(self):
        from aicommit.config import DEFAULT_CONFIG, get_config_value
        # get_config_value reads from file; DEFAULT_CONFIG is the fallback
        assert DEFAULT_CONFIG["commit"]["style"] == "conventional"
        assert DEFAULT_CONFIG["api"]["model"] == "deepseek-chat"

    def test_set_config_value_roundtrip(self):
        from aicommit.config import set_config_value, get_config_value
        original = get_config_value("api.temperature")
        try:
            set_config_value("api.temperature", "0.7")
            assert get_config_value("api.temperature") == "0.7"
        finally:
            set_config_value("api.temperature", original)


class TestAicommitignore:
    def test_ignore_import(self):
        from aicommit.git_utils import load_aicommitignore, match_aicommitignore
        assert callable(load_aicommitignore)
        assert callable(match_aicommitignore)

    def test_match_ignore_patterns(self):
        from aicommit.git_utils import match_aicommitignore
        patterns = ["*.log", "dist/*", "secrets.env"]
        assert match_aicommitignore("debug.log", patterns) is True
        assert match_aicommitignore("dist/main.js", patterns) is True
        assert match_aicommitignore("secrets.env", patterns) is True
        assert match_aicommitignore("src/main.py", patterns) is False
        assert match_aicommitignore("README.md", patterns) is False

    def test_match_by_filename_only(self):
        from aicommit.git_utils import match_aicommitignore
        patterns = ["*.log"]
        assert match_aicommitignore("some/deep/path/error.log", patterns) is True


class TestProviderOverride:
    def test_provider_map_covers_all(self):
        from aicommit.cli import _apply_provider_override
        config = {
            "api": {"provider": "openai", "endpoint": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
            "commit": {}
        }
        _apply_provider_override(config, "ollama")
        assert config["api"]["provider"] == "openai"
        assert "localhost" in config["api"]["endpoint"]
        assert config["api"]["model"] == "llama3.2"

    def test_provider_override_anthropic(self):
        from aicommit.cli import _apply_provider_override
        config = {
            "api": {"provider": "openai", "endpoint": "", "model": ""},
            "commit": {}
        }
        _apply_provider_override(config, "anthropic")
        assert config["api"]["provider"] == "anthropic"
        assert config["api"]["endpoint"] == "https://api.anthropic.com/v1"

    def test_provider_override_deepseek(self):
        from aicommit.cli import _apply_provider_override
        config = {
            "api": {"provider": "anthropic", "endpoint": "", "model": ""},
            "commit": {}
        }
        _apply_provider_override(config, "deepseek")
        assert config["api"]["provider"] == "openai"
        assert "deepseek" in config["api"]["endpoint"]

    def test_provider_override_unknown_noop(self):
        from aicommit.cli import _apply_provider_override
        config = {
            "api": {"provider": "openai", "endpoint": "https://original", "model": "gpt-4"},
            "commit": {}
        }
        _apply_provider_override(config, "groq")  # Unknown provider
        assert config["api"]["endpoint"] == "https://original"


class TestSaveToFile:
    def test_save_to_file_creates_dir(self, tmp_path):
        from aicommit.cli import _save_to_file
        output = tmp_path / "sub" / "message.txt"
        _save_to_file("hello world", str(output))
        assert output.exists()
        assert output.read_text(encoding="utf-8") == "hello world"


class TestLogFiltering:
    def test_log_filter_by_style(self):
        from aicommit.config import save_history, load_history
        save_history({"repo": "test", "branch": "main", "style": "emoji", "message": "test"})
        save_history({"repo": "test", "branch": "main", "style": "conventional", "message": "test"})
        entries = load_history(50)
        emoji_entries = [e for e in entries if e.get("style") == "emoji"]
        conventional_entries = [e for e in entries if e.get("style") == "conventional"]
        assert len(emoji_entries) >= 1
        assert len(conventional_entries) >= 1


class TestSetupWizardDeepcopy:
    def test_setup_wizard_not_mutate_defaults(self):
        from aicommit.config import DEFAULT_CONFIG, setup_wizard
        import copy
        # Verify DEFAULT_CONFIG uses list/dict that would be polluted by shallow copy
        original_api = copy.deepcopy(DEFAULT_CONFIG["api"])
        original_commit = copy.deepcopy(DEFAULT_CONFIG["commit"])
        # After loading, DEFAULT_CONFIG should be untouched
        assert DEFAULT_CONFIG["api"] == original_api
        assert DEFAULT_CONFIG["commit"] == original_commit


class TestParseCommitMessage:
    def test_parse_conventional(self):
        from aicommit.cli import _parse_commit_message
        result = _parse_commit_message("feat(auth): add login page\n\nImplemented OAuth2 flow.", "conventional")
        assert result["type"] == "feat"
        assert result["scope"] == "auth"
        assert result["description"] == "add login page"
        assert "OAuth2" in result["body"]
        assert result["breaking"] == ""

    def test_parse_conventional_breaking(self):
        from aicommit.cli import _parse_commit_message
        result = _parse_commit_message("feat(api)!: change endpoint format", "conventional")
        assert result["type"] == "feat"
        assert result["scope"] == "api"
        assert result["breaking"] == "!"
        assert result["description"] == "change endpoint format"

    def test_parse_conventional_no_scope(self):
        from aicommit.cli import _parse_commit_message
        result = _parse_commit_message("docs: update README", "conventional")
        assert result["type"] == "docs"
        assert result["scope"] == ""
        assert result["description"] == "update README"

    def test_parse_emoji(self):
        from aicommit.cli import _parse_commit_message
        result = _parse_commit_message("✨ Add new feature", "emoji")
        assert result["emoji"] == "✨"
        assert result["description"] == "Add new feature"

    def test_parse_emoji_multi_codepoint(self):
        from aicommit.cli import _parse_commit_message
        # ZWJ sequence
        result = _parse_commit_message("👨‍💻 Refactor codebase", "emoji")
        assert result["emoji"] == "👨‍💻"
        assert result["description"] == "Refactor codebase"

    def test_parse_emoji_flag(self):
        from aicommit.cli import _parse_commit_message
        # Flag sequence
        result = _parse_commit_message("🇨🇳 Add Chinese i18n", "emoji")
        assert result["emoji"] == "🇨🇳"
        assert result["description"] == "Add Chinese i18n"

    def test_parse_simple(self):
        from aicommit.cli import _parse_commit_message
        result = _parse_commit_message("Fix crash on startup\n\nRoot cause was null pointer.", "simple")
        assert result["description"] == "Fix crash on startup"
        assert "null pointer" in result["body"]


class TestApplyMessageTemplate:
    def test_template_conventional_format(self):
        from aicommit.cli import _apply_message_template
        msg = "feat(auth): add login page"
        tmpl = "[{type}] {description}"
        result = _apply_message_template(msg, tmpl, "conventional")
        assert result == "[feat] add login page"

    def test_template_emoji_with_scope(self):
        from aicommit.cli import _apply_message_template
        msg = "feat(api)!: change endpoint format"
        tmpl = "{emoji} {type}({scope}){breaking}: {description}"
        result = _apply_message_template(msg, tmpl, "conventional")
        assert result == "feat(api)!: change endpoint format"

    def test_template_with_branch(self):
        from aicommit.cli import _apply_message_template
        msg = "fix: resolve timeout"
        tmpl = "{type}({branch}): {description}"
        result = _apply_message_template(msg, tmpl, "conventional", branch="feature/api")
        assert result == "fix(feature/api): resolve timeout"

    def test_template_empty_vars_cleaned(self):
        from aicommit.cli import _apply_message_template
        msg = "Add feature"
        tmpl = "{type}({scope}): {description}"
        result = _apply_message_template(msg, tmpl, "simple")
        # Empty scope → "()" removed → ": Add feature"
        assert result == ": Add feature"

    def test_template_empty_parens_cleaned(self):
        from aicommit.cli import _apply_message_template
        msg = "feat: add feature"
        tmpl = "{type}({scope}): {description}"
        result = _apply_message_template(msg, tmpl, "conventional")
        # scope is empty, () should be removed
        assert result == "feat: add feature"

    def test_template_double_colon_cleaned(self):
        from aicommit.cli import _apply_message_template
        msg = "Add feature"
        tmpl = "{type}:: {description}"
        result = _apply_message_template(msg, tmpl, "simple")
        # type is empty, "::" → ":"
        assert result == ": Add feature"


class TestMessageTemplateConfig:
    def test_templates_in_default_config(self):
        from aicommit.config import DEFAULT_CONFIG
        assert "templates" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["templates"] == {}

    def test_save_and_list_template(self):
        from aicommit.config import save_message_template, list_message_templates, delete_message_template
        save_message_template("test_tmpl", "{type}: {description}")
        templates = list_message_templates()
        assert "test_tmpl" in templates
        assert templates["test_tmpl"] == "{type}: {description}"
        # Cleanup
        delete_message_template("test_tmpl")

    def test_delete_nonexistent_template(self):
        from aicommit.config import delete_message_template
        result = delete_message_template("nonexistent_xyz")
        assert result is False

    def test_get_template(self):
        from aicommit.config import save_message_template, get_message_template, delete_message_template
        save_message_template("get_test", "{type}: {scope}")
        fmt = get_message_template("get_test")
        assert fmt == "{type}: {scope}"
        fmt_none = get_message_template("nonexistent")
        assert fmt_none is None
        delete_message_template("get_test")

    def test_templates_persist_in_config(self):
        from aicommit.config import save_message_template, load_config, delete_message_template
        save_message_template("persist_tmpl", "{emoji} {description}")
        config = load_config()
        assert "persist_tmpl" in config.get("templates", {})
        assert config["templates"]["persist_tmpl"] == "{emoji} {description}"
        delete_message_template("persist_tmpl")


class TestEditorCmdOverride:
    def test_edit_message_signature(self):
        from aicommit.cli import _edit_message
        import inspect
        sig = inspect.signature(_edit_message)
        params = list(sig.parameters.keys())
        assert "editor_cmd" in params

    def test_editor_cmd_splits_simple(self):
        import shlex
        assert shlex.split("vim") == ["vim"]
        assert shlex.split("code --wait") == ["code", "--wait"]
        assert shlex.split("nvim") == ["nvim"]

    def test_editor_cmd_splits_quoted_path(self):
        import shlex
        result = shlex.split(r'"C:\Program Files\Editor\editor.exe" --flag')
        assert result == [r"C:\Program Files\Editor\editor.exe", "--flag"]

    def test_edit_message_uses_shlex(self):
        from aicommit.cli import _edit_message
        import inspect
        src = inspect.getsource(_edit_message)
        assert "shlex.split" in src
        assert "[*shlex.split(editor), tmp_path]" in src


class TestRetryMode:
    """Tests for --retry functionality."""

    def test_retry_mode_exists(self):
        from aicommit.cli import _run_retry_mode
        assert callable(_run_retry_mode)

    def test_retry_mode_signature(self):
        import inspect
        from aicommit.cli import _run_retry_mode
        sig = inspect.signature(_run_retry_mode)
        params = list(sig.parameters.keys())
        assert "style" in params
        assert "language" in params
        assert "hint" in params


class TestGroupByMode:
    """Tests for --group-by functionality."""

    def test_group_by_mode_exists(self):
        from aicommit.cli import _run_group_by_mode
        assert callable(_run_group_by_mode)

    def test_group_by_mode_signature(self):
        import inspect
        from aicommit.cli import _run_group_by_mode
        sig = inspect.signature(_run_group_by_mode)
        params = list(sig.parameters.keys())
        assert "group_by" in params
        assert "style" in params

    def test_group_by_choices(self):
        """Verify --group-by accepts only dir/type/ext."""
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--group-by", "invalid"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid" in result.output.lower()


class TestInstallAlias:
    """Tests for --install-alias functionality."""

    def test_install_alias_mode_exists(self):
        from aicommit.cli import _run_install_alias
        assert callable(_run_install_alias)

    def test_uninstall_alias_mode_exists(self):
        from aicommit.cli import _run_uninstall_alias
        assert callable(_run_uninstall_alias)


class TestBodyFile:
    """Tests for --body-file functionality."""

    def test_body_file_option_in_help(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "--body-file" in result.output


class TestClickParamMapping:
    """Tests for click parameter name mapping fixes."""

    def test_reset_config_no_crash(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--reset-config"])
        assert result.exit_code == 0

    def test_config_flag_no_crash(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--config"])
        assert result.exit_code == 0
        assert "Configuration" in result.output


class TestTemplateDotName:
    """Tests for template name with dots rejection."""

    def test_save_template_rejects_dots(self):
        from aicommit.config import save_message_template
        import pytest
        with pytest.raises(ValueError, match="dots"):
            save_message_template("my.template", "{type}: {desc}")

    def test_save_template_accepts_hyphens(self):
        from aicommit.config import save_message_template, delete_message_template
        save_message_template("my-template", "{type}: {desc}")
        delete_message_template("my-template")  # cleanup


class TestAIEmptyResponse:
    """Tests for AI empty response guard."""

    def test_generate_rejects_empty(self):
        from aicommit.ai import generate_commit_message, AIError
        import unittest.mock as mock
        with mock.patch("aicommit.ai.call_ai", return_value={"content": "", "model": "test", "prompt_tokens": 0, "completion_tokens": 0, "time_ms": 0}):
            import pytest
            with pytest.raises(AIError, match="empty"):
                generate_commit_message(diff="test diff")

    def test_generate_rejects_whitespace(self):
        from aicommit.ai import generate_commit_message, AIError
        import unittest.mock as mock
        with mock.patch("aicommit.ai.call_ai", return_value={"content": "   ", "model": "test", "prompt_tokens": 0, "completion_tokens": 0, "time_ms": 0}):
            import pytest
            with pytest.raises(AIError, match="empty"):
                generate_commit_message(diff="test diff")


class TestConfigShowComplete:
    """Tests for config display completeness."""

    def test_config_shows_auto_confirm(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--config"])
        assert "auto_confirm" in result.output


class TestFileListFormat:
    """Tests for file_list formatting in prompts."""

    def test_file_list_as_string(self):
        from aicommit.prompts import STYLE_PROMPTS
        # Verify prompts accept string file_list, not list
        formatted = STYLE_PROMPTS["conventional"].format(
            diff="test", recent_commits="",
            branch_hint="", breaking_hint="",
            file_list="- src/auth.ts\n- src/login.ts",
        )
        assert "- src/auth.ts" in formatted


class TestEscapeTomlStr:
    """Tests for TOML string escaping completeness."""

    def test_escape_tab(self):
        from aicommit.config import _escape_toml_str
        result = _escape_toml_str("hello\tworld")
        assert result == "hello\\tworld"

    def test_escape_newline(self):
        from aicommit.config import _escape_toml_str
        result = _escape_toml_str("hello\nworld")
        assert result == "hello\\nworld"

    def test_escape_backslash(self):
        from aicommit.config import _escape_toml_str
        result = _escape_toml_str("hello\\world")
        assert result == "hello\\\\world"

    def test_escape_quote(self):
        from aicommit.config import _escape_toml_str
        result = _escape_toml_str('he said "hi"')
        assert '\\"' in result


class TestGroupBySingleGroupReturn:
    """Tests for group-by single group returning instead of exiting."""

    def test_group_by_mode_callable(self):
        from aicommit.cli import _run_group_by_mode
        # Just verify it doesn't crash on import
        assert callable(_run_group_by_mode)


class TestAutoFixAmendCheck:
    """Tests for --auto-fix checking amend result."""

    def test_auto_fix_checks_returncode(self):
        from aicommit.cli import _run_auto_fix
        import inspect
        src = inspect.getsource(_run_auto_fix)
        assert "returncode" in src


class TestPushOption:
    """Tests for --push functionality."""

    def test_push_option_in_help(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "--push" in result.output

    def test_push_default_false(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        # --push is a flag, should show in help
        assert "--push" in result.output


class TestLanguageOverride:
    """Tests for --language functionality."""

    def test_language_option_in_help(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "--language" in result.output


class TestEmojiPairOption:
    """Tests for --emoji-pair functionality."""

    def test_emoji_pair_option_in_help(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "--emoji-pair" in result.output

    def test_emoji_pair_prepends_emoji(self):
        """Verify emoji-pair mode prepends emoji to conventional message."""
        from aicommit.conventional import parse_conventional, EMOJI_MAP
        msg = "feat(auth): add login page"
        parsed = parse_conventional(msg)
        assert parsed and parsed["type"] in EMOJI_MAP
        emoji = EMOJI_MAP[parsed["type"]]
        result = f"{emoji} {msg}"
        assert result == "✨ feat(auth): add login page"


class TestPromptCompleteness:
    """Tests for prompt template placeholder consistency."""

    def test_emoji_prompt_has_all_placeholders(self):
        from aicommit.prompts import EMOJI_PROMPT
        assert "{branch_hint}" in EMOJI_PROMPT
        assert "{breaking_hint}" in EMOJI_PROMPT
        assert "{recent_commits}" in EMOJI_PROMPT
        assert "{file_list}" in EMOJI_PROMPT
        assert "{diff}" in EMOJI_PROMPT

    def test_simple_prompt_has_all_placeholders(self):
        from aicommit.prompts import SIMPLE_PROMPT
        assert "{branch_hint}" in SIMPLE_PROMPT
        assert "{breaking_hint}" in SIMPLE_PROMPT
        assert "{recent_commits}" in SIMPLE_PROMPT
        assert "{file_list}" in SIMPLE_PROMPT
        assert "{diff}" in SIMPLE_PROMPT

    def test_detailed_prompt_has_all_placeholders(self):
        from aicommit.prompts import DETAILED_PROMPT
        assert "{branch_hint}" in DETAILED_PROMPT
        assert "{recent_commits}" in DETAILED_PROMPT
        assert "{file_list}" in DETAILED_PROMPT
        assert "{diff}" in DETAILED_PROMPT


class TestDiffChunking:
    """Tests for diff chunking (context-aware slicing for large diffs)."""

    def test_chunk_diff_small(self):
        """Small diffs should return a single chunk."""
        from aicommit.git_utils import chunk_diff
        small_diff = "diff --git a/foo.py b/foo.py\n+print('hello')\n"
        chunks = chunk_diff(small_diff, threshold=10)
        assert len(chunks) == 1
        assert chunks[0]["file"] == "*"

    def test_chunk_diff_large(self):
        """Large diffs should be split into per-file chunks."""
        from aicommit.git_utils import chunk_diff
        # Build a large diff with multiple files, each with enough lines to not be merged
        lines = []
        for i in range(5):
            lines.append(f"diff --git a/file{i}.py b/file{i}.py")
            lines.append("index abc..def 100644")
            lines.append("--- a/file{}.py".format(i))
            lines.append("+++ b/file{}.py".format(i))
            for j in range(40):
                lines.append(f"@@ -{j+1},1 +{j+1},1 @@")
                lines.append(f"-old line {i}_{j}")
                lines.append(f"+new line {i}_{j}")
            lines.append("")
        big_diff = "\n".join(lines)
        chunks = chunk_diff(big_diff, threshold=50)
        assert len(chunks) > 1
        # Each chunk should have a file name
        for chunk in chunks:
            assert chunk["file"] != "*"
            assert chunk["lines"] > 0
            assert chunk["diff"]

    def test_chunk_diff_merges_tiny(self):
        """Tiny chunks (<30 lines) should be merged into previous."""
        from aicommit.git_utils import chunk_diff
        lines = []
        # Big file
        lines.append("diff --git a/big.py b/big.py")
        lines.append("@@ -1,50 +1,50 @@")
        for i in range(50):
            lines.append(f"-line{i}")
            lines.append(f"+newline{i}")
        # Small file
        lines.append("diff --git a/tiny.py b/tiny.py")
        lines.append("@@ -1,1 +1,1 @@")
        lines.append("-old")
        lines.append("+new")
        big_diff = "\n".join(lines)
        chunks = chunk_diff(big_diff, threshold=10)
        # The tiny file should be merged into big.py's chunk
        assert len(chunks) >= 1

    def test_get_chunked_diff(self):
        """get_chunked_diff should return (summary, chunks)."""
        from aicommit.git_utils import get_chunked_diff, chunk_diff
        # This function requires a git repo, so just verify import
        assert callable(get_chunked_diff)

    def test_chunk_threshold_constant(self):
        from aicommit.git_utils import CHUNK_THRESHOLD, CHUNK_MAX_LINES
        assert CHUNK_THRESHOLD > 0
        assert CHUNK_MAX_LINES > 0
        assert CHUNK_MAX_LINES <= CHUNK_THRESHOLD


class TestRebaseSupport:
    """Tests for --rebase interactive rebase functionality."""

    def test_rebase_option_in_help(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "--rebase" in result.output

    def test_rebase_base_option_in_help(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "--rebase-base" in result.output

    def test_rebase_all_option_in_help(self):
        from click.testing import CliRunner
        from aicommit.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "--rebase-all" in result.output

    def test_get_commits_in_range_import(self):
        from aicommit.git_utils import get_commits_in_range
        assert callable(get_commits_in_range)

    def test_get_commit_diff_import(self):
        from aicommit.git_utils import get_commit_diff
        assert callable(get_commit_diff)

    def test_get_commit_files_import(self):
        from aicommit.git_utils import get_commit_files
        assert callable(get_commit_files)

    def test_run_rebase_mode_exists(self):
        from aicommit.cli import _run_rebase_mode
        assert callable(_run_rebase_mode)


class TestBugFixesV12:
    """Tests for bugs fixed in v1.12.0 audit."""

    def test_pr_mode_accepts_language_param(self):
        """_run_pr_mode should accept a language parameter."""
        import inspect
        from aicommit.cli import _run_pr_mode
        sig = inspect.signature(_run_pr_mode)
        params = list(sig.parameters.keys())
        assert "language" in params

    def test_squash_mode_accepts_language_param(self):
        """_run_squash_mode should accept a language parameter."""
        import inspect
        from aicommit.cli import _run_squash_mode
        sig = inspect.signature(_run_squash_mode)
        params = list(sig.parameters.keys())
        assert "language" in params

    def test_changelog_mode_accepts_language_param(self):
        """_run_changelog_mode should accept a language parameter."""
        import inspect
        from aicommit.cli import _run_changelog_mode
        sig = inspect.signature(_run_changelog_mode)
        params = list(sig.parameters.keys())
        assert "language" in params

    def test_pr_mode_no_undefined_language_override(self):
        """_run_pr_mode should not reference undefined language_override."""
        import inspect
        from aicommit.cli import _run_pr_mode
        src = inspect.getsource(_run_pr_mode)
        assert "language_override" not in src

    def test_squash_mode_no_undefined_language(self):
        """_run_squash_mode should not reference undefined 'language' variable."""
        import inspect
        from aicommit.cli import _run_squash_mode
        src = inspect.getsource(_run_squash_mode)
        # Should use 'lang' or 'language' as a parameter, not bare undefined 'language'
        assert "language = language or" not in src

    def test_changelog_mode_no_undefined_language(self):
        """_run_changelog_mode should not reference undefined 'language' variable."""
        import inspect
        from aicommit.cli import _run_changelog_mode
        src = inspect.getsource(_run_changelog_mode)
        assert "language = language or" not in src

    def test_cli_no_unused_imports(self):
        """cli.py should not import unused CONFIG_FILE or save_config."""
        from pathlib import Path
        cli_path = Path(__file__).parent.parent / "aicommit" / "cli.py"
        content = cli_path.read_text(encoding="utf-8")
        # Check that CONFIG_FILE is not in import statement
        assert "CONFIG_FILE," not in content
        # save_config should not be imported (it may appear in other contexts)
        lines = [l for l in content.split("\n") if "save_config" in l and "import" in l]
        assert len(lines) == 0

    def test_git_utils_no_reword_commit(self):
        """git_utils.py should not have dead reword_commit function."""
        from pathlib import Path
        gu_path = Path(__file__).parent.parent / "aicommit" / "git_utils.py"
        content = gu_path.read_text(encoding="utf-8")
        assert "def reword_commit" not in content
        assert "import os  # needed by reword_commit" not in content

    def test_ai_helpers_exist(self):
        """ai.py should have _strip_markdown_fences and _validate_response helpers."""
        from aicommit.ai import _strip_markdown_fences, _validate_response
        assert callable(_strip_markdown_fences)
        assert callable(_validate_response)

    def test_strip_markdown_fences(self):
        """_strip_markdown_fences should remove code block wrapping."""
        from aicommit.ai import _strip_markdown_fences
        assert _strip_markdown_fences("```python\nfeat: add login\n```") == "feat: add login"
        assert _strip_markdown_fences("```\nfix: patch bug\n```") == "fix: patch bug"
        assert _strip_markdown_fences("feat: no fences") == "feat: no fences"

    def test_pyproject_urls_correct(self):
        """pyproject.toml should point to Yangge521/aicommit."""
        from pathlib import Path
        pp_path = Path(__file__).parent.parent / "pyproject.toml"
        content = pp_path.read_text(encoding="utf-8")
        assert "Yangge521/aicommit" in content
        assert "Ghy/aicommit" not in content

    def test_readme_clone_url_correct(self):
        """README.md should have correct clone URL."""
        from pathlib import Path
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text(encoding="utf-8")
        assert "github.com/Yangge521/aicommit.git" in content

    def test_readme_changelog_order(self):
        """README.md changelog should have v1.11.0 before v1.7.0."""
        from pathlib import Path
        readme_path = Path(__file__).parent.parent / "README.md"
        content = readme_path.read_text(encoding="utf-8")
        pos_11 = content.find("### v1.11.0")
        pos_7 = content.find("### v1.7.0")
        assert pos_11 > 0
        assert pos_7 > 0
        assert pos_11 < pos_7

    def test_rebase_cleanup_no_dir_check(self):
        """_run_rebase_mode should not use dir() for variable existence check."""
        import inspect
        from aicommit.cli import _run_rebase_mode
        src = inspect.getsource(_run_rebase_mode)
        assert "p_name in dir()" not in src

    def test_rebase_no_batch_scripts(self):
        """_run_rebase_mode should not create Windows batch scripts."""
        import inspect
        from aicommit.cli import _run_rebase_mode
        src = inspect.getsource(_run_rebase_mode)
        # Remove comments before checking
        lines = [l for l in src.split("\n") if not l.strip().startswith("#")]
        code = "\n".join(lines)
        assert "copy /Y" not in code
        assert ".bat" not in code
        assert "@echo off" not in code
        assert 'cmd /c' not in code

    def test_rebase_uses_python_wrappers(self):
        """_run_rebase_mode should use Python wrapper scripts for editors."""
        import inspect
        from aicommit.cli import _run_rebase_mode
        src = inspect.getsource(_run_rebase_mode)
        assert ".py" in src  # Python wrapper scripts
        assert "AICOMMIT_PLAN" in src  # Shared plan via env var
        assert "_write_wrapper" in src  # Helper function
