"""Работа с официальными файлами Mojang: версии, библиотеки, ассеты, natives."""
import hashlib
import json
import os
import platform
import re
import shutil
import uuid
import zipfile

from . import config, net

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
RESOURCES_URL = "https://resources.download.minecraft.net/"
LIBRARIES_URL = "https://libraries.minecraft.net/"


# ---------- манифест и версии ----------
def load_manifest():
    cache = os.path.join(config.CACHE_DIR, "version_manifest.json")
    try:
        data = net.get_json(MANIFEST_URL, 15)
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data
    except Exception:
        if os.path.isfile(cache):
            with open(cache, "r", encoding="utf-8") as f:
                return json.load(f)
        raise


def version_json_path(vid):
    return os.path.join(config.VERS_DIR, vid, vid + ".json")


def installed_versions():
    out = []
    if os.path.isdir(config.VERS_DIR):
        for d in sorted(os.listdir(config.VERS_DIR)):
            if os.path.isfile(version_json_path(d)):
                out.append(d)
    return out


def ensure_version_json(vid):
    p = version_json_path(vid)
    if not os.path.isfile(p):
        manifest = load_manifest()
        for v in manifest["versions"]:
            if v["id"] == vid:
                net.download(v["url"], p, v.get("sha1"))
                break
        else:
            raise ValueError(f"Версия {vid} не найдена в манифесте Mojang")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_version(vid):
    """Загружает JSON версии и склеивает с родителем (inheritsFrom), как у Fabric."""
    data = ensure_version_json(vid)
    parent_id = data.get("inheritsFrom")
    if not parent_id:
        data["_jar_id"] = vid
        return data
    parent = resolve_version(parent_id)
    merged = dict(parent)
    for k, v in data.items():
        if k == "libraries":
            merged["libraries"] = list(v) + list(parent.get("libraries", []))
        elif k == "arguments":
            pa = parent.get("arguments", {})
            merged["arguments"] = {
                "game": list(pa.get("game", [])) + list(v.get("game", [])),
                "jvm": list(pa.get("jvm", [])) + list(v.get("jvm", [])),
            }
        else:
            merged[k] = v
    merged["_jar_id"] = parent["_jar_id"]
    merged["id"] = vid
    return merged


# ---------- правила ----------
def rules_allow(rules, features=None):
    if not rules:
        return True
    features = features or {}
    allowed = False
    for r in rules:
        ok = True
        o = r.get("os")
        if o:
            if "name" in o and o["name"] != config.OS_NAME:
                ok = False
            if "arch" in o and o["arch"] != config.ARCH:
                ok = False
            if "version" in o and not re.search(o["version"], platform.version() or ""):
                ok = False
        feats = r.get("features")
        if feats:
            for k, v in feats.items():
                if bool(features.get(k, False)) != bool(v):
                    ok = False
        if ok:
            allowed = r.get("action") == "allow"
    return allowed


def maven_path(name):
    ext = "jar"
    if "@" in name:
        name, ext = name.split("@", 1)
    parts = name.split(":")
    g, a, v = parts[0], parts[1], parts[2]
    cl = parts[3] if len(parts) > 3 else None
    fn = f"{a}-{v}" + (f"-{cl}" if cl else "") + "." + ext
    return f"{g.replace('.', '/')}/{a}/{v}/{fn}"


# ---------- библиотеки ----------
def collect_libraries(vdata):
    """Возвращает (classpath, natives[(jar, excludes)], tasks)."""
    cp, natives, tasks, seen = [], [], [], set()
    for lib in vdata.get("libraries", []):
        if not rules_allow(lib.get("rules")):
            continue
        name = lib["name"]
        dl = lib.get("downloads")
        parts = name.split("@")[0].split(":")

        # старый формат natives (до 1.19)
        if lib.get("natives"):
            cl = lib["natives"].get(config.OS_NAME)
            if cl:
                cl = cl.replace("${arch}", "32" if config.ARCH == "x86" else "64")
                art = ((dl or {}).get("classifiers") or {}).get(cl)
                if art:
                    p = os.path.join(config.LIB_DIR, art["path"].replace("/", os.sep))
                    tasks.append({"url": art["url"], "path": p, "sha1": art.get("sha1"),
                                  "size": art.get("size")})
                    natives.append((p, (lib.get("extract") or {}).get("exclude", [])))

        key = ":".join(parts[:2] + parts[3:])
        if key in seen:
            continue
        if dl is None:  # формат Fabric/Forge: только имя + url репозитория
            rel = maven_path(name)
            base = lib.get("url", LIBRARIES_URL)
            if not base.endswith("/"):
                base += "/"
            url, sha1, size = base + rel, lib.get("sha1"), lib.get("size")
        elif "artifact" in dl:
            art = dl["artifact"]
            rel, url, sha1, size = art["path"], art.get("url"), art.get("sha1"), art.get("size")
        else:
            continue
        seen.add(key)
        p = os.path.join(config.LIB_DIR, rel.replace("/", os.sep))
        if url:
            tasks.append({"url": url, "path": p, "sha1": sha1, "size": size})
        cp.append(p)
        if len(parts) > 3 and parts[3].startswith("natives"):
            natives.append((p, []))
    return cp, natives, tasks


