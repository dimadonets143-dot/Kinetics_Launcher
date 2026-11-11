import copy
import json
import os
import queue
import random
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
import tkinter.font as tkfont
import time

from . import (assistant, config, fabric, icon_data, java_utils, launcher, modrinth, mojang, optimizer, perf, quick, store, system)
from . import ui_kit as ui
from .ui_kit import THEME

TYPE_RU = {"release": "Релиз", "snapshot": "Снапшот", "old_beta": "Бета", "old_alpha": "Альфа",
           "installed": "Локальная"}
FILTERS = [("release", "Релизы"), ("snapshot", "Снапшоты"), ("old_beta", "Беты"),
           ("old_alpha", "Альфы"), ("installed", "Установленные")]
GRAPHICS = ["Быстрая", "Красивая", "Fabulous"]
PARTICLES = ["Все", "Уменьшенные", "Минимальные"]
AFTER = {"keep": "Оставить лаунчер открытым", "minimize": "Свернуть на время игры",
         "close": "Закрыть лаунчер после запуска"}
PRIORITIES = {"normal": "Обычный", "above": "Выше обычного", "high": "Высокий (Windows)"}
SORTS = {"Популярные": "downloads", "Релевантные": "relevance", "Новые": "newest", "Обновлённые": "updated"}
STORE_KINDS = [("opt", "⚡ Оптимизация"), ("mod", "Моды"), ("shader", "Шейдеры"),
               ("resourcepack", "Ресурспаки"), ("installed", "Установлено")]
ACCENTS = ["#7c5cff", "#38bdf8", "#34d399", "#f472b6", "#fbbf24", "#fb7185"]
FPS_PACK = ["sodium", "lithium", "ferrite-core", "modernfix", "immediatelyfast", "entityculling", "dynamic-fps"]
NICK_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")

PROFILE_FIELDS = {"username": "str", "version": "str", "loader": "str", "loader_version": "str",
                  "ram_min": "int", "ram_max": "int", "java_path": "str", "jvm_extra": "str",
                  "game_args": "str", "width": "int", "height": "int", "fullscreen": "bool",
                  "server": "str", "game_dir": "str", "apply_game_options": "bool",
                  "pre_cmd": "str", "post_cmd": "str", "env": "str"}
OPTION_FIELDS = {"render_distance": "int", "simulation_distance": "int", "max_fps": "int",
                 "vsync": "bool", "biome_blend": "int", "clouds": "bool", "mipmap": "int",
                 "ao": "bool", "gui_scale": "int", "entity_distance": "float"}
KINDS = {"str": tk.StringVar, "int": tk.IntVar, "bool": tk.BooleanVar, "float": tk.DoubleVar}


class Cb:
    def __init__(self, q):
        self.q = q

    def log(self, msg):
        self.q.put(("log", str(msg)))

    def progress(self, done, total, label=""):
        self.q.put(("progress", done, total, label))


