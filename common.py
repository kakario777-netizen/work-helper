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
    """세로 스크롤 되는 영역. 내용은 self.inner 에"""

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
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
            w.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120), "units")


class AdjustPanel(ttk.Frame):
    """색감 조절 바 묶음.  왼쪽 체크 = '랜덤' 누를 때 바뀌는 항목"""

    def __init__(self, master, app, key, on_change=None):
        super().__init__(master)
        self.app = app
        self.key = key
        self.on_change = on_change
        self._job = None
        saved = app.settings.get(key, {})
        rnd_saved = app.settings.get(key + "_rnd", {})
        self.vars, self.rnd = {}, {}
        sf = ScrollFrame(self)
        sf.pack(fill="both", expand=True)
        hdr = ttk.Frame(sf.inner)
        hdr.pack(fill="x")
        self.all_var = tk.BooleanVar(value=all(rnd_saved.get(k, True) for k, *_ in core.ADJUSTS))
        ttk.Checkbutton(hdr, text="랜덤", variable=self.all_var, command=self._toggle_all).pack(side="left")
        ttk.Label(hdr, text="← 체크한 항목만 랜덤 때 바뀜", foreground=GRAY).pack(side="left", padx=4)
        for k, name, lo, hi in core.ADJUSTS:
            row = ttk.Frame(sf.inner)
            row.pack(fill="x", pady=1)
            rv = tk.BooleanVar(value=rnd_saved.get(k, True))
            ttk.Checkbutton(row, variable=rv, command=self._save).pack(side="left")
            ttk.Label(row, text=name, width=12).pack(side="left")
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
    """눈에 보이는 폭 조절바(회색 굵은 막대 + 손잡이)가 있는 분할 영역. 위치는 자동 저장"""

    def __init__(self, master, app, key, orient="horizontal"):
        super().__init__(master, orient=orient, sashwidth=9, sashrelief="raised", sashpad=1,
                         showhandle=True, handlesize=14, handlepad=60, bg="#b9c3cf", bd=0,
                         opaqueresize=True, sashcursor="sb_h_double_arrow" if orient == "horizontal" else "sb_v_double_arrow")
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
        rows = (("len", "긴 변 크기 (px)", 1, 50, 6000), ("trim", "테두리 자르기 (px)", 1, 0, 200),
                ("aspect", "가로·세로 비율 흔들림 (%)", 0.1, 0, 30))
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
    """선택한 이미지에 지금 색감 값을 입힌 작은 미리보기 (원본 | 결과)"""

    def __init__(self, master, height=150):
        super().__init__(master)
        self.h = height
        self.lbl = ttk.Label(self, text="이미지를 선택하면 미리보기가 나옵니다.", anchor="center", foreground=GRAY)
        self.lbl.pack(fill="x")
        self._img = None
        self._src = None
        self._src_path = None

    def show(self, path, params):
        try:
            from PIL import Image, ImageTk
            if not path:
                self._img = None
                self.lbl.config(image="", text="이미지를 선택하면 미리보기가 나옵니다.")
                return
            if path != self._src_path:
                im = core._load_rgb(path)
                im.thumbnail((self.h * 2, self.h))
                self._src, self._src_path = im, path
            a = self._src
            b = core.apply_adjust(a.copy(), params or {})
            canvas = Image.new("RGB", (a.width * 2 + 6, a.height), (240, 240, 240))
            canvas.paste(a, (0, 0))
            canvas.paste(b, (a.width + 6, 0))
            self._img = ImageTk.PhotoImage(canvas)
            self.lbl.config(image=self._img, text="")
        except Exception as e:
            self.lbl.config(image="", text=f"미리보기 불가: {e}")
