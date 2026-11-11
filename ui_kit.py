"""Мини-UI-кит на tkinter: анимированные кнопки, сайдбар, переключатели, прогресс, частицы."""
import math
import random
import time
import tkinter as tk
from tkinter import ttk

FONT = "Segoe UI"
def _t(bg, panel, card, field, accent, fg="#eceef6", dim="#8d93a8", light=0, hero_mix=.42, line="#2a2f40"):
    return {"bg": bg, "panel": panel, "card": card, "field": field, "fg": fg, "dim": dim,
            "accent": accent, "ok": "#34d399" if not light else "#10b981",
            "danger": "#f87171" if not light else "#ef4444", "line": line,
            "hero_fg": "#ffffff", "hero_mix": hero_mix, "light": light}


THEMES = {
    "Полночь": _t("#0e1016", "#141720", "#1b1f2b", "#252a3a", "#7c5cff"),
    "Океан": _t("#08121a", "#0d1b26", "#12273a", "#1b364d", "#38bdf8", line="#1f3a52"),
    "Лес": _t("#0b130e", "#101c14", "#162619", "#213726", "#34d399", line="#233a29"),
    "Закат": _t("#170d12", "#1f1118", "#2a1620", "#3a1f2c", "#fb7185", line="#44232f"),
    "Сакура": _t("#160e18", "#1e1322", "#291a2e", "#3a2540", "#f472b6", line="#43294a"),
    "Графит": _t("#111111", "#171717", "#202020", "#2b2b2b", "#fbbf24", line="#333333"),
    "Лаванда ☀": _t("#eef0f7", "#e2e5f1", "#ffffff", "#e8eaf4", "#6d4aff", fg="#1c2030", dim="#68708f",
                    light=1, hero_mix=.62, line="#d5d9e8"),
    "Мята ☀": _t("#edf5f1", "#dfece6", "#ffffff", "#e5f0ea", "#0f9f76", fg="#14231d", dim="#5d7a6d",
                 light=1, hero_mix=.62, line="#cfe0d7"),
}
THEME = dict(THEMES["Полночь"])
THEME["accent2"] = "#38bdf8"


def apply_theme(name, accent=None):
    t = THEMES.get(name, THEMES["Полночь"])
    THEME.update(t)
    if accent:
        THEME["accent"] = accent
    THEME["accent2"] = mix(THEME["accent"], "#0ea5e9" if THEME["light"] else "#38bdf8", .5)


ANIM = {"on": True}
STATE = {"paused": False}  # True, пока идёт игра — лаунчер не тратит CPU на анимации
_registry = []


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(x + (y - x) * t))) for x, y in zip(ra, rb))


def ease(t):
    return 1 - (1 - t) ** 3


def register(w):
    _registry.append(w)


def refresh_all():
    for w in list(_registry):
        try:
            w.refresh()
        except tk.TclError:
            _registry.remove(w)


def tween(w, key, ms, fn, done=None):
    """Плавная анимация 0..1 с отменой предыдущей по ключу."""
    tokens = w.__dict__.setdefault("_tw", {})
    tok = tokens[key] = tokens.get(key, 0) + 1
    if not ANIM["on"] or ms <= 0:
        fn(1.0)
        if done:
            done()
        return
    t0 = time.time()

    def tick():
        if tokens.get(key) != tok:
            return
        try:
            t = min(1.0, (time.time() - t0) * 1000 / ms)
            fn(ease(t))
            if t < 1:
                w.after(15, tick)
            elif done:
                done()
        except tk.TclError:
            pass
    tick()


def bg_of(w):
    try:
        return w.cget("bg")
    except tk.TclError:
        return THEME["bg"]


def round_rect(c, x1, y1, x2, y2, r, **kw):
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


import tkinter.font as tkfont  # noqa: E402

_fcache = {}


