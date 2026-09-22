"""Unit tests for TOML config loading/overriding."""
import pytest

from signaturize.config import ConfigError, list_profiles, load_config


def test_defaults_with_no_path():
    config = load_config(None)
    assert config.paper.width_in == 11.0
    assert config.trim.width_in == 5.5
    assert config.imposition.duplex_mirror is False


def test_partial_override_keeps_other_defaults(tmp_path):
    config_file = tmp_path / "custom.toml"
    config_file.write_text(
        '[trim]\nwidth_in = 4.25\nheight_in = 5.5\nmargin_in = 0.5\n'
        '[imposition]\nduplex_mirror = true\n',
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.trim.width_in == 4.25
    assert config.trim.height_in == 5.5
    assert config.imposition.duplex_mirror is True
    # untouched sections keep built-in defaults
    assert config.paper.width_in == 11.0
    assert config.font.name == "bookman"


def test_unknown_key_is_an_error_naming_the_key(tmp_path):
    config_file = tmp_path / "typo.toml"
    config_file.write_text("[trim]\nwidth_inches = 4\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="width_inches"):
        load_config(config_file)


def test_unknown_section_is_an_error(tmp_path):
    config_file = tmp_path / "typo.toml"
    config_file.write_text("[papr]\nwidth_in = 4\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="papr"):
        load_config(config_file)


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_shipped_profile_loads_by_name_and_matches_defaults():
    assert "pamphlet-folio-letter" in list_profiles()
    assert load_config("pamphlet-folio-letter") == load_config(None)


def test_unknown_profile_lists_the_available_ones():
    with pytest.raises(ConfigError, match="pamphlet-folio-letter"):
        load_config("no-such-profile")
