"""업무 도우미 - 공용 도구"""
import json
import os
import queue
import shutil
import sys
import threading
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import core

APP_NAME = "업무 도우미"

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except Exception:
    TkinterDnD = None
    DND_FILES = None

FONT = ("맑은 고딕", 10)
FONT_B = ("맑은 고딕", 10, "bold")
MONO = ("맑은 고딕", 11)
GRAY = "#666"


def known_folder(which):
    """윈도우의 실제 '문서'·'바탕화면' 경로(원드라이브로 옮겨진 경우 포함)"""
    guids = {"documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
             "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"}
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD),
                            ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]
            g = GUID()
            ctypes.oledll.ole32.CLSIDFromString(guids[which], ctypes.byref(g))
            p = ctypes.c_wchar_p()
            ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p))
            path = p.value
            ctypes.windll.ole32.CoTaskMemFree(p)
            if path:
                return path
        except Exception:
            pass
    home = os.path.expanduser("~")
    return os.path.join(home, "Documents" if which == "documents" else "Desktop")


def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "WorkHelper")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")


def load_settings():
    try:
        with open(settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(s):
    """설정을 안전하게 저장(임시 파일에 쓴 뒤 바꿔치기)"""
    try:
        p = settings_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        pass


def enable_drop(widget, callback):
    """파일·폴더를 끌어다 놓으면 callback(경로 목록)"""
    if not DND_FILES:
        return False
    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", lambda e: (callback(list(widget.tk.splitlist(e.data))), e.action)[1])
        return True
    except Exception:
        return False


def drop_hint():
    return "여기로 끌어다 놓거나 " if DND_FILES else ""


def open_folder(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)
    except Exception:
        pass


def text_box(parent, height=10):
    frame = ttk.Frame(parent)
    t = tk.Text(frame, wrap="word", font=MONO, undo=True, height=height,
                relief="solid", borderwidth=1, padx=8, pady=6)
    sb = ttk.Scrollbar(frame, command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, t


def copy_to_clipboard(root, text):
    root.clipboard_clear()
    root.clipboard_append(text)



def read_text_file(p):
    for enc in ("utf-8-sig", "cp949", "utf-16"):
        try:
            with open(p, encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    return ""



# ════════════════════════════ 공용 위젯 ════════════════════════════

class ScrollFrame(ttk.Frame):
    """세로 스크롤 되는 영역. 내용은 self.inner 에. 마우스 휠은 install_wheel()이 처리"""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._wjob = None
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas._scrollframe = self
        self.inner._scrollframe = self

    def _on_canvas(self, e):
        # 창 크기를 바꾸는 동안 매번 안쪽을 다시 배치하면 버벅이므로 잠깐 모았다가 한 번에
        if self._wjob:
            self.after_cancel(self._wjob)
        self._wjob = self.after(60, lambda w=e.width: (self.canvas.itemconfigure(self._win, width=w),
                                                       setattr(self, "_wjob", None)))

    def scroll(self, delta):
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-delta / 120) or (-1 if delta > 0 else 1), "units")


def install_wheel(root):
    """마우스 휠: 포인터 아래에 있는 스크롤 영역을 굴림 (목록·글상자는 원래대로)"""
    def on_wheel(e):
        try:
            w = root.winfo_containing(e.x_root, e.y_root)
        except Exception:
            return
        while w is not None:
            if isinstance(w, (tk.Text, ttk.Treeview, tk.Listbox)):
                return
            sf = getattr(w, "_scrollframe", None)
            if sf:
                sf.scroll(e.delta)
                return
            w = w.master
    root.bind_all("<MouseWheel>", on_wheel, add="+")


class WrapLabel(ttk.Label):
    """칸 너비에 맞춰 자동으로 줄바꿈되는 글자 (잘리지 않게)"""

    def __init__(self, master, **kw):
        kw.setdefault("justify", "left")
        super().__init__(master, **kw)
        self.bind("<Configure>", lambda e: self.configure(wraplength=max(60, e.width - 4)))


class SizeCropPanel(ttk.LabelFrame):
    """가로변 크기 · 테두리 자르기 · 세로 비율 조정 (한 묶음 안에서는 모두 같은 값)"""

    def __init__(self, master, app, key, width=850, enable=False, on_change=None):
        super().__init__(master, text=" 크기 · 자르기 ", padding=8)
        s = app.settings
        self.key = key
        self.app = app
        self.on_change = on_change
        self.on = tk.BooleanVar(value=s.get(f"{key}_crop_on", not enable))
        self.width_v = tk.IntVar(value=s.get(f"{key}_w", width))
        self.trim_v = tk.IntVar(value=s.get(f"{key}_trim", 4))
        self.asp_v = tk.DoubleVar(value=s.get(f"{key}_asp", 0.0))
        r = 0
        if enable:
            ttk.Checkbutton(self, text="크기·자르기 적용", variable=self.on,
                            command=self._changed).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
            r = 1
        rows = (("가로변 크기 (px)", self.width_v, 50, 8000, 1),
                ("테두리 자르기 (원본 px)", self.trim_v, 0, 200, 1),
                ("세로 비율 조정 (±%)", self.asp_v, -15, 15, 0.1))
        for i, (name, var, lo, hi, inc) in enumerate(rows):
            ttk.Label(self, text=name).grid(row=r + i, column=0, sticky="w", pady=2)
            sp = ttk.Spinbox(self, from_=lo, to=hi, increment=inc, textvariable=var, width=7)
            sp.grid(row=r + i, column=1, sticky="w", padx=6)
            var.trace_add("write", lambda *a: self._changed())
        WrapLabel(self, foreground=GRAY,
                  text="순서: 원본 네 변을 같은 픽셀만큼 잘라냄(한 변 최대 4%) → 가로를 지정 크기로 키우거나 줄임"
                       " → 세로는 원래 비율에서 ±% 만큼 조정. 한 번에 만드는 묶음(폴더) 안에서는 모두 같은 값."
                  ).grid(row=r + 3, column=0, columnspan=2, sticky="we", pady=(6, 0))
        self.columnconfigure(0, weight=1)

    def get(self):
        try:
            return {"on": bool(self.on.get()), "width": int(self.width_v.get()),
                    "trim": int(self.trim_v.get()), "aspect": round(float(self.asp_v.get()), 1)}
        except Exception:
            return {"on": bool(self.on.get()), "width": 850, "trim": 0, "aspect": 0.0}

    def set(self, width=None, trim=None, aspect=None):
        if width is not None:
            self.width_v.set(int(width))
        if trim is not None:
            self.trim_v.set(int(trim))
        if aspect is not None:
            self.asp_v.set(round(float(aspect), 1))

    def apply_random(self, rng, cfg):
        size = core.random_size(rng, cfg)
        use = cfg.get("use", {})
        self.set(size["width"] if use.get("len", True) else None,
                 size["trim"] if use.get("trim", True) else None,
                 size["aspect"] if use.get("aspect", True) else None)

    def _changed(self):
        g = self.get()
        self.app.settings.update({f"{self.key}_crop_on": g["on"], f"{self.key}_w": g["width"],
                                  f"{self.key}_trim": g["trim"], f"{self.key}_asp": g["aspect"]})
        if self.on_change:
            self.on_change()


class AdjustPanel(ttk.Frame):
    """색감 조절 바 묶음.  왼쪽 체크 = '랜덤' 누를 때 바뀌는 항목"""

    def __init__(self, master, app, key, on_change=None, scroll=True):
        super().__init__(master)
        self.app = app
        self.key = key
        self.on_change = on_change
        self._job = None
        saved = app.settings.get(key, {})
        rnd_saved = app.settings.get(key + "_rnd", {})
        self.vars, self.rnd = {}, {}
        if scroll:
            sf = ScrollFrame(self)
            sf.pack(fill="both", expand=True)
            body = sf.inner
        else:
            body = self

        class _B:  # 아래 코드에서 sf.inner 로 쓰던 자리
            inner = body
        sf = _B
        hdr = ttk.Frame(sf.inner)
        hdr.pack(fill="x")
        self.all_var = tk.BooleanVar(value=all(rnd_saved.get(k, True) for k, *_ in core.ADJUSTS))
        ttk.Checkbutton(hdr, text="랜덤", variable=self.all_var, command=self._toggle_all).pack(side="left")
        ttk.Label(hdr, text="← 체크한 것만 랜덤", foreground=GRAY).pack(side="left", padx=4)
        for k, name, lo, hi in core.ADJUSTS:
            row = ttk.Frame(sf.inner)
            row.pack(fill="x", pady=1)
            rv = tk.BooleanVar(value=rnd_saved.get(k, True))
            ttk.Checkbutton(row, variable=rv, command=self._save).pack(side="left")
            ttk.Label(row, text=name, width=10).pack(side="left")
            v = tk.DoubleVar(value=float(saved.get(k, 0) or 0))
            sc = tk.Scale(row, from_=lo, to=hi, resolution=0.1, orient="horizontal", variable=v,
                          showvalue=True, length=120, sliderlength=12, width=9, bd=0,
                          highlightthickness=0, font=("맑은 고딕", 8),
                          command=lambda _x: self._changed())
            sc.pack(side="left", fill="x", expand=True)
            sc.bind("<Double-Button-1>", lambda e, var=v: (var.set(0), self._changed()))
            self.vars[k] = v
            self.rnd[k] = rv
        ttk.Label(sf.inner, text="바를 더블클릭하면 0으로 돌아갑니다.", foreground=GRAY).pack(anchor="w", pady=(4, 0))

    def get(self):
        return {k: round(v.get(), 1) for k, v in self.vars.items()}

    def set(self, values):
        for k, v in self.vars.items():
            v.set(float(values.get(k, 0) or 0))
        self._changed()

    def reset(self):
        self.set({})

    def randomize(self, rng):
        """체크된 항목만 아주 약한 값으로"""
        keys = [k for k, rv in self.rnd.items() if rv.get()]
        vals = core.random_adjust(rng, keys)
        cur = self.get()
        cur.update(vals)
        self.set(cur)

    def _toggle_all(self):
        for rv in self.rnd.values():
            rv.set(self.all_var.get())
        self._save()

    def _save(self):
        self.app.settings[self.key] = self.get()
        self.app.settings[self.key + "_rnd"] = {k: rv.get() for k, rv in self.rnd.items()}

    def _changed(self):
        self._save()
        if self.on_change:
            if self._job:
                self.after_cancel(self._job)
            self._job = self.after(250, self.on_change)


PANES = []   # 저장할 폭 조절 영역들


class Paned(tk.PanedWindow):
    """얇은 회색 줄로 폭을 조절하는 분할 영역(마우스를 대면 ↔ 표시). 위치는 자동 저장"""

    def __init__(self, master, app, key, orient="horizontal"):
        super().__init__(master, orient=orient, sashwidth=5, sashrelief="flat", sashpad=0,
                         showhandle=False, bg="#dcdfe3", bd=0,
                         opaqueresize=False, sashcursor="sb_h_double_arrow" if orient == "horizontal" else "sb_v_double_arrow")
        self.app = app
        self.key = key
        PANES.append(self)
        self._restored = False
        self.bind("<Map>", lambda e: self.after(150, self._restore))

    def add(self, child, weight=1, width=None, height=None, minsize=120):
        opts = {"minsize": minsize, "stretch": "always" if weight else "never"}
        if width:
            opts["width"] = width
        if height:
            opts["height"] = height
        super().add(child, **opts)

    def _restore(self):
        if self._restored:
            return
        self._restored = True
        pos = self.app.settings.get("panes", {}).get(self.key)
        if not pos:
            return
        for i, p in enumerate(pos):
            try:
                if self.cget("orient") == "horizontal":
                    self.sash_place(i, int(p), 1)
                else:
                    self.sash_place(i, 1, int(p))
            except Exception:
                pass

    def remember(self):
        if not self._restored:
            return
        try:
            n = len(self.panes()) - 1
            i = 0 if self.cget("orient") == "horizontal" else 1
            self.app.settings.setdefault("panes", {})[self.key] = [self.sash_coord(j)[i] for j in range(n)]
        except Exception:
            pass


class RandomRangeDialog(tk.Toplevel):
    """랜덤 버튼이 고를 범위(긴 변·테두리·비율)와 포함 여부"""

    def __init__(self, parent, app, key, default):
        super().__init__(parent)
        self.app = app
        self.key = key
        self.title("랜덤 범위")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        cfg = dict(default)
        cfg.update(app.settings.get(key, {}))
        use = cfg.get("use", {"len": True, "trim": True, "aspect": True})
        f = ttk.Frame(self, padding=16)
        f.pack()
        ttk.Label(f, text="'랜덤'을 누르면 아래 범위 안에서 값이 정해집니다.", foreground=GRAY).grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 10))
        self.v = {}
        rows = (("len", "가로변 크기 (px)", 1, 50, 8000), ("trim", "테두리 자르기 (px)", 1, 0, 200),
                ("aspect", "세로 비율 조정 (±%, 크기)", 0.1, 0, 15))
        for r, (k, name, inc, lo, hi) in enumerate(rows, start=1):
            u = tk.BooleanVar(value=use.get(k, True))
            ttk.Checkbutton(f, variable=u).grid(row=r, column=0, sticky="w")
            ttk.Label(f, text=name, width=22).grid(row=r, column=1, sticky="w", pady=4)
            a = tk.DoubleVar(value=cfg[k][0])
            b = tk.DoubleVar(value=cfg[k][1])
            ttk.Spinbox(f, from_=lo, to=hi, increment=inc, textvariable=a, width=7).grid(row=r, column=2)
            ttk.Label(f, text="~").grid(row=r, column=3, padx=4)
            ttk.Spinbox(f, from_=lo, to=hi, increment=inc, textvariable=b, width=7).grid(row=r, column=4)
            self.v[k] = (u, a, b)
        ttk.Label(f, text="왼쪽 체크를 끄면 그 항목은 랜덤 때 그대로 둡니다.", foreground=GRAY).grid(
            row=5, column=0, columnspan=5, sticky="w", pady=(10, 0))
        bar = ttk.Frame(f)
        bar.grid(row=6, column=0, columnspan=5, sticky="e", pady=(12, 0))
        ttk.Button(bar, text="처음값", command=lambda: self._fill(default)).pack(side="left")
        ttk.Button(bar, text="저장", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bar, text="취소", command=self.destroy).pack(side="left")
        self.grab_set()

    def _fill(self, d):
        for k, (u, a, b) in self.v.items():
            u.set(True)
            a.set(d[k][0])
            b.set(d[k][1])

    def _ok(self):
        try:
            out = {"use": {}}
            for k, (u, a, b) in self.v.items():
                lo, hi = sorted((float(a.get()), float(b.get())))
                out[k] = [int(lo), int(hi)] if k != "aspect" else [round(lo, 1), round(hi, 1)]
                out["use"][k] = bool(u.get())
        except Exception:
            messagebox.showwarning("랜덤 범위", "숫자를 확인해주세요.", parent=self)
            return
        self.app.settings[self.key] = out
        self.destroy()


