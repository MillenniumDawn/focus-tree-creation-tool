"""Persisted user settings for the HOI4 Content Maker.

The JSON file stays at ``~/.hoi4_focus_maker.json``. This object owns those
settings. It does not own a loaded mod, edit targets, or any Tk image.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from hoi4cm.core.config import cfg_load, cfg_save
from hoi4cm.mod.index import ScanSettings


def _default_event_dim_profiles() -> dict[str, dict[str, tuple[int, int]]]:
    return {"vanilla": {"country": (210, 176), "news": (397, 165)}}


@dataclass
class AppConfig:
    """User preferences loaded from and written back to the config file."""

    path_goals: str = os.path.join("gfx", "interface", "goals")
    path_ideas_gfx: str = os.path.join("gfx", "interface", "ideas")
    path_event_pictures: str = os.path.join("gfx", "event_pictures")
    event_dim_profiles: dict[str, Any] = field(
        default_factory=_default_event_dim_profiles
    )
    event_dim_active_profile: str = "vanilla"
    custom_mod_path: str = ""
    custom_gfx_dirs: list[str] = field(default_factory=list)
    country_tag_names: dict[str, str] = field(default_factory=dict)
    loc_token_style: str = "colon"
    loc_language: str = "english"
    md_mode_override: bool | None = None
    sidebar_refresh_skip: bool = True
    window_geometry: str = ""
    recent_mods: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> AppConfig:
        """Return settings from disk, or defaults when the file is missing."""
        from hoi4cm.focus_tree.loc import LocTarget

        cfg = cfg_load()
        config = cls()
        if not isinstance(cfg, dict):
            return config
        for key in (
            "path_goals",
            "path_ideas_gfx",
            "path_event_pictures",
            "event_dim_active_profile",
            "custom_mod_path",
            "loc_token_style",
        ):
            if isinstance(cfg.get(key), str):
                setattr(config, key, cfg[key])
        profiles = cfg.get("event_dim_profiles")
        if isinstance(profiles, dict):
            config.event_dim_profiles = profiles
        dirs = cfg.get("custom_gfx_dirs")
        if isinstance(dirs, list):
            config.custom_gfx_dirs = [item for item in dirs if isinstance(item, str)]
        names = cfg.get("country_tag_names")
        if isinstance(names, dict):
            config.country_tag_names = {
                str(tag): str(name) for tag, name in names.items()
            }
        override = cfg.get("md_mode_override", None)
        if isinstance(override, bool):
            config.md_mode_override = override
        if "sidebar_refresh_skip" in cfg:
            config.sidebar_refresh_skip = bool(cfg["sidebar_refresh_skip"])
        geometry = cfg.get("window_geometry", "")
        if isinstance(geometry, str):
            config.window_geometry = geometry
        recent = cfg.get("recent_mods", [])
        if isinstance(recent, list):
            config.recent_mods = [item for item in recent if isinstance(item, str)]
        language = cfg.get("loc_language", config.loc_language)
        config.loc_language = LocTarget(
            language if isinstance(language, str) else "english"
        ).language
        return config

    def save(self, window_geometry: str | None = None, last_mod_path: str = "") -> bool:
        """Write these settings. Unknown keys already in the file are kept."""
        if window_geometry is not None:
            self.window_geometry = window_geometry
        payload = {
            "path_goals": self.path_goals,
            "path_ideas_gfx": self.path_ideas_gfx,
            "path_event_pictures": self.path_event_pictures,
            "event_dim_profiles": self.event_dim_profiles,
            "event_dim_active_profile": self.event_dim_active_profile,
            "custom_mod_path": self.custom_mod_path,
            "custom_gfx_dirs": list(self.custom_gfx_dirs),
            "country_tag_names": dict(self.country_tag_names),
            "loc_token_style": self.loc_token_style,
            "loc_language": self.loc_language,
            "md_mode_override": self.md_mode_override,
            "sidebar_refresh_skip": self.sidebar_refresh_skip,
            "window_geometry": self.window_geometry,
            "last_mod_path": last_mod_path,
            "recent_mods": list(self.recent_mods),
        }
        return cfg_save(payload)

    def scan_settings(self, *, use_cache: bool = True) -> ScanSettings:
        """Copy the inputs a scan needs so a worker cannot share live lists."""
        override = self.md_mode_override
        return ScanSettings(
            path_goals=self.path_goals,
            path_ideas_gfx=self.path_ideas_gfx,
            path_event_pictures=self.path_event_pictures,
            custom_gfx_dirs=tuple(self.custom_gfx_dirs),
            md_mode_override=override if isinstance(override, bool) else None,
            loc_language=self.loc_language,
            use_cache=use_cache,
        )

    @property
    def loc_target(self):
        """Return the normalised localisation target for the saved language."""
        from hoi4cm.focus_tree.loc import LocTarget

        return LocTarget(self.loc_language)


__all__ = ["AppConfig"]
