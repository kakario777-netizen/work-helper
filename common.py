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
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
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
    """색감 조절 바 묶음. get()/set() 으로 값 주고받기"""

    def __init__(self, master, app, key, on_change=None):
        super().__init__(master)
        self.app = app
        self.key = key
        self.on_change = on_change
        self._job = None
        saved = app.settings.get(key, {})
        self.vars = {}
        sf = ScrollFrame(self)
        sf.pack(fill="both", expand=True)
        for k, name, lo, hi in core.ADJUSTS:
            row = ttk.Frame(sf.inner)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=name, width=15).pack(side="left")
            v = tk.DoubleVar(value=float(saved.get(k, 0) or 0))
            sc = tk.Scale(row, from_=lo, to=hi, resolution=0.1, orient="horizontal", variable=v,
                          showvalue=True, length=170, sliderlength=14, width=10, bd=0,
                          highlightthickness=0, font=("맑은 고딕", 8),
                          command=lambda _x: self._changed())
            sc.pack(side="left", fill="x", expand=True)
            sc.bind("<Double-Button-1>", lambda e, var=v: (var.set(0), self._changed()))
            self.vars[k] = v
        ttk.Label(sf.inner, text="바를 더블클릭하면 0으로 돌아갑니다.", foreground=GRAY).pack(anchor="w", pady=(4, 0))

    def get(self):
        return {k: round(v.get(), 1) for k, v in self.vars.items()}

    def set(self, values):
        for k, v in self.vars.items():
            v.set(float(values.get(k, 0) or 0))
        self._changed()

    def reset(self):
        self.set({})

    def is_zero(self):
        return not any(self.get().values())

    def _changed(self):
        self.app.settings[self.key] = self.get()
        if self.on_change:
            if self._job:
                self.after_cancel(self._job)
            self._job = self.after(250, self.on_change)


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
