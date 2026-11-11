"""Шестерёнка справа сверху: быстрые настройки запуска (графический API, видеокарта, быстрый старт, ярлыки)."""
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, ttk

from . import config, perf
from . import ui_kit as ui
from .ui_kit import THEME

API_HINTS = {
    "opengl": "Стандартный режим Minecraft Java. Работает у всех.",
    "zink": "Игра рисует через OpenGL, а Mesa Zink превращает вызовы в Vulkan. Нужна папка Mesa (opengl32.dll). "
            "Экспериментально: на части ПК даёт больше FPS, на части — меньше.",
    "software": "Рисует процессором (Mesa llvmpipe). Для ПК, где нет поддержки OpenGL. Медленно, но запускается.",
}


class Quick:
    W = 470

    def __init__(self, app):
        self.app = app
        self.open = False
        self.panel = None
        self.btn = ui.AnimButton(app, "⚙", self.toggle, kind="card", width=42, height=42,
                                 font=("Segoe UI Symbol", 16), radius=13, bg=THEME["bg"])
        self.btn.place(relx=1.0, y=14, x=-16, anchor="ne")
        self.set_page("play")

    # цвет подложки кнопки, чтобы не было «квадрата» поверх шапки
    def set_page(self, key):
        try:
            self.btn.pbg = self.app.hero.color_at(30) if key == "play" else THEME["bg"]
            self.btn.config(bg=self.btn.pbg)
            self.btn._draw()
        except (tk.TclError, AttributeError):
            pass

    def cfg(self):
        return self.app.store.settings["perf"]

    def set(self, key, value):
        self.cfg()[key] = value
        self.app.store.save()
        self.refresh()

    # ------------------------------------------------------------ окно
    def toggle(self):
        if self.open:
            return self.close()
        self.open = True
        if getattr(self.app, "doc", None):
            self.app.doc.hide_tip()
        if self.panel is None or not self.panel.winfo_exists():
            self._build()
        h = max(420, min(640, self.app.winfo_height() - 90))
        self.panel.place(relx=1.0, y=62, x=-16, anchor="ne", width=self.W, height=h)
        self.panel.tk.call("raise", self.panel._w)
        ui.tween(self.panel, "drop", 220, lambda t: self.panel.place_configure(y=40 + 22 * t))
        self.refresh()
        threading.Thread(target=lambda: self.app.q.put(("gpus", perf.list_gpus())), daemon=True).start()

    def close(self):
        if not self.open:
            return
        self.open = False
        p = self.panel
        ui.tween(p, "drop", 160, lambda t: p.place_configure(y=62 - 22 * t), done=p.place_forget)

    def destroy(self):
        for w in (self.btn, self.panel):
            try:
                if w is not None:
                    w.destroy()
            except tk.TclError:
                pass

    # ------------------------------------------------------------ содержимое
    def _section(self, parent, title):
        ui.label(parent, title, 10, True, fg=THEME["accent"], bg=THEME["panel"]).pack(anchor="w", pady=(14, 4))

    def _build(self):
        T = THEME
        self.panel = tk.Frame(self.app, bg=T["panel"], highlightthickness=2, highlightbackground=T["accent"])
        hd = tk.Frame(self.panel, bg=ui.mix(T["panel"], T["accent"], .25))
        hd.pack(fill="x")
        tk.Label(hd, text="⚙  Быстрые настройки", bg=hd.cget("bg"), fg=T["fg"],
                 font=(ui.FONT, 13, "bold")).pack(side="left", padx=16, pady=12)
        ui.AnimButton(hd, "✕", self.close, kind="ghost", width=34, height=30, bg=hd.cget("bg")).pack(side="right", padx=10)
        sf = ui.ScrollFrame(self.panel, bg=T["panel"], pad=10)
        sf.pack(fill="both", expand=True)
        body = tk.Frame(sf.inner, bg=T["panel"])
        body.pack(fill="x", padx=18, pady=(0, 12))
        self.chips = {}

        # --- графический API
        self._section(body, "ГРАФИЧЕСКИЙ API")
        row = tk.Frame(body, bg=T["panel"])
        row.pack(fill="x")
        for key, name in perf.APIS.items():
            b = ui.AnimButton(row, name, lambda k=key: self.set("api", k), kind="chip", width=138, height=34, bg=T["panel"])
            b.pack(side="left", padx=(0, 6))
            self.chips[("api", key)] = b
        self.hint = ui.label(body, "", 9, dim=True, bg=T["panel"], wraplength=420)
        self.hint.pack(anchor="w", pady=(6, 0))
        self.mesa_row = tk.Frame(body, bg=T["panel"])
        self.mesa_var = tk.StringVar(value=self.cfg()["mesa_dir"])
        self.mesa_var.trace_add("write", lambda *a: self._mesa_changed())
        er = tk.Frame(self.mesa_row, bg=T["panel"])
        er.pack(fill="x", pady=(8, 2))
        ttk.Entry(er, textvariable=self.mesa_var).pack(side="left", fill="x", expand=True)
        ui.AnimButton(er, "Обзор", self._browse_mesa, kind="card", width=70, height=30, bg=T["panel"]).pack(side="left", padx=(6, 0))
        ui.AnimButton(er, "Скачать Mesa", lambda: webbrowser.open(perf.MESA_URL), kind="card", width=120, height=30,
                      bg=T["panel"]).pack(side="left", padx=(6, 0))
        self.mesa_status = ui.label(self.mesa_row, "", 9, bg=T["panel"])
        self.mesa_status.pack(anchor="w")

        # --- видеокарта
        self._section(body, "ВИДЕОКАРТА (WINDOWS)")
        gr = tk.Frame(body, bg=T["panel"])
        gr.pack(fill="x")
        for key, name in perf.GPUS.items():
            b = ui.AnimButton(gr, name, lambda k=key: self.set("gpu", k), kind="chip", width=138, height=34, bg=T["panel"])
            b.pack(side="left", padx=(0, 6))
            self.chips[("gpu", key)] = b
        self.gpu_lbl = ui.label(body, "На ноутбуках выбери «Дискретная» — игра перестанет работать на слабой встроенной.",
                                9, dim=True, bg=T["panel"], wraplength=420)
        self.gpu_lbl.pack(anchor="w", pady=(6, 0))

        # --- запуск
        self._section(body, "ЗАПУСК ИГРЫ")
        self.vars = {}
        for key, text in (("fast_start", "Быстрый старт (кэш классов, Java 19+)"),
                          ("skip_verify", "Пропуск проверки байткода (риск)"),
                          ("pause_anim", "Пауза анимаций во время игры")):
            v = tk.BooleanVar(value=bool(self.cfg().get(key)))
            v.trace_add("write", lambda *a, k=key, v=v: self.set(k, bool(v.get())))
            ui.Switch(body, text, v).pack(anchor="w", pady=4)
            self.vars[key] = v

        # --- ярлыки
        self._section(body, "ЯРЛЫК")
        sr = tk.Frame(body, bg=T["panel"])
        sr.pack(fill="x")
        ui.AnimButton(sr, "Ярлык на рабочий стол", lambda: self._shortcut("desktop"), kind="accent", width=200, height=34,
                      bg=T["panel"]).pack(side="left", padx=(0, 6))
        ui.AnimButton(sr, "В меню Пуск", lambda: self._shortcut("start"), kind="card", width=120, height=34,
                      bg=T["panel"]).pack(side="left")
        self.preview = ui.label(body, "", 9, dim=True, bg=T["panel"], wraplength=420)
        self.preview.pack(anchor="w", pady=(16, 0))
        ui.label(body, "Изменения применяются при следующем запуске игры.", 9, dim=True, bg=T["panel"]).pack(anchor="w", pady=(2, 0))

    # ------------------------------------------------------------ логика
    def refresh(self):
        if self.panel is None:
            return
        cfg = perf.normalize(self.cfg())
        try:
            for (grp, key), b in self.chips.items():
                b.set_selected(cfg[grp] == key)
            self.hint.config(text=API_HINTS[cfg["api"]])
            if cfg["api"] == "opengl":
                self.mesa_row.pack_forget()
            else:
                self.mesa_row.pack(fill="x", after=self.hint)
                ok, msg = perf.mesa_status(cfg)
                self.mesa_status.config(text=("✓ " if ok else "✗ ") + msg, fg=THEME["ok"] if ok else THEME["danger"])
            self.preview.config(text=perf.describe(cfg))
        except tk.TclError:
            pass

    def _mesa_changed(self):
        self.cfg()["mesa_dir"] = self.mesa_var.get().strip().strip('"')
        self.app.store.save()
        self.refresh()

    def _browse_mesa(self):
        d = filedialog.askdirectory(title="Папка Mesa (где лежит opengl32.dll)")
        if d:
            self.mesa_var.set(d)

    def set_gpus(self, names):
        try:
            if names:
                self.gpu_lbl.config(text="Найдено: " + "  •  ".join(names))
            elif not config.IS_WIN:
                self.gpu_lbl.config(text="Выбор видеокарты работает только в Windows.")
        except (tk.TclError, AttributeError):
            pass

    def _shortcut(self, where):
        self.app.toast.show("Создаю ярлык…", "info")

        def work():
            ok, msg = perf.create_shortcut(where)
            self.app.q.put(("toast", msg, "ok" if ok else "err"))
        threading.Thread(target=work, daemon=True).start()
