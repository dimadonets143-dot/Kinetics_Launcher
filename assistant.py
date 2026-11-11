"""Док — встроенный помощник Kinetics: анимированный пёс + мини-чат с готовыми вопросами.
Работает офлайн: понимает вопросы по ключевым словам и отвечает с учётом твоего ПК и профиля."""
import math
import os
import random
import re
import time
import tkinter as tk
from tkinter import ttk

from . import launcher, modrinth, optimizer, system
from . import ui_kit as ui
from .ui_kit import THEME

# ======================================================================= действия (кнопки в ответах)


def _go(page):
    return lambda a: a.show(page)


def _store(kind, query=None):
    def f(a):
        a.show("store")
        if query is not None:
            a.store_q.set(query)
        a._store_set_kind(kind)
    return f


def _skins_dir(a):
    p = a._collect_safe()
    path = os.path.join(launcher.game_dir_for(p), "CustomSkinLoader", "LocalSkin", "skins")
    os.makedirs(path, exist_ok=True)
    a._open(path)
    a.toast.show(f"Положи сюда файл {p['username']}.png", "info")


def _log(a):
    a.show("play")
    a.log_open = True
    a._layout_play()


def _verify(a):
    p = a._save()
    if p["version"] and not a.busy:
        a.show("play")
        a._run(p, True, True)


ACTIONS = {
    "auto": ("Применить авто-оптимизацию", lambda a: (a.show("optim"), a._auto_opt())),
    "to_optim": ("Открыть «Оптимизация»", _go("optim")),
    "pack": ("Открыть набор FPS", _store("opt")),
    "mods_store": ("Магазин модов", _store("mod", "")),
    "shaders_store": ("Магазин шейдеров", _store("shader", "")),
    "iris": ("Установить Iris + Sodium", lambda a: a._install_iris()),
    "csl": ("Найти CustomSkinLoader", _store("mod", "CustomSkinLoader")),
    "skins_dir": ("Открыть папку скинов", _skins_dir),
    "installed": ("Установленные файлы", _store("installed")),
    "versions": ("Открыть «Версии»", _go("versions")),
    "game_dir": ("Открыть папку игры", lambda a: a._open_game_dir()),
    "mods_dir": ("Открыть папку mods", lambda a: a._open_sub("mods")),
    "saves_dir": ("Открыть папку миров", lambda a: a._open_sub("saves")),
    "log": ("Открыть журнал", _log),
    "verify": ("Проверить файлы версии", _verify),
    "diag": ("Диагностика ПК", lambda a: a._diag()),
    "theme": ("Открыть «Внешний вид»", _go("settings")),
    "profile": ("Открыть «Профиль»", _go("profile")),
}

# ======================================================================= ответы


def a_about(a):
    return ("Kinetics — лёгкий лаунчер Minecraft на Python.\n\n"
            "• качает игру с официальных серверов Mojang\n"
            "• Vanilla и Fabric: релизы, снапшоты, беты и альфы\n"
            "• магазин модов, шейдеров и ресурспаков (Modrinth)\n"
            "• авто-оптимизация под твой ПК\n"
            "• профили, 8 тем и свой дизайн шапки\n\n"
            "Работает в оффлайн-режиме: ник любой, но лицензионные серверы и официальные скины недоступны.",
            ["versions", "theme"])


def a_optimize(a):
    ram, cores = system.total_ram_mb(), system.cpu_cores()
    r = optimizer.recommend()
    return (f"У тебя {ram / 1024:.1f} ГБ ОЗУ и {cores} яд. Вот что даёт больше всего FPS:\n\n"
            f"1. Нажми «Авто под мой ПК» — я выставлю память (до {r['ram_max']} МБ), JVM-флаги и графику.\n"
            "2. Выбери загрузчик Fabric и поставь «Набор FPS» в магазине (Sodium, Lithium, FerriteCore…). "
            "Это самый большой прирост.\n"
            "3. Снизь дальность прорисовки до 8–10 чанков (вкладка «Графика»).\n"
            "4. Не давай игре больше ~60% ОЗУ — иначе будут лаги.\n"
            "5. Закрой браузер и тяжёлые программы перед игрой.",
            ["auto", "pack", "to_optim"])


