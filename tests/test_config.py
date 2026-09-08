"""Unit tests for TOML config loading/overriding."""
from signaturize.config import load_config


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