class Preview(ttk.Frame):
    """선택한 이미지에 지금 조건(자르기·비율·색감)을 입힌 작은 미리보기. 클릭하면 전체 화면 비교"""

    def __init__(self, master, height=150):
        super().__init__(master)
        self.h = height
        self.lbl = ttk.Label(self, text="이미지를 선택하면 미리보기가 나옵니다.", anchor="center",
                             foreground=GRAY, cursor="hand2")
        self.lbl.pack(fill="x")
        self.tip = WrapLabel(self, text="", foreground=GRAY)
        self.tip.pack(fill="x")
        self.lbl.bind("<Button-1>", lambda e: self.open_full())
        self._img = None
        self._src = None
        self._scale = 1.0
        self._src_path = None
        self._proc = lambda im, sc: im
        self._list = []

    def show(self, path, proc, files=None):
        """proc(작은이미지, 원본대비배율) → 결과 이미지. files: 전체 화면에서 넘겨 볼 목록"""
        self._proc = proc or (lambda im, sc: im)
        self._list = list(files or ([path] if path else []))
        try:
            from PIL import Image, ImageTk
            if not path:
                self._img = None
                self._src_path = None
                self.lbl.config(image="", text="이미지를 선택하면 미리보기가 나옵니다.")
                self.tip.config(text="")
                return
            if path != self._src_path:
                im = core._load_rgb(path)
                w0 = im.width
                im.thumbnail((self.h * 2, self.h))
                self._src, self._src_path, self._scale = im, path, im.width / w0
            a = self._src
            b = self._proc(a.copy(), self._scale)
            b.thumbnail((a.width, a.height))
            canvas = Image.new("RGB", (a.width * 2 + 6, a.height), (240, 240, 240))
            canvas.paste(a, (0, 0))
            canvas.paste(b, (a.width + 6, (a.height - b.height) // 2))
            self._img = ImageTk.PhotoImage(canvas)
            self.lbl.config(image=self._img, text="")
            self.tip.config(text="왼쪽 원본 · 오른쪽 결과 (클릭하면 크게 비교)")
        except Exception as e:
            self.lbl.config(image="", text=f"미리보기 불가: {e}")

    def open_full(self):
        if not self._src_path:
            return
        files = self._list or [self._src_path]
        start = files.index(self._src_path) if self._src_path in files else 0
        CompareWindow(self, files, start, lambda im, sc: self._proc(im, sc))


class CompareWindow(tk.Toplevel):
    """전체 화면에 원본과 결과를 나란히. 휠·←→ 로 다음/이전 장, ESC·오른쪽 클릭·더블클릭으로 닫기"""
    BG = "#1e1f22"

    def __init__(self, master, files, index, proc):
        super().__init__(master)
        self.files, self.i, self.proc = files, index, proc
        self._cache = {}
        self._photo = None
        self.configure(bg=self.BG)
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.c = tk.Canvas(self, bg=self.BG, highlightthickness=0)
        self.c.pack(fill="both", expand=True)
        for seq in ("<Escape>", "<Button-3>"):
            self.bind(seq, lambda e: self.destroy())
        self.c.bind("<Double-Button-1>", lambda e: self.destroy())
        self.bind("<MouseWheel>", lambda e: self.step(-1 if e.delta > 0 else 1))
        for k, d in (("<Right>", 1), ("<Down>", 1), ("<Next>", 1), ("<space>", 1),
                     ("<Left>", -1), ("<Up>", -1), ("<Prior>", -1)):
            self.bind(k, lambda e, d=d: self.step(d))
        self.focus_force()
        self.after(50, self.render)

    def step(self, d):
        n = len(self.files)
        if n > 1:
            self.i = (self.i + d) % n
            self.render()

    def _load(self, path, box):
        key = (path, box)
        if key not in self._cache:
            im = core._load_rgb(path)
            w0 = im.width
            im.thumbnail(box)
            if len(self._cache) > 6:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (im, im.width / w0)
        return self._cache[key]

    def render(self):
        from PIL import Image, ImageTk
        W, H = self.winfo_width(), self.winfo_height()
        if W < 100:
            W, H = self.winfo_screenwidth(), self.winfo_screenheight()
        gap, top, bottom = 16, 44, 34
        box = ((W - gap * 3) // 2, H - top - bottom)
        path = self.files[self.i]
        self.c.delete("all")
        try:
            a, sc = self._load(path, box)
            b = self.proc(a.copy(), sc)
            b.thumbnail(box)
            hh = max(a.height, b.height)
            sheet = Image.new("RGB", (a.width + b.width + gap, hh), self.BG)
            sheet.paste(a, (0, (hh - a.height) // 2))
            sheet.paste(b, (a.width + gap, (hh - b.height) // 2))
            self._photo = ImageTk.PhotoImage(sheet)
            cx, cy = W // 2, top + (H - top - bottom) // 2
            self.c.create_image(cx, cy, image=self._photo)
            x0 = cx - sheet.width // 2
            ly = cy - hh // 2 - 14
            self.c.create_text(x0 + a.width // 2, ly, text="원본", fill="#cfd3da", font=FONT_B)
            self.c.create_text(x0 + a.width + gap + b.width // 2, ly, text="결과", fill="#cfd3da", font=FONT_B)
        except Exception as e:
            self.c.create_text(W // 2, H // 2, text=f"열 수 없는 이미지: {e}", fill="#f88", font=FONT)
        self.c.create_text(16, 14, anchor="nw", fill="#e8eaed", font=FONT_B,
                           text=f"{self.i + 1} / {len(self.files)}   {os.path.basename(path)}")
        self.c.create_text(W - 16, H - 12, anchor="se", fill="#8a8f98", font=FONT,
                           text="마우스 휠 · ← → : 다음/이전 장     ESC · 오른쪽 클릭 · 더블클릭 : 닫기")
