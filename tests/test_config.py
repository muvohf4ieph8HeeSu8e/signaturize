"""Unit tests for TOML config loading/overriding."""
import pytest

from signaturize.config import ConfigError, list_profiles, load_config


def test_defaults_with_no_path():
    config = load_config(None)
    assert config.trim.margin_in == 0.6
    assert config.imposition.duplex_mirror is False


def test_partial_override_keeps_other_defaults(tmp_path):
    config_file = tmp_path / "custom.toml"
    config_file.write_text(
        '[trim]\nmargin_in = 0.5\n'
        '[imposition]\nduplex_mirror = true\n',
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.trim.margin_in == 0.5
    assert config.imposition.duplex_mirror is True
    # untouched sections keep built-in defaults
    assert config.font.name == "bookman"


def test_unknown_key_is_an_error_naming_the_key(tmp_path):
    config_file = tmp_path / "typo.toml"
    config_file.write_text("[trim]\nmargin_inches = 4\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="margin_inches"):
        load_config(config_file)


def test_unknown_section_is_an_error(tmp_path):
    config_file = tmp_path / "typo.toml"
    config_file.write_text("[nope]\nwidth_in = 4\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="nope"):
        load_config(config_file)


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_shipped_profile_loads_by_name_and_matches_defaults():
    assert "default" in list_profiles()
    assert load_config("default") == load_config(None)


def test_unknown_profile_lists_the_available_ones():
    with pytest.raises(ConfigError, match="default"):
        load_config("no-such-profile")