def get_font(size, weight="bold", slant="roman", family=None):
    key = (family or FONT, size, weight, slant)
    if key not in _fcache:
        _fcache[key] = tkfont.Font(family=family or FONT, size=size, weight=weight, slant=slant)
    return _fcache[key]


def logo_mark(c, x, y, s, tag="logo"):
    """Знак: скруглённый квадрат с буквой K и линиями скорости."""
    def poly(pts, **kw):
        flat = []
        for i, (px, py) in enumerate(pts):
            flat += [x + px * s, y + py * s]
        c.create_polygon(flat, tags=tag, **kw)
    a = THEME["accent"]
    round_rect(c, x, y, x + s, y + s, s * .3, fill=a, outline="", tags=tag)
    round_rect(c, x + s * .05, y + s * .05, x + s * .95, y + s * .52, s * .25,
               fill=mix(a, "#ffffff", .16), outline="", tags=tag)
    round_rect(c, x, y + s * .5, x + s, y + s, s * .3, fill=a, outline="", tags=tag)
    white = "#ffffff"
    poly([(.30, .22), (.41, .22), (.41, .78), (.30, .78)], fill=white, outline="")
    poly([(.41, .52), (.63, .22), (.77, .22), (.52, .58)], fill=white, outline="")
    poly([(.47, .50), (.77, .78), (.62, .78), (.41, .58)], fill=white, outline="")
    for yy, x0 in ((.38, .12), (.50, .05), (.62, .14)):
        c.create_line(x + x0 * s, y + yy * s, x + .22 * s, y + yy * s, fill=mix(white, a, .45),
                      width=max(2, s * .05), capstyle="round", tags=tag)


def wordmark(c, x, y, size, tag="logo", c1=None, c2=None):
    """Косой логотип KINETICS: градиент по буквам + хвост из линий скорости.
    Возвращает [(id, цвет)] для анимации блика."""
    f = get_font(-size, "bold", "italic")
    c1, c2 = c1 or THEME["accent"], c2 or THEME["accent2"]
    word, items, cx = "KINETICS", [], x
    for i, ch in enumerate(word):
        col = mix(c1, c2, i / (len(word) - 1))
        items.append((c.create_text(cx, y, text=ch, anchor="w", font=f, fill=col, tags=tag), col))
        cx += f.measure(ch) + size * .09
    for j, ln in enumerate((size * 1.0, size * .66, size * .36)):
        yy = y + size * .70 + j * size * .12
        c.create_line(cx - ln, yy, cx, yy, fill=mix(c2, THEME["bg"], j * .25), width=max(2, size * .06),
                      capstyle="round", tags=tag)
    return items, cx


# ------------------------------------------------------------------ текст
def label(parent, text="", size=10, bold=False, dim=False, **kw):
    kw.setdefault("bg", bg_of(parent))
    kw.setdefault("fg", THEME["dim"] if dim else THEME["fg"])
    kw.setdefault("anchor", "w")
    kw.setdefault("justify", "left")
    return tk.Label(parent, text=text, font=(FONT, size, "bold" if bold else "normal"), **kw)


def card(parent, **kw):
    return tk.Frame(parent, bg=THEME["card"], **kw)


