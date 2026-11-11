"""Подготовка файлов и запуск игры."""
import json
import os
import re
import shlex
import subprocess
import time

from . import config, fabric, java_utils, modrinth, mojang, net, optimizer, perf


def split_args(s):
    if not s or not s.strip():
        return []
    try:
        parts = shlex.split(s, posix=False)
    except ValueError:
        parts = s.split()
    return [p[1:-1] if len(p) > 1 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]


def safe_name(name):
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "profile"


def game_dir_for(profile):
    d = profile.get("game_dir") or os.path.join(config.INSTANCES_DIR, safe_name(profile["name"]))
    os.makedirs(d, exist_ok=True)
    return d


def resolve_java(profile, required, cb):
    path = (profile.get("java_path") or "").strip().strip('"')
    if path:
        if os.path.isfile(path):
            m = java_utils.java_major(path)
            if m and m >= required:
                return path, m
            cb.log(f"! Выбранная Java ({m}) старее требуемой ({required}) — подбираю другую.")
        else:
            cb.log("! Указанный файл Java не найден — подбираю автоматически.")
    path, m = java_utils.find_java_for(required)
    if path:
        cb.log(f"Java {m}: {path}")
        return path, m
    cb.log(f"Подходящая Java {required} не найдена — скачиваю автоматически.")
    path = java_utils.download_java(
        required, lambda d, t: cb.progress(d, t, f"Java {required}"), cb.log)
    return path, java_utils.java_major(path) or required


def prepare(profile, settings, cb, force_mods=False):
    mc = (profile.get("version") or "").strip()
    if not mc:
        raise RuntimeError("Не выбрана версия Minecraft (вкладка «Профиль»).")
    threads = int(settings.get("threads", 8))
    strict = bool(settings.get("verify_files", False))

    vid = mc
    if profile.get("loader") == "fabric":
        cb.log(f"Подготовка Fabric для {mc}...")
        vid = fabric.install(mc, profile.get("loader_version") or None)
    cb.log(f"Чтение описания версии {vid}...")
    vdata = mojang.resolve_version(vid)

    required = (vdata.get("javaVersion") or {}).get("majorVersion", 8)
    java, jmajor = resolve_java(profile, required, cb)

    t0 = time.time()
    game_dir = game_dir_for(profile)
    cp, natives, tasks = mojang.collect_libraries(vdata)
    extra, log_cfg = mojang.client_and_logging_tasks(vdata)
    jar = mojang.client_jar_path(vdata)
    marker = os.path.join(config.VERS_DIR, vid, ".ready.json")
    ready = None
    if not strict and os.path.isfile(marker):
        try:
            with open(marker, "r", encoding="utf-8") as f:
                ready = json.load(f)
            if not (ready.get("game_dir") == game_dir and os.path.isfile(jar)
                    and all(os.path.isfile(p) for p in cp) and os.path.isdir(ready.get("assets_dir", ""))):
                ready = None
        except Exception:
            ready = None
    perf.warm_cache(cp + [jar])  # пока проверяем файлы — греем диск
    natives_dir = os.path.join(config.NATIVES_DIR, vid)
    if ready:
        cb.log("Файлы версии уже проверены — быстрый запуск.")
        assets_dir = ready["assets_dir"]
        if not (os.path.isdir(natives_dir) and os.listdir(natives_dir)):
            natives_dir = mojang.extract_natives(natives, vid)
    else:
        cb.log("Проверка библиотек и клиента...")
        n = net.download_many(tasks + extra, threads, lambda d, t: cb.progress(d, t, "Библиотеки"), strict)
        cb.log(f"Библиотеки готовы (скачано файлов: {n}).")
        cb.log("Проверка ресурсов (звуки, языки)...")
        assets_dir = mojang.prepare_assets(
            vdata, game_dir, threads, lambda d, t: cb.progress(d, t, "Ресурсы"), strict)
        natives_dir = mojang.extract_natives(natives, vid)
        if os.path.isfile(jar):
            try:
                with open(marker, "w", encoding="utf-8") as f:
                    json.dump({"game_dir": game_dir, "assets_dir": assets_dir, "time": time.time()}, f)
            except OSError:
                pass
    if not os.path.isfile(jar):
        raise RuntimeError(f"Нет файла клиента: {jar}")

    if profile.get("loader") == "fabric" and profile.get("opt_mods"):
        cb.log("Синхронизация модов оптимизации (Modrinth)...")
        try:
            modrinth.sync(game_dir, mc, profile["opt_mods"], cb.log, force_mods)
        except Exception as e:  # noqa
            cb.log(f"! Моды не обновлены: {e}")

    if profile.get("apply_game_options"):
        optimizer.apply_game_options(game_dir, profile["game_options"])
        cb.log("Настройки графики применены к options.txt.")

    cb.progress(1, 1, "Готово")
    cb.log(f"Подготовка заняла {time.time() - t0:.1f} с.")
    return {"vdata": vdata, "vid": vid, "java": java, "java_major": jmajor, "game_dir": game_dir,
            "classpath": cp + [jar], "natives": natives_dir, "assets_dir": assets_dir,
            "log_cfg": log_cfg, "jar": jar}