def a_skin(a):
    nick = a._collect_safe().get("username") or "Nick"
    return ("В оффлайн-режиме Mojang не отдаёт скины по нику, поэтому нужен мод. Самый простой путь:\n\n"
            "1. На странице «Версии» выбери загрузчик Fabric.\n"
            "2. Установи мод CustomSkinLoader (кнопка ниже).\n"
            "3. Скачай скин в формате PNG (сайты вроде NameMC или minecraftskins.com).\n"
            f"4. Назови файл «{nick}.png» и положи в папку CustomSkinLoader/LocalSkin/skins внутри "
            "папки игры — кнопка ниже откроет её.\n\n"
            "Если мод не находится — для твоей версии Minecraft его пока нет, попробуй другую версию. "
            "Свой скин увидишь ты; на серверах другие игроки его не увидят.",
            ["csl", "skins_dir"])


def a_mods(a):
    return ("Моды ставятся так:\n\n"
            "1. «Версии» → выбери версию и загрузчик Fabric.\n"
            "2. «Магазин» → «Моды» → найди мод и нажми «Установить». Нужные зависимости скачаются сами.\n"
            "3. Свои моды: кнопка «+ Свой файл» или просто положи .jar в папку mods.\n\n"
            "Мод должен подходить под твою версию игры — магазин показывает только подходящие.",
            ["mods_store", "mods_dir", "installed"])


def a_shaders(a):
    return ("Для шейдеров нужны Fabric + Iris + Sodium.\n\n"
            "1. Выбери Fabric на странице «Версии».\n"
            "2. Нажми «Установить Iris + Sodium».\n"
            "3. В магазине открой «Шейдеры», скачай понравившийся пак, во вкладке «Установлено» нажми «Применить».\n"
            "4. В игре: Настройки → Настройки видео → Шейдеры.\n\n"
            "Шейдеры сильно нагружают видеокарту — на слабом ПК лучше без них.",
            ["iris", "shaders_store", "installed"])


def a_delete(a):
    return ("Удаление:\n\n"
            "• Версию: на главном экране красная кнопка «Удалить» у нужной версии (миры и моды останутся).\n"
            "• Мод, шейдер или ресурспак: «Магазин» → «Установлено» → «Удалить». "
            "Мод можно просто «Отключить» — файл останется.\n"
            "• Мир: открой папку миров и удали нужную папку внутри saves.",
            ["installed", "saves_dir"])


def a_folder(a):
    p = a._collect_safe()
    path = p.get("game_dir") or os.path.join("data", "instances", launcher.safe_name(p["name"]))
    return (f"Папка игры твоего профиля: {path}\n\n"
            "Внутри: mods — моды, saves — миры, shaderpacks — шейдеры, resourcepacks — ресурспаки, "
            "options.txt — настройки игры.\n\n"
            "Открыть её можно кнопкой «Папка игры» на главном экране.",
            ["game_dir", "mods_dir", "saves_dir"])


def a_fail(a):
    return ("Если игра не запускается:\n\n"
            "1. Открой «Журнал» — в конце будет причина (ищи строки с ERROR).\n"
            "2. Нажми «Проверить файлы версии» — докачаю недостающее.\n"
            "3. Для модов нужен Fabric и версия мода под твою версию игры; отключи недавно поставленный мод.\n"
            "4. Не ставь память больше ~60% ОЗУ.\n"
            "5. Лаунчер сам подбирает Java, но можно скачать вручную в «Оптимизация».\n"
            "6. Настройки → «Очистить кэш».",
            ["log", "verify", "diag"])


def a_friends(a):
    return ("Играть с друзьями в оффлайн-режиме можно так:\n\n"
            "• по локальной сети: в одиночной игре нажми Esc → «Открыть для сети», друг подключается по адресу, "
            "который покажет игра;\n"
            "• на сервере с online-mode=false (оффлайн-серверы);\n"
            "• у всех должна быть одна и та же версия игры, у каждого — свой ник.\n\n"
            "Серверы с лицензионной проверкой пустят только с купленным аккаунтом.",
            ["versions", "profile"])