# ------------------------------------------------------------------ кнопка
class AnimButton(tk.Canvas):
    def __init__(self, parent, text="", command=None, kind="card", width=130, height=36,
                 font=None, radius=10, pulse=False, bg=None):
        self.pbg = bg or bg_of(parent)
        super().__init__(parent, width=width, height=height, bg=self.pbg, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.text, self.command, self.kind, self.radius = text, command, kind, radius
        self.selected = False
        self.disabled = False
        self.font = font or (FONT, 10, "bold")
        self._hover = 0.0
        self._press = False
        self._phase = 0.0
        self._pulse = pulse
        self.bind("<Enter>", lambda e: self._h(1))
        self.bind("<Leave>", lambda e: self._h(0))
        self.bind("<ButtonPress-1>", self._down)
        self.bind("<ButtonRelease-1>", self._up)
        self.bind("<Configure>", lambda e: self._draw())
        register(self)
        self._draw()
        if pulse:
            self.after(400, self._pulse_tick)

    def set_text(self, t):
        self.text = t
        self._draw()

    def set_selected(self, s):
        self.selected = s
        self._draw()

    def set_disabled(self, d):
        self.disabled = d
        self.config(cursor="arrow" if d else "hand2")
        self._draw()

    def refresh(self):
        self._draw()

    def _h(self, to):
        if self.disabled:
            to = 0
        start = self._hover
        tween(self, "h", 140, lambda t: self._set_h(start + (to - start) * t))

    def _set_h(self, v):
        self._hover = v
        self._draw()

    def _down(self, e):
        if not self.disabled:
            self._press = True
            self._draw()

    def _up(self, e):
        was = self._press
        self._press = False
        self._draw()
        if was and not self.disabled and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            if self.command:
                self.command()

    def _pulse_tick(self):
        try:
            if self._pulse and ANIM["on"] and not STATE["paused"] and self.winfo_viewable() and not self.disabled:
                self._phase += 0.12
                self._draw()
            self.after(45, self._pulse_tick)
        except tk.TclError:
            pass

    def _colors(self):
        T = THEME
        k = self.kind
        if k == "accent":
            base = mix(T["accent"], "#000000", .22) if T["light"] else T["accent"]
            hov, fg = mix(base, "#ffffff", .2), "#ffffff"
        elif k == "chip":
            if self.selected:
                base, hov, fg = T["accent"], mix(T["accent"], "#ffffff", .12), "#ffffff"
            else:
                cb = T["field"] if self.pbg == T["card"] else T["card"]
                base, hov, fg = cb, mix(cb, T["accent"], .3), T["fg"]
        elif k == "danger":
            base, hov, fg = mix(T["danger"], T["bg"], .35 if T["light"] else .7), T["danger"], "#ffffff"
        elif k == "ghost":
            base, hov, fg = self.pbg, mix(self.pbg, T["accent"], .22), T["fg"]
        else:
            base, hov, fg = T["field"], mix(T["field"], T["accent"], .35), T["fg"]
        if self.disabled:
            base, fg = mix(base, T["bg"], .5), T["dim"]
            hov = base
        col = mix(base, hov, self._hover)
        if self._press:
            col = mix(col, "#000000", .18)
        return col, fg

    def _draw(self):
        try:
            w = self.winfo_width()
            h = self.winfo_height()
        except tk.TclError:
            return
        if w < 4:
            w, h = int(self["width"]), int(self["height"])
        self.delete("all")
        col, fg = self._colors()
        if self._pulse and ANIM["on"] and not self.disabled:
            g = (math.sin(self._phase) + 1) / 2
            round_rect(self, 0, 0, w, h, self.radius + 2, fill=mix(self.pbg, THEME["accent"], .25 * g), outline="")
            round_rect(self, 3, 3, w - 3, h - 3, self.radius, fill=col, outline="")
        else:
            round_rect(self, 1, 1, w - 1, h - 1, self.radius, fill=col, outline="")
        self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=self.font)


