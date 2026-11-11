import glob
import json
import os
import re
import shutil
import subprocess
import tarfile
import zipfile

from . import config, net

_cache = {}
_disk = None
_DISK_FILE = os.path.join(config.CACHE_DIR, "java_cache.json")
_NOWIN = 0x08000000 if config.IS_WIN else 0
_EXE = "java.exe" if config.IS_WIN else "java"


def _load_disk():
    global _disk
    if _disk is None:
        try:
            with open(_DISK_FILE, "r", encoding="utf-8") as f:
                _disk = json.load(f)
        except Exception:
            _disk = {}
        _disk.setdefault("ver", {})
        _disk.setdefault("pref", {})
    return _disk


def _save_disk():
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        with open(_DISK_FILE, "w", encoding="utf-8") as f:
            json.dump(_disk, f)
    except OSError:
        pass


def _sig(path):
    try:
        st = os.stat(path)
        return f"{st.st_mtime_ns}-{st.st_size}"
    except OSError:
        return None


def java_major(path):
    if path in _cache:
        return _cache[path]
    d, sig = _load_disk(), _sig(path)
    hit = d["ver"].get(path)
    if hit and sig and hit[0] == sig:
        _cache[path] = hit[1]
        return hit[1]
    major = None
    try:
        r = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=20,
                           creationflags=_NOWIN)
        out = (r.stderr or "") + (r.stdout or "")
        m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
        if m:
            major = int(m.group(1))
            if major == 1 and m.group(2):
                major = int(m.group(2))
    except Exception:
        pass
    _cache[path] = major
    if major and sig:
        d["ver"][path] = [sig, major]
        _save_disk()
    return major


def _scan(root, depth=4):
    found = []
    if not root or not os.path.isdir(root):
        return found
    base = root.rstrip(os.sep).count(os.sep)
    for cur, dirs, files in os.walk(root):
        if cur.count(os.sep) - base >= depth:
            dirs[:] = []
        if os.path.basename(cur) == "bin" and _EXE in files:
            found.append(os.path.join(cur, _EXE))
            dirs[:] = []
    return found


def find_javas():
    """Список (major, path), отсортирован по версии."""
    cands = set(_scan(config.RUNTIME_DIR, 5))
    jh = os.environ.get("JAVA_HOME")
    if jh:
        p = os.path.join(jh, "bin", _EXE)
        if os.path.isfile(p):
            cands.add(p)
    w = shutil.which("java")
    if w:
        cands.add(w)
    if config.IS_WIN:
        roots = []
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if not base:
                continue
            for sub in ("Java", "Eclipse Adoptium", "Eclipse Foundation", "Microsoft", "Zulu",
                        "BellSoft", "Amazon Corretto", "Semeru", "AdoptOpenJDK", "Programs\\Eclipse Adoptium"):
                roots.append(os.path.join(base, sub))
        appdata = os.environ.get("APPDATA")
        if appdata:
            roots.append(os.path.join(appdata, ".minecraft", "runtime"))
        for r in roots:
            cands.update(_scan(r, 4))
    else:
        for pat in ("/usr/lib/jvm/*/bin/java", "/Library/Java/JavaVirtualMachines/*/Contents/Home/bin/java"):
            cands.update(glob.glob(pat))
    res = []
    for p in cands:
        m = java_major(p)
        if m:
            res.append((m, p))
    res.sort()
    return res


def remember(required, path):
    d = _load_disk()
    d["pref"][str(required)] = path
    _save_disk()


def find_java_for(required):
    pref = _load_disk()["pref"].get(str(required))
    if pref and os.path.isfile(pref):  # быстрый путь: без сканирования диска
        m = java_major(pref)
        if m == required or (m and required > 8 and m > required):
            return pref, m
    javas = find_javas()
    for m, p in javas:
        if m == required:
            remember(required, p)
            return p, m
    if required > 8:
        for m, p in javas:
            if m > required:
                remember(required, p)
                return p, m
    return None, None


def download_java(major, progress=None, log=None):
    osn = {"windows": "windows", "linux": "linux", "osx": "mac"}[config.OS_NAME]
    arch = "aarch64" if config.ARCH == "arm64" else "x64"
    url = (f"https://api.adoptium.net/v3/binary/latest/{major}/ga/{osn}/{arch}/jre/hotspot/normal/eclipse")
    ext = ".zip" if config.IS_WIN else ".tar.gz"
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    tmp = os.path.join(config.CACHE_DIR, f"jre-{major}{ext}")
    if log:
        log(f"Скачивание Java {major} (Eclipse Temurin, ~50 МБ)...")
    net.download(url, tmp, on_bytes=(lambda d, t: progress(d, t or max(d, 1))) if progress else None)
    dest = os.path.join(config.RUNTIME_DIR, f"jre-{major}")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    if ext == ".zip":
        with zipfile.ZipFile(tmp) as z:
            z.extractall(dest)
    else:
        with tarfile.open(tmp) as t:
            base = os.path.realpath(dest)
            for m in t.getmembers():
                target = os.path.realpath(os.path.join(dest, m.name))
                if not target.startswith(base):
                    raise RuntimeError("Небезопасный архив")
            t.extractall(dest)
    try:
        os.remove(tmp)
    except OSError:
        pass
    found = _scan(dest, 5)
    if not found:
        raise RuntimeError("Не удалось найти java в скачанном архиве")
    if not config.IS_WIN:
        os.chmod(found[0], 0o755)
    remember(major, found[0])
    return found[0]
