"""업무 도우미 - 텍스트 정리 / 이미지 관리 / 이미지 캡쳐 / 썸네일"""
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
VERSION = "1.1.0"

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



# ════════════════════════════ 텍스트 정리 ════════════════════════════

class TextTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.check = CheckPanel(nb, app)
        nb.add(self.check, text="  원고 검사(글자수·키워드·금지어)  ")
        nb.add(self._build_rank(nb), text="  순위 정리  ")
        nb.add(self._build_wrap(nb), text="  줄바꿈 정리  ")

    # ── 순위 정리 ──
    def _build_rank(self, nb):
        f = ttk.Frame(nb, padding=8)
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Label(bar, text="왼쪽에 '키워드  링크  순위  병원명' 표를 붙여넣으면 오른쪽에 '링크 [병원명] 키워드'로 바로 바뀝니다.",
                  foreground=GRAY).pack(side="left")
        ttk.Button(bar, text="결과 복사", command=lambda: self._copy(self.rank_out)).pack(side="right")
        ttk.Button(bar, text="지우기", command=lambda: self.rank_in.delete("1.0", "end")).pack(side="right", padx=4)
        body = ttk.PanedWindow(f, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(6, 0))
        lf, self.rank_in = text_box(body)
        rf, self.rank_out = text_box(body)
        self.rank_in.configure(wrap="none")
        self.rank_out.configure(wrap="none")
        body.add(lf, weight=1)
        body.add(rf, weight=1)
        self.rank_info = ttk.Label(f, text="")
        self.rank_info.pack(anchor="e", pady=(4, 0))
        self.rank_in.bind("<<Modified>>", self._rank_changed)
        return f

    def _rank_changed(self, _e=None):
        if not self.rank_in.edit_modified():
            return
        self.rank_in.edit_modified(False)
        res = core.convert_rank(self.rank_in.get("1.0", "end-1c"))
        self.rank_out.delete("1.0", "end")
        self.rank_out.insert("1.0", res)
        n = len(res.splitlines()) if res else 0
        self.rank_info.config(text=f"{n}줄 변환")

    # ── 줄바꿈 정리 ──
    def _build_wrap(self, nb):
        f = ttk.Frame(nb, padding=8)
        opt = ttk.Frame(f)
        opt.pack(fill="x")
        ttk.Label(opt, text="한 줄 글자수").pack(side="left")
        self.wrap_w = tk.IntVar(value=self.app.settings.get("wrap_width", 20))
        ttk.Spinbox(opt, from_=8, to=80, textvariable=self.wrap_w, width=5).pack(side="left", padx=(4, 12))
        self.wrap_first = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="문단 첫 문장은 한 줄 유지", variable=self.wrap_first).pack(side="left", padx=4)
        self.wrap_sent = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="문장마다 빈 줄", variable=self.wrap_sent).pack(side="left", padx=4)
        ttk.Button(opt, text="정리하기 ▶", command=self._do_wrap).pack(side="left", padx=12)
        ttk.Button(opt, text="결과 복사", command=lambda: self._copy(self.wrap_out)).pack(side="left")
        ttk.Label(f, text="'-', '#', '[' 로 시작하는 줄(요약·소제목·이미지 표시)은 그대로 둡니다.",
                  foreground=GRAY).pack(anchor="w", pady=(6, 0))
        body = ttk.PanedWindow(f, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(6, 0))
        lf, self.wrap_in = text_box(body)
        rf, self.wrap_out = text_box(body)
        body.add(lf, weight=1)
        body.add(rf, weight=1)
        self.wrap_info = ttk.Label(f, text="")
        self.wrap_info.pack(anchor="e", pady=(4, 0))
        return f

    def _do_wrap(self):
        try:
            w = int(self.wrap_w.get())
        except Exception:
            w = 20
        self.app.settings["wrap_width"] = w
        res = core.wrap_text(self.wrap_in.get("1.0", "end-1c"), w,
                             sentence_blank=self.wrap_sent.get(), keep_first=self.wrap_first.get())
        self.wrap_out.delete("1.0", "end")
        self.wrap_out.insert("1.0", res)
        s = core.count_stats(res, [])
        self.wrap_info.config(text=f"결과  공백 제외 {s['no_space']:,}자 · 문단 {s['paragraphs']}개")

    def _copy(self, box):
        copy_to_clipboard(self.app.root, box.get("1.0", "end-1c"))
        self.app.status("클립보드에 복사했습니다.")