# ------------------------------------------------------------------ переключатель
class Switch(tk.Frame):
    def __init__(self, parent, text, variable, command=None):
        bg = bg_of(parent)
        super().__init__(parent, bg=bg)
        self.var, self.command, self.bg = variable, command, bg
        self.c = tk.Canvas(self, width=42, height=22, bg=bg, highlightthickness=0, cursor="hand2")
        self.c.pack(side="left")
        self.lbl = tk.Label(self, text=text, bg=bg, fg=THEME["fg"], font=(FONT, 10), cursor="hand2")
        self.lbl.pack(side="left", padx=8)
        try:
            self.pos = 1.0 if variable.get() else 0.0
        except tk.TclError:
            self.pos = 0.0
        for w in (self.c, self.lbl):
            w.bind("<Button-1>", lambda e: self.toggle())
        self._tid = variable.trace_add("write", self._on_var)
        register(self)
        self._draw()

    def destroy(self):
        try:
            self.var.trace_remove("write", self._tid)
        except Exception:
            pass
        super().destroy()

    def toggle(self):
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def _on_var(self, *a):
        try:
            target = 1.0 if self.var.get() else 0.0
        except tk.TclError:
            return
        start = self.pos
        try:
            tween(self.c, "sw", 170, lambda t: self._set(start + (target - start) * t))
        except tk.TclError:
            pass

    def _set(self, p):
        self.pos = p
        self._draw()

    def refresh(self):
        self.lbl.config(fg=THEME["fg"])
        self._draw()

    def _draw(self):
        c = self.c
        c.delete("all")
        round_rect(c, 1, 2, 41, 20, 9, fill=mix(THEME["field"], THEME["accent"], self.pos), outline="")
        x = 11 + 20 * self.pos
        c.create_oval(x - 7, 4, x + 7, 18, fill=mix("#9aa0b5", "#ffffff", self.pos), outline="")


# ------------------------------------------------------------------ сайдбар
class Sidebar(tk.Canvas):
    def __init__(self, parent, entries, command, width=230):
        super().__init__(parent, width=width, bg=THEME["panel"], highlightthickness=0, bd=0)
        self.command, self.w = command, width
        self.rows, y = [], 124
        for e in entries:
            if e[0] == "hdr":
                self.rows.append({"kind": "hdr", "text": e[1], "y": y, "h": 38})
                y += 38
            else:
                self.rows.append({"kind": "item", "key": e[0], "text": e[1], "icon": e[2], "y": y, "h": 44})
                y += 44
        self.items = [r for r in self.rows if r["kind"] == "item"]
        self.sel = self.items[0]["key"]
        self.ind_y = self.items[0]["y"]
        self.hover = {r["key"]: 0.0 for r in self.items}
        self.cur = None
        self.user = ("Player", "Default")
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        self.bind("<Button-1>", self._click)
        self.bind("<Configure>", lambda e: self._draw())
        register(self)

    def set_user(self, nick, profile):
        self.user = (nick or "Player", profile or "")
        self._draw()

    def _hit(self, y):
        for r in self.items:
            if r["y"] <= y < r["y"] + r["h"]:
                return r["key"]
        return None

    def _is_user(self, y):
        return y > self.winfo_height() - 84

    def _motion(self, e):
        k = self._hit(e.y)
        self.config(cursor="hand2" if (k or self._is_user(e.y)) else "arrow")
        self._set_hover(k)

    def _set_hover(self, key):
        if key == self.cur:
            return
        self.cur = key
        for r in self.items:
            k = r["key"]
            start, to = self.hover[k], 1.0 if k == key else 0.0
            if abs(start - to) > .01:
                tween(self, "h" + k, 160, lambda t, k=k, s=start, to=to: self._seth(k, s + (to - s) * t))

    def _seth(self, k, v):
        self.hover[k] = v
        self._draw()

    def _click(self, e):
        k = self._hit(e.y)
        if k is None and self._is_user(e.y):
            k = "profile"
        if k:
            self.select(k)
            self.command(k)

    def select(self, key):
        self.sel = key
        target = next(r["y"] for r in self.items if r["key"] == key)
        start = self.ind_y
        tween(self, "ind", 280, lambda t: self._seti(start + (target - start) * t))

    def _seti(self, y):
        self.ind_y = y
        self._draw()

    def refresh(self):
        self.config(bg=THEME["panel"])
        self._draw()

    def _draw(self):
        self.delete("all")
        T = THEME
        logo_mark(self, 20, 22, 40)
        wordmark(self, 70, 36, 19, c1=T["fg"], c2=T["accent"])
        self.create_text(72, 62, text="MINECRAFT  LAUNCHER", anchor="w", fill=T["dim"],
                         font=(FONT, 7, "bold"))
        y = self.ind_y
        round_rect(self, 12, y + 2, self.w - 12, y + 42, 12, fill=mix(T["panel"], T["accent"], .2), outline="")
        round_rect(self, 4, y + 12, 8, y + 32, 2, fill=T["accent"], outline="")
        for r in self.rows:
            if r["kind"] == "hdr":
                self.create_text(26, r["y"] + 22, text=r["text"], anchor="w", fill=T["dim"], font=(FONT, 8, "bold"))
                self.create_line(26 + 8 * len(r["text"]) + 14, r["y"] + 22, self.w - 22, r["y"] + 22, fill=T["line"])
                continue
            top, k = r["y"], r["key"]
            h = self.hover[k]
            if h > .01:
                round_rect(self, 12, top + 2, self.w - 12, top + 42, 12, fill=mix(T["panel"], T["card"], h), outline="")
            near = max(0, 1 - abs(top - y) / 44)
            col = mix(mix(T["dim"], T["fg"], h * .6), T["fg"], near)
            self.create_text(36, top + 22, text=r["icon"], fill=mix(T["dim"], T["accent"], max(near, h)),
                             font=("Segoe UI Symbol", 13))
            self.create_text(64, top + 22, text=r["text"], anchor="w", fill=col,
                             font=(FONT, 11, "bold" if near > .5 else "normal"))
        H = int(self.winfo_height() or 700)
        round_rect(self, 12, H - 80, self.w - 12, H - 14, 14, fill=T["card"], outline="")
        nick, prof = self.user
        col = mix(T["field"], T["accent"], .8)
        self.create_oval(24, H - 68, 62, H - 30, fill=col, outline="")
        self.create_text(43, H - 49, text=(nick[:1] or "?").upper(), fill="#ffffff", font=(FONT, 15, "bold"))
        self.create_text(72, H - 56, text=nick[:14], anchor="w", fill=T["fg"], font=(FONT, 11, "bold"))
        self.create_text(72, H - 38, text=f"профиль: {prof[:14]}", anchor="w", fill=T["dim"], font=(FONT, 8))


