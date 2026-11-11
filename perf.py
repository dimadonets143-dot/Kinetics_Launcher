"""Производительность и системные настройки: графический API, выбор видеокарты Windows,
быстрый старт JVM, ярлыки, прогрев диска."""
import base64
import os
import subprocess
import sys
import threading

from . import config

DEFAULT_PERF = {"api": "opengl", "mesa_dir": "", "gpu": "auto", "fast_start": True,
                "skip_verify": False, "pause_anim": True}
APIS = {"opengl": "OpenGL", "zink": "Vulkan (Zink)", "software": "Программный"}
GPUS = {"auto": "Авто", "low": "Встроенная", "high": "Дискретная"}
MESA_URL = "https://github.com/pal1000/mesa-dist-win/releases"
_NOWIN = 0x08000000 if config.IS_WIN else 0


def normalize(cfg):
    out = dict(DEFAULT_PERF)
    out.update(cfg or {})
    return out


# ---------------------------------------------------------------- Mesa / графический API
def mesa_ok(folder):
    return bool(folder) and os.path.isfile(os.path.join(folder, "opengl32.dll"))


def mesa_status(cfg):
    cfg = normalize(cfg)
    if cfg["api"] == "opengl":
        return True, "Стандартный режим Minecraft Java: OpenGL."
    if not config.IS_WIN:
        return False, "Режимы Zink и программный доступны только на Windows."
    if mesa_ok(cfg["mesa_dir"]):
        return True, "Mesa найдена: opengl32.dll"
    return False, "Папка Mesa не выбрана или в ней нет opengl32.dll."


def effective_api(cfg):
    cfg = normalize(cfg)
    ok, _ = mesa_status(cfg)
    return cfg["api"] if (cfg["api"] == "opengl" or ok) else "opengl"


def jvm_flags(cfg, java_major, vid):
    cfg = normalize(cfg)
    flags = []
    if cfg["fast_start"] and java_major and java_major >= 19:
        d = os.path.join(config.CACHE_DIR, "cds")
        os.makedirs(d, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in vid)
        flags += ["-XX:+AutoCreateSharedArchive",
                  "-XX:SharedArchiveFile=" + os.path.join(d, f"{safe}-j{java_major}.jsa")]
    if cfg["skip_verify"]:
        flags.append("-XX:-BytecodeVerificationRemote")
    if flags:  # старые/будущие JVM не должны падать из-за незнакомого флага
        flags.insert(0, "-XX:+IgnoreUnrecognizedVMOptions")
    if effective_api(cfg) != "opengl":
        flags.append("-Dorg.lwjgl.opengl.libname=" + os.path.join(cfg["mesa_dir"], "opengl32.dll"))
    return flags


def env_additions(cfg):
    cfg = normalize(cfg)
    api = effective_api(cfg)
    if api == "opengl":
        return {}
    env = {"PATH": cfg["mesa_dir"] + os.pathsep + os.environ.get("PATH", "")}
    if api == "zink":
        env.update({"GALLIUM_DRIVER": "zink", "MESA_LOADER_DRIVER_OVERRIDE": "zink"})
    else:
        env.update({"GALLIUM_DRIVER": "llvmpipe", "LIBGL_ALWAYS_SOFTWARE": "true"})
    return env


def describe(cfg):
    cfg = normalize(cfg)
    lines = [f"API: {APIS[cfg['api']]}" + ("" if effective_api(cfg) == cfg["api"] else " → пока OpenGL (нет Mesa)")]
    if config.IS_WIN:
        lines.append(f"Видеокарта: {GPUS[cfg['gpu']]}")
    lines.append("Кэш классов Java: " + ("вкл (Java 19+)" if cfg["fast_start"] else "выкл"))
    return "  •  ".join(lines)


# ---------------------------------------------------------------- видеокарта Windows
def _gpu_value(pref):
    return {"low": "GpuPreference=1;", "high": "GpuPreference=2;"}.get(pref)