class CheckPanel(ttk.Frame):
    """메모장 원고 여러 개를 끌어다 놓으면 파일별 글자수·키워드 수·금지어를 표로"""
    COLS = (("file", "파일", 220, "w"), ("kw", "키워드 (더블클릭해서 수정)", 200, "w"),
            ("kwn", "키워드 수", 130, "center"), ("ns", "공백 제외", 80, "center"),
            ("ws", "공백 포함", 80, "center"), ("bad", "금지어", 200, "w"))

    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.docs = {}  # iid → {"path","text","kw"}

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="금지어", font=FONT_B).pack(side="left")
        self.forbid = tk.StringVar(value=app.settings.get("forbidden", "전문, 자료"))
        ttk.Entry(top, textvariable=self.forbid).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(top, text="쉼표로 구분", foreground=GRAY).pack(side="left")
        self.forbid.trace_add("write", lambda *a: self.refresh_all())

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(8, 4))
        ttk.Label(bar, text=f"메모장(.txt) 파일이나 폴더를 {drop_hint()}버튼으로 추가하세요.",
                  foreground=GRAY).pack(side="left")
        for txt, cmd in (("표 복사", self.copy_table), ("다시 읽기", self.reload), ("비우기", self.clear),
                         ("선택 삭제", self.remove_sel), ("폴더 추가", self.add_folder), ("파일 추가", self.add_files)):
            ttk.Button(bar, text=txt, command=cmd).pack(side="right", padx=2)

        pw = ttk.PanedWindow(self, orient="vertical")
        pw.pack(fill="both", expand=True)

        tf = ttk.Frame(pw)
        self.tree = ttk.Treeview(tf, columns=[c[0] for c in self.COLS], show="headings", selectmode="extended")
        for cid, title, w, anchor in self.COLS:
            self.tree.heading(cid, text=title)
            self.tree.column(cid, width=w, anchor=anchor)
        sb = ttk.Scrollbar(tf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("bad", background="#ffe3e3")
        self.tree.tag_configure("nokw", background="#fff6d6")
        self.tree.bind("<Double-1>", self._dbl)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_preview())
        pw.add(tf, weight=3)

        pf = ttk.Frame(pw)
        kb = ttk.Frame(pf)
        kb.pack(fill="x", pady=(6, 4))
        ttk.Label(kb, text="선택한 파일 키워드").pack(side="left")
        self.kw_edit = tk.StringVar()
        e = ttk.Entry(kb, textvariable=self.kw_edit, width=40)
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda ev: self._apply_kw())
        ttk.Button(kb, text="적용", command=self._apply_kw).pack(side="left")
        ttk.Label(kb, text="키워드가 여러 개면 쉼표로  ·  미리보기: 파랑=키워드, 빨강=금지어",
                  foreground=GRAY).pack(side="left", padx=10)
        box, self.preview = text_box(pf, height=8)
        box.pack(fill="both", expand=True)
        self.preview.tag_configure("kw", background="#d6e8ff", foreground="#0645ad")
        self.preview.tag_configure("bad", background="#ffd0d0", foreground="#c00")
        pw.add(pf, weight=2)

        self.summary = ttk.Label(self, text="")
        self.summary.pack(anchor="w", pady=(4, 0))

        for w in (self.tree, self):
            enable_drop(w, self.add_paths)

    # ── 파일 추가 ──
    def add_paths(self, paths):
        files = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, fs in os.walk(p):
                    files += [os.path.join(root, f) for f in sorted(fs) if f.lower().endswith(".txt")]
            elif p.lower().endswith(".txt"):
                files.append(p)
        known = {d["path"] for d in self.docs.values()}
        for p in files:
            p = os.path.normpath(p)
            if p in known:
                continue
            text = read_text_file(p)
            iid = self.tree.insert("", "end")
            self.docs[iid] = {"path": p, "text": text, "kw": core.guess_keyword(p, text)}
            self._refresh_row(iid)
        self._summary()

    def add_files(self):
        self.add_paths(filedialog.askopenfilenames(filetypes=[("메모장", "*.txt"), ("모든 파일", "*.*")]))

    def add_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.add_paths([d])

    def remove_sel(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.docs.pop(iid, None)
        self._summary()

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.docs.clear()
        self.preview.delete("1.0", "end")
        self._summary()

    def reload(self):
        for iid, d in self.docs.items():
            d["text"] = read_text_file(d["path"])
        self.refresh_all()

    # ── 계산 ──
    def _forbidden_words(self):
        return [w.strip() for w in self.forbid.get().split(",") if w.strip()]

    def _refresh_row(self, iid):
        d = self.docs[iid]
        st = core.count_stats(d["text"], [])
        kws = core.count_keywords(d["text"], d["kw"])
        kwn = " / ".join(f"{n}개" if len(kws) == 1 else f"{k} {n}개" for k, n in kws) or "-"
        bad = core.count_forbidden(d["text"], self._forbidden_words())
        badtxt = "  ".join(f"{w}:{n}개" for w, n in bad) if bad else "없음"
        tags = ("bad",) if bad else (("nokw",) if not kws or any(n == 0 for _, n in kws) else ())
        self.tree.item(iid, values=(os.path.basename(d["path"]), d["kw"], kwn,
                                    f"{st['no_space']:,}", f"{st['with_space']:,}", badtxt), tags=tags)

    def refresh_all(self):
        self.app.settings["forbidden"] = self.forbid.get()
        for iid in self.docs:
            self._refresh_row(iid)
        self._show_preview()
        self._summary()

    def _summary(self):
        n = len(self.docs)
        bad = sum(1 for i in self.docs if "bad" in self.tree.item(i, "tags"))
        self.summary.config(text=f"파일 {n}개" + (f"  ·  금지어 들어간 파일 {bad}개" if bad else ""))

    # ── 키워드 수정 ──
    def _dbl(self, e):
        iid = self.tree.identify_row(e.y)
        col = self.tree.identify_column(e.x)
        if not iid or col != "#2":
            return
        x, y, w, h = self.tree.bbox(iid, col)
        ent = ttk.Entry(self.tree)
        ent.insert(0, self.docs[iid]["kw"])
        ent.select_range(0, "end")
        ent.place(x=x, y=y, width=w, height=h)
        ent.focus_set()

        def done(save):
            if save:
                self.docs[iid]["kw"] = ent.get().strip()
                self._refresh_row(iid)
                self._show_preview()
            ent.destroy()
        ent.bind("<Return>", lambda ev: done(True))
        ent.bind("<FocusOut>", lambda ev: done(True))
        ent.bind("<Escape>", lambda ev: done(False))

    def _apply_kw(self):
        sel = self.tree.selection()
        for iid in sel:
            self.docs[iid]["kw"] = self.kw_edit.get().strip()
            self._refresh_row(iid)
        self._show_preview()

    def _show_preview(self):
        sel = self.tree.selection()
        self.preview.delete("1.0", "end")
        if not sel or sel[0] not in self.docs:
            return
        d = self.docs[sel[0]]
        self.kw_edit.set(d["kw"])
        self.preview.insert("1.0", d["text"])
        words = [(k, "kw") for k, _ in core.count_keywords(d["text"], d["kw"])]
        words += [(w, "bad") for w in self._forbidden_words()]
        for word, tag in words:
            start = "1.0"
            while True:
                pos = self.preview.search(word, start, stopindex="end")
                if not pos:
                    break
                end = f"{pos}+{len(word)}c"
                self.preview.tag_add(tag, pos, end)
                start = end

    def copy_table(self):
        lines = ["\t".join(c[1].split(" (")[0] for c in self.COLS)]
        for iid in self.tree.get_children():
            lines.append("\t".join(str(v) for v in self.tree.item(iid, "values")))
        copy_to_clipboard(self.app.root, "\n".join(lines))
        self.app.status("표를 복사했습니다. 엑셀에 바로 붙여넣을 수 있어요.")


def read_text_file(p):
    for enc in ("utf-8-sig", "cp949", "utf-16"):
        try:
            with open(p, encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    return ""



# ════════════════════════════ 이미지 관리 ════════════════════════════

class ImageTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.files = []
        self.worker = None
        self.q = queue.Queue()
        s = app.settings

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="파일 추가", command=self._add_files).pack(side="left")
        ttk.Button(top, text="폴더 추가", command=self._add_folder).pack(side="left", padx=4)
        self.sub_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="하위 폴더 포함", variable=self.sub_var).pack(side="left", padx=4)
        ttk.Button(top, text="선택 삭제", command=self._remove_sel).pack(side="left", padx=(12, 4))
        ttk.Button(top, text="목록 비우기", command=self._clear).pack(side="left")
        self.count_lbl = ttk.Label(top, text="0개")
        self.count_lbl.pack(side="right")

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, pady=8)

        lf = ttk.Frame(body)
        self.tree = ttk.Treeview(lf, columns=("name", "size", "folder"), show="headings", selectmode="extended")
        for c, t, w in (("name", "파일명", 220), ("size", "용량", 70), ("folder", "폴더", 260)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c == "size" else "w")
        sb = ttk.Scrollbar(lf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        body.add(lf, weight=3)
        enable_drop(self.tree, self._drop)

        opt = ttk.Frame(body, padding=(10, 0))
        body.add(opt, weight=2)

        # 크기
        g1 = ttk.LabelFrame(opt, text=" 크기 조절·압축 ", padding=8)
        g1.pack(fill="x")
        self.rs_on = tk.BooleanVar(value=s.get("rs_on", True))
        ttk.Checkbutton(g1, text="크기 조절", variable=self.rs_on).grid(row=0, column=0, sticky="w")
        self.rs_mode = tk.StringVar(value=s.get("rs_mode", "가로 최대(px)"))
        ttk.Combobox(g1, textvariable=self.rs_mode, state="readonly", width=13,
                     values=["가로 최대(px)", "긴 변 최대(px)", "비율(%)"]).grid(row=0, column=1, padx=4)
        self.rs_val = tk.IntVar(value=s.get("rs_val", 1000))
        ttk.Spinbox(g1, from_=1, to=10000, textvariable=self.rs_val, width=7).grid(row=0, column=2)
        ttk.Label(g1, text="품질(JPG·WEBP)").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.quality = tk.IntVar(value=s.get("quality", 85))
        ttk.Spinbox(g1, from_=10, to=100, textvariable=self.quality, width=5).grid(row=1, column=1, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(g1, text="낮을수록 용량↓", foreground="#666").grid(row=1, column=2, sticky="w", pady=(6, 0))

        # 포맷
        g2 = ttk.LabelFrame(opt, text=" 포맷 변환 ", padding=8)
        g2.pack(fill="x", pady=8)
        self.fmt = tk.StringVar(value=s.get("fmt", "원본 유지"))
        for i, name in enumerate(core.FORMATS):
            ttk.Radiobutton(g2, text=name, value=name, variable=self.fmt).grid(row=0, column=i, padx=4)

        # 이름
        g3 = ttk.LabelFrame(opt, text=" 파일명 일괄 변경 ", padding=8)
        g3.pack(fill="x")
        self.rn_on = tk.BooleanVar(value=s.get("rn_on", False))
        ttk.Checkbutton(g3, text="이름 바꾸기", variable=self.rn_on).grid(row=0, column=0, sticky="w")
        self.pattern = tk.StringVar(value=s.get("pattern", "{날짜}_{번호}"))
        ttk.Entry(g3, textvariable=self.pattern, width=24).grid(row=0, column=1, columnspan=3, sticky="we", padx=4)
        ttk.Label(g3, text="시작 번호").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.start_no = tk.IntVar(value=1)
        ttk.Spinbox(g3, from_=0, to=99999, textvariable=self.start_no, width=6).grid(row=1, column=1, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(g3, text="자릿수").grid(row=1, column=2, sticky="e", pady=(6, 0))
        self.digits = tk.IntVar(value=s.get("digits", 3))
        ttk.Spinbox(g3, from_=1, to=6, textvariable=self.digits, width=4).grid(row=1, column=3, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(g3, text="{이름} 원래 이름 · {번호} 순번 · {날짜} 오늘 날짜", foreground="#666").grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.preview_lbl = ttk.Label(g3, text="", foreground="#0a5")
        self.preview_lbl.grid(row=3, column=0, columnspan=4, sticky="w")
        for v in (self.pattern, self.start_no, self.digits, self.rn_on):
            v.trace_add("write", lambda *a: self._preview())

        # 저장 위치
        g4 = ttk.LabelFrame(opt, text=" 저장 위치 ", padding=8)
        g4.pack(fill="x", pady=8)
        self.out_dir = tk.StringVar(value=s.get("img_out", ""))
        ttk.Entry(g4, textvariable=self.out_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(g4, text="찾기", command=self._pick_out).pack(side="left", padx=4)
        ttk.Label(opt, text="비워두면 원본 폴더 안 '변환결과' 폴더에 저장 (원본은 그대로)",
                  foreground="#666").pack(anchor="w")

        bot = ttk.Frame(self)
        bot.pack(fill="x")
        self.prog = ttk.Progressbar(bot, mode="determinate")
        self.prog.pack(side="left", fill="x", expand=True)
        self.run_btn = ttk.Button(bot, text="  실행  ", command=self._run)
        self.run_btn.pack(side="left", padx=8)
        self.result_lbl = ttk.Label(self, text="")
        self.result_lbl.pack(anchor="w", pady=(4, 0))
        self._preview()

    def _add(self, paths):
        known = set(self.files)
        for p in paths:
            p = os.path.normpath(p)
            if p in known or os.path.splitext(p)[1].lower() not in core.IMAGE_EXT:
                continue
            known.add(p)
            self.files.append(p)
            try:
                sz = core.human_size(os.path.getsize(p))
            except OSError:
                sz = "?"
            self.tree.insert("", "end", iid=p, values=(os.path.basename(p), sz, os.path.dirname(p)))
        self.count_lbl.config(text=f"{len(self.files)}개")
        self._preview()

    def _drop(self, paths):
        out = []
        for p in paths:
            out += core.list_images(p, self.sub_var.get()) if os.path.isdir(p) else [p]
        self._add(out)

    def _add_files(self):
        ps = filedialog.askopenfilenames(filetypes=[("이미지", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff"),
                                                    ("모든 파일", "*.*")])
        self._add(ps)

    def _add_folder(self):
        d = filedialog.askdirectory()
        if d:
            self._add(core.list_images(d, self.sub_var.get()))

    def _remove_sel(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
            if iid in self.files:
                self.files.remove(iid)
        self.count_lbl.config(text=f"{len(self.files)}개")

    def _clear(self):
        self.tree.delete(*self.tree.get_children())
        self.files.clear()
        self.count_lbl.config(text="0개")
        self.prog["value"] = 0

    def _pick_out(self):
        d = filedialog.askdirectory()
        if d:
            self.out_dir.set(d)

    def _preview(self):
        if not self.rn_on.get():
            self.preview_lbl.config(text="")
            return
        try:
            stem = os.path.splitext(os.path.basename(self.files[0]))[0] if self.files else "사진"
            n = core.build_name(self.pattern.get(), stem, int(self.start_no.get()), int(self.digits.get()))
            self.preview_lbl.config(text=f"예시: {n}")
        except Exception:
            pass

    def _opts(self):
        mode = {"가로 최대(px)": "width", "긴 변 최대(px)": "long", "비율(%)": "percent"}[self.rs_mode.get()]
        return {"resize": self.rs_on.get(), "resize_mode": mode, "resize_value": int(self.rs_val.get()),
                "fmt": self.fmt.get(), "quality": int(self.quality.get()), "rename": self.rn_on.get(),
                "pattern": self.pattern.get(), "digits": int(self.digits.get())}

    def _remember(self):
        s = self.app.settings
        s.update(rs_on=self.rs_on.get(), rs_mode=self.rs_mode.get(), rs_val=int(self.rs_val.get()),
                 quality=int(self.quality.get()), fmt=self.fmt.get(), rn_on=self.rn_on.get(),
                 pattern=self.pattern.get(), digits=int(self.digits.get()), img_out=self.out_dir.get())

    def _run(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.files:
            messagebox.showinfo(APP_NAME, "먼저 이미지 파일이나 폴더를 추가해주세요.")
            return
        try:
            opts = self._opts()
            start = int(self.start_no.get())
        except Exception:
            messagebox.showwarning(APP_NAME, "숫자 칸을 확인해주세요.")
            return
        self._remember()
        out = self.out_dir.get().strip()
        files = list(self.files)
        self.prog.config(maximum=len(files), value=0)
        self.run_btn.config(state="disabled")
        self.result_lbl.config(text="처리 중...")

        def work():
            before = after = ok = 0
            errors = []
            last_dir = out
            for i, src in enumerate(files):
                d = out or os.path.join(os.path.dirname(src), "변환결과")
                try:
                    os.makedirs(d, exist_ok=True)
                    _, b, a = core.process_image(src, d, start + i, opts)
                    before += b
                    after += a
                    ok += 1
                    last_dir = d
                except Exception as e:
                    errors.append(f"{os.path.basename(src)}: {e}")
                self.q.put(("prog", i + 1))
            self.q.put(("done", ok, before, after, errors, last_dir))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self._poll()

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "prog":
                    self.prog["value"] = msg[1]
                elif msg[0] == "done":
                    _, ok, b, a, errors, last_dir = msg
                    self.run_btn.config(state="normal")
                    pct = f" ({(1 - a / b) * 100:.0f}% 줄임)" if b and a < b else ""
                    self.result_lbl.config(
                        text=f"완료 {ok}개 · {core.human_size(b)} → {core.human_size(a)}{pct}"
                             + (f" · 실패 {len(errors)}개" if errors else ""))
                    if errors:
                        messagebox.showwarning(APP_NAME, "일부 파일을 처리하지 못했습니다.\n\n" + "\n".join(errors[:15]))
                    if last_dir and messagebox.askyesno(APP_NAME, "완료했습니다. 결과 폴더를 열까요?"):
                        open_folder(last_dir)
                    return
        except queue.Empty:
            pass
        self.after(80, self._poll)




# ════════════════════════════ 이미지 캡쳐 / 썸네일 ════════════════════════════

META = "_정보.json"


class LibraryTab(ttk.Frame):
    """폴더를 끌어다 놓으면 '내 문서\\업무도우미'에 보관하고,
    요청한 장수만큼 랜덤하게 잘라·색감 미세조정·메타 교체해서 바탕화면에 저장"""

    def __init__(self, master, app, kind):
        super().__init__(master, padding=8)
        self.app = app
        self.kind = kind  # "image" | "thumb"
        self.is_img = kind == "image"
        sub = "병원이미지" if self.is_img else "썸네일"
        self.lib = os.path.join(known_folder("documents"), "업무도우미", sub)
        os.makedirs(self.lib, exist_ok=True)
        self.q = queue.Queue()
        self.worker = None
        self.last_out = None
        s = app.settings

        # ── 왼쪽: 보관 목록 ──
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        body.add(left, weight=3)
        what = "병원·시술별 이미지 폴더" if self.is_img else "병원별 썸네일 폴더"
        ttk.Label(left, text=f"{what}를 {drop_hint()}'폴더 추가'를 누르세요. 폴더 여러 개를 한 번에 넣어도 됩니다.",
                  foreground=GRAY).pack(anchor="w")
        tf = ttk.Frame(left)
        tf.pack(fill="both", expand=True, pady=6)
        cols = [("h", "병원명", 160)] + ([("p", "시술명", 160)] if self.is_img else []) + [("n", "이미지 수", 70)]
        self.tree = ttk.Treeview(tf, columns=[c[0] for c in cols], show="headings", selectmode="extended")
        for cid, t, w in cols:
            self.tree.heading(cid, text=t)
            self.tree.column(cid, width=w, anchor="center" if cid == "n" else "w")
        sb = ttk.Scrollbar(tf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        lb = ttk.Frame(left)
        lb.pack(fill="x")
        ttk.Button(lb, text="폴더 추가", command=self._add_folder).pack(side="left")
        ttk.Button(lb, text="선택 항목에 사진 추가", command=self._add_to_selected).pack(side="left", padx=4)
        ttk.Button(lb, text="선택 삭제", command=self._delete).pack(side="left")
        ttk.Button(lb, text="보관 폴더 열기", command=lambda: open_folder(self.lib)).pack(side="right")
        enable_drop(self.tree, self._dropped)
        enable_drop(left, self._dropped)

        # ── 오른쪽: 이름 · 만들기 ──
        right = ttk.Frame(body, padding=(12, 0))
        body.add(right, weight=2)

        g1 = ttk.LabelFrame(right, text=" 선택한 항목 이름 ", padding=8)
        g1.pack(fill="x")
        self.h_var = tk.StringVar()
        self.p_var = tk.StringVar()
        ttk.Label(g1, text="병원명").grid(row=0, column=0, sticky="w")
        ttk.Entry(g1, textvariable=self.h_var, width=24).grid(row=0, column=1, sticky="we", padx=6, pady=2)
        if self.is_img:
            ttk.Label(g1, text="시술명").grid(row=1, column=0, sticky="w")
            ttk.Entry(g1, textvariable=self.p_var, width=24).grid(row=1, column=1, sticky="we", padx=6, pady=2)
        ttk.Button(g1, text="이름 저장", command=self._rename).grid(row=0, column=2, rowspan=2, padx=4)
        g1.columnconfigure(1, weight=1)

        g2 = ttk.LabelFrame(right, text=" 만들기 ", padding=8)
        g2.pack(fill="x", pady=10)
        key = "img" if self.is_img else "th"
        ttk.Label(g2, text="장수").grid(row=0, column=0, sticky="w")
        self.count = tk.IntVar(value=s.get(f"{key}_count", 10))
        ttk.Spinbox(g2, from_=1, to=500, textvariable=self.count, width=6).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(g2, text="긴 변 크기(px)").grid(row=1, column=0, sticky="w", pady=(6, 0))
        rng = ttk.Frame(g2)
        rng.grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        dmin, dmax = (800, 900) if self.is_img else (750, 950)
        self.lmin = tk.IntVar(value=s.get(f"{key}_min", dmin))
        self.lmax = tk.IntVar(value=s.get(f"{key}_max", dmax))
        ttk.Spinbox(rng, from_=100, to=5000, textvariable=self.lmin, width=6).pack(side="left")
        ttk.Label(rng, text=" ~ ").pack(side="left")
        ttk.Spinbox(rng, from_=100, to=5000, textvariable=self.lmax, width=6).pack(side="left")
        desc = ("자르는 위치·크기·비율을 매번 다르게, 밝기·대비 약 1%, 채도 1~2%, 감마 1~3%를 무작위로 틀고,\n"
                "원본 메타데이터는 지운 뒤 새 날짜·고유번호로 저장합니다.")
        ttk.Label(g2, text=desc, foreground=GRAY, justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.where = ttk.Label(g2, text="", foreground="#0a5", justify="left")
        self.where.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.run_btn = ttk.Button(right, text="  선택 항목 만들기  ", command=self._run)
        self.run_btn.pack(fill="x")
        ttk.Label(right, text="여러 항목을 선택하면 항목마다 따로 폴더를 만듭니다.", foreground=GRAY).pack(anchor="w", pady=(4, 8))
        self.prog = ttk.Progressbar(right, mode="determinate")
        self.prog.pack(fill="x")
        self.result = ttk.Label(right, text="", justify="left")
        self.result.pack(anchor="w", pady=6)
        self.open_btn = ttk.Button(right, text="결과 폴더 열기", command=lambda: self.last_out and open_folder(self.last_out),
                                   state="disabled")
        self.open_btn.pack(anchor="w")

        self.reload()

    # ── 보관 목록 ──
    def _read_meta(self, d):
        try:
            with open(os.path.join(d, META), encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            m = {}
        name = os.path.basename(d)
        return {"hospital": m.get("hospital", name), "procedure": m.get("procedure", "")}

    def _write_meta(self, d, h, p):
        with open(os.path.join(d, META), "w", encoding="utf-8") as f:
            json.dump({"hospital": h, "procedure": p}, f, ensure_ascii=False)

    def reload(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for name in sorted(os.listdir(self.lib)):
            d = os.path.join(self.lib, name)
            if not os.path.isdir(d):
                continue
            m = self._read_meta(d)
            n = len(core.list_images(d))
            vals = (m["hospital"], m["procedure"], n) if self.is_img else (m["hospital"], n)
            self.tree.insert("", "end", iid=d, values=vals)
        if select and self.tree.exists(select):
            self.tree.selection_set(select)
            self.tree.see(select)
        self._on_select()

    def _guess_names(self, folder_name):
        name = folder_name.strip()
        if self.is_img:
            parts = [x for x in __import__("re").split(r"\s*[-_]\s*|\s+", name) if x]
            if len(parts) >= 2:
                return parts[0], " ".join(parts[1:])
            return name, ""
        for w in ("썸네일", "썸넬"):
            name = name.replace(w, "")
        return name.strip(" -_") or folder_name, ""

    def _safe(self, s):
        return "".join("_" if c in '\\/:*?"<>|' else c for c in s).strip() or "이름없음"

    def _new_group(self, h, p, files):
        base = self._safe(f"{h} {p}".strip())
        d = os.path.join(self.lib, base)
        n = 2
        while os.path.exists(d):
            d = os.path.join(self.lib, f"{base} ({n})")
            n += 1
        os.makedirs(d)
        self._write_meta(d, h, p)
        self._copy_into(d, files)
        return d

    def _copy_into(self, d, files):
        for f in files:
            dst = core._unique(os.path.join(d, os.path.basename(f)))
            shutil.copy2(f, dst)

    def _dropped(self, paths):
        groups = []
        loose = []
        for p in paths:
            if os.path.isdir(p):
                imgs = core.list_images(p)
                if imgs:
                    groups.append((os.path.basename(os.path.normpath(p)), imgs))
                else:  # 상위 폴더를 넣은 경우: 하위 폴더 하나하나를 항목으로
                    for sub in sorted(os.listdir(p)):
                        sp = os.path.join(p, sub)
                        if os.path.isdir(sp):
                            si = core.list_images(sp, recursive=True)
                            if si:
                                groups.append((sub, si))
            elif os.path.splitext(p)[1].lower() in core.IMAGE_EXT:
                loose.append(p)
        if loose:
            sel = self.tree.selection()
            if len(sel) == 1 and messagebox.askyesno(APP_NAME, "선택한 항목에 사진을 추가할까요?\n(아니요 = 새 항목으로 만들기)"):
                self._copy_into(sel[0], loose)
                self.reload(select=sel[0])
                return
            groups.append((os.path.basename(os.path.dirname(loose[0])), loose))
        if not groups:
            messagebox.showinfo(APP_NAME, "이미지가 들어 있는 폴더를 넣어주세요.")
            return
        self.app.root.config(cursor="watch")
        self.app.root.update()
        last = None
        try:
            for name, files in groups:
                h, p = self._guess_names(name)
                last = self._new_group(h, p, files)
        finally:
            self.app.root.config(cursor="")
        self.reload(select=last)
        self.app.status(f"{len(groups)}개 항목을 보관했습니다. 이름이 맞는지 확인해주세요.")

    def _add_folder(self):
        d = filedialog.askdirectory()
        if d:
            self._dropped([d])

    def _add_to_selected(self):
        sel = self.tree.selection()
        if len(sel) != 1:
            messagebox.showinfo(APP_NAME, "사진을 넣을 항목 하나를 먼저 선택해주세요.")
            return
        fs = filedialog.askopenfilenames(filetypes=[("이미지", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"), ("모든 파일", "*.*")])
        if fs:
            self._copy_into(sel[0], fs)
            self.reload(select=sel[0])

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        if not messagebox.askyesno(APP_NAME, f"선택한 {len(sel)}개 항목을 보관함에서 지울까요?\n(처음 넣었던 원본 폴더는 그대로 남습니다)"):
            return
        for d in sel:
            shutil.rmtree(d, ignore_errors=True)
        self.reload()

    def _on_select(self):
        sel = self.tree.selection()
        if len(sel) == 1:
            m = self._read_meta(sel[0])
            self.h_var.set(m["hospital"])
            self.p_var.set(m["procedure"])
        else:
            self.h_var.set("")
            self.p_var.set("")
        self.where.config(text=self._where_text(sel))

    def _out_base(self, d):
        m = self._read_meta(d)
        if self.is_img:
            return self._safe(f"{m['hospital']} {m['procedure']}".strip())
        return self._safe(f"{m['hospital']} 썸넬")

    def _where_text(self, sel):
        if not sel:
            return "항목을 선택하면 저장 위치가 여기 표시됩니다."
        ex = os.path.basename(core.next_numbered_dir(known_folder("desktop"), self._out_base(sel[0])))
        tail = "\\output\\" if self.is_img else "\\"
        more = f"  외 {len(sel) - 1}개" if len(sel) > 1 else ""
        return f"저장 위치: 바탕화면\\{ex}{tail}{more}"

    def _rename(self):
        sel = self.tree.selection()
        if len(sel) != 1:
            messagebox.showinfo(APP_NAME, "이름을 바꿀 항목 하나를 선택해주세요.")
            return
        d = sel[0]
        h, p = self.h_var.get().strip(), self.p_var.get().strip()
        if not h:
            messagebox.showinfo(APP_NAME, "병원명을 입력해주세요.")
            return
        self._write_meta(d, h, p)
        target = os.path.join(self.lib, self._safe(f"{h} {p}".strip()))
        if os.path.normcase(target) != os.path.normcase(d) and not os.path.exists(target):
            try:
                os.rename(d, target)
                d = target
            except OSError:
                pass
        self.reload(select=d)

    # ── 만들기 ──
    def _run(self):
        if self.worker and self.worker.is_alive():
            return
        sel = list(self.tree.selection())
        if not sel:
            messagebox.showinfo(APP_NAME, "만들 항목을 먼저 선택해주세요.")
            return
        try:
            count, lo, hi = int(self.count.get()), int(self.lmin.get()), int(self.lmax.get())
        except Exception:
            messagebox.showwarning(APP_NAME, "숫자 칸을 확인해주세요.")
            return
        if lo > hi:
            lo, hi = hi, lo
        key = "img" if self.is_img else "th"
        self.app.settings.update({f"{key}_count": count, f"{key}_min": lo, f"{key}_max": hi})
        jobs = []
        for d in sel:
            files = core.list_images(d)
            if files:
                jobs.append((d, files))
        if not jobs:
            messagebox.showinfo(APP_NAME, "선택한 항목에 이미지가 없습니다.")
            return
        desktop = known_folder("desktop")
        self.prog.config(maximum=count * len(jobs), value=0)
        self.run_btn.config(state="disabled")
        self.result.config(text="만드는 중...")

        def work():
            done = 0
            outs = []
            try:
                for d, files in jobs:
                    top = core.next_numbered_dir(desktop, self._out_base(d))
                    out = os.path.join(top, "output") if self.is_img else top
                    base = done
                    core.generate_set(files, out, count, lo, hi,
                                      progress=lambda i, b=base: self.q.put(("prog", b + i)))
                    done += count
                    outs.append(out)
                self.q.put(("done", outs, None))
            except Exception as e:
                self.q.put(("done", outs, str(e)))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self._poll()

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "prog":
                    self.prog["value"] = msg[1]
                else:
                    _, outs, err = msg
                    self.run_btn.config(state="normal")
                    names = "\n".join("바탕화면\\" + os.path.relpath(o, known_folder("desktop")) for o in outs)
                    self.result.config(text=(f"완료: {len(outs)}개 폴더\n{names}" if outs else "") +
                                       (f"\n오류: {err}" if err else ""))
                    if outs:
                        self.last_out = outs[-1]
                        self.open_btn.config(state="normal")
                    self._on_select()
                    if err:
                        messagebox.showerror(APP_NAME, f"만드는 중 문제가 생겼습니다.\n{err}")
                    return
        except queue.Empty:
            pass
        self.after(80, self._poll)


# ════════════════════════════ 메인 창 ════════════════════════════

class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        root.title(f"{APP_NAME} {VERSION}")
        root.geometry(self.settings.get("geometry", "1200x780"))
        root.minsize(980, 640)

        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            pass
        root.option_add("*Font", FONT)
        style.configure(".", font=FONT)
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", font=FONT_B)
        style.configure("TNotebook.Tab", padding=(14, 6))

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.text_tab = TextTab(nb, self)
        self.image_tab = ImageTab(nb, self)
        self.cap_tab = LibraryTab(nb, self, "image")
        self.thumb_tab = LibraryTab(nb, self, "thumb")
        nb.add(self.text_tab, text="   텍스트 정리   ")
        nb.add(self.image_tab, text="   이미지 관리   ")
        nb.add(self.cap_tab, text="   이미지 캡쳐   ")
        nb.add(self.thumb_tab, text="   썸네일   ")
        try:
            nb.select(self.settings.get("tab", 0))
        except Exception:
            pass
        self.nb = nb

        self.status_lbl = ttk.Label(root, text="준비", anchor="w", padding=(10, 4))
        self.status_lbl.pack(fill="x")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def status(self, msg):
        self.status_lbl.config(text=msg)

    def on_close(self):
        try:
            self.image_tab._remember()
        except Exception:
            pass
        self.settings["geometry"] = self.root.geometry()
        try:
            self.settings["tab"] = self.nb.index(self.nb.select())
        except Exception:
            pass
        save_settings(self.settings)
        self.root.destroy()


def main():
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    app = App(root)
    if "--selftest" in sys.argv:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

        def test():
            try:
                run_test()
            except Exception:
                import traceback
                traceback.print_exc()
                sys.exitcode = 1
            finally:
                root.destroy()

        def run_test():
            import tempfile
            from PIL import Image
            tmp = tempfile.mkdtemp()
            # 원고 검사
            p = os.path.join(tmp, "01_서울역피부과 원고.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("서울역피부과 안내입니다. 전문 상담과 자료를 준비했어요. 서울역피부과")
            app.text_tab.check.add_paths([tmp])
            row = app.text_tab.check.tree.item(app.text_tab.check.tree.get_children()[0], "values")
            print("check:", row, flush=True)
            # 순위 정리
            app.text_tab.rank_in.insert("1.0", "서울역피부과\thttps://blog.naver.com/a/1\t8\t나음피부과")
            app.text_tab._rank_changed()
            print("rank:", app.text_tab.rank_out.get("1.0", "end-1c"), flush=True)
            # 랜덤 캡쳐
            src = os.path.join(tmp, "나음피부과-수술흉터제거")
            os.makedirs(src)
            Image.effect_mandelbrot((1400, 1000), (-2, -1.5, 1, 1.5), 60).convert("RGB").save(os.path.join(src, "a.jpg"))
            made = core.generate_set(core.list_images(src), os.path.join(tmp, "out"), 3, 800, 900)
            print("made:", [m[2] for m in made], flush=True)
            print("dnd:", bool(TkinterDnD), "docs:", known_folder("documents"), "desktop:", known_folder("desktop"), flush=True)
            print("selftest ok", flush=True)
        root.after(800, test)
    root.mainloop()
    if getattr(sys, "exitcode", 0):
        sys.exit(1)


if __name__ == "__main__":
    main()
