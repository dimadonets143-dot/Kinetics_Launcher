import copy
import json
import os

from . import config, perf

DEFAULT_GAME_OPTIONS = dict(render_distance=10, simulation_distance=8, max_fps=120, vsync=False,
                            graphics=1, particles=1, entity_distance=1.0, biome_blend=2,
                            clouds=True, mipmap=2, ao=True, gui_scale=0)

DEFAULT_PROFILE = {
    "name": "Default", "username": "Player",
    "version_type": "release", "version": "",
    "loader": "vanilla", "loader_version": "",
    "ram_min": 1024, "ram_max": 4096,
    "java_path": "", "jvm_preset": "balanced", "jvm_extra": "",
    "game_args": "", "width": 854, "height": 480, "fullscreen": False,
    "server": "", "game_dir": "",
    "opt_mods": [], "apply_game_options": False,
    "jvm_toggles": ["utf8", "log4j"], "pre_cmd": "", "post_cmd": "", "env": "", "priority": "normal",
    "game_options": DEFAULT_GAME_OPTIONS,
}

DEFAULT_SETTINGS = {"threads": 8, "verify_files": False, "after_launch": "minimize",
                    "last_profile": "Default", "accent": "#7c5cff", "animations": True,
                    "theme": "Полночь", "hero_bg": "particles", "hero_image": "", "font": "Segoe UI",
                    "recent": [], "perf": dict(perf.DEFAULT_PERF)}


def new_profile(name):
    p = copy.deepcopy(DEFAULT_PROFILE)
    p["name"] = name
    return p


class Store:
    def __init__(self):
        self.settings = dict(DEFAULT_SETTINGS)
        self.profiles = {}
        self.load()

    def _merge(self, raw, name):
        p = copy.deepcopy(DEFAULT_PROFILE)
        p.update({k: v for k, v in raw.items() if k != "game_options"})
        p["game_options"] = {**DEFAULT_GAME_OPTIONS, **raw.get("game_options", {})}
        p["name"] = name
        return p

    def load(self):
        try:
            with open(config.CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        self.settings.update(data.get("settings", {}))
        self.settings["perf"] = perf.normalize(self.settings.get("perf"))
        for name, raw in data.get("profiles", {}).items():
            self.profiles[name] = self._merge(raw, name)
        if not self.profiles:
            self.profiles["Default"] = new_profile("Default")
        if self.settings.get("last_profile") not in self.profiles:
            self.settings["last_profile"] = next(iter(self.profiles))

    def save(self):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        tmp = config.CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"settings": self.settings, "profiles": self.profiles}, f,
                      ensure_ascii=False, indent=2)
        os.replace(tmp, config.CONFIG_FILE)