def apply_gpu_pref(java_path, pref):
    """Windows 10+: пишет предпочтение GPU для java.exe/javaw.exe (как в Параметры → Графика)."""
    if not config.IS_WIN or not java_path:
        return False
    try:
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\DirectX\UserGpuPreferences")
        base = os.path.dirname(os.path.normpath(java_path))
        for exe in ("java.exe", "javaw.exe"):
            path = os.path.join(base, exe)
            if _gpu_value(pref):
                winreg.SetValueEx(key, path, 0, winreg.REG_SZ, _gpu_value(pref))
            else:
                try:
                    winreg.DeleteValue(key, path)
                except FileNotFoundError:
                    pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def prepare_launch(cfg, java_path, log):
    """Проверяет настройки перед запуском, применяет выбор GPU. Возвращает рабочий конфиг."""
    cfg = normalize(cfg)
    ok, msg = mesa_status(cfg)
    if cfg["api"] != "opengl":
        log(("Графика: " + APIS[cfg["api"]] + " — " + msg) if ok else ("! " + msg + " Запускаю через OpenGL."))
    if config.IS_WIN:
        if apply_gpu_pref(java_path, cfg["gpu"]) and cfg["gpu"] != "auto":
            log(f"Видеокарта Windows для Java: {GPUS[cfg['gpu']]}.")
    return cfg


def list_gpus():
    if not config.IS_WIN:
        return []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }"],
                           capture_output=True, text=True, timeout=12, creationflags=_NOWIN)
        return [x.strip() for x in r.stdout.splitlines() if x.strip()]
    except Exception:
        return []


# ---------------------------------------------------------------- прогрев диска
def warm_cache(paths, limit_mb=600):
    """Читает файлы игры в фоне, чтобы они попали в кэш ОС до старта Java."""
    def work():
        total = 0
        for p in paths:
            try:
                size = os.path.getsize(p)
                if size > 250 * 1048576 or total > limit_mb * 1048576:
                    continue
                with open(p, "rb") as f:
                    while f.read(1 << 20):
                        pass
                total += size
            except OSError:
                pass
    threading.Thread(target=work, daemon=True).start()


# ---------------------------------------------------------------- ярлыки
def ensure_icon():
    from . import icon_data
    os.makedirs(config.DATA_DIR, exist_ok=True)
    path = os.path.join(config.DATA_DIR, "kinetics.ico")
    if not os.path.isfile(path):
        with open(path, "wb") as f:
            f.write(base64.b64decode(icon_data.ICON_ICO))
    return path


def _q(s):
    return "'" + str(s).replace("'", "''") + "'"


def create_shortcut(where="desktop"):
    """Создаёт .lnk с явно указанной иконкой (не зависит от кэша значков Windows)."""
    if not config.IS_WIN:
        return False, "Ярлыки создаются только на Windows."
    ico = ensure_icon()
    if getattr(sys, "frozen", False):
        target, args, wd = sys.executable, "", os.path.dirname(sys.executable)
    else:
        exe = sys.executable
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        target = pyw if os.path.isfile(pyw) else exe
        args, wd = '"' + os.path.join(config.BASE_DIR, "main.py") + '"', config.BASE_DIR
    folder = "[Environment]::GetFolderPath('Desktop')" if where == "desktop" else "$w.SpecialFolders('Programs')"
    ps = ("$w=New-Object -ComObject WScript.Shell;"
          f"$d={folder};"
          "$s=$w.CreateShortcut((Join-Path $d 'Kinetics.lnk'));"
          f"$s.TargetPath={_q(target)};$s.Arguments={_q(args)};$s.WorkingDirectory={_q(wd)};"
          f"$s.IconLocation={_q(ico + ',0')};$s.Description='Kinetics - Minecraft Launcher';$s.Save();"
          "Write-Output $s.FullName")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           capture_output=True, text=True, timeout=30, creationflags=_NOWIN)
        if r.returncode != 0:
            return False, (r.stderr or "PowerShell вернул ошибку").strip()[:200]
        try:
            subprocess.run(["ie4uinit.exe", "-show"], timeout=10, creationflags=_NOWIN)  # обновить кэш значков
        except Exception:
            pass
        return True, "Ярлык создан: " + r.stdout.strip()
    except Exception as e:  # noqa
        return False, str(e)
