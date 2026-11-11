"""Modrinth: поиск и установка модов, шейдеров и ресурспаков (официальный открытый API)."""
import json
import os
import urllib.parse

from . import net

API = "https://api.modrinth.com/v2"
KIND_DIRS = {"mod": "mods", "shader": "shaderpacks", "resourcepack": "resourcepacks"}

# slug -> (название, описание)
OPT_MODS = {
    "sodium": ("Sodium", "Современный рендер — самый большой прирост FPS"),
    "lithium": ("Lithium", "Оптимизация игровой логики и тиков"),
    "ferrite-core": ("FerriteCore", "Снижает потребление оперативной памяти"),
    "modernfix": ("ModernFix", "Быстрый старт игры, меньше RAM, меньше лагов"),
    "immediatelyfast": ("ImmediatelyFast", "Ускоряет отрисовку интерфейса и текста"),
    "entityculling": ("Entity Culling", "Не рисует сущности за стенами"),
    "krypton": ("Krypton", "Оптимизация сетевого стека"),
    "dynamic-fps": ("Dynamic FPS", "Снижает нагрузку, когда окно в фоне"),
    "sodium-extra": ("Sodium Extra", "Дополнительные настройки графики Sodium"),
    "iris": ("Iris Shaders", "Поддержка шейдеров (нужен вместе с Sodium)"),
    "fabric-api": ("Fabric API", "Базовая библиотека для большинства модов"),
}


def search(query, kind, mc, loader, index="downloads", offset=0, limit=20):
    facets = [[f"project_type:{kind}"]]
    if mc:
        facets.append([f"versions:{mc}"])
    if kind == "mod" and loader and loader != "vanilla":
        facets.append([f"categories:{loader}"])
    q = urllib.parse.urlencode({"query": query, "facets": json.dumps(facets), "limit": limit,
                                "offset": offset, "index": index})
    data = net.get_json(f"{API}/search?{q}", 20)
    return data.get("hits", []), data.get("total_hits", 0)


def best_version(project, mc, loader=None, relax=False):
    def fetch(with_mc):
        params = {}
        if loader:
            params["loaders"] = json.dumps([loader])
        if with_mc and mc:
            params["game_versions"] = json.dumps([mc])
        q = urllib.parse.urlencode(params)
        return net.get_json(f"{API}/project/{urllib.parse.quote(project)}/version" + (f"?{q}" if q else ""), 20)
    vers = fetch(True)
    if not vers and relax:
        vers = fetch(False)
    if not vers:
        return None
    for v in vers:
        if v.get("version_type") == "release":
            return v
    return vers[0]


# ---------- манифест установленного ----------
def _mf_path(game_dir):
    return os.path.join(game_dir, "kinetics_installed.json")