# ------------------------------------------------------------------ прогресс
class AnimProgress(tk.Canvas):
    def __init__(self, parent, height=10):
        super().__init__(parent, height=height, bg=bg_of(parent), highlightthickness=0, bd=0)
        self.val = 0.0
        self.busy = False
        self.phase = 0.0
        self.bind("<Configure>", lambda e: self._draw())
        register(self)

    def set(self, frac):
        frac = max(0.0, min(1.0, frac))
        start = self.val
        tween(self, "v", 260, lambda t: self._setv(start + (frac - start) * t))

    def _setv(self, v):
        self.val = v
        self._draw()

    def set_busy(self, b):
        was = self.busy
        self.busy = b
        if b and not was:
            self._shimmer()
        elif not b:
            self._draw()

    def _shimmer(self):
        try:
            if not self.busy:
                return
            if ANIM["on"] and not STATE["paused"] and self.winfo_viewable():
                self.phase = (self.phase + 0.025) % 1.0
                self._draw()
            self.after(33, self._shimmer)
        except tk.TclError:
            pass

    def refresh(self):
        self.config(bg=bg_of(self.master))
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        T = THEME
        round_rect(self, 0, 0, w, h, h / 2, fill=T["field"], outline="")
        fw = max(h, w * self.val) if self.val > 0 else 0
        if fw:
            round_rect(self, 0, 0, fw, h, h / 2, fill=T["accent"], outline="")
            if self.busy and ANIM["on"]:
                x = (self.phase * (fw + 80)) - 40
                x1, x2 = max(h / 2, x), min(fw - h / 2, x + 40)
                if x2 > x1:
                    self.create_rectangle(x1, 2, x2, h - 2, fill=mix(T["accent"], "#ffffff", .35), outline="")