def a_theme(a):
    return ("Оформление меняется во вкладке «Внешний вид»: 8 тем (есть светлые), любой акцентный цвет, "
            "шрифт, фон шапки — градиент, частицы или твоя картинка, а также анимации можно выключить.",
            ["theme"])


def a_nick(a):
    return ("Ник меняется прямо в шапке главного экрана или во вкладке «Профиль». "
            "Нужно 3–16 символов: латиница, цифры и «_».\n\n"
            "Важно: у ника в оффлайне свой идентификатор, поэтому на серверах при смене ника инвентарь будет новый. "
            "В одиночной игре мир сохраняется.",
            ["profile"])


def a_java(a):
    return ("Java подбирается автоматически под версию игры: 8 — старые версии, 17 — 1.17–1.20.4, "
            "21 — 1.20.5 и новее. Если нужной нет, я скачаю её сам при запуске.\n\n"
            "Вручную: «Оптимизация» → «Скачать Java 8/17/21» или «Найти».",
            ["to_optim", "diag"])


def a_ram(a):
    ram = system.total_ram_mb()
    r = optimizer.recommend()
    return (f"У тебя {ram / 1024:.1f} ГБ ОЗУ. Я бы поставил максимум {r['ram_max'] / 1024:.1f} ГБ "
            f"(минимум {r['ram_min'] / 1024:.1f} ГБ).\n\n"
            "Для ванильной игры хватает 2–4 ГБ, для больших сборок модов 6–8 ГБ. "
            "Слишком много — не лучше: сборщик мусора начнёт тормозить.",
            ["auto", "to_optim"])


def a_fabric(a):
    return ("Fabric — лёгкий загрузчик модов. Он нужен для модов оптимизации (Sodium, Lithium…), шейдеров "
            "(Iris) и скинов. Выбирается на странице «Версии» справа: Vanilla или Fabric. "
            "Файлы Fabric скачаются сами при первом запуске.",
            ["versions", "mods_store"])


ENTRIES = [
    {"id": "about", "q": "Что это за лаунчер?", "fn": a_about,
     "kw": ["лаунчер", "что это", "что за", "кто ты", "kinetics", "кинетикс", "что умеет", "для чего", "зачем"]},
    {"id": "skin", "q": "Как скачать скин?", "fn": a_skin, "kw": ["скин", "skin", "плащ", "cape"]},
    {"id": "optimize", "q": "Как повысить оптимизацию?", "fn": a_optimize,
     "kw": ["оптимиз", "fps", "фпс", "лаг", "тормоз", "быстр", "производит", "ускор", "фриз", "кадров"]},
    {"id": "fail", "q": "Игра не запускается", "fn": a_fail,
     "kw": ["не запуск", "не работает", "ошибк", "вылет", "краш", "crash", "закрывается", "не открывается",
            "черный экран", "чёрный экран", "баг"]},
    {"id": "delete", "q": "Удалить версию или мод?", "fn": a_delete,
     "kw": ["удал", "стереть", "убрать", "снести", "деинстал"]},
    {"id": "shaders", "q": "Как включить шейдеры?", "fn": a_shaders, "kw": ["шейдер", "shader", "iris", "ирис"]},
    {"id": "mods", "q": "Как установить моды?", "fn": a_mods, "kw": ["мод", "mod", "скачать мод", "установить мод"]},
    {"id": "folder", "q": "Где папка с игрой?", "fn": a_folder,
     "kw": ["папк", "где игра", "где лежит", "где файл", "мир", "сохранени", "saves"]},
    {"id": "friends", "q": "Как играть с друзьями?", "fn": a_friends,
     "kw": ["друз", "сервер", "сетев", "lan", "вместе", "мультиплеер", "онлайн"]},
    {"id": "theme", "q": "Как сменить тему?", "fn": a_theme,
     "kw": ["тем", "дизайн", "цвет", "оформл", "внешн", "шрифт", "фон", "картинк"]},
    {"id": "nick", "q": "Как сменить ник?", "fn": a_nick, "kw": ["ник", "имя", "uuid"]},
    {"id": "java", "q": "Какая Java нужна?", "fn": a_java, "kw": ["java", "джава", "жава"]},
    {"id": "ram", "q": "Сколько памяти ставить?", "fn": a_ram, "kw": ["памят", "ram", "озу", "оператив", "гб"]},
    {"id": "fabric", "q": "Что такое Fabric?", "fn": a_fabric, "kw": ["fabric", "фабрик", "загрузчик"]},
]
BY_ID = {e["id"]: e for e in ENTRIES}
PAGES = [["about", "optimize", "skin", "mods", "shaders", "delete", "folder"],
         ["fail", "friends", "theme", "nick", "java", "ram", "fabric"]]


