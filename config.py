import os
import platform
import sys

APP_NAME = "Kinetics"
APP_VERSION = "2.2.0"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
MC_DIR = os.path.join(DATA_DIR, "minecraft")
LIB_DIR = os.path.join(MC_DIR, "libraries")
ASSETS_DIR = os.path.join(MC_DIR, "assets")
VERS_DIR = os.path.join(MC_DIR, "versions")
NATIVES_DIR = os.path.join(MC_DIR, "natives")
INSTANCES_DIR = os.path.join(DATA_DIR, "instances")
RUNTIME_DIR = os.path.join(DATA_DIR, "runtime")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
CONFIG_FILE = os.path.join(DATA_DIR, "launcher.json")
CRASH_LOG = os.path.join(DATA_DIR, "crash.log")

OS_NAME = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}.get(platform.system(), "linux")
IS_WIN = OS_NAME == "windows"
CP_SEP = ";" if IS_WIN else ":"


def _arch():
    m = platform.machine().lower()
    if m in ("amd64", "x86_64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return "x86"


ARCH = _arch()


def ensure_dirs():
    for d in (DATA_DIR, MC_DIR, LIB_DIR, ASSETS_DIR, VERS_DIR, NATIVES_DIR,
              INSTANCES_DIR, RUNTIME_DIR, CACHE_DIR):
        os.makedirs(d, exist_ok=True)


APP_ID = "Kinetics.Launcher.2"


def set_app_id():
    """Говорит Windows, что это отдельное приложение (своя иконка и группа на панели задач, а не Python)."""
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