# ------------------------------------------------------------------ шапка
class Hero(tk.Canvas):
    def __init__(self, parent, height=300):
        super().__init__(parent, height=height, bg=THEME["bg"], highlightthickness=0, bd=0)
        self.H = height
        self.parts = [[random.random(), random.random(), random.uniform(1.5, 4.2),
                       random.uniform(.0006, .0021), random.uniform(0, 6.28)] for _ in range(36)]
        self.img = None
        self.src = None
        self._job = None
        self.t = 0.0
        self.running = False
        self.mode, self.image_path = "particles", ""
        self.letters = []
        self.bind("<Configure>", self._cfg)
        self.greet = self.create_text(44, 150, anchor="w", text="", fill=THEME["hero_fg"], font=(FONT, 16), tags="ui")
        self.cur_title = self.create_text(0, 0, anchor="w", text="", fill=THEME["hero_fg"], font=(FONT, 17, "bold"), tags="ui")
        self.cur_sub = self.create_text(0, 0, anchor="w", text="", fill=THEME["hero_fg"], font=(FONT, 10), tags="ui")
        self._logo()
        register(self)

    def _logo(self):
        self.delete("logo")
        logo_mark(self, 42, 30, 66)
        self.letters, _ = wordmark(self, 126, 62, 48, c1=THEME["hero_fg"], c2=mix(THEME["accent2"], "#ffffff", .45))
        self.create_text(130, 108, anchor="w", text="M I N E C R A F T   L A U N C H E R",
                         fill=mix(THEME["hero_fg"], self.color_at(108), .35), font=(FONT, 8, "bold"), tags="logo")
        self.tag_raise("logo")
        self.tag_raise("ui")

    def set_mode(self, mode, path=""):
        self.mode, self.image_path = mode, path
        self.src = None
        self._grad(self.winfo_width())

    def color_at(self, y):
        k = min(1, max(0, y / self.H))
        if THEME["light"]:
            return mix(mix(THEME["accent"], "#000000", .08), mix(THEME["accent"], "#ffffff", .12), k)
        top = mix(THEME["bg"], THEME["accent"], THEME["hero_mix"])
        return mix(top, THEME["bg"], k ** 1.15)

    def _cfg(self, e):
        self.layout(e.width)
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(120, lambda: self._grad(e.width))

    def layout(self, w):
        by = self.H - 30
        self.coords(self.cur_title, 42 + 300 + 26, by - 44)
        self.coords(self.cur_sub, 42 + 300 + 26, by - 18)
        self.event_generate("<<HeroLayout>>")

    def _grad(self, w):
        w = max(w, 10)
        self.delete("bg")
        img = None
        if self.mode == "image" and self.image_path:
            try:
                try:
                    from PIL import Image, ImageTk
                    im = Image.open(self.image_path).convert("RGB")
                    sc = max(w / im.width, self.H / im.height)
                    im = im.resize((int(im.width * sc) + 1, int(im.height * sc) + 1))
                    l, t = (im.width - w) // 2, (im.height - self.H) // 2
                    img = ImageTk.PhotoImage(im.crop((l, t, l + w, t + self.H)))
                except ImportError:
                    img = tk.PhotoImage(file=self.image_path)
            except Exception:
                img = None
        if img is None:
            img = tk.PhotoImage(width=w, height=self.H)
            for y in range(self.H):
                img.put(self.color_at(y), to=(0, y, w, y + 1))
            self.img = img
            self.create_image(0, 0, anchor="nw", image=img, tags="bg")
        else:
            self.img = img
            self.create_image(0, 0, anchor="nw", image=img, tags="bg")
            self.create_rectangle(0, 0, w, self.H, fill="#000000", stipple="gray25", outline="", tags="bg")
            self.create_rectangle(0, self.H - 8, w, self.H, fill=THEME["bg"], outline="", tags="bg")
        self.tag_lower("bg")

    def refresh(self):
        self.config(bg=THEME["bg"])
        self._logo()
        self._grad(self.winfo_width())

    def set_texts(self, greet, title, sub):
        self.itemconfigure(self.greet, text=greet)
        self.itemconfigure(self.cur_title, text=title)
        self.itemconfigure(self.cur_sub, text=sub, fill=mix(THEME["hero_fg"], self.color_at(self.H - 40), .3))

    def start(self):
        if not self.running:
            self.running = True
            self._tick()

    def stop(self):
        self.running = False

    def _tick(self):
        if not self.running:
            return
        try:
            if ANIM["on"] and not STATE["paused"] and self.winfo_viewable():
                self._frame()
            self.after(33, self._tick)
        except tk.TclError:
            self.running = False

    def _frame(self):
        self.t += 0.03
        w = self.winfo_width()
        phase = (self.t * 1.1) % 3.2
        for i, (iid, base) in enumerate(self.letters):
            b = max(0.0, 1 - abs(phase - i * .3 - .2) / .55)
            self.itemconfigure(iid, fill=mix(base, "#ffffff", b * .9))
        self.delete("p")
        if self.mode != "particles":
            return
        for p in self.parts:
            p[1] -= p[3]
            if p[1] < -0.05:
                p[1], p[0] = 1.05, random.random()
            x = (p[0] + math.sin(self.t + p[4]) * 0.012) * w
            y = p[1] * self.H
            a = max(0.0, min(1.0, math.sin(min(1, max(0, p[1])) * math.pi)))
            col = mix(self.color_at(y), THEME["accent2"] if p[2] > 3 else "#ffffff", .5 * a)
            self.create_oval(x - p[2], y - p[2], x + p[2], y + p[2], fill=col, outline="", tags="p")
        self.tag_lower("p")
        self.tag_lower("bg")
        self.tag_raise("logo")
        self.tag_raise("ui")