def match(text):
    t = text.lower().replace("ё", "е")
    best, score = None, 0
    for e in ENTRIES:
        s = sum(1 for kw in e["kw"] if re.search(r"(?<!\w)" + re.escape(kw.replace("ё", "е")), t))
        if s > score:
            best, score = e, s
    return best


def _raise(w):
    """У Canvas методы lift/tkraise — это tag_raise, поэтому поднимаем виджет вручную."""
    w.tk.call("raise", w._w)


# ======================================================================= пёс
class Dog(tk.Canvas):
    def __init__(self, parent, size=88, bg=None, command=None, on_hover=None):
        self.k = size / 88.0
        self.size = size
        super().__init__(parent, width=size, height=size, bg=bg or ui.bg_of(parent),
                         highlightthickness=0, bd=0, cursor="hand2" if command else "arrow")
        self.command, self.on_hover = command, on_hover
        self.t = random.random() * 6
        self.hover, self.hover_to = 0.0, 0.0
        self.jump = 0.0
        self.happy = False
        self.next_blink, self.blink_until = time.time() + 2, 0.0
        self.alive = True
        if command:
            self.bind("<Enter>", lambda e: self._hov(1))
            self.bind("<Leave>", lambda e: self._hov(0))
            self.bind("<Button-1>", lambda e: (self.bark(), command()))
        self._draw()
        self.after(40, self._tick)

    def _hov(self, v):
        self.hover_to = v
        if v:
            self.bark()
        if self.on_hover:
            self.on_hover(v)

    def bark(self):
        if self.jump <= 0:
            self.jump = 0.001

    def set_happy(self, b):
        self.happy = b

    def _tick(self):
        if not self.alive:
            return
        try:
            if ui.ANIM["on"] and not ui.STATE["paused"] and self.winfo_viewable():
                self.t += 0.07
                self.hover += (self.hover_to - self.hover) * 0.25
                if self.jump > 0:
                    self.jump += 0.07
                    if self.jump >= 1:
                        self.jump = 0
                now = time.time()
                if now > self.next_blink:
                    self.blink_until = now + 0.14
                    self.next_blink = now + random.uniform(2.0, 5.0)
                self._draw()
            self.after(40, self._tick)
        except tk.TclError:
            self.alive = False

    def destroy(self):
        self.alive = False
        super().destroy()

    def _draw(self):
        k, t, T, hov = self.k, self.t, THEME, self.hover
        self.delete("all")
        bob = math.sin(t * 2.2) * 1.0
        jump = -7 * math.sin(self.jump * math.pi) if self.jump > 0 else 0
        hb = bob + jump
        tan, dark, cream, nose = "#dca468", "#9b6a3c", "#f7e9d3", "#2a2019"

        def ov(a, b, c, d, fill, off=0.0, **kw):
            self.create_oval(a * k, (b + off) * k, c * k, (d + off) * k, fill=fill, outline=kw.pop("outline", ""), **kw)

        def pl(pts, fill, off=0.0, **kw):
            flat = []
            for x, y in pts:
                flat += [x * k, (y + off) * k]
            self.create_polygon(flat, fill=fill, outline="", **kw)

        s = self.size
        ring = ui.mix(T["card"], T["accent"], .22 + .22 * hov)
        self.create_oval(1, 1, s - 1, s - 1, fill=ring, outline=T["accent"], width=2)
        # хвост
        wag = 14 if self.happy else (11 if hov > .3 else 6)
        sw = math.sin(t * wag * .55)
        pts = [58 * k, (70 + bob * .5) * k, (65 + 3 * sw) * k, 63 * k, (72 + 6 * sw) * k, (56 - 3 * abs(sw)) * k]
        self.create_line(*pts, fill=tan, width=7 * k, smooth=True, capstyle="round")
        # тело
        ov(30, 58, 58, 82, tan, bob * .5)
        ov(38, 62, 50, 80, cream, bob * .5)
        ov(33, 76, 43, 83, cream, bob * .3)
        ov(45, 76, 55, 83, cream, bob * .3)
        # ошейник
        self.create_rectangle(34 * k, (59 + hb * .6) * k, 54 * k, (63 + hb * .6) * k, fill="#e5484d", outline="")
        ov(41, 63, 47, 69, "#fbbf24", hb * .6)
        # уши
        ew = math.sin(t * 3) * 1.5 + 2.5 * hov + (2 if self.happy else 0)
        pl([(25, 26), (16, 36 + ew), (19, 52 + ew), (30, 46), (31, 30)], dark, hb, smooth=True)
        pl([(63, 26), (72, 36 + ew), (69, 52 + ew), (58, 46), (57, 30)], dark, hb, smooth=True)
        # голова и морда
        ov(24, 22, 64, 62, tan, hb)
        ov(32, 41, 56, 60, cream, hb)
        ov(40, 43, 48, 49, nose, hb)
        self.create_line(44 * k, (49 + hb) * k, 44 * k, (52 + hb) * k, fill=nose, width=max(1, k * 1.4))
        self.create_arc(37 * k, (48 + hb) * k, 44 * k, (56 + hb) * k, start=200, extent=140, style="arc",
                        outline=nose, width=max(1, k * 1.4))
        self.create_arc(44 * k, (48 + hb) * k, 51 * k, (56 + hb) * k, start=200, extent=140, style="arc",
                        outline=nose, width=max(1, k * 1.4))
        if hov > .3 or self.happy or (math.sin(t * .7) > .55):
            ln = 3 + 3 * (math.sin(t * 6) + 1) / 2
            ov(41, 52.5, 47, 52.5 + ln, "#f2788f", hb)
        # глаза
        blink = time.time() < self.blink_until
        er = 3.2 + 0.5 * hov
        for ex in (35, 53):
            if blink:
                self.create_line((ex - 3) * k, (36 + hb) * k, (ex + 3) * k, (36 + hb) * k, fill=nose, width=max(1, 1.6 * k))
            else:
                ov(ex - er, 36 - er, ex + er, 36 + er, nose, hb)
                ov(ex - 1.6, 34.2, ex - .2, 35.6, "#ffffff", hb)
        if hov > .3:
            self.create_line(31 * k, (29 + hb) * k, 38 * k, (27.5 + hb) * k, fill=dark, width=max(1, 1.6 * k))
            self.create_line(50 * k, (27.5 + hb) * k, 57 * k, (29 + hb) * k, fill=dark, width=max(1, 1.6 * k))

    def refresh(self):
        self.config(bg=ui.bg_of(self.master))
        self._draw()


