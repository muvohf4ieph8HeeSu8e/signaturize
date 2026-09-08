"""Load and validate signaturize TOML configuration.

A Config is always fully populated from built-in defaults; passing a TOML
file to load_config() only overrides the keys it explicitly sets.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass
class PaperConfig:
    width_in: float = 11.0
    height_in: float = 8.5


@dataclass
class TrimConfig:
    width_in: float = 5.5
    height_in: float = 8.5
    margin_in: float = 0.6


@dataclass
class FontConfig:
    name: str = "bookman"


@dataclass
class ImpositionConfig:
    # Some printers mirror the back face of a duplexed sheet left/right
    # relative to the front face -- see impose.py's build() for detail.
    duplex_mirror: bool = False


@dataclass
class GrayscaleConfig:
    enabled: bool = True
    contrast_stretch: str = "1%x1%"


@dataclass
class Config:
    paper: PaperConfig = field(default_factory=PaperConfig)
    trim: TrimConfig = field(default_factory=TrimConfig)
    font: FontConfig = field(default_factory=FontConfig)
    imposition: ImpositionConfig = field(default_factory=ImpositionConfig)
    grayscale: GrayscaleConfig = field(default_factory=GrayscaleConfig)


_SECTIONS = {
    "paper": "paper",
    "trim": "trim",
    "font": "font",
    "imposition": "imposition",
    "grayscale": "grayscale",
}


def load_config(path: Path | str | None) -> Config:
    """Build a Config from built-in defaults, optionally overridden by a TOML file."""
    config = Config()
    if path is None:
        return config

    with Path(path).open("rb") as f:
        data = tomllib.load(f)

    for section_name in _SECTIONS:
        overrides = data.get(section_name)
        if not overrides:
            continue
        current = getattr(config, section_name)
        setattr(config, section_name, replace(current, **overrides))

    return config
