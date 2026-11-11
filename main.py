import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kinetics import config  # noqa: E402


def diag():
    import platform
    from kinetics import java_utils, system
    print(f"Kinetics {config.APP_VERSION}")
    print("Python :", sys.version.split()[0], platform.platform())
    print("RAM    :", system.total_ram_mb(), "МБ")
    print("Ядра   :", system.cpu_cores())
    javas = java_utils.find_javas()
    print("Java   :", "не найдена" if not javas else "")
    for m, p in javas:
        print(f"   Java {m}: {p}")
    print("Данные :", config.DATA_DIR)


def main():
    args = sys.argv[1:]
    config.set_app_id()
    config.ensure_dirs()
    if "--diag" in args:
        return diag()
    if "--install-java" in args:
        from kinetics import java_utils
        major = int(args[args.index("--install-java") + 1])
        print("Результат:", java_utils.download_java(major, log=print))
        return
    try:
        from kinetics.gui import run
        run()
    except Exception:
        with open(config.CRASH_LOG, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