# ======================================================================= чат
class Chat(tk.Frame):
    W = 430

    def __init__(self, app, doc):
        super().__init__(app, bg=THEME["panel"], highlightthickness=2, highlightbackground=THEME["accent"])
        self.app, self.doc = app, doc
        self.page = 0
        self.busy = False
        hd = tk.Frame(self, bg=ui.mix(THEME["panel"], THEME["accent"], .28))
        hd.pack(fill="x")
        self.avatar = Dog(hd, 46, bg=hd.cget("bg"))
        self.avatar.pack(side="left", padx=(12, 8), pady=8)
        col = tk.Frame(hd, bg=hd.cget("bg"))
        col.pack(side="left")
        tk.Label(col, text="Док", bg=hd.cget("bg"), fg=THEME["fg"], font=(ui.FONT, 13, "bold")).pack(anchor="w")
        tk.Label(col, text="встроенный помощник · работает офлайн", bg=hd.cget("bg"), fg=THEME["dim"],
                 font=(ui.FONT, 8)).pack(anchor="w")
        x = ui.AnimButton(hd, "✕", doc.toggle, kind="ghost", width=34, height=30, bg=hd.cget("bg"))
        x.pack(side="right", padx=10)
        self.msgs = ui.ScrollFrame(self, bg=THEME["panel"], pad=8)
        self.msgs.pack(fill="both", expand=True, pady=(6, 0))
        self.chips = tk.Frame(self, bg=THEME["panel"])
        self.chips.pack(fill="x", padx=10, pady=(4, 4))
        inp = tk.Frame(self, bg=THEME["panel"])
        inp.pack(fill="x", padx=10, pady=(0, 10))
        self.var = tk.StringVar()
        e = ttk.Entry(inp, textvariable=self.var)
        e.pack(side="left", fill="x", expand=True, ipady=3)
        e.bind("<Return>", lambda ev: self.submit())
        ui.AnimButton(inp, "➤", self.submit, kind="accent", width=44, height=32, bg=THEME["panel"]).pack(side="left", padx=(8, 0))
        self.entry = e
        self._chips()
        for h in app.doc_history:
            self._render(h["who"], h["text"], h.get("actions", []), animate=False)
        if not app.doc_history:
            self._say("Гав! Я Док — встроенный помощник Kinetics. Выбери вопрос ниже или напиши свой.", [], first=True)

    # ---- плашки
    def _chips(self):
        for w in self.chips.winfo_children():
            w.destroy()
        ids = PAGES[self.page]
        items = [(BY_ID[i]["q"], (lambda i=i: self.ask(i))) for i in ids]
        items.append(("Ещё вопросы ›" if self.page == 0 else "‹ Назад", self._flip))
        for n, (text, cmd) in enumerate(items):
            b = ui.AnimButton(self.chips, text, cmd, kind="chip" if n < len(items) - 1 else "ghost",
                              width=196, height=30, font=(ui.FONT, 8), radius=9, bg=THEME["panel"])
            b.grid(row=n // 2, column=n % 2, padx=3, pady=3, sticky="ew")
        self.chips.columnconfigure((0, 1), weight=1)

    def _flip(self):
        self.page = 1 - self.page
        self._chips()

    # ---- сообщения
    def _bottom(self):
        try:
            self.msgs.canvas.update_idletasks()
            self.msgs.canvas.yview_moveto(1.0)
        except tk.TclError:
            pass

    def _render(self, who, text, actions, animate=True, done=None):
        row = tk.Frame(self.msgs.inner, bg=THEME["panel"])
        row.pack(fill="x", padx=10, pady=4)
        if who == "user":
            tk.Label(row, text=text, bg=THEME["accent"], fg="#ffffff", wraplength=250, justify="left",
                     padx=12, pady=8, font=(ui.FONT, 10)).pack(side="right")
            self._bottom()
            return
        col = tk.Frame(row, bg=THEME["panel"])
        col.pack(side="left")
        lbl = tk.Label(col, text="" if animate else text, bg=THEME["card"], fg=THEME["fg"], wraplength=320,
                       justify="left", anchor="w", padx=12, pady=9, font=(ui.FONT, 10))
        lbl.pack(anchor="w")

        def finish():
            if actions:
                af = tk.Frame(col, bg=THEME["panel"])
                af.pack(anchor="w", pady=(4, 0))
                for aid in actions:
                    label, fn = ACTIONS[aid]
                    ui.AnimButton(af, label, lambda fn=fn: fn(self.app), kind="accent", width=min(330, 44 + 8 * len(label)),
                                  height=30, font=(ui.FONT, 9, "bold"), radius=9, bg=THEME["panel"]).pack(anchor="w", pady=2)
            self._bottom()
            if done:
                done()
        if not animate or not ui.ANIM["on"]:
            lbl.config(text=text)
            finish()
            return
        i = [0]

        def step():
            try:
                i[0] += 5
                lbl.config(text=text[:i[0]])
                if i[0] % 20 == 0:
                    self._bottom()
                if i[0] < len(text):
                    lbl.after(12, step)
                else:
                    lbl.config(text=text)
                    finish()
            except tk.TclError:
                pass
        step()

    def _say(self, text, actions, first=False):
        self.app.doc_history.append({"who": "doc", "text": text, "actions": actions})
        self.busy = True
        self.doc.dog.set_happy(True)

        def done():
            self.busy = False
            self.doc.dog.set_happy(False)
        self._render("doc", text, actions, animate=True, done=done)

    def _think_then(self, fn):
        row = tk.Frame(self.msgs.inner, bg=THEME["panel"])
        row.pack(fill="x", padx=10, pady=4)
        lbl = tk.Label(row, text="Док думает", bg=THEME["card"], fg=THEME["dim"], padx=12, pady=8, font=(ui.FONT, 10))
        lbl.pack(side="left")
        self._bottom()
        n = [0]
        total = random.randint(7, 12) if ui.ANIM["on"] else 0

        def tick():
            try:
                n[0] += 1
                if n[0] > total:
                    row.destroy()
                    fn()
                    return
                lbl.config(text="Док думает" + "." * (n[0] % 4))
                lbl.after(80, tick)
            except tk.TclError:
                pass
        tick()

    def _user_msg(self, text):
        self.app.doc_history.append({"who": "user", "text": text})
        self._render("user", text, [], animate=False)

    def ask(self, eid):
        if self.busy:
            return
        e = BY_ID[eid]
        self._user_msg(e["q"])
        self._reply(e)

    def _reply(self, e):
        def go():
            text, acts = e["fn"](self.app)
            self._say(text, acts)
        self._think_then(go)

    def submit(self):
        if self.busy:
            return
        text = self.var.get().strip()
        if not text:
            return
        self.var.set("")
        self._user_msg(text)
        e = match(text)
        if e:
            self._reply(e)
        else:
            self._think_then(lambda: self._say(
                "Хм, не совсем понял. Я знаю про оптимизацию, моды, шейдеры, скины, версии, папки и запуск. "
                "Выбери вопрос ниже или спроси другими словами.", []))


# ======================================================================= виджет целиком
class Doc:
    def __init__(self, app):
        self.app = app
        self.open = False
        self.tip = None
        self._tip_job = None
        self.dog = Dog(app, 88, bg=THEME["bg"], command=self.toggle, on_hover=self._hover)
        self.dog.place(relx=1.0, rely=1.0, anchor="se", x=-18, y=-16)
        self.chat = None
        _raise(self.dog)
        app.after(4000, self._first_tip)

    def _hover(self, v):
        if v and not self.open:
            self.say_tip("Гав! Спроси меня", 2200)

    def _first_tip(self):
        if not self.open and not getattr(self.app, "_doc_tip_shown", False):
            self.app._doc_tip_shown = True
            self.say_tip("Нужна помощь? Нажми на меня!", 5000)

    def say_tip(self, text, ms):
        self.hide_tip()
        try:
            self.tip = tk.Label(self.app, text=text, bg=THEME["card"], fg=THEME["fg"], font=(ui.FONT, 10, "bold"),
                                padx=12, pady=7, highlightthickness=1, highlightbackground=THEME["accent"])
            self.tip.place(relx=1.0, rely=1.0, anchor="se", x=-114, y=-44)
            self._tip_job = self.app.after(ms, self.hide_tip)
        except tk.TclError:
            pass

    def hide_tip(self):
        if self._tip_job:
            try:
                self.app.after_cancel(self._tip_job)
            except Exception:
                pass
            self._tip_job = None
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None

    def toggle(self):
        self.hide_tip()
        if self.open:
            self.open = False
            self.dog.set_happy(False)
            ch = self.chat
            ui.tween(ch, "slide", 200, lambda t: ch.place_configure(y=-116 + 30 * t), done=ch.place_forget)
            return
        self.open = True
        if self.chat is None or not self.chat.winfo_exists():
            self.chat = Chat(self.app, self)
        h = max(380, min(570, self.app.winfo_height() - 140))
        ch = self.chat
        ch.place(relx=1.0, rely=1.0, anchor="se", x=-18, y=-86, width=Chat.W, height=h)
        _raise(ch)
        _raise(self.dog)
        ui.tween(ch, "slide", 260, lambda t: ch.place_configure(y=-86 - 30 * t))
        self.dog.set_happy(True)
        self.app.after(1500, lambda: self.dog.set_happy(False) if not (self.chat and self.chat.busy) else None)

    def destroy(self):
        self.hide_tip()
        for w in (self.dog, self.chat):
            try:
                if w is not None:
                    w.destroy()
            except tk.TclError:
                pass