# ------------------------------------------------------------------ скролл
class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg=None, pad=96):
        bg = bg or bg_of(parent)
        super().__init__(parent, bg=bg)
        self.pad = pad
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self._upd())
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.bind_all("<MouseWheel>", self._wheel, add="+")
        self.bind_all("<Button-4>", self._wheel, add="+")
        self.bind_all("<Button-5>", self._wheel, add="+")

    def _upd(self):
        b = self.canvas.bbox("all")
        if b:
            self.canvas.configure(scrollregion=(b[0], b[1], b[2], b[3] + self.pad))

    def _wheel(self, e):
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
            while w is not None and w is not self:
                w = w.master
            if w is None or self.inner.winfo_height() + self.pad <= self.canvas.winfo_height():
                return
            d = -1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1
            self.canvas.yview_scroll(d * 3, "units")
        except (tk.TclError, KeyError):
            pass

    def to_top(self):
        self.canvas.yview_moveto(0)


# ------------------------------------------------------------------ тост
class Toast:
    def __init__(self, root):
        self.root = root
        self.f = None
        self._job = None

    def show(self, text, kind="ok"):
        if self.f is not None:
            try:
                self.f.destroy()
            except tk.TclError:
                pass
        col = {"ok": THEME["ok"], "err": THEME["danger"]}.get(kind, THEME["accent"])
        f = tk.Frame(self.root, bg=THEME["card"], highlightthickness=2, highlightbackground=col)
        tk.Label(f, text=text, bg=THEME["card"], fg=THEME["fg"], font=(FONT, 10, "bold"), padx=16, pady=10).pack()
        self.f = f
        f.place(relx=1.0, rely=1.0, x=-24, y=70, anchor="se")
        f.lift()
        tween(f, "in", 260, lambda t: f.place_configure(y=70 - 106 * t))
        if self._job:
            self.root.after_cancel(self._job)
        self._job = self.root.after(3000, lambda: self._hide(f))

    def _hide(self, f):
        try:
            tween(f, "out", 220, lambda t: f.place_configure(y=-36 + 106 * t), done=f.destroy)
        except tk.TclError:
            pass