def build_command(ctx, profile, settings):
    vdata = ctx["vdata"]
    name = profile["username"].strip()
    uid = mojang.offline_uuid(name).replace("-", "")
    w, h = int(profile.get("width") or 0), int(profile.get("height") or 0)
    cp = config.CP_SEP.join(ctx["classpath"])
    variables = {
        "auth_player_name": name, "version_name": ctx["vid"], "game_directory": ctx["game_dir"],
        "assets_root": config.ASSETS_DIR, "game_assets": ctx["assets_dir"],
        "assets_index_name": (vdata.get("assetIndex") or {}).get("id") or vdata.get("assets", "legacy"),
        "auth_uuid": uid, "auth_access_token": "0", "auth_session": f"token:0:{uid}",
        "user_type": "legacy", "user_properties": "{}", "clientid": "", "auth_xuid": "",
        "version_type": "Kinetics", "natives_directory": ctx["natives"],
        "launcher_name": config.APP_NAME, "launcher_version": config.APP_VERSION,
        "classpath": cp, "classpath_separator": config.CP_SEP, "library_directory": config.LIB_DIR,
        "resolution_width": w, "resolution_height": h, "primary_jar": ctx["jar"],
    }
    features = {"has_custom_resolution": bool(w and h and not profile.get("fullscreen")),
                "is_demo_user": False, "has_quick_plays_support": False}

    def subst(s):
        return re.sub(r"\$\{([^}]+)\}", lambda m: str(variables.get(m.group(1), m.group(0))), s)

    def expand(items):
        out = []
        for it in items:
            if isinstance(it, str):
                out.append(subst(it))
            elif mojang.rules_allow(it.get("rules"), features):
                v = it["value"]
                out += [subst(x) for x in ([v] if isinstance(v, str) else v)]
        return out

    # --- JVM ---
    jvm = ["-Xms%dM" % int(profile["ram_min"]), "-Xmx%dM" % int(profile["ram_max"])]
    jvm += optimizer.jvm_flags(profile.get("jvm_preset", "balanced"), ctx["java_major"])
    for t in profile.get("jvm_toggles", []):
        if t in optimizer.JVM_TOGGLES:
            jvm.append(optimizer.JVM_TOGGLES[t][0])
    jvm += perf.jvm_flags(settings.get("perf"), ctx["java_major"], ctx["vid"])
    jvm += split_args(profile.get("jvm_extra", ""))
    args = vdata.get("arguments") or {}
    if args.get("jvm"):
        jvm += expand(args["jvm"])
    else:
        jvm += ["-Djava.library.path=" + ctx["natives"], "-cp", cp]
    lg = (vdata.get("logging") or {}).get("client")
    if lg and ctx.get("log_cfg"):
        jvm.append(lg["argument"].replace("${path}", ctx["log_cfg"]))

    # --- игра ---
    if "minecraftArguments" in vdata:
        game = [subst(a) for a in vdata["minecraftArguments"].split()]
    else:
        game = expand(args.get("game", []))
    flags_ok = "arguments" in vdata or "--username" in vdata.get("minecraftArguments", "")
    if flags_ok and w and h and not profile.get("fullscreen") and "--width" not in game:
        game += ["--width", str(w), "--height", str(h)]
    if flags_ok and profile.get("fullscreen"):
        game.append("--fullscreen")
    srv = (profile.get("server") or "").strip()
    if srv and flags_ok:
        host, _, port = srv.partition(":")
        game += ["--server", host, "--port", port or "25565"]
    game += split_args(profile.get("game_args", ""))

    return [ctx["java"]] + jvm + [vdata["mainClass"]] + game


def build_env(profile, settings=None):
    env = dict(os.environ)
    env.update(perf.env_additions((settings or {}).get("perf")))
    for part in re.split(r"[;\n]", profile.get("env", "") or ""):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip():
                env[k.strip()] = v.strip()
    return env


PRIORITY = {"normal": 0, "above": 0x00008000, "high": 0x00000080}


def start(cmd, cwd, capture=True, env=None, priority="normal"):
    kw = {"cwd": cwd, "env": env}
    if config.IS_WIN:
        kw["creationflags"] = 0x08000000 | PRIORITY.get(priority, 0)  # CREATE_NO_WINDOW | приоритет
    if capture:
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", bufsize=1, **kw)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, **kw)
