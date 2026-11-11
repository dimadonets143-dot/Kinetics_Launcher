"""JVM-флаги, пресеты оптимизации и правка options.txt."""
import os

from . import system

# ключ -> (название, флаги)
JVM_PRESETS = {
    "balanced": ("Сбалансированный (G1GC) — рекомендуется", [
        "-XX:+UseG1GC", "-XX:+UnlockExperimentalVMOptions", "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=50", "-XX:+DisableExplicitGC", "-XX:G1NewSizePercent=20",
        "-XX:G1ReservePercent=20", "-XX:G1HeapRegionSize=16M",
        "-XX:InitiatingHeapOccupancyPercent=15", "-XX:-UsePerfData",
    ]),
    "aikar": ("Aikar's Flags (мощные ПК, 6+ ГБ)", [
        "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200",
        "-XX:+UnlockExperimentalVMOptions", "-XX:+DisableExplicitGC",
        "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M",
        "-XX:G1ReservePercent=20", "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
        "-XX:InitiatingHeapOccupancyPercent=15", "-XX:G1MixedGCLiveThresholdPercent=90",
        "-XX:G1RSetUpdatingPauseTimePercent=5", "-XX:SurvivorRatio=32",
        "-XX:+PerfDisableSharedMem", "-XX:MaxTenuringThreshold=1",
    ]),
    "lowend": ("Слабый ПК (SerialGC, минимум нагрузки)", [
        "-XX:+UseSerialGC", "-XX:+DisableExplicitGC", "-XX:-UsePerfData", "-Xshare:auto",
    ]),
    "zgc": ("ZGC (только Java 21+, минимум фризов)", []),  # собирается динамически
    "none": ("Без флагов (по умолчанию Java)", []),
}


# ключ -> (флаг, описание)
JVM_TOGGLES = {
    "utf8": ("-Dfile.encoding=UTF-8", "Кодировка UTF-8 (кириллица в логах и никах)"),
    "log4j": ("-Dlog4j2.formatMsgNoLookups=true", "Защита от Log4Shell для старых версий"),
    "ipv4": ("-Djava.net.preferIPv4Stack=true", "Предпочитать IPv4 (помогает при проблемах с сетью)"),
    "pretouch": ("-XX:+AlwaysPreTouch", "Предзагрузка памяти (долгий старт, меньше микрофризов)"),
    "codecache": ("-XX:ReservedCodeCacheSize=512m", "Увеличенный code cache (тяжёлые сборки модов)"),
    "xss": ("-Xss4M", "Увеличенный стек потоков (нужно некоторым модам)"),
}


def preset_labels():
    return {k: v[0] for k, v in JVM_PRESETS.items()}


def jvm_flags(preset, java_major=None):
    if preset == "zgc":
        if not java_major or java_major < 21:
            preset = "balanced"
        else:
            flags = ["-XX:+UseZGC"]
            if java_major < 24:
                flags.append("-XX:+ZGenerational")
            flags.append("-XX:+DisableExplicitGC")
            return flags
    return list(JVM_PRESETS.get(preset, JVM_PRESETS["balanced"])[1])


# ---------- пресеты качества ----------
QUALITY_PRESETS = {
    "lowend": {
        "label": "Слабый ПК", "jvm": "lowend",
        "options": dict(render_distance=6, simulation_distance=5, max_fps=60, vsync=False, graphics=0,
                        particles=2, entity_distance=0.5, biome_blend=0, clouds=False, mipmap=0,
                        ao=False, gui_scale=0),
        "mods": ["sodium", "lithium", "ferrite-core", "modernfix", "immediatelyfast",
                 "entityculling", "dynamic-fps"],
    },
    "balanced": {
        "label": "Баланс", "jvm": "balanced",
        "options": dict(render_distance=10, simulation_distance=8, max_fps=120, vsync=False, graphics=1,
                        particles=1, entity_distance=1.0, biome_blend=2, clouds=True, mipmap=2,
                        ao=True, gui_scale=0),
        "mods": ["sodium", "lithium", "ferrite-core", "modernfix", "immediatelyfast"],
    },
    "maxfps": {
        "label": "Максимум FPS", "jvm": "aikar",
        "options": dict(render_distance=8, simulation_distance=6, max_fps=260, vsync=False, graphics=0,
                        particles=2, entity_distance=0.75, biome_blend=1, clouds=False, mipmap=0,
                        ao=False, gui_scale=0),
        "mods": ["sodium", "lithium", "ferrite-core", "modernfix", "immediatelyfast",
                 "entityculling", "krypton"],
    },
}


def recommend():
    """Подбор настроек под железо. Возвращает dict(ram_min, ram_max, preset, jvm)."""
    ram = system.total_ram_mb()
    cores = system.cpu_cores()
    ram_max = int(ram * 0.5) // 256 * 256
    ram_max = max(1024, min(ram_max, 6144))
    ram_min = max(512, ram_max // 2 // 256 * 256)
    if ram <= 4096 or cores <= 2:
        preset, jvm = "lowend", "lowend"
    elif ram >= 12288 and cores >= 6:
        preset, jvm = "balanced", "aikar"
    else:
        preset, jvm = "balanced", "balanced"
    return {"ram_min": ram_min, "ram_max": ram_max, "preset": preset, "jvm": jvm,
            "ram_total": ram, "cores": cores}


# ---------- options.txt ----------
def _b(v):
    return "true" if v else "false"


def to_options(o):
    gm = int(o.get("graphics", 1))
    return {
        "renderDistance": int(o.get("render_distance", 10)),
        "simulationDistance": int(o.get("simulation_distance", 8)),
        "maxFps": int(o.get("max_fps", 120)),
        "enableVsync": _b(o.get("vsync", False)),
        "graphicsMode": gm,
        "fancyGraphics": _b(gm >= 1),
        "particles": int(o.get("particles", 1)),
        "entityDistanceScaling": "%.1f" % float(o.get("entity_distance", 1.0)),
        "biomeBlendRadius": int(o.get("biome_blend", 2)),
        "renderClouds": '"true"' if o.get("clouds", True) else '"false"',
        "mipmapLevels": int(o.get("mipmap", 2)),
        "ao": _b(o.get("ao", True)),
        "guiScale": int(o.get("gui_scale", 0)),
    }


def apply_game_options(game_dir, o):
    path = os.path.join(game_dir, "options.txt")
    new = to_options(o)
    lines, seen = [], set()
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f.read().splitlines():
                if ":" in line:
                    k = line.split(":", 1)[0]
                    if k in new:
                        lines.append(f"{k}:{new[k]}")
                        seen.add(k)
                        continue
                lines.append(line)
    for k, v in new.items():
        if k not in seen:
            lines.append(f"{k}:{v}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