def extract_natives(natives, vid):
    d = os.path.join(config.NATIVES_DIR, vid)
    os.makedirs(d, exist_ok=True)
    for jar, excludes in natives:
        if not os.path.isfile(jar):
            continue
        try:
            with zipfile.ZipFile(jar) as z:
                for info in z.infolist():
                    n = info.filename
                    if info.is_dir() or any(n.startswith(e) for e in excludes):
                        continue
                    if not n.lower().endswith((".dll", ".so", ".dylib", ".jnilib")):
                        continue
                    target = os.path.join(d, os.path.basename(n))
                    if os.path.isfile(target) and os.path.getsize(target) == info.file_size:
                        continue
                    try:
                        with z.open(info) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                    except OSError:
                        pass  # файл может быть занят запущенной игрой
        except zipfile.BadZipFile:
            pass
    return d


# ---------- клиент, логирование ----------
def client_jar_path(vdata):
    jid = vdata["_jar_id"]
    return os.path.join(config.VERS_DIR, jid, jid + ".jar")


def client_and_logging_tasks(vdata):
    tasks, log_cfg = [], None
    c = (vdata.get("downloads") or {}).get("client")
    if c:
        tasks.append({"url": c["url"], "path": client_jar_path(vdata), "sha1": c.get("sha1"),
                      "size": c.get("size")})
    lg = (vdata.get("logging") or {}).get("client")
    if lg and lg.get("file"):
        f = lg["file"]
        log_cfg = os.path.join(config.ASSETS_DIR, "log_configs", f["id"])
        tasks.append({"url": f["url"], "path": log_cfg, "sha1": f.get("sha1"), "size": f.get("size")})
    return tasks, log_cfg


# ---------- ассеты ----------
def prepare_assets(vdata, game_dir, threads, progress, strict=False):
    """Скачивает ассеты. Возвращает путь для ${game_assets}."""
    ai = vdata.get("assetIndex")
    if not ai:
        return config.ASSETS_DIR
    idx_path = os.path.join(config.ASSETS_DIR, "indexes", ai["id"] + ".json")
    if not net.file_ok(idx_path, ai.get("sha1"), ai.get("size")):
        net.download(ai["url"], idx_path, ai.get("sha1"))
    with open(idx_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    objects = index.get("objects", {})
    tasks = []
    for name, obj in objects.items():
        h = obj["hash"]
        tasks.append({"url": f"{RESOURCES_URL}{h[:2]}/{h}",
                      "path": os.path.join(config.ASSETS_DIR, "objects", h[:2], h),
                      "sha1": h, "size": obj.get("size")})
    net.download_many(tasks, threads, progress, strict)

    virtual = index.get("virtual") or index.get("map_to_resources")
    if not virtual:
        return config.ASSETS_DIR
    target = (os.path.join(game_dir, "resources") if index.get("map_to_resources")
              else os.path.join(config.ASSETS_DIR, "virtual", "legacy"))
    for name, obj in objects.items():
        h = obj["hash"]
        src = os.path.join(config.ASSETS_DIR, "objects", h[:2], h)
        dst = os.path.join(target, *name.split("/"))
        if os.path.isfile(src) and not os.path.isfile(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
    return target


# ---------- оффлайн-профиль ----------
def offline_uuid(name):
    h = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest())
    h[6] = (h[6] & 0x0F) | 0x30
    h[8] = (h[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(h)))
