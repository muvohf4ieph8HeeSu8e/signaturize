"""Load and validate signaturize TOML configuration.

A Config is always fully populated from built-in defaults; passing a TOML
file (or a shipped profile name) to load_config() only overrides the keys it
explicitly sets. Unknown sections or keys are an error, so a typo in a
config file never silently falls back to a default.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, replace
from importlib import resources
from pathlib import Path

DEFAULT_PROFILE = "default"


class ConfigError(ValueError):
    """Raised for an unreadable, unknown-profile, or invalid config."""


@dataclass
class TrimConfig:
    # Trim width/height are derived from --paper + --scheme (see
    # impose/scheme.py's resolve_scheme()), not configured here -- only
    # the text margin is a config/project-level choice.
    margin_in: float = 0.6


@dataclass
class FontConfig:
    name: str = "bookman"


@dataclass
class ImpositionConfig:
    # A standard duplex printer flipping a sheet on its long edge mirrors
    # the back face's columns left/right relative to the front -- on by
    # default, verified byte-for-byte against five real, physically
    # printed-and-folded books (see tests/test_regression_legacy.py and
    # impose/render.py's render(duplex_mirror=...)). Set this to false
    # only if your printer's duplex unit doesn't do this (uncommon).
    duplex_mirror: bool = True


@dataclass
class GrayscaleConfig:
    enabled: bool = True
    contrast_stretch: str = "1%x1%"


@dataclass
class Config:
    trim: TrimConfig = field(default_factory=TrimConfig)
    font: FontConfig = field(default_factory=FontConfig)
    imposition: ImpositionConfig = field(default_factory=ImpositionConfig)
    grayscale: GrayscaleConfig = field(default_factory=GrayscaleConfig)


_SECTIONS = tuple(f.name for f in fields(Config))


def list_profiles() -> list[str]:
    """Names of the profiles shipped in signaturize/config/profiles/."""
    root = resources.files(__package__) / "profiles"
    return sorted(p.name.removesuffix(".toml") for p in root.iterdir() if p.name.endswith(".toml"))


def _read_toml(path: Path | str) -> dict:
    try:
        with Path(path).open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from None


def _read_profile(name: str) -> dict:
    resource = resources.files(__package__) / "profiles" / f"{name}.toml"
    if not resource.is_file():
        raise ConfigError(f"unknown profile {name!r}; available: {', '.join(list_profiles())}")
    return tomllib.loads(resource.read_text(encoding="utf-8"))


def _apply(config: Config, data: dict, origin: str) -> None:
    for section_name, overrides in data.items():
        if section_name not in _SECTIONS:
            raise ConfigError(f"{origin}: unknown section [{section_name}]; known: {', '.join(_SECTIONS)}")
        if not overrides:
            continue
        current = getattr(config, section_name)
        known = {f.name for f in fields(current)}
        unknown = sorted(set(overrides) - known)
        if unknown:
            raise ConfigError(
                f"{origin}: unknown key(s) in [{section_name}]: {', '.join(unknown)}; "
                f"known: {', '.join(sorted(known))}"
            )
        setattr(config, section_name, replace(current, **overrides))


def load_config(source: Path | str | None) -> Config:
    """Build a Config from built-in defaults, optionally overridden.

    `source` is None (defaults), a path to a TOML file, or the bare name of
    a shipped profile (e.g. "default"). An existing file wins over a
    profile of the same name.
    """
    config = Config()
    if source is None:
        return config

    as_path = Path(source)
    is_bare_name = as_path.suffix != ".toml" and as_path.parent == Path(".")
    if is_bare_name and not as_path.exists():
        _apply(config, _read_profile(str(source)), f"profile {source!r}")
    else:
        _apply(config, _read_toml(as_path), str(as_path))
    return config
