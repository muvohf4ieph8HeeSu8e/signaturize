"""Binding profiles: the padding, blank-leaf, and nesting choices that
depend on how a book will be bound rather than on its content.

A pamphlet stapled at the fold needs no facing blanks; a hardcover needs a
blank leaf (or more) at the front and back for the case to attach to.
These are shipped as TOML under impose/binding_profiles/ so they can be
copied and adjusted without touching code, the same pattern config/
profiles/ uses for typesetting.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields, replace
from importlib import resources


class BindingError(ValueError):
    pass


@dataclass(frozen=True)
class BindingProfile:
    name: str = "pamphlet"
    # Blank leaves inserted before/after the content, for a binding's own
    # facing pages (e.g. hardcover endpapers) -- counted in LEAVES, not
    # pages, so a value of 1 always adds one recto+verso blank pair.
    leading_blank_leaves: int = 0
    trailing_blank_leaves: int = 0
    # How many sheets are nested together to form one signature (folds>=1
    # schemes only; ignored for folds=0/single leaves, where every leaf is
    # its own sheet). The last signature may use fewer sheets than
    # nest_preferred (down to 1) to reduce padding.
    nest_preferred: int = 8
    nest_max: int = 8
    # Warn (not error) if padding exceeds this many pages.
    max_pad_pages: int = 4


def list_binding_profiles() -> list[str]:
    root = resources.files(__package__) / "binding_profiles"
    return sorted(p.name.removesuffix(".toml") for p in root.iterdir() if p.name.endswith(".toml"))


def load_binding_profile(source: str) -> BindingProfile:
    """Load a shipped binding profile by name."""
    resource = resources.files(__package__) / "binding_profiles" / f"{source}.toml"
    if not resource.is_file():
        raise BindingError(
            f"unknown binding profile {source!r}; available: {', '.join(list_binding_profiles())}"
        )
    data = tomllib.loads(resource.read_text(encoding="utf-8"))
    known = {f.name for f in fields(BindingProfile)}
    unknown = sorted(set(data) - known - {"name"})
    if unknown:
        raise BindingError(f"binding profile {source!r}: unknown key(s): {', '.join(unknown)}")
    return replace(BindingProfile(name=source), **{k: v for k, v in data.items() if k != "name"})
