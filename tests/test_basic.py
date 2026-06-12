"""Basic tests for aicommit."""


def test_import():
    """Test that the package can be imported."""
    import aicommit
    assert aicommit.__version__ == "1.0.0"


def test_config_defaults():
    """Test default configuration values."""
    from aicommit.config import DEFAULT_CONFIG
    assert "api" in DEFAULT_CONFIG
    assert "commit" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["commit"]["style"] == "conventional"
    assert DEFAULT_CONFIG["commit"]["max_diff_lines"] == 200


def test_style_prompts():
    """Test that all style prompts exist."""
    from aicommit.prompts import STYLE_PROMPTS
    assert "conventional" in STYLE_PROMPTS
    assert "emoji" in STYLE_PROMPTS
    assert "simple" in STYLE_PROMPTS
    assert "detailed" in STYLE_PROMPTS


def test_git_utils_no_repo():
    """Test git_utils in non-git directory."""
    import tempfile
    import os
    from aicommit.git_utils import is_git_repo

    with tempfile.TemporaryDirectory() as tmpdir:
        # Use os.chdir but restore after test
        original = os.getcwd()
        try:
            os.chdir(tmpdir)
            assert not is_git_repo()
        finally:
            os.chdir(original)