def fmt_num(n):
    if n is None:
        return ""
    for div, s in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            return f"{n / div:.1f}{s}"
    return str(n)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        config.ensure_dirs()
        self.store = store.Store()
        st0 = self.store.settings
        ui.apply_theme(st0.get("theme", "Полночь"), st0.get("accent"))
        ui.ANIM["on"] = bool(st0.get("animations", True))
        fams = set(tkfont.families())
        ui.FONT = st0.get("font") if st0.get("font") in fams else next(
            (f for f in ("Segoe UI", "Calibri", "DejaVu Sans", "Arial") if f in fams), "TkDefaultFont")
        self.log_lines = []
        self.log_open = False
        self.title(f"Kinetics Launcher {config.APP_VERSION}")
        try:
            self._icons = [tk.PhotoImage(data=d) for d in (icon_data.ICON_32, icon_data.ICON_64, icon_data.ICON_128)]
            self.iconphoto(True, *self._icons)
        except tk.TclError:
            pass
        self.doc_history = []
        self.doc = None
        self.quick = None
        self._played = 0
        self.geometry("1180x760")
        self.minsize(1020, 680)
        self.q = queue.Queue()
        self.manifest = None
        self.proc = None
        self.busy = False
        self.current = None
        self.opt_mods = []
        self.cur_page = None
        self.pages = {}
        self.ver_filter = "release"
        self.sel_ver = None
        self.store_kind = "opt"
        self.store_token = 0
        self.store_offset = 0
        self.v = {}
        for k, kind in PROFILE_FIELDS.items():
            self.v["p." + k] = KINDS[kind]()
        for k, kind in OPTION_FIELDS.items():
            self.v["o." + k] = KINDS[kind]()
        self.name_var = tk.StringVar()
        self.jvm_var = tk.StringVar()
        self.gfx_var = tk.StringVar()
        self.part_var = tk.StringVar()
        self.after_var = tk.StringVar()
        self.prio_var = tk.StringVar()
        self.threads_var = tk.IntVar()
        self.verify_var = tk.BooleanVar()
        self.anim_var = tk.BooleanVar(value=ui.ANIM["on"])
        self.tog_vars = {k: tk.BooleanVar() for k in optimizer.JVM_TOGGLES}
        self.status_var = tk.StringVar(value="Готов к запуску")
        self.ver_search = tk.StringVar()
        self.store_q = tk.StringVar()
        self.hero_bg_var = tk.StringVar()
        self.font_var = tk.StringVar(value=ui.FONT)
        self.sort_var = tk.StringVar(value="Популярные")
        self._style()
        self._build()
        self._traces()
        self._load_profile(self.store.settings["last_profile"])
        self.show("play", animate=False)
        self.bind("<Escape>", lambda e: self.quick and self.quick.close())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)
        threading.Thread(target=self._fetch_manifest, daemon=True).start()

    # ================================================================ стиль
    def _style(self):
        T = THEME
        s = ttk.Style(self)
        s.theme_use("clam")
        self.configure(bg=T["bg"])
        s.configure(".", background=T["card"], foreground=T["fg"], fieldbackground=T["field"],
                    bordercolor=T["line"], lightcolor=T["field"], darkcolor=T["field"],
                    troughcolor=T["field"], focuscolor=T["card"], arrowcolor=T["dim"])
        for w in ("TEntry", "TCombobox", "TSpinbox"):
            s.configure(w, fieldbackground=T["field"], foreground=T["fg"], insertcolor=T["fg"], padding=6,
                        borderwidth=0, bordercolor=T["field"], lightcolor=T["field"], darkcolor=T["field"])
        s.configure("TCombobox", background=T["field"], arrowcolor=T["dim"])
        s.map("TCombobox", fieldbackground=[("readonly", T["field"])], foreground=[("readonly", T["fg"])],
              background=[("active", T["field"])])
        s.configure("Horizontal.TScale", background=T["accent"], troughcolor=T["field"],
                    bordercolor=T["card"], lightcolor=T["accent"], darkcolor=T["accent"])
        s.configure("Vertical.TScrollbar", background=T["field"], troughcolor=T["bg"], bordercolor=T["bg"],
                    arrowcolor=T["dim"], lightcolor=T["field"], darkcolor=T["field"], gripcount=0)
        s.map("Vertical.TScrollbar", background=[("active", T["accent"])])
        s.configure("Treeview", background=T["card"], fieldbackground=T["card"], foreground=T["fg"],
                    rowheight=30, borderwidth=0)
        s.map("Treeview", background=[("selected", ui.mix(T["card"], T["accent"], .8))],
              foreground=[("selected", "#ffffff")])
        s.configure("Treeview.Heading", background=T["field"], foreground=T["dim"], relief="flat",
                    padding=7, font=(ui.FONT, 9, "bold"))
        s.map("Treeview.Heading", background=[("active", T["field"])])
        self.option_add("*TCombobox*Listbox.background", T["field"])
        self.option_add("*TCombobox*Listbox.foreground", T["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", T["accent"])
        self.option_add("*TCombobox*Listbox.font", (ui.FONT, 10))

    # ================================================================ каркас
    def _build(self):
        entries = [("hdr", "ИГРА"), ("play", "Главная", "⌂"), ("versions", "Версии", "☰"), ("store", "Магазин", "◆"),
                   ("hdr", "НАСТРОЙКИ"), ("profile", "Профиль", "☻"), ("optim", "Оптимизация", "⚡"),
                   ("gfx", "Графика", "▣"), ("settings", "Внешний вид", "✦")]
        self.sidebar = ui.Sidebar(self, entries, lambda k: self.show(k))
        self.sidebar.pack(side="left", fill="y")
        self.content = tk.Frame(self, bg=THEME["bg"])
        self.content.pack(side="left", fill="both", expand=True)
        self.toast = ui.Toast(self)
        self.pages = {}
        self.cur_page = None
        for key, fn in (("play", self._page_play), ("versions", self._page_versions),
                        ("store", self._page_store), ("profile", self._page_profile),
                        ("optim", self._page_optim), ("gfx", self._page_gfx),
                        ("settings", self._page_settings)):
            fr = tk.Frame(self.content, bg=THEME["bg"])
            self.pages[key] = fr
            fn(fr)
        self.quick = quick.Quick(self)
        self.after(350, self._make_doc)

    def _make_doc(self):
        if self.doc is None:
            self.doc = assistant.Doc(self)

    def _traces(self):
        T = lambda var, fn: var.trace_add("write", lambda *a: fn())  # noqa: E731
        for k in ("p.ram_min", "p.ram_max", "p.jvm_extra"):
            T(self.v[k], self._refresh_preview)
        T(self.jvm_var, self._refresh_preview)
        for tv in self.tog_vars.values():
            T(tv, self._refresh_preview)
        for k in ("p.version", "p.loader", "p.ram_max", "p.username"):
            T(self.v[k], self._refresh_summary)
        T(self.v["p.loader"], self._sync_chips)
        T(self.v["p.username"], self._refresh_uuid)
        for k in ("p.ram_min", "p.ram_max"):
            self.v[k].trace_add("write", lambda *a, k=k: self._sync_ram(k))
        T(self.ver_search, self._fill_versions)
        self.sort_var.trace_add("write", lambda *a: getattr(self, "store_loaded", False) and self._store_search())

    def _rebuild(self):
        """Пересборка интерфейса после смены темы/шрифта."""
        key = next((k for k, v in self.pages.items() if v is self.cur_page), "play")
        try:
            self._save()
            self.hero.stop()
        except Exception:
            pass
        if self.doc:
            self.doc.destroy()
            self.doc = None
        if self.quick:
            self.quick.destroy()
        self.sidebar.destroy()
        self.content.destroy()
        ui._registry.clear()
        self._style()
        self._build()
        self._load_profile(self.current)
        self.show(key, animate=False)
        self._refresh_recent()

    def show(self, key, animate=True):
        new, old = self.pages[key], self.cur_page
        if new is old:
            return
        self.sidebar.select(key)
        if self.quick:
            self.quick.set_page(key)
            self.quick.close()
        if key == "play":
            self.hero.start()
            self._refresh_recent()
        else:
            self.hero.stop()
        if key == "store":
            self._store_refresh_ctx()
            if not self.store_loaded:
                self.store_loaded = True
                self._store_search()
        new.place(x=0, y=0, relwidth=1, relheight=1)
        new.lift()
        self.cur_page = new

        def finish():
            try:
                if old is not None and old is not self.cur_page:
                    old.place_forget()
            except tk.TclError:
                pass
        if animate and old is not None and ui.ANIM["on"]:
            new.place_configure(x=40)
            ui.tween(new, "slide", 260, lambda t: new.place_configure(x=int(40 * (1 - t))), done=finish)
            self.after(300, finish)
        else:
            if old is not None:
                old.place_forget()
            new.place_configure(x=0)

    def _head(self, page, title, sub=""):
        h = tk.Frame(page, bg=THEME["bg"])
        h.pack(fill="x", padx=30, pady=(24, 10))
        ui.label(h, title, 22, True).pack(anchor="w")
        if sub:
            ui.label(h, sub, 10, dim=True).pack(anchor="w")
        return h

    def _scroll_page(self, page, title, sub=""):
        self._head(page, title, sub)
        sf = ui.ScrollFrame(page, bg=THEME["bg"])
        sf.pack(fill="both", expand=True, padx=(30, 14), pady=(0, 14))
        return sf.inner

    def _section(self, parent, title):
        outer = ui.card(parent)
        outer.pack(fill="x", pady=(0, 14), padx=(0, 16))
        if title:
            ui.label(outer, title, 11, True, fg=THEME["accent"]).pack(anchor="w", padx=20, pady=(14, 0))
        body = ui.card(outer)
        body.pack(fill="both", expand=True, padx=20, pady=14)
        body.columnconfigure(1, weight=1)
        return body

    def _row(self, body, r, text, widget, span=1):
        ui.label(body, text, 10, dim=True).grid(row=r, column=0, sticky="w", padx=(0, 16), pady=6)
        widget.grid(row=r, column=1, columnspan=span, sticky="ew", pady=6)
        return widget

    def _btn(self, parent, text, cmd, kind="card", w=120, h=34, **kw):
        return ui.AnimButton(parent, text, cmd, kind=kind, width=w, height=h, **kw)

    def _inline(self, parent):
        return tk.Frame(parent, bg=ui.bg_of(parent))

    # ================================================================ ИГРАТЬ
    def _page_play(self, f):
        st = self.store.settings
        self.hero = ui.Hero(f, 300)
        self.hero.set_mode(st.get("hero_bg", "particles"), st.get("hero_image", ""))
        self.hero.pack(fill="x")
        H = self.hero.H
        self.play_btn = ui.AnimButton(self.hero, "▶   ИГРАТЬ", self._play, kind="accent", width=300, height=64,
                                      font=(ui.FONT, 17, "bold"), radius=16, pulse=True,
                                      bg=self.hero.color_at(H - 40))
        self.hero.create_window(42, H - 30, anchor="sw", window=self.play_btn, tags="ui")
        nf = tk.Frame(self.hero, bg=self.hero.color_at(40))
        ttk.Entry(nf, textvariable=self.v["p.username"], width=16).pack(side="left")
        self._btn(nf, "🎲", self._rand_nick, "card", 36, 30, bg=self.hero.color_at(40)).pack(side="left", padx=(6, 0))
        nick_win = self.hero.create_window(0, 30, anchor="ne", window=nf, tags="ui")
        self.hero.bind("<Configure>", lambda e: (self.hero.coords(nick_win, e.width - 76, 30),
                                                 self.hero._cfg(e)), add="+")

        body = tk.Frame(f, bg=THEME["bg"])
        body.pack(fill="both", expand=True, padx=30, pady=(14, 18))
        self.strip = tk.Frame(body, bg=THEME["bg"])
        sc = ui.card(self.strip)
        sc.pack(fill="x")
        si = tk.Frame(sc, bg=THEME["card"])
        si.pack(fill="x", padx=16, pady=10)
        ui.label(si, "", 9, dim=True, textvariable=self.status_var, width=26).pack(side="left")
        self.progress = ui.AnimProgress(si, 10)
        self.progress.pack(side="left", fill="x", expand=True, padx=12)
        self.stop_btn = self._btn(si, "Остановить игру", self._stop, "danger", 150, 32, bg=THEME["card"])
        self.stop_btn.pack(side="left")
        self.stop_btn.set_disabled(True)
        self.logbox = ui.card(body)
        self.log = tk.Text(self.logbox, bg=THEME["card"], fg=THEME["dim"], insertbackground=THEME["fg"],
                           relief="flat", height=8, wrap="word", font=("Consolas", 9), state="disabled",
                           bd=0, highlightthickness=0)
        lsb = ttk.Scrollbar(self.logbox, command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y", padx=(0, 6), pady=8)
        self.log.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        self.log.config(state="normal")
        self.log.insert("end", "\n".join(self.log_lines[-400:]) + ("\n" if self.log_lines else ""))
        self.log.config(state="disabled")

        self.list_area = tk.Frame(body, bg=THEME["bg"])
        self.list_area.pack(fill="both", expand=True)
        hd = tk.Frame(self.list_area, bg=THEME["bg"])
        hd.pack(fill="x", pady=(0, 8))
        ui.label(hd, "Твои версии", 14, True).pack(side="left")
        self._btn(hd, "Все версии  →", lambda: self.show("versions"), "ghost", 130, 30).pack(side="right")
        self._btn(hd, "Журнал", self._toggle_log, "ghost", 90, 30).pack(side="right", padx=6)
        self._btn(hd, "📁  Папка игры", self._open_game_dir, "card", 150, 30).pack(side="right", padx=6)
        self.recent_box = ui.ScrollFrame(self.list_area, bg=THEME["bg"])
        self.recent_box.pack(fill="both", expand=True)

    def _toggle_log(self):
        self.log_open = not self.log_open
        self._layout_play()

    def _layout_play(self):
        self.strip.pack_forget()
        self.logbox.pack_forget()
        if self.busy:
            self.strip.pack(fill="x", pady=(0, 10), before=self.list_area)
        if self.log_open:
            self.logbox.pack(fill="x", pady=(0, 10), before=self.list_area)

    @staticmethod
    def _parse_vid(vid):
        m = re.match(r"^fabric-loader-(.+?)-(\d.*)$", vid)
        return (m.group(2), "fabric", m.group(1)) if m else (vid, "vanilla", "")

    @staticmethod
    def _ago(ts):
        if not ts:
            return ""
        d = max(0, time.time() - ts)
        if d < 90:
            return "только что"
        if d < 3600:
            return f"{int(d // 60)} мин назад"
        if d < 86400:
            return f"{int(d // 3600)} ч назад"
        if d < 172800:
            return "вчера"
        return f"{int(d // 86400)} дн. назад"

    def _recent_entries(self):
        out, seen = [], set()
        for r in self.store.settings.get("recent", []):
            key = (r["version"], r["loader"])
            if key not in seen:
                seen.add(key)
                out.append(dict(r))
        for vid in mojang.installed_versions():
            mc, loader, lv = self._parse_vid(vid)
            if (mc, loader) not in seen:
                seen.add((mc, loader))
                out.append({"version": mc, "loader": loader, "loader_version": lv, "ts": 0})
        return out[:30]

    def _refresh_recent(self):
        try:
            inner = self.recent_box.inner
            for w in inner.winfo_children():
                w.destroy()
        except (tk.TclError, AttributeError):
            return
        entries = self._recent_entries()
        types = {}
        if self.manifest:
            types = {v["id"]: v["type"] for v in self.manifest["versions"]}
        cur = (self.v["p.version"].get(), self.v["p.loader"].get())
        if not entries:
            c = ui.card(inner)
            c.pack(fill="x", pady=4, padx=(0, 14))
            ui.label(c, "Пока нет скачанных версий", 12, True).pack(anchor="w", padx=20, pady=(16, 0))
            ui.label(c, "Выбери версию Minecraft — она скачается при первом запуске.", 9, dim=True).pack(anchor="w", padx=20)
            self._btn(c, "Выбрать версию", lambda: self.show("versions"), "accent", 180, 36).pack(anchor="w", padx=20, pady=14)
            return
        for i, e in enumerate(entries):
            c = ui.card(inner)
            c.pack(fill="x", pady=4, padx=(0, 14))
            is_cur = (e["version"], e["loader"]) == cur
            av = tk.Canvas(c, width=54, height=54, bg=THEME["card"], highlightthickness=0)
            ui.round_rect(av, 2, 2, 52, 52, 14, fill=THEME["accent"] if is_cur else THEME["field"], outline="")
            av.create_text(27, 27, text=".".join(e["version"].split(".")[:2])[:5], fill="#ffffff" if is_cur else THEME["fg"],
                           font=(ui.FONT, 11, "bold"))
            av.pack(side="left", padx=16, pady=12)
            mid = tk.Frame(c, bg=THEME["card"])
            mid.pack(side="left", fill="x", expand=True)
            title = e["version"] + ("   • последняя" if i == 0 and e.get("ts") else "")
            ui.label(mid, title, 12, True).pack(anchor="w")
            bits = ["Fabric" if e["loader"] == "fabric" else "Vanilla"]
            t = types.get(e["version"])
            if t:
                bits.append({"release": "релиз", "snapshot": "снапшот", "old_beta": "бета", "old_alpha": "альфа"}.get(t, t))
            if e.get("ts"):
                bits.append("запуск " + self._ago(e["ts"]))
                if e.get("played", 0) >= 60:
                    bits.append("наиграно " + self._fmt_play(e["played"]))
            else:
                bits.append("скачана")
            ui.label(mid, "  ·  ".join(bits), 9, dim=True).pack(anchor="w")
            label = "Продолжить" if (i == 0 and e.get("ts")) else "Играть"
            self._btn(c, "Удалить", lambda e=e: self._delete_entry(e), "danger", 88, 38).pack(side="right", padx=(0, 16))
            self._btn(c, "▶  " + label, lambda e=e: self._launch_entry(e), "accent" if i == 0 and e.get("ts") else "card",
                      150, 38).pack(side="right", padx=(18, 8))

    def _delete_entry(self, e):
        if self.busy:
            return
        label = e["version"] + (" (Fabric)" if e["loader"] == "fabric" else "")
        if not messagebox.askyesno("Kinetics", f"Удалить версию {label}?\n\nФайлы этой версии будут удалены с диска.\n"
                                   "Миры, моды и настройки НЕ затрагиваются."):
            return
        for vid in mojang.installed_versions():
            if self._parse_vid(vid)[:2] == (e["version"], e["loader"]):
                shutil.rmtree(os.path.join(config.VERS_DIR, vid), ignore_errors=True)
                shutil.rmtree(os.path.join(config.NATIVES_DIR, vid), ignore_errors=True)
        st = self.store.settings
        st["recent"] = [r for r in st.get("recent", []) if (r["version"], r["loader"]) != (e["version"], e["loader"])]
        self.store.save()
        if (self.v["p.version"].get(), self.v["p.loader"].get()) == (e["version"], e["loader"]):
            self.v["p.version"].set("")
        self._refresh_recent()
        self._refresh_summary()
        self.toast.show(f"Версия {label} удалена")

    def _add_playtime(self, version, loader, secs):
        for r in self.store.settings.get("recent", []):
            if (r["version"], r["loader"]) == (version, loader):
                r["played"] = r.get("played", 0) + max(0, secs)
        self.store.save()
        self._refresh_recent()

    @staticmethod
    def _fmt_play(secs):
        m = int(secs // 60)
        return f"{m // 60} ч {m % 60} мин" if m >= 60 else f"{m} мин"

    def _open_sub(self, sub):
        self._open(os.path.join(launcher.game_dir_for(self._collect()), sub))

    def _launch_entry(self, e):
        if self.busy:
            return
        self.v["p.version"].set(e["version"])
        self.v["p.loader"].set(e["loader"])
        self.v["p.loader_version"].set(e.get("loader_version") or "auto")
        self._play()

    def _record_launch(self, version, loader, lv):
        old = next((r for r in self.store.settings.get("recent", []) if (r["version"], r["loader"]) == (version, loader)), {})
        rec = [r for r in self.store.settings.get("recent", []) if (r["version"], r["loader"]) != (version, loader)]
        rec.insert(0, {"version": version, "loader": loader, "loader_version": lv, "ts": time.time(),
                       "played": old.get("played", 0)})
        self.store.settings["recent"] = rec[:12]
        self.store.save()
        self._refresh_summary()
        self._refresh_recent()

    # ================================================================ ВЕРСИИ
    def _page_versions(self, f):
        self._head(f, "Версии Minecraft", "Релизы, снапшоты, старые беты и альфы, Fabric и локальные сборки")
        body = tk.Frame(f, bg=THEME["bg"])
        body.pack(fill="both", expand=True, padx=30, pady=(0, 24))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        top = tk.Frame(body, bg=THEME["bg"])
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.filter_btns = {}
        for key, text in FILTERS:
            b = self._btn(top, text, lambda k=key: self._set_filter(k), "chip", 146 if key == "installed" else 96, 34)
            b.pack(side="left", padx=(0, 6))
            self.filter_btns[key] = b
        self.filter_btns[self.ver_filter].set_selected(True)
        sr = tk.Frame(body, bg=THEME["bg"])
        sr.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ui.label(sr, "Поиск версии  ", 10, dim=True).pack(side="left")
        ttk.Entry(sr, textvariable=self.ver_search, width=30).pack(side="left")

        tf = ui.card(body)
        tf.grid(row=2, column=0, sticky="nsew")
        cols = ("id", "type", "date", "state")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("id", "Версия", 190), ("type", "Тип", 100), ("date", "Дата", 110), ("state", "Статус", 110)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=8)
        self.tree.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._ver_selected())
        self.tree.bind("<Double-1>", lambda e: self._pick_version())

        side = ui.card(body, width=320)
        side.grid(row=0, column=1, rowspan=3, sticky="ns", padx=(14, 0))
        side.grid_propagate(False)
        inner = ui.card(side)
        inner.pack(fill="both", expand=True, padx=20, pady=18)
        self.ver_title = ui.label(inner, "Выбери версию", 18, True)
        self.ver_title.pack(anchor="w")
        self.ver_info = ui.label(inner, "Двойной клик по версии — выбрать для профиля.", 9, dim=True, wraplength=270)
        self.ver_info.pack(anchor="w", pady=(2, 16))
        ui.label(inner, "ЗАГРУЗЧИК", 8, True, dim=True).pack(anchor="w")
        lr = tk.Frame(inner, bg=THEME["card"])
        lr.pack(fill="x", pady=(6, 8))
        self.chip_van = self._btn(lr, "Vanilla", lambda: self.v["p.loader"].set("vanilla"), "chip", 130, 34)
        self.chip_van.pack(side="left", padx=(0, 6))
        self.chip_fab = self._btn(lr, "Fabric", lambda: self.v["p.loader"].set("fabric"), "chip", 130, 34)
        self.chip_fab.pack(side="left")
        ui.label(inner, "Версия Fabric Loader", 9, dim=True).pack(anchor="w", pady=(6, 2))
        lv = tk.Frame(inner, bg=THEME["card"])
        lv.pack(fill="x")
        self.lv_box = ttk.Combobox(lv, textvariable=self.v["p.loader_version"], values=["auto"], width=16)
        self.lv_box.pack(side="left", fill="x", expand=True)
        self._btn(lv, "↻", self._fetch_loaders, "card", 40, 32).pack(side="left", padx=(6, 0))
        tk.Frame(inner, bg=THEME["card"], height=16).pack()
        self._btn(inner, "Выбрать для профиля", self._pick_version, "accent", 270, 42).pack(pady=4)
        self._btn(inner, "Скачать / проверить файлы", self._download_selected, "card", 270, 38).pack(pady=4)
        self._btn(inner, "Удалить файлы версии", self._delete_selected, "danger", 270, 38).pack(pady=4)
        self._btn(inner, "📁  Открыть папку игры", self._open_game_dir, "card", 270, 38).pack(pady=4)
        ui.label(inner, "Альфы и беты — запуск «как есть»: окно, сервер и полный экран\nдля них не применяются, нужна Java 8.",
                 8, dim=True, wraplength=270).pack(anchor="w", pady=(14, 0))

    def _set_filter(self, key):
        self.ver_filter = key
        for k, b in self.filter_btns.items():
            b.set_selected(k == key)
        self._fill_versions()

    def _fill_versions(self):
        installed = set(mojang.installed_versions())
        q = self.ver_search.get().strip().lower()
        rows = []
        if self.ver_filter == "installed":
            rows = [(v, TYPE_RU["installed"], "", "✓ установлена") for v in sorted(installed)]
        elif self.manifest:
            for v in self.manifest["versions"]:
                if v["type"] == self.ver_filter:
                    rows.append((v["id"], TYPE_RU.get(v["type"], v["type"]), v["releaseTime"][:10],
                                 "✓ установлена" if v["id"] in installed else ""))
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            if q and q not in r[0].lower():
                continue
            self.tree.insert("", "end", iid=r[0], values=r)
        cur = self.v["p.version"].get()
        if cur and self.tree.exists(cur):
            self.tree.selection_set(cur)
            self.tree.see(cur)

    def _ver_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        self.sel_ver = sel[0]
        vals = self.tree.item(sel[0], "values")
        self.ver_title.config(text=self.sel_ver)
        self.ver_info.config(text=f"{vals[1]}  •  {vals[2] or 'без даты'}  •  {vals[3] or 'не скачана'}")

    def _pick_version(self):
        if not self.sel_ver:
            self.toast.show("Сначала выбери версию в списке", "err")
            return
        self.v["p.version"].set(self.sel_ver)
        self._save()
        self.toast.show(f"Выбрана версия {self.sel_ver} ({self.v['p.loader'].get()})")

    def _sync_chips(self):
        fab = self.v["p.loader"].get() == "fabric"
        self.chip_van.set_selected(not fab)
        self.chip_fab.set_selected(fab)

    def _download_selected(self):
        if not self.sel_ver or self.busy:
            return
        p = self._collect()
        p["version"] = self.sel_ver
        self.show("play")
        self._run(p, install_only=True, strict=True)

    def _delete_selected(self):
        vid = self.sel_ver
        if not vid:
            return
        if not messagebox.askyesno("Kinetics", f"Удалить файлы версии {vid}?\n(Миры и настройки останутся.)"):
            return
        shutil.rmtree(os.path.join(config.VERS_DIR, vid), ignore_errors=True)
        shutil.rmtree(os.path.join(config.NATIVES_DIR, vid), ignore_errors=True)
        self._fill_versions()
        self.toast.show(f"Версия {vid} удалена")

    def _fetch_loaders(self):
        mc = self.v["p.version"].get().strip() or self.sel_ver
        if not mc:
            self.toast.show("Выбери версию Minecraft", "err")
            return

        def work():
            try:
                self.q.put(("loaders", fabric.loader_versions(mc)))
            except Exception as e:  # noqa
                self.q.put(("toast", f"Fabric недоступен для {mc}", "err"))
        threading.Thread(target=work, daemon=True).start()

    # ================================================================ МАГАЗИН
    def _page_store(self, f):
        self.store_loaded = False
        self._head(f, "Магазин", "Моды, шейдеры и ресурспаки с Modrinth — ставятся в папку выбранного профиля")
        top = tk.Frame(f, bg=THEME["bg"])
        top.pack(fill="x", padx=30)
        self.store_chips = {}
        for key, text in STORE_KINDS:
            b = self._btn(top, text, lambda k=key: self._store_set_kind(k), "chip", 132 if key == "opt" else 110, 34)
            b.pack(side="left", padx=(0, 6))
            self.store_chips[key] = b
        self.store_chips[self.store_kind].set_selected(True)
        sr = tk.Frame(f, bg=THEME["bg"])
        sr.pack(fill="x", padx=30, pady=(12, 4))
        self.store_entry = ttk.Entry(sr, textvariable=self.store_q, width=36)
        self.store_entry.pack(side="left")
        self.store_entry.bind("<Return>", lambda e: self._store_search())
        self._btn(sr, "Найти", self._store_search, "accent", 90, 32).pack(side="left", padx=8)
        ttk.Combobox(sr, state="readonly", textvariable=self.sort_var, values=list(SORTS), width=14).pack(side="left")
        self.ctx_lbl = ui.label(top, "", 10, dim=True)
        self.ctx_lbl.pack(side="right")
        self._btn(sr, "+ Свой файл", self._store_add_file, "card", 125, 32).pack(side="right", padx=(8, 0))
        self._btn(sr, "📁  Папка", self._store_open_folder, "card", 105, 32).pack(side="right")
        self.shader_banner = ui.card(f)
        ui.label(self.shader_banner, "Для шейдеров нужны Iris и Sodium (загрузчик Fabric).", 10).pack(
            side="left", padx=16, pady=10)
        self._btn(self.shader_banner, "Установить Iris + Sodium", self._install_iris, "accent", 200, 32).pack(
            side="right", padx=12)
        self.opt_banner = ui.card(f)
        ui.label(self.opt_banner, "Проверенный набор для FPS: Sodium, Lithium, FerriteCore, ModernFix и др.", 10).pack(
            side="left", padx=16, pady=10)
        self._btn(self.opt_banner, "Установить набор FPS", self._install_pack, "accent", 190, 32).pack(side="right", padx=12)
        self.store_scroll = ui.ScrollFrame(f, bg=THEME["bg"])
        self.store_scroll.pack(fill="both", expand=True, padx=(30, 14), pady=(8, 16))
        self.opt_banner.pack(fill="x", padx=30, pady=(8, 0), before=self.store_scroll)

    def _tool_kind(self):
        return {"opt": "mod", "installed": "mod"}.get(self.store_kind, self.store_kind)

    def _store_open_folder(self):
        self._open(os.path.join(launcher.game_dir_for(self._collect()), modrinth.KIND_DIRS[self._tool_kind()]))

    def _store_add_file(self, kind=None):
        kind = kind or self._tool_kind()
        ft = [("Моды (.jar)", "*.jar")] if kind == "mod" else [("Архивы (.zip)", "*.zip")]
        paths = filedialog.askopenfilenames(title="Выбери свои файлы", filetypes=ft + [("Все файлы", "*.*")])
        if not paths:
            return
        n = modrinth.add_files(launcher.game_dir_for(self._collect()), kind, paths)
        self.toast.show(f"Добавлено файлов: {n}")
        if self.store_kind == "installed":
            self._store_render_installed()

    def _store_refresh_ctx(self):
        p = self._collect_safe()
        self.ctx_lbl.config(text=f"{p['version'] or 'версия?'} · {p['loader']}")

    def _store_set_kind(self, kind):
        self.store_kind = kind
        for k, b in self.store_chips.items():
            b.set_selected(k == kind)
        self.shader_banner.pack_forget()
        self.opt_banner.pack_forget()
        if kind == "shader":
            self.shader_banner.pack(fill="x", padx=30, pady=(8, 0), before=self.store_scroll)
        elif kind == "opt":
            self.opt_banner.pack(fill="x", padx=30, pady=(8, 0), before=self.store_scroll)
        self._store_refresh_ctx()
        self._store_search()

    def _store_clear(self):
        for w in self.store_scroll.inner.winfo_children():
            w.destroy()
        self.store_scroll.to_top()

    def _store_note(self, text):
        ui.label(self.store_scroll.inner, text, 11, dim=True).pack(anchor="w", pady=20, padx=4)

    def _store_search(self, append=False):
        kind = self.store_kind
        if kind == "opt":
            return self._store_render_opt()
        if kind == "installed":
            return self._store_render_installed()
        self.store_token += 1
        tok = self.store_token
        if not append:
            self.store_offset = 0
            self._store_clear()
            self._store_note("Загрузка…")
        p = self._collect_safe()
        q, index, off = self.store_q.get().strip(), SORTS.get(self.sort_var.get(), "downloads"), self.store_offset

        def work():
            try:
                hits, total = modrinth.search(q, kind, p["version"], p["loader"], index, off)
                self.q.put(("store_results", tok, hits, total, append))
            except Exception as e:  # noqa
                self.q.put(("store_error", tok, str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _store_results(self, hits, total, append):
        inner = self.store_scroll.inner
        if not append:
            self._store_clear()
        else:
            for w in inner.winfo_children():
                if getattr(w, "_more", False):
                    w.destroy()
        if not hits and not append:
            self._store_note("Ничего не найдено. Проверь версию в профиле или измени запрос.")
            return
        p = self._collect_safe()
        mf = modrinth.load_installed(launcher.game_dir_for(p))
        for h in hits:
            self._store_card(h, self.store_kind, mf)
        self.store_offset += len(hits)
        if self.store_offset < total:
            b = self._btn(inner, f"Показать ещё ({total - self.store_offset})", lambda: self._store_search(True), "card", 220, 36)
            b._more = True
            b.pack(pady=12)

    def _store_render_opt(self):
        self._store_clear()
        p = self._collect_safe()
        mf = modrinth.load_installed(launcher.game_dir_for(p))
        for slug, (name, desc) in modrinth.OPT_MODS.items():
            self._store_card({"slug": slug, "title": name, "description": desc, "author": "Modrinth",
                              "downloads": None}, "mod", mf)

    def _store_card(self, h, kind, mf):
        c = ui.card(self.store_scroll.inner)
        c.pack(fill="x", pady=5, padx=(0, 16))
        title = h.get("title", "?")
        col = ui.mix(THEME["field"], "#" + "%06x" % (hash(title) & 0xFFFFFF), .55)
        av = tk.Canvas(c, width=52, height=52, bg=THEME["card"], highlightthickness=0)
        ui.round_rect(av, 2, 2, 50, 50, 12, fill=col, outline="")
        av.create_text(26, 26, text=title[:1].upper(), fill="#ffffff", font=(ui.FONT, 18, "bold"))
        av.pack(side="left", padx=16, pady=14)
        mid = tk.Frame(c, bg=THEME["card"])
        mid.pack(side="left", fill="x", expand=True, pady=10)
        ui.label(mid, title, 12, True).pack(anchor="w")
        meta = h.get("author", "")
        if h.get("downloads") is not None:
            meta += f"   ⬇ {fmt_num(h['downloads'])}"
        ui.label(mid, meta, 9, dim=True).pack(anchor="w")
        d = (h.get("description") or "")
        ui.label(mid, d[:170] + ("…" if len(d) > 170 else ""), 9, wraplength=620).pack(anchor="w", pady=(3, 0))
        done = modrinth.is_installed(mf, h.get("project_id"), h.get("slug"))
        trash = None
        if done:
            trash = self._btn(c, "Удалить", None, "danger", 88, 36)
            trash.pack(side="right", padx=(0, 16))
        btn = self._btn(c, "✓ Установлено" if done else "Установить", None, "chip" if done else "accent", 140, 36)
        btn.pack(side="right", padx=(18, 8) if done else 18)
        btn.command = lambda: self._store_install(h, kind, btn, force=done)
        if trash:
            trash.command = lambda: self._store_remove(h, kind, btn, trash)

    def _store_remove(self, h, kind, btn, trash):
        title = h.get("title", "?")
        if not messagebox.askyesno("Kinetics", f"Удалить «{title}» из профиля?"):
            return
        gd = launcher.game_dir_for(self._collect())
        ok = modrinth.remove_project(gd, h.get("project_id"), h.get("slug"))
        if ok:
            btn.kind = "accent"
            btn.set_selected(False)
            btn.set_text("Установить")
            btn.command = lambda: self._store_install(h, kind, btn)
            btn._trash = None
            trash.destroy()
            self.toast.show(f"«{title}» удалён")
        else:
            self.toast.show("Файл не найден — удали вручную во вкладке «Установлено»", "err")

    def _store_install(self, h, kind, btn, force=False):
        p = self._collect()
        if not p["version"]:
            self.toast.show("Сначала выбери версию Minecraft", "err")
            return
        if kind == "mod" and p["loader"] != "fabric":
            self.toast.show("Для модов выбери загрузчик Fabric (вкладка «Версии»)", "err")
            return
        if btn.disabled:
            return
        btn.set_text("Установка…")
        btn.set_disabled(True)
        proj = h.get("project_id") or h.get("slug")
        title = h.get("title", proj)

        def work():
            msgs = []
            try:
                modrinth.install_project(proj, kind, p["version"], p["loader"],
                                         launcher.game_dir_for(p), msgs.append, force)
                self.q.put(("store_done", btn, True, f"{title}: установлено", h, kind))
            except Exception as e:  # noqa
                self.q.put(("store_done", btn, False, f"{title}: {e}", h, kind))
        threading.Thread(target=work, daemon=True).start()

    def _bulk_install(self, items, label):
        p = self._collect()
        if not p["version"] or p["loader"] != "fabric":
            self.toast.show("Нужны версия и загрузчик Fabric (вкладка «Версии»)", "err")
            return
        self.toast.show(f"{label}: устанавливаю…", "info")

        def work():
            msgs = []
            modrinth.sync(launcher.game_dir_for(p), p["version"], items, msgs.append)
            self.q.put(("toast", f"{label}: готово. " + (f"Пропущено: {len(msgs)}" if msgs else ""), "ok"))
            self.q.put(("store_rerender",))
        threading.Thread(target=work, daemon=True).start()

    def _install_pack(self):
        self._bulk_install(FPS_PACK, "Набор FPS")

    def _install_iris(self):
        self._bulk_install(["sodium", "iris"], "Iris + Sodium")

    def _store_render_installed(self):
        self._store_clear()
        p = self._collect_safe()
        gd = launcher.game_dir_for(p)
        inner = self.store_scroll.inner
        tb = ui.card(inner)
        tb.pack(fill="x", pady=(0, 10), padx=(0, 16))
        ui.label(tb, "Свои файлы и папки", 11, True, fg=THEME["accent"]).pack(anchor="w", padx=20, pady=(12, 4))
        r1 = tk.Frame(tb, bg=THEME["card"])
        r1.pack(fill="x", padx=20, pady=(0, 6))
        for text, sub in (("📁  Папка игры", ""), ("📁  mods", "mods"), ("📁  Шейдеры", "shaderpacks"),
                          ("📁  Ресурспаки", "resourcepacks"), ("📁  Миры", "saves")):
            self._btn(r1, text, lambda s=sub: self._open_sub(s), "card", 130, 32).pack(side="left", padx=(0, 8))
        r2 = tk.Frame(tb, bg=THEME["card"])
        r2.pack(fill="x", padx=20, pady=(0, 14))
        for text, kind in (("+ Свой мод (.jar)", "mod"), ("+ Свой шейдер (.zip)", "shader"),
                           ("+ Свой ресурспак (.zip)", "resourcepack")):
            self._btn(r2, text, lambda k=kind: self._store_add_file(k), "accent", 190, 32).pack(side="left", padx=(0, 8))
        items = modrinth.list_installed(gd)
        if not items:
            self._store_note("Пока пусто. Скачай что-нибудь во вкладках магазина или добавь свой файл кнопками выше.")
        names = {"mod": "Мод", "shader": "Шейдер", "resourcepack": "Ресурспак"}
        for it in items:
            c = ui.card(inner)
            c.pack(fill="x", pady=4, padx=(0, 16))
            mid = tk.Frame(c, bg=THEME["card"])
            mid.pack(side="left", fill="x", expand=True, padx=16, pady=10)
            ui.label(mid, it["name"], 11, True, fg=THEME["dim"] if it["disabled"] else THEME["fg"]).pack(anchor="w")
            ui.label(mid, f"{names[it['kind']]}  •  {it['size'] / 1048576:.1f} МБ" + ("  •  отключён" if it["disabled"] else ""),
                     9, dim=True).pack(anchor="w")
            self._btn(c, "Удалить", lambda i=it: self._inst_delete(i), "danger", 90, 32).pack(side="right", padx=(6, 14))
            if it["kind"] == "mod":
                self._btn(c, "Включить" if it["disabled"] else "Отключить",
                          lambda i=it: self._inst_toggle(i), "card", 100, 32).pack(side="right")
            if it["kind"] == "shader" and not it["disabled"]:
                self._btn(c, "Применить", lambda i=it, g=gd: self._inst_shader(g, i), "card", 100, 32).pack(side="right")

    def _inst_delete(self, it):
        if messagebox.askyesno("Kinetics", f"Удалить {it['name']}?"):
            try:
                if os.path.isdir(it["path"]):
                    shutil.rmtree(it["path"])
                else:
                    os.remove(it["path"])
                modrinth.forget_file(launcher.game_dir_for(self._collect()), it["name"])
                self.toast.show(f"«{it['name']}» удалён")
            except OSError as e:
                self.toast.show(str(e), "err")
            self._store_render_installed()

    def _inst_toggle(self, it):
        try:
            modrinth.toggle_disabled(it["path"])
        except OSError as e:
            self.toast.show(str(e), "err")
        self._store_render_installed()

    def _inst_shader(self, gd, it):
        modrinth.enable_shader(gd, it["name"])
        self.toast.show(f"Шейдер «{it['name']}» выбран в Iris. Нужны Iris + Sodium.")

    # ================================================================ ПРОФИЛЬ
    def _page_profile(self, f):
        inner = self._scroll_page(f, "Профиль", "Профили, ник, окно, папка игры, команды и переменные окружения")
        b = self._section(inner, "Профили")
        pr = self._inline(b)
        self.profile_box = ttk.Combobox(pr, state="readonly", width=24)
        self.profile_box.pack(side="left")
        self.profile_box.bind("<<ComboboxSelected>>", lambda e: self._switch_profile())
        for text, cmd in (("Новый", self._new_profile), ("Копия", self._dup_profile), ("Удалить", self._del_profile)):
            self._btn(pr, text, cmd, "card", 90, 32).pack(side="left", padx=(8, 0))
        self._row(b, 0, "Активный профиль", pr)
        b = self._section(inner, "Основное")
        self._row(b, 0, "Название профиля", ttk.Entry(b, textvariable=self.name_var))
        nick = self._inline(b)
        ttk.Entry(nick, textvariable=self.v["p.username"]).pack(side="left", fill="x", expand=True)
        self._btn(nick, "🎲 Случайный", self._rand_nick, "card", 120, 32).pack(side="left", padx=8)
        self._row(b, 1, "Ник (оффлайн)", nick)
        self.uuid_lbl = ui.label(b, "", 9, dim=True)
        self.uuid_lbl.grid(row=2, column=1, sticky="w")
        gd = self._inline(b)
        ttk.Entry(gd, textvariable=self.v["p.game_dir"]).pack(side="left", fill="x", expand=True)
        self._btn(gd, "Обзор", lambda: self._browse_dir("p.game_dir"), "card", 80, 32).pack(side="left", padx=8)
        self._btn(gd, "Открыть", self._open_game_dir, "accent", 90, 32).pack(side="left")
        self._row(b, 3, "Папка игры (пусто = авто)", gd)

        b = self._section(inner, "Окно и сервер")
        win = self._inline(b)
        ttk.Spinbox(win, from_=320, to=7680, width=7, textvariable=self.v["p.width"]).pack(side="left")
        ui.label(win, "  ×  ", 10).pack(side="left")
        ttk.Spinbox(win, from_=240, to=4320, width=7, textvariable=self.v["p.height"]).pack(side="left")
        ui.Switch(win, "Полный экран", self.v["p.fullscreen"]).pack(side="left", padx=24)
        self._row(b, 0, "Размер окна", win)
        self._row(b, 1, "Автоподключение к серверу", ttk.Entry(b, textvariable=self.v["p.server"]))
        self._row(b, 2, "Доп. аргументы игры", ttk.Entry(b, textvariable=self.v["p.game_args"]))

        b = self._section(inner, "Запуск")
        self._row(b, 0, "Команда ДО запуска", ttk.Entry(b, textvariable=self.v["p.pre_cmd"]))
        self._row(b, 1, "Команда ПОСЛЕ закрытия", ttk.Entry(b, textvariable=self.v["p.post_cmd"]))
        self._row(b, 2, "Переменные окружения", ttk.Entry(b, textvariable=self.v["p.env"]))
        ui.label(b, "Формат: КЛЮЧ=значение;КЛЮЧ2=значение (например, для выбора видеокарты)", 8, dim=True).grid(
            row=3, column=1, sticky="w")
        self._row(b, 4, "Приоритет процесса", ttk.Combobox(b, state="readonly", textvariable=self.prio_var,
                                                           values=list(PRIORITIES.values())))

        b = self._section(inner, "Профиль как файл")
        r = self._inline(b)
        r.grid(row=0, column=0, columnspan=2, sticky="w")
        self._btn(r, "Экспорт в файл", self._export_profile, "card", 150, 34).pack(side="left", padx=(0, 8))
        self._btn(r, "Импорт из файла", self._import_profile, "card", 150, 34).pack(side="left", padx=(0, 8))
        self._btn(r, "Сохранить", self._save_and_notify, "accent", 130, 34).pack(side="left")

    # ================================================================ ОПТИМИЗАЦИЯ
    def _page_optim(self, f):
        inner = self._scroll_page(f, "Оптимизация", "Память, Java, JVM-флаги и быстрые пресеты под твой ПК")
        b = self._section(inner, "Быстрая оптимизация")
        r = self._inline(b)
        r.grid(row=0, column=0, columnspan=2, sticky="w")
        self._btn(r, "✨ Авто под мой ПК", self._auto_opt, "accent", 180, 38).pack(side="left", padx=(0, 8))
        for key, p in optimizer.QUALITY_PRESETS.items():
            self._btn(r, p["label"], lambda k=key: self._apply_preset(k), "card", 140, 38).pack(side="left", padx=4)
        ui.label(b, "Пресет выставляет RAM, JVM-флаги, графику; моды пресета ставятся при запуске (Fabric).", 9, dim=True).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        b = self._section(inner, "Оперативная память")
        total = system.total_ram_mb()
        top = max(2048, total // 256 * 256)
        self.ram_labels, self.ram_scales = {}, {}
        for i, (key, text) in enumerate((("p.ram_min", "Минимум (Xms)"), ("p.ram_max", "Максимум (Xmx)"))):
            sc = ttk.Scale(b, from_=512, to=top, command=lambda val, k=key: self._on_ram(k, val))
            lbl = ui.label(b, "", 10, True)
            self._row(b, i, text, sc)
            lbl.grid(row=i, column=2, padx=14)
            self.ram_scales[key], self.ram_labels[key] = sc, lbl
        ui.label(b, f"Всего в системе: {total} МБ. Ставь Xmx не больше ~60% RAM.", 9, dim=True).grid(
            row=2, column=1, sticky="w")

        b = self._section(inner, "Java и сборщик мусора")
        self.jvm_box = ttk.Combobox(b, state="readonly", textvariable=self.jvm_var,
                                    values=list(optimizer.preset_labels().values()))
        self._row(b, 0, "Набор JVM-флагов", self.jvm_box)
        self._row(b, 1, "Свои JVM-аргументы", ttk.Entry(b, textvariable=self.v["p.jvm_extra"]))
        jp = self._inline(b)
        self.java_box = ttk.Combobox(jp, textvariable=self.v["p.java_path"])
        self.java_box.pack(side="left", fill="x", expand=True)
        self._btn(jp, "Найти", self._find_java, "card", 70, 32).pack(side="left", padx=6)
        self._btn(jp, "Обзор", self._browse_java, "card", 70, 32).pack(side="left")
        self._row(b, 2, "Java (пусто = авто)", jp)
        dl = self._inline(b)
        for m in (8, 17, 21):
            self._btn(dl, f"Скачать Java {m}", lambda m=m: self._dl_java(m), "card", 130, 32).pack(side="left", padx=(0, 6))
        self._row(b, 3, "Загрузка Java", dl)
        self.preview = ui.label(b, "", 9, dim=True, wraplength=760)
        self.preview.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        b = self._section(inner, "Тонкие настройки JVM")
        for i, (k, (flag, desc)) in enumerate(optimizer.JVM_TOGGLES.items()):
            ui.Switch(b, f"{desc}", self.tog_vars[k]).grid(row=i, column=0, columnspan=2, sticky="w", pady=4)
            ui.label(b, flag, 8, dim=True).grid(row=i, column=2, sticky="e", padx=10)

    # ================================================================ ГРАФИКА
    def _page_gfx(self, f):
        inner = self._scroll_page(f, "Графика", "Настройки пишутся в options.txt профиля")
        b = self._section(inner, "Применение")
        ui.Switch(b, "Применять эти настройки к options.txt при каждом запуске",
                  self.v["p.apply_game_options"]).grid(row=0, column=0, columnspan=2, sticky="w")
        ui.label(b, "Выключено — лаунчер не трогает настройки игры.", 9, dim=True).grid(row=1, column=0, columnspan=2, sticky="w")
        b = self._section(inner, "Параметры")
        spins = [("Дальность прорисовки (чанки)", "render_distance", 2, 32, 1),
                 ("Дальность симуляции (чанки)", "simulation_distance", 5, 32, 1),
                 ("Лимит FPS (260 = без лимита)", "max_fps", 10, 260, 10),
                 ("Сглаживание биомов (0–7)", "biome_blend", 0, 7, 1),
                 ("Mipmap (0–4)", "mipmap", 0, 4, 1),
                 ("Масштаб GUI (0 = авто)", "gui_scale", 0, 6, 1),
                 ("Дальность сущностей (0.5–5)", "entity_distance", 0.5, 5.0, 0.25)]
        r = 0
        for text, key, lo, hi, step in spins:
            self._row(b, r, text, ttk.Spinbox(b, from_=lo, to=hi, increment=step, width=10,
                                              textvariable=self.v["o." + key]))
            r += 1
        self._row(b, r, "Графика", ttk.Combobox(b, state="readonly", textvariable=self.gfx_var, values=GRAPHICS, width=18))
        self._row(b, r + 1, "Частицы", ttk.Combobox(b, state="readonly", textvariable=self.part_var, values=PARTICLES, width=18))
        sw = self._inline(b)
        for text, key in (("VSync", "vsync"), ("Облака", "clouds"), ("Плавное освещение", "ao")):
            ui.Switch(sw, text, self.v["o." + key]).pack(side="left", padx=(0, 22))
        self._row(b, r + 2, "Опции", sw)

    # ================================================================ ЛАУНЧЕР
    def _page_settings(self, f):
        inner = self._scroll_page(f, "Внешний вид", "Тема, цвета, шрифт и шапка главного экрана — подстрой под себя")
        st = self.store.settings
        b = self._section(inner, "Тема")
        grid = self._inline(b)
        grid.grid(row=0, column=0, columnspan=2, sticky="w")
        for i, (name, t) in enumerate(ui.THEMES.items()):
            cell = tk.Frame(grid, bg=THEME["card"])
            cell.grid(row=i // 4, column=i % 4, padx=6, pady=6)
            cv = tk.Canvas(cell, width=132, height=84, bg=THEME["card"], highlightthickness=0, cursor="hand2")
            cv.pack()
            sel = name == st.get("theme", "Полночь")
            ui.round_rect(cv, 2, 2, 130, 82, 12, fill=t["bg"], outline=THEME["accent"] if sel else t["line"], width=2 if sel else 1)
            ui.round_rect(cv, 8, 8, 34, 76, 8, fill=t["panel"], outline="")
            ui.round_rect(cv, 42, 14, 124, 40, 7, fill=t["card"], outline="")
            ui.round_rect(cv, 42, 48, 100, 70, 7, fill=t["accent"], outline="")
            cv.create_text(66, 59, text="Aa", fill="#ffffff", font=(ui.FONT, 9, "bold"))
            cv.bind("<Button-1>", lambda e, n=name: self._set_theme(n))
            ui.label(cell, name, 9, bold=sel).pack()
        b = self._section(inner, "Цвета и шрифт")
        sw = self._inline(b)
        for col in ACCENTS:
            c = tk.Canvas(sw, width=34, height=34, bg=THEME["card"], highlightthickness=0, cursor="hand2")
            c.pack(side="left", padx=4)
            c.bind("<Button-1>", lambda e, col=col: self._set_accent(col))
            ui.round_rect(c, 3, 3, 31, 31, 10, fill=col, outline=THEME["fg"] if col.lower() == THEME["accent"].lower() else "")
        self._btn(sw, "Свой цвет…", self._custom_accent, "card", 110, 32).pack(side="left", padx=10)
        self._row(b, 0, "Акцентный цвет", sw)
        fams = set(tkfont.families())
        fonts = [x for x in ("Segoe UI", "Calibri", "Verdana", "Trebuchet MS", "Georgia", "Tahoma", "Arial",
                             "Consolas", "Comic Sans MS", "DejaVu Sans", "Ubuntu", "Noto Sans") if x in fams] or [ui.FONT]
        fb = ttk.Combobox(b, state="readonly", textvariable=self.font_var, values=fonts, width=24)
        fb.bind("<<ComboboxSelected>>", lambda e: self._set_font())
        self._row(b, 1, "Шрифт интерфейса", fb)
        b = self._section(inner, "Шапка главного экрана")
        labels = {"particles": "Градиент и частицы", "gradient": "Только градиент", "image": "Своя картинка"}
        self.hero_labels = labels
        self.hero_bg_var.set(labels.get(st.get("hero_bg", "particles")))
        hb = ttk.Combobox(b, state="readonly", textvariable=self.hero_bg_var, values=list(labels.values()), width=24)
        hb.bind("<<ComboboxSelected>>", lambda e: self._set_hero_bg())
        self._row(b, 0, "Фон", hb)
        r = self._inline(b)
        self._btn(r, "Выбрать картинку…", self._pick_hero_image, "card", 195, 32).pack(side="left")
        ui.label(r, "   PNG или GIF (с Pillow — ещё и JPG)", 9, dim=True).pack(side="left")
        self._row(b, 1, "Картинка", r)
        ui.Switch(b, "Анимации интерфейса", self.anim_var, self._toggle_anim).grid(row=2, column=0, columnspan=2, sticky="w", pady=8)
        b = self._section(inner, "Загрузка и запуск")
        self._row(b, 0, "Потоков загрузки", ttk.Spinbox(b, from_=1, to=32, width=8, textvariable=self.threads_var))
        self._row(b, 1, "После запуска игры", ttk.Combobox(b, state="readonly", textvariable=self.after_var,
                                                           values=list(AFTER.values())))
        ui.Switch(b, "Строго проверять контрольные суммы всех файлов (медленнее)", self.verify_var).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=6)
        b = self._section(inner, "Обслуживание")
        r = self._inline(b)
        r.grid(row=0, column=0, columnspan=2, sticky="w")
        for text, cmd, w in (("Папка данных", lambda: self._open(config.DATA_DIR), 130),
                             ("Очистить кэш", self._clear_cache, 130),
                             ("Диагностика", self._diag, 130),
                             ("Ярлык на рабочий стол", lambda: self.quick._shortcut("desktop"), 200),
                             ("Сбросить настройки", self._reset_settings, 170)):
            self._btn(r, text, cmd, "card", w, 34).pack(side="left", padx=(0, 8))
        self._btn(r, "Сохранить", self._save_and_notify, "accent", 120, 34).pack(side="left")
        ui.label(b, "Kinetics скачивает файлы игры с официальных серверов Mojang.\nОффлайн-режим: свободный ник; серверы с online-mode и скины недоступны.",
                 9, dim=True).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _set_theme(self, name):
        st = self.store.settings
        st["theme"], st["accent"] = name, ui.THEMES[name]["accent"]
        ui.apply_theme(name)
        self.store.save()
        self._rebuild()
        self.toast.show(f"Тема «{name}»")

    def _set_accent(self, col):
        st = self.store.settings
        st["accent"] = col
        ui.apply_theme(st.get("theme", "Полночь"), col)
        self.store.save()
        self._rebuild()

    def _custom_accent(self):
        c = colorchooser.askcolor(color=THEME["accent"], title="Акцентный цвет")[1]
        if c:
            self._set_accent(c)

    def _set_font(self):
        ui.FONT = self.font_var.get()
        self.store.settings["font"] = ui.FONT
        self.store.save()
        self._rebuild()

    def _set_hero_bg(self):
        rev = {v: k for k, v in self.hero_labels.items()}
        mode = rev.get(self.hero_bg_var.get(), "particles")
        st = self.store.settings
        if mode == "image" and not st.get("hero_image"):
            return self._pick_hero_image()
        st["hero_bg"] = mode
        self.store.save()
        self.hero.set_mode(mode, st.get("hero_image", ""))

    def _pick_hero_image(self):
        p = filedialog.askopenfilename(filetypes=[("Изображения", "*.png *.gif *.jpg *.jpeg"), ("Все файлы", "*.*")])
        if p:
            st = self.store.settings
            st["hero_image"], st["hero_bg"] = p, "image"
            self.hero_bg_var.set(self.hero_labels["image"])
            self.store.save()
            self.hero.set_mode("image", p)
            self.toast.show("Фон шапки изменён")
        else:
            self.hero_bg_var.set(self.hero_labels.get(self.store.settings.get("hero_bg", "particles")))

    def _toggle_anim(self):
        ui.ANIM["on"] = bool(self.anim_var.get())
        self.store.settings["animations"] = ui.ANIM["on"]
        self.store.save()
        if ui.ANIM["on"] and self.cur_page is self.pages["play"]:
            self.hero.start()

    # ================================================================ профили
    def _load_profile(self, name):
        p = self.store.profiles[name]
        self.current = name
        self.name_var.set(name)
        for k in PROFILE_FIELDS:
            self.v["p." + k].set(p.get(k, store.DEFAULT_PROFILE.get(k)))
        for k in OPTION_FIELDS:
            self.v["o." + k].set(p["game_options"].get(k))
        self.gfx_var.set(GRAPHICS[int(p["game_options"].get("graphics", 1)) % 3])
        self.part_var.set(PARTICLES[int(p["game_options"].get("particles", 1)) % 3])
        labels = optimizer.preset_labels()
        self.jvm_var.set(labels.get(p.get("jvm_preset"), labels["balanced"]))
        self.prio_var.set(PRIORITIES.get(p.get("priority"), PRIORITIES["normal"]))
        for k, var in self.tog_vars.items():
            var.set(k in p.get("jvm_toggles", []))
        st = self.store.settings
        self.threads_var.set(st.get("threads", 8))
        self.verify_var.set(st.get("verify_files", False))
        self.after_var.set(AFTER.get(st.get("after_launch"), AFTER["minimize"]))
        self.profile_box.configure(values=list(self.store.profiles))
        self.profile_box.set(name)
        self.opt_mods = list(p.get("opt_mods", []))
        rec = self.store.settings.get("recent", [])
        if not p.get("version") and rec:
            self.v["p.version"].set(rec[0]["version"])
            self.v["p.loader"].set(rec[0]["loader"])
            self.v["p.loader_version"].set(rec[0].get("loader_version") or "auto")
        for k in ("p.ram_min", "p.ram_max"):
            self._sync_ram(k)
        self._sync_chips()
        self._refresh_uuid()
        self._refresh_preview()
        self._refresh_summary()
        if self.manifest is not None or self.ver_filter == "installed":
            self._fill_versions()
        self._refresh_recent()

    def _collect(self):
        p = {"name": self.name_var.get().strip() or "Default"}
        for k in PROFILE_FIELDS:
            try:
                p[k] = self.v["p." + k].get()
            except tk.TclError:
                p[k] = store.DEFAULT_PROFILE.get(k)
        p["username"] = p["username"].strip()
        p["version_type"] = "release"
        rl = {v: k for k, v in optimizer.preset_labels().items()}
        p["jvm_preset"] = rl.get(self.jvm_var.get(), "balanced")
        p["priority"] = {v: k for k, v in PRIORITIES.items()}.get(self.prio_var.get(), "normal")
        p["jvm_toggles"] = [k for k, v in self.tog_vars.items() if v.get()]
        go = {}
        for k in OPTION_FIELDS:
            try:
                go[k] = self.v["o." + k].get()
            except tk.TclError:
                go[k] = store.DEFAULT_GAME_OPTIONS[k]
        go["graphics"] = GRAPHICS.index(self.gfx_var.get()) if self.gfx_var.get() in GRAPHICS else 1
        go["particles"] = PARTICLES.index(self.part_var.get()) if self.part_var.get() in PARTICLES else 1
        p["game_options"] = go
        p["opt_mods"] = list(self.opt_mods)
        if p["ram_min"] > p["ram_max"]:
            p["ram_min"] = p["ram_max"]
        return p

    def _collect_safe(self):
        try:
            return self._collect()
        except Exception:
            return store.new_profile("Default")

    def _save(self):
        p = self._collect()
        old = self.current
        if old and old in self.store.profiles and old != p["name"]:
            if p["name"] in self.store.profiles:
                p["name"] = old
            else:
                del self.store.profiles[old]
        self.store.profiles[p["name"]] = p
        self.current = p["name"]
        st = self.store.settings
        st["last_profile"] = p["name"]
        try:
            st["threads"] = int(self.threads_var.get())
        except tk.TclError:
            pass
        st["verify_files"] = bool(self.verify_var.get())
        st["after_launch"] = {v: k for k, v in AFTER.items()}.get(self.after_var.get(), "minimize")
        self.store.save()
        self.profile_box.configure(values=list(self.store.profiles))
        self.profile_box.set(p["name"])
        self.name_var.set(p["name"])
        self._refresh_summary()
        return p

    def _save_and_notify(self):
        self._save()
        self.toast.show("Настройки сохранены")

    def _switch_profile(self):
        target = self.profile_box.get()
        self._save()
        if target in self.store.profiles:
            self._load_profile(target)

    def _new_profile(self):
        self._save()
        i = 1
        while f"Профиль {i}" in self.store.profiles:
            i += 1
        name = f"Профиль {i}"
        self.store.profiles[name] = store.new_profile(name)
        self.store.profiles[name]["username"] = self.v["p.username"].get() or "Player"
        self._load_profile(name)
        self.toast.show(f"Создан «{name}»")

    def _dup_profile(self):
        p = self._save()
        name, i = p["name"] + " (копия)", 2
        while name in self.store.profiles:
            name = f"{p['name']} (копия {i})"
            i += 1
        c = copy.deepcopy(p)
        c["name"], c["game_dir"] = name, ""
        self.store.profiles[name] = c
        self._load_profile(name)
        self.toast.show("Профиль скопирован")

    def _del_profile(self):
        if len(self.store.profiles) <= 1:
            self.toast.show("Нельзя удалить последний профиль", "err")
            return
        if messagebox.askyesno("Kinetics", f"Удалить профиль «{self.current}»?\n(Папка с миром останется на диске.)"):
            del self.store.profiles[self.current]
            self._load_profile(next(iter(self.store.profiles)))
            self.store.save()

    def _export_profile(self):
        p = self._save()
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile=f"{p['name']}.json",
                                            filetypes=[("Профиль Kinetics", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(p, fh, ensure_ascii=False, indent=2)
            self.toast.show("Профиль экспортирован")

    def _import_profile(self):
        path = filedialog.askopenfilename(filetypes=[("Профиль Kinetics", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            name = raw.get("name", "Импорт")
            while name in self.store.profiles:
                name += " (импорт)"
            raw["game_dir"] = ""
            self._save()
            self.store.profiles[name] = self.store._merge(raw, name)
            self._load_profile(name)
            self.toast.show(f"Импортирован «{name}»")
        except Exception as e:  # noqa
            self.toast.show(f"Не удалось импортировать: {e}", "err")

    # ================================================================ мелочи
    def _rand_nick(self):
        self.v["p.username"].set("Kinetic" + str(random.randint(100, 99999)))

    def _refresh_uuid(self):
        try:
            n = self.v["p.username"].get().strip()
            self.uuid_lbl.config(text=f"Offline UUID: {mojang.offline_uuid(n)}" if n else "")
        except (tk.TclError, AttributeError):
            pass

    def _refresh_summary(self):
        try:
            nick = self.v["p.username"].get().strip() or "Player"
            ver = self.v["p.version"].get()
            loader = self.v["p.loader"].get()
            rec = self.store.settings.get("recent", [])
            last = rec[0] if rec and (rec[0]["version"], rec[0]["loader"]) == (ver, loader) else None
            if not ver:
                self.play_btn.set_text("ВЫБРАТЬ ВЕРСИЮ")
                self.hero.set_texts(f"Привет, {nick}!", "Версия не выбрана", "Открой «Версии» и выбери, во что играть")
            else:
                self.play_btn.set_text("▶   ПРОДОЛЖИТЬ" if last else "▶   ИГРАТЬ")
                self.hero.set_texts(f"Привет, {nick}!", f"{ver}  ·  {'Fabric' if loader == 'fabric' else 'Vanilla'}",
                                    ("последний запуск: " + self._ago(last["ts"])) if last else "готово к запуску")
            self.sidebar.set_user(nick, self.name_var.get() or "Default")
        except (tk.TclError, AttributeError):
            pass

    def _on_ram(self, key, val):
        v = int(round(float(val) / 256) * 256)
        if self.v[key].get() != v:
            self.v[key].set(v)

    def _sync_ram(self, key):
        try:
            v = self.v[key].get()
        except tk.TclError:
            return
        try:
            self.ram_labels[key].config(text=f"{v} МБ ({v / 1024:.1f} ГБ)")
            if abs(float(self.ram_scales[key].get()) - v) > 1:
                self.ram_scales[key].set(v)
        except (tk.TclError, AttributeError, KeyError):
            pass

    def _refresh_preview(self):
        try:
            rl = {v: k for k, v in optimizer.preset_labels().items()}
            preset = rl.get(self.jvm_var.get(), "balanced")
            flags = optimizer.jvm_flags(preset, 21 if preset == "zgc" else None)
            flags += [optimizer.JVM_TOGGLES[k][0] for k, v in self.tog_vars.items() if v.get()]
            txt = f"-Xms{self.v['p.ram_min'].get()}M -Xmx{self.v['p.ram_max'].get()}M " + " ".join(flags)
            if self.v["p.jvm_extra"].get().strip():
                txt += " " + self.v["p.jvm_extra"].get().strip()
            self.preview.config(text="Итоговые аргументы: " + txt)
        except (tk.TclError, AttributeError):
            pass

    def _browse_dir(self, key):
        d = filedialog.askdirectory()
        if d:
            self.v[key].set(d)

    def _browse_java(self):
        p = filedialog.askopenfilename(filetypes=[("Java", "java.exe javaw.exe java"), ("Все файлы", "*.*")])
        if p:
            self.v["p.java_path"].set(p)

    def _find_java(self):
        self.toast.show("Ищу Java…", "info")
        threading.Thread(target=lambda: self.q.put(("javas", java_utils.find_javas())), daemon=True).start()

    def _dl_java(self, major):
        if self.busy:
            return
        self._set_busy(True)
        self.show("play")

        def work():
            cb = Cb(self.q)
            try:
                path = java_utils.download_java(major, lambda d, t: cb.progress(d, t, f"Java {major}"), cb.log)
                cb.log(f"Java {major} установлена: {path}")
                self.q.put(("toast", f"Java {major} установлена", "ok"))
            except Exception as e:  # noqa
                cb.log(f"ОШИБКА: {e}")
            self.q.put(("idle",))
        threading.Thread(target=work, daemon=True).start()

    def _open(self, path):
        os.makedirs(path, exist_ok=True)
        try:
            if config.IS_WIN:
                os.startfile(path)  # noqa
            else:
                subprocess.Popen(["xdg-open" if config.OS_NAME == "linux" else "open", path])
        except Exception as e:  # noqa
            self.toast.show(str(e), "err")

    def _open_game_dir(self):
        self._open(launcher.game_dir_for(self._collect()))

    def _clear_cache(self):
        if messagebox.askyesno("Kinetics", "Удалить кэш и распакованные natives?\n(Миры и настройки не затрагиваются.)"):
            shutil.rmtree(config.CACHE_DIR, ignore_errors=True)
            shutil.rmtree(config.NATIVES_DIR, ignore_errors=True)
            config.ensure_dirs()
            self.toast.show("Кэш очищен")

    def _reset_settings(self):
        if messagebox.askyesno("Kinetics", "Удалить ВСЕ профили и настройки лаунчера?\n(Папки миров останутся.)"):
            try:
                os.remove(config.CONFIG_FILE)
            except OSError:
                pass
            self.store = store.Store()
            self._load_profile(self.store.settings["last_profile"])
            self.toast.show("Настройки сброшены")

    def _diag(self):
        self.show("play")
        self._append_log(f"RAM: {system.total_ram_mb()} МБ, ядер: {system.cpu_cores()}")
        self.q.put(("javas", java_utils.find_javas()))
        self._append_log(f"Данные: {config.DATA_DIR}")

    # ================================================================ оптимизация
    def _auto_opt(self):
        r = optimizer.recommend()
        self._apply_preset(r["preset"], ram=(r["ram_min"], r["ram_max"]), jvm=r["jvm"])
        self.toast.show(f"Авто: {r['ram_total']} МБ RAM, {r['cores']} ядер → «{optimizer.QUALITY_PRESETS[r['preset']]['label']}»")

    def _apply_preset(self, key, ram=None, jvm=None):
        p = optimizer.QUALITY_PRESETS[key]
        r = optimizer.recommend()
        ram = ram or (r["ram_min"], r["ram_max"])
        self.v["p.ram_min"].set(ram[0])
        self.v["p.ram_max"].set(ram[1])
        self.jvm_var.set(optimizer.preset_labels()[jvm or p["jvm"]])
        for k, val in p["options"].items():
            if k == "graphics":
                self.gfx_var.set(GRAPHICS[val])
            elif k == "particles":
                self.part_var.set(PARTICLES[val])
            else:
                self.v["o." + k].set(val)
        self.v["p.apply_game_options"].set(True)
        self.opt_mods = list(p["mods"])
        self.toast.show(f"Пресет «{p['label']}» применён")

    # ================================================================ версии / манифест
    def _fetch_manifest(self):
        try:
            self.q.put(("manifest", mojang.load_manifest()))
        except Exception as e:  # noqa
            self.q.put(("log", f"Нет связи с Mojang ({e}). Доступны только установленные версии."))
            self.q.put(("manifest_fail",))

    # ================================================================ запуск
    def _set_busy(self, b):
        self.busy = b
        self.play_btn.set_disabled(b)
        self.progress.set_busy(b)
        if b:
            self.progress.set(0)
        self._layout_play()

    def _play(self, install_only=False):
        if self.busy:
            return
        p = self._save()
        if not NICK_RE.match(p["username"]):
            self.toast.show("Ник: 3–16 символов, латиница, цифры и _", "err")
            self.show("profile")
            return
        if not p["version"]:
            self.toast.show("Выбери версию Minecraft", "err")
            self.show("versions")
            return
        self._run(p, install_only)

    def _run(self, p, install_only=False, strict=False):
        self._set_busy(True)
        threading.Thread(target=self._worker, args=(p, install_only, strict), daemon=True).start()

    def _worker(self, p, install_only, strict):
        cb = Cb(self.q)
        st = dict(self.store.settings)
        if strict:
            st["verify_files"] = True
        try:
            ctx = launcher.prepare(p, st, cb)
            if install_only:
                cb.log("Готово: файлы проверены и скачаны.")
                self.q.put(("toast", f"Версия {ctx['vid']} готова к запуску", "ok"))
                self.q.put(("refill",))
                return
            st["perf"] = perf.prepare_launch(st.get("perf"), ctx["java"], cb.log)
            cmd = launcher.build_command(ctx, p, st)
            mode = st.get("after_launch", "minimize")
            if p.get("pre_cmd", "").strip():
                cb.log("Команда перед запуском...")
                subprocess.run(p["pre_cmd"], shell=True, cwd=ctx["game_dir"], timeout=180)
            cb.log(f"Запуск {ctx['vid']} (Java {ctx['java_major']}, {p['ram_max']} МБ)...")
            proc = launcher.start(cmd, ctx["game_dir"], capture=(mode != "close"),
                                  env=launcher.build_env(p, st), priority=p.get("priority", "normal"))
            self.proc = proc
            self.q.put(("record", p["version"], p["loader"], p.get("loader_version") or ""))
            self.q.put(("launched", mode))
            if mode == "close":
                return
            t_start = time.time()
            for line in proc.stdout:
                cb.log(line.rstrip())
            code = proc.wait()
            self.q.put(("played", p["version"], p["loader"], int(time.time() - t_start)))
            cb.log(f"Игра закрыта (код {code}).")
            if p.get("post_cmd", "").strip():
                subprocess.Popen(p["post_cmd"], shell=True, cwd=ctx["game_dir"])
            if code not in (0, 1, -1):
                self.q.put(("crash", code))
        except Exception as e:  # noqa
            cb.log(f"ОШИБКА: {e}")
            self.q.put(("toast", f"Ошибка: {e}", "err"))
        finally:
            self.proc = None
            self.q.put(("idle",))

    def _stop(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass

    # ================================================================ очередь
    def _append_log(self, text):
        self.log_lines.append(text)
        if len(self.log_lines) > 1500:
            del self.log_lines[:500]
        try:
            self.log.config(state="normal")
            self.log.insert("end", text + "\n")
            if int(self.log.index("end-1c").split(".")[0]) > 1500:
                self.log.delete("1.0", "500.0")
            self.log.see("end")
            self.log.config(state="disabled")
        except tk.TclError:
            pass
        if text.startswith("ОШИБКА") and not self.log_open:
            self.log_open = True
            self._layout_play()

    def _poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                k = m[0]
                if k == "log":
                    self._append_log(m[1])
                elif k == "progress":
                    _, d, t, label = m
                    if t:
                        self.progress.set(d / t)
                    self.status_var.set(f"{label}: {d}/{t}" if t else label)
                elif k == "manifest":
                    self.manifest = m[1]
                    if not self.v["p.version"].get():
                        self.v["p.version"].set(self.manifest["latest"]["release"])
                    self._fill_versions()
                    self._refresh_summary()
                    self._refresh_recent()
                elif k == "manifest_fail":
                    self.manifest = None
                    self.ver_filter = "installed"
                    self._set_filter("installed")
                elif k == "refill":
                    self._fill_versions()
                    self._refresh_recent()
                elif k == "loaders":
                    self.lv_box.configure(values=["auto"] + m[1])
                    self.toast.show(f"Версий Fabric Loader: {len(m[1])}")
                elif k == "javas":
                    self.java_box.configure(values=[p for _, p in m[1]])
                    self._append_log("Найденные Java: " + (", ".join(f"{a} → {b}" for a, b in m[1]) or "нет"))
                    self.toast.show(f"Найдено Java: {len(m[1])}", "info")
                elif k == "toast":
                    self.toast.show(m[1], m[2])
                elif k == "store_results":
                    if m[1] == self.store_token:
                        self._store_results(m[2], m[3], m[4])
                elif k == "store_error":
                    if m[1] == self.store_token:
                        self._store_clear()
                        self._store_note("Не удалось связаться с Modrinth: " + m[2])
                elif k == "store_done":
                    btn, ok = m[1], m[2]
                    try:
                        btn.set_disabled(False)
                        btn.kind = "chip" if ok else "accent"
                        btn.set_selected(ok)
                        btn.set_text("✓ Установлено" if ok else "Повторить")
                    except tk.TclError:
                        pass
                    if ok and not getattr(btn, "_trash", None):
                        try:
                            tr = self._btn(btn.master, "Удалить", None, "danger", 88, 36)
                            tr.pack(side="right", padx=(0, 16), before=btn)
                            tr.command = lambda h=m[4], k=m[5], b=btn, t=tr: self._store_remove(h, k, b, t)
                            btn._trash = tr
                        except tk.TclError:
                            pass
                    self.toast.show(m[3], "ok" if ok else "err")
                elif k == "store_rerender":
                    if self.store_kind == "opt":
                        self._store_render_opt()
                elif k == "gpus":
                    self.quick and self.quick.set_gpus(m[1])
                elif k == "played":
                    self._add_playtime(m[1], m[2], m[3])
                elif k == "record":
                    self._record_launch(m[1], m[2], m[3])
                elif k == "launched":
                    if self.store.settings["perf"].get("pause_anim", True):
                        ui.STATE["paused"] = True
                    self.stop_btn.set_disabled(False)
                    self.status_var.set("Игра запущена")
                    if m[1] == "minimize":
                        self.iconify()
                    elif m[1] == "close":
                        self.after(1500, self.destroy)
                elif k == "crash":
                    self.deiconify()
                    self.toast.show(f"Игра завершилась с ошибкой (код {m[1]}). Смотри лог.", "err")
                elif k == "idle":
                    ui.STATE["paused"] = False
                    self._set_busy(False)
                    self.stop_btn.set_disabled(True)
                    self.deiconify()
                    self.status_var.set("Готов к запуску")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _on_close(self):
        try:
            self._save()
        except Exception:
            pass
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Kinetics", "Игра ещё запущена. Закрыть лаунчер? (игра продолжит работу)"):
                return
        self.destroy()


def run():
    config.set_app_id()
    app = App()
    try:  # заставка PyInstaller (есть только в собранном exe)
        import pyi_splash
        app.after(250, pyi_splash.close)
    except Exception:
        pass
    app.mainloop()