def load_installed(game_dir):
    try:
        with open(_mf_path(game_dir), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_installed(game_dir, data):
    os.makedirs(game_dir, exist_ok=True)
    with open(_mf_path(game_dir), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_installed(manifest, project_id=None, slug=None):
    for k, v in manifest.items():
        if (project_id and k == project_id) or (slug and v.get("slug") == slug):
            return True
    return False


def _install(project, kind, mc, loader, folder, manifest, log, force, visited):
    if project in visited:
        return
    visited.add(project)
    for k, v in manifest.items():
        if (k == project or v.get("slug") == project) and not force \
                and os.path.isfile(os.path.join(folder, v["file"])):
            return
    ver = best_version(project, mc, loader if kind == "mod" else None, relax=(kind != "mod"))
    if not ver:
        log(f"  • {project}: нет сборки для {mc} — пропущено")
        return
    files = ver.get("files") or []
    if not files:
        return
    f = next((x for x in files if x.get("primary")), files[0])
    pid = ver.get("project_id", project)
    old = manifest.get(pid, {}).get("file")
    dest = os.path.join(folder, f["filename"])
    if old and old != f["filename"]:
        for suffix in ("", ".disabled"):
            try:
                os.remove(os.path.join(folder, old + suffix))
            except OSError:
                pass
    if not os.path.isfile(dest):
        log(f"  • скачиваю {f['filename']}")
        net.download(f["url"], dest, (f.get("hashes") or {}).get("sha1"))
    manifest[pid] = {"file": f["filename"], "slug": project, "kind": kind}
    if kind == "mod":
        for dep in ver.get("dependencies", []):
            if dep.get("dependency_type") == "required" and dep.get("project_id"):
                _install(dep["project_id"], "mod", mc, loader, folder, manifest, log, force, visited)


def install_project(project, kind, mc, loader, game_dir, log, force=False):
    folder = os.path.join(game_dir, KIND_DIRS[kind])
    os.makedirs(folder, exist_ok=True)
    manifest = load_installed(game_dir)
    try:
        _install(project, kind, mc, loader, folder, manifest, log, force, set())
    finally:
        _save_installed(game_dir, manifest)


def sync(game_dir, mc, slugs, log, force=False):
    sp = os.path.join(game_dir, "kinetics_skip.json")
    try:
        with open(sp, "r", encoding="utf-8") as f:
            skip = set(json.load(f))
    except Exception:
        skip = set()
    for s in slugs:
        key = f"{s}@{mc}"
        if key in skip and not force:
            continue  # для этой версии сборки нет — не мучаем сеть при каждом запуске
        try:
            install_project(s, "mod", mc, "fabric", game_dir, log, force)
            if not is_installed(load_installed(game_dir), slug=s):
                skip.add(key)
        except Exception as e:  # noqa
            log(f"  • {s}: ошибка ({e})")
    try:
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(sorted(skip), f)
    except OSError:
        pass


# ---------- локальные файлы ----------
def list_installed(game_dir):
    out = []
    for kind, d in KIND_DIRS.items():
        folder = os.path.join(game_dir, d)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            p = os.path.join(folder, name)
            if os.path.isfile(p) or (kind == "shader" and os.path.isdir(p)):
                size = os.path.getsize(p) if os.path.isfile(p) else 0
                out.append({"kind": kind, "name": name, "path": p, "size": size,
                            "disabled": name.endswith(".disabled")})
    return out


def toggle_disabled(path):
    new = path[:-9] if path.endswith(".disabled") else path + ".disabled"
    os.replace(path, new)
    return new


def enable_shader(game_dir, filename):
    """Best-effort: прописывает шейдер в config/iris.properties."""
    cfg = os.path.join(game_dir, "config")
    os.makedirs(cfg, exist_ok=True)
    path = os.path.join(cfg, "iris.properties")
    lines, seen = [], set()
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f.read().splitlines():
                k = line.split("=", 1)[0]
                if k in ("shaderPack", "enableShaders"):
                    continue
                lines.append(line)
    lines += [f"shaderPack={filename}", "enableShaders=true"]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def remove_project(game_dir, project_id=None, slug=None):
    """Удаляет файл установленного через лаунчер мода/шейдера и запись о нём."""
    mf = load_installed(game_dir)
    for k, v in list(mf.items()):
        if (project_id and k == project_id) or (slug and v.get("slug") == slug):
            folder = os.path.join(game_dir, KIND_DIRS.get(v.get("kind", "mod"), "mods"))
            for suf in ("", ".disabled"):
                try:
                    os.remove(os.path.join(folder, v["file"] + suf))
                except OSError:
                    pass
            mf.pop(k)
            _save_installed(game_dir, mf)
            return True
    return False


def forget_file(game_dir, filename):
    name = filename[:-9] if filename.endswith(".disabled") else filename
    mf = load_installed(game_dir)
    keys = [k for k, v in mf.items() if v.get("file") == name]
    for k in keys:
        mf.pop(k)
    if keys:
        _save_installed(game_dir, mf)


def add_files(game_dir, kind, paths):
    """Копирует свои файлы (.jar / .zip) в нужную папку профиля."""
    import shutil
    folder = os.path.join(game_dir, KIND_DIRS[kind])
    os.makedirs(folder, exist_ok=True)
    n = 0
    for src in paths:
        try:
            shutil.copy2(src, os.path.join(folder, os.path.basename(src)))
            n += 1
        except OSError:
            pass
    return n
