"""업무 도우미 - 텍스트 정리 / 이미지 관리 / 화면 캡쳐"""
import json
import os
import queue
import sys
import threading
import time
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import core

APP_NAME = "업무 도우미"
VERSION = "1.0.0"

# ── 윈도우 고해상도(배율) 대응: 캡쳐 좌표가 실제 픽셀과 맞도록 ──
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

try:
    from pynput import keyboard as pkeyboard
except Exception:
    pkeyboard = None

FONT = ("맑은 고딕", 10)
FONT_B = ("맑은 고딕", 10, "bold")
MONO = ("맑은 고딕", 11)


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
        nb.add(self._build_count(nb), text="  글자수·키워드  ")
        nb.add(self._build_wrap(nb), text="  줄바꿈·형식 정리  ")
        nb.add(self._build_report(nb), text="  메모 → 보고서  ")

    # ── 글자수·키워드 ──
    def _build_count(self, nb):
        f = ttk.Frame(nb, padding=8)
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="키워드(쉼표로 구분)").pack(side="left")
        self.kw_var = tk.StringVar(value=self.app.settings.get("keywords", ""))
        e = ttk.Entry(top, textvariable=self.kw_var, width=50)
        e.pack(side="left", padx=6, fill="x", expand=True)
        self.kw_var.trace_add("write", lambda *a: self._update_count())
        ttk.Button(top, text="파일 열기", command=self._open_count_file).pack(side="left")

        body = ttk.PanedWindow(f, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(8, 0))
        left, self.count_text = text_box(body)
        body.add(left, weight=3)
        right = ttk.Frame(body, padding=(10, 0))
        body.add(right, weight=1)
        self.count_text.bind("<<Modified>>", self._on_count_modified)

        ttk.Label(right, text="결과", font=FONT_B).pack(anchor="w")
        self.stat_lbl = ttk.Label(right, text="", justify="left", font=MONO)
        self.stat_lbl.pack(anchor="w", pady=(4, 10))
        self.kw_tree = ttk.Treeview(right, columns=("kw", "n"), show="headings", height=12)
        self.kw_tree.heading("kw", text="키워드")
        self.kw_tree.heading("n", text="횟수")
        self.kw_tree.column("kw", width=140)
        self.kw_tree.column("n", width=50, anchor="center")
        self.kw_tree.pack(fill="both", expand=True)
        self._update_count()
        return f

    def _open_count_file(self):
        p = filedialog.askopenfilename(filetypes=[("텍스트", "*.txt"), ("모든 파일", "*.*")])
        if p:
            self.count_text.delete("1.0", "end")
            self.count_text.insert("1.0", read_text_file(p))

    def _on_count_modified(self, _e):
        if self.count_text.edit_modified():
            self._update_count()
            self.count_text.edit_modified(False)

    def _update_count(self):
        text = self.count_text.get("1.0", "end-1c")
        kws = [k for k in self.kw_var.get().split(",") if k.strip()]
        self.app.settings["keywords"] = self.kw_var.get()
        s = core.count_stats(text, kws)
        self.stat_lbl.config(text=(
            f"공백 제외 : {s['no_space']:,}자\n"
            f"공백 포함 : {s['with_space']:,}자\n"
            f"문단 수   : {s['paragraphs']}개\n"
            f"줄 수     : {s['lines']}줄"))
        self.kw_tree.delete(*self.kw_tree.get_children())
        for k, n in s["keywords"]:
            self.kw_tree.insert("", "end", values=(k, n))

    # ── 줄바꿈·형식 정리 ──
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
        ttk.Button(opt, text="결과 저장", command=lambda: self._save(self.wrap_out)).pack(side="left", padx=4)
        ttk.Label(f, text="'-', '#', '[' 로 시작하는 줄(요약·소제목·이미지 표시)은 그대로 둡니다.",
                  foreground="#666").pack(anchor="w", pady=(6, 0))

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

    # ── 메모 → 보고서 ──
    def _build_report(self, nb):
        f = ttk.Frame(nb, padding=8)
        form = ttk.Frame(f)
        form.pack(fill="x")
        self.rp_kind = tk.StringVar(value="업무 보고서")
        self.rp_title = tk.StringVar()
        self.rp_author = tk.StringVar(value=self.app.settings.get("author", ""))
        self.rp_date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.rp_extra = tk.StringVar()
        ttk.Label(form, text="양식").grid(row=0, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.rp_kind, values=list(core.REPORT_KINDS),
                     state="readonly", width=14).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(form, text="제목").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(form, textvariable=self.rp_title, width=36).grid(row=0, column=3, sticky="we", padx=4)
        ttk.Label(form, text="작성자").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.rp_author, width=16).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(form, text="날짜").grid(row=1, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(form, textvariable=self.rp_date, width=14).grid(row=1, column=3, sticky="w", padx=4)
        ttk.Label(form, text="비고/참석자").grid(row=2, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.rp_extra, width=50).grid(row=2, column=1, columnspan=3, sticky="we", padx=4)
        form.columnconfigure(3, weight=1)

        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=6)
        ttk.Label(bar, text="메모는 한 줄에 하나씩. '#'로 시작하거나 ':'로 끝나는 줄은 항목 제목이 됩니다.",
                  foreground="#666").pack(side="left")
        ttk.Button(bar, text="결과 저장", command=lambda: self._save(self.rp_out)).pack(side="right")
        ttk.Button(bar, text="결과 복사", command=lambda: self._copy(self.rp_out)).pack(side="right", padx=4)
        ttk.Button(bar, text="보고서 만들기 ▶", command=self._do_report).pack(side="right")

        body = ttk.PanedWindow(f, orient="horizontal")
        body.pack(fill="both", expand=True)
        lf, self.rp_in = text_box(body)
        rf, self.rp_out = text_box(body)
        body.add(lf, weight=1)
        body.add(rf, weight=1)
        self.rp_in.insert("1.0", "# 진행 사항\n거래처 미팅 완료\n견적서 발송\n# 예정 사항\n다음 주 계약 검토")
        return f

    def _do_report(self):
        self.app.settings["author"] = self.rp_author.get()
        res = core.make_report(self.rp_kind.get(), self.rp_title.get(), self.rp_author.get(),
                               self.rp_date.get(), self.rp_in.get("1.0", "end-1c"), self.rp_extra.get())
        self.rp_out.delete("1.0", "end")
        self.rp_out.insert("1.0", res)

    # ── 공용 ──
    def _copy(self, box):
        copy_to_clipboard(self.app.root, box.get("1.0", "end-1c"))
        self.app.status("클립보드에 복사했습니다.")

    def _save(self, box):
        p = filedialog.asksaveasfilename(defaultextension=".txt",
                                         initialfile=datetime.now().strftime("정리_%Y%m%d_%H%M.txt"),
                                         filetypes=[("텍스트", "*.txt")])
        if p:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(box.get("1.0", "end-1c"))
            self.app.status(f"저장했습니다: {p}")


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


# ════════════════════════════ 화면 캡쳐 ════════════════════════════

def virtual_screen():
    """(left, top, width, height) 모든 모니터를 합친 영역"""
    if sys.platform == "win32":
        import ctypes
        u = ctypes.windll.user32
        return u.GetSystemMetrics(76), u.GetSystemMetrics(77), u.GetSystemMetrics(78), u.GetSystemMetrics(79)
    return 0, 0, 1920, 1080


def primary_screen():
    if sys.platform == "win32":
        import ctypes
        u = ctypes.windll.user32
        return 0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    return 0, 0, 1920, 1080


def grab(bbox):
    from PIL import ImageGrab
    x, y, w, h = bbox
    return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)


class RegionPicker(tk.Toplevel):
    """화면 위에 반투명 판을 깔고 드래그로 영역 선택"""

    def __init__(self, root, callback):
        super().__init__(root)
        from PIL import ImageTk, ImageEnhance
        self.callback = callback
        vx, vy, vw, vh = virtual_screen()
        self.vx, self.vy = vx, vy
        shot = grab((vx, vy, vw, vh))
        self.bg = ImageTk.PhotoImage(ImageEnhance.Brightness(shot).enhance(0.55))
        self.bright = ImageTk.PhotoImage(shot)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.c = tk.Canvas(self, width=vw, height=vh, highlightthickness=0, cursor="cross")
        self.c.pack()
        self.c.create_image(0, 0, image=self.bg, anchor="nw")
        self.crop = self.c.create_image(0, 0, image=self.bright, anchor="nw", state="hidden")
        self.rect = self.c.create_rectangle(0, 0, 0, 0, outline="#ff3b30", width=2)
        self.info = self.c.create_text(20, 20, anchor="nw", fill="white", font=("맑은 고딕", 14, "bold"),
                                       text="드래그해서 캡쳐할 영역을 선택하세요  (ESC 취소)")
        self.start = None
        self.c.bind("<ButtonPress-1>", self._down)
        self.c.bind("<B1-Motion>", self._move)
        self.c.bind("<ButtonRelease-1>", self._up)
        self.bind("<Escape>", lambda e: self._finish(None))
        self.focus_force()
        self.grab_set()

    def _down(self, e):
        self.start = (e.x, e.y)

    def _move(self, e):
        if not self.start:
            return
        x0, y0 = self.start
        self.c.coords(self.rect, x0, y0, e.x, e.y)
        w, h = abs(e.x - x0), abs(e.y - y0)
        self.c.itemconfig(self.info, text=f"{w} × {h}")
        self.c.coords(self.info, min(x0, e.x), max(0, min(y0, e.y) - 28))

    def _up(self, e):
        if not self.start:
            return
        x0, y0 = self.start
        x1, y1 = min(x0, e.x), min(y0, e.y)
        w, h = abs(e.x - x0), abs(e.y - y0)
        if w < 5 or h < 5:
            self.start = None
            return
        self._finish((x1 + self.vx, y1 + self.vy, w, h))

    def _finish(self, region):
        self.grab_release()
        self.destroy()
        self.callback(region)


class CaptureTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=12)
        self.app = app
        s = app.settings
        self.region = tuple(s["cap_region"]) if s.get("cap_region") else None
        self.running = False
        self.job = None
        self.count = 0
        self.prev = None
        self.seq = s.get("cap_seq", 1)

        g1 = ttk.LabelFrame(self, text=" 캡쳐 범위 ", padding=10)
        g1.pack(fill="x")
        self.area = tk.StringVar(value=s.get("cap_area", "지정 영역"))
        for i, name in enumerate(("지정 영역", "주 모니터", "모든 모니터")):
            ttk.Radiobutton(g1, text=name, value=name, variable=self.area).grid(row=0, column=i, padx=6, sticky="w")
        ttk.Button(g1, text="영역 선택", command=self._pick).grid(row=0, column=3, padx=12)
        self.region_lbl = ttk.Label(g1, text="")
        self.region_lbl.grid(row=0, column=4, sticky="w")
        self._show_region()

        g2 = ttk.LabelFrame(self, text=" 반복 설정 ", padding=10)
        g2.pack(fill="x", pady=10)
        ttk.Label(g2, text="간격(초)").grid(row=0, column=0, sticky="w")
        self.interval = tk.DoubleVar(value=s.get("cap_interval", 2.0))
        ttk.Spinbox(g2, from_=0.2, to=3600, increment=0.5, textvariable=self.interval, width=7).grid(row=0, column=1, padx=6)
        ttk.Label(g2, text="장수(0 = 멈출 때까지)").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.max_n = tk.IntVar(value=s.get("cap_max", 0))
        ttk.Spinbox(g2, from_=0, to=100000, textvariable=self.max_n, width=7).grid(row=0, column=3, padx=6)
        self.skip_same = tk.BooleanVar(value=s.get("cap_skip", True))
        ttk.Checkbutton(g2, text="화면이 그대로면 저장 안 함", variable=self.skip_same).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.minimize = tk.BooleanVar(value=s.get("cap_min", True))
        ttk.Checkbutton(g2, text="시작하면 이 창 최소화", variable=self.minimize).grid(row=1, column=2, columnspan=2, sticky="w", pady=(8, 0))

        g3 = ttk.LabelFrame(self, text=" 저장 ", padding=10)
        g3.pack(fill="x")
        ttk.Label(g3, text="폴더").grid(row=0, column=0, sticky="w")
        default_dir = os.path.join(os.path.expanduser("~"), "Pictures", "업무캡쳐")
        self.out_dir = tk.StringVar(value=s.get("cap_out", default_dir))
        ttk.Entry(g3, textvariable=self.out_dir, width=50).grid(row=0, column=1, columnspan=3, sticky="we", padx=6)
        ttk.Button(g3, text="찾기", command=self._pick_dir).grid(row=0, column=4)
        ttk.Button(g3, text="열기", command=lambda: (os.makedirs(self.out_dir.get(), exist_ok=True),
                                                    open_folder(self.out_dir.get()))).grid(row=0, column=5, padx=4)
        ttk.Label(g3, text="파일 이름 앞부분").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.prefix = tk.StringVar(value=s.get("cap_prefix", "캡쳐"))
        ttk.Entry(g3, textvariable=self.prefix, width=16).grid(row=1, column=1, sticky="w", padx=6, pady=(8, 0))
        ttk.Label(g3, text="형식").grid(row=1, column=2, sticky="e", pady=(8, 0))
        self.fmt = tk.StringVar(value=s.get("cap_fmt", "PNG"))
        ttk.Combobox(g3, textvariable=self.fmt, values=["PNG", "JPG"], state="readonly", width=6).grid(
            row=1, column=3, sticky="w", padx=6, pady=(8, 0))
        g3.columnconfigure(1, weight=1)

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=14)
        self.start_btn = ttk.Button(bar, text="  반복 캡쳐 시작  ", command=self.toggle)
        self.start_btn.pack(side="left")
        ttk.Button(bar, text="  지금 1장  ", command=self.capture_once).pack(side="left", padx=8)
        self.state_lbl = ttk.Label(bar, text="대기 중", font=FONT_B)
        self.state_lbl.pack(side="left", padx=12)

        hk = ("단축키:  F9 = 지금 1장   ·   F10 = 반복 캡쳐 시작/멈춤   (다른 프로그램을 보고 있어도 동작)"
              if pkeyboard else "단축키를 쓸 수 없는 환경입니다. 버튼으로 사용해주세요.")
        ttk.Label(self, text=hk, foreground="#666").pack(anchor="w")
        self.last_lbl = ttk.Label(self, text="", foreground="#0a5")
        self.last_lbl.pack(anchor="w", pady=(6, 0))

    def _show_region(self):
        if self.region:
            x, y, w, h = self.region
            self.region_lbl.config(text=f"선택됨: {w}×{h}  (위치 {x},{y})")
        else:
            self.region_lbl.config(text="아직 선택 안 함")

    def _pick(self):
        self.app.root.withdraw()
        self.app.root.after(250, lambda: RegionPicker(self.app.root, self._picked))

    def _picked(self, region):
        self.app.root.deiconify()
        if region:
            self.region = region
            self.area.set("지정 영역")
            self.app.settings["cap_region"] = list(region)
        self._show_region()

    def _pick_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.out_dir.set(d)

    def _bbox(self):
        a = self.area.get()
        if a == "주 모니터":
            return primary_screen()
        if a == "모든 모니터":
            return virtual_screen()
        return self.region

    def _remember(self):
        s = self.app.settings
        s.update(cap_area=self.area.get(), cap_interval=float(self.interval.get()), cap_max=int(self.max_n.get()),
                 cap_skip=self.skip_same.get(), cap_min=self.minimize.get(), cap_out=self.out_dir.get(),
                 cap_prefix=self.prefix.get(), cap_fmt=self.fmt.get(), cap_seq=self.seq)

    def _save_shot(self, check_same=False):
        bbox = self._bbox()
        if not bbox:
            self.app.root.deiconify()
            messagebox.showinfo(APP_NAME, "'영역 선택'으로 캡쳐할 부분을 먼저 정해주세요.")
            return False
        img = grab(bbox)
        if check_same and self.prev is not None:
            from PIL import ImageChops
            if img.size == self.prev.size and ImageChops.difference(img.convert("RGB"), self.prev.convert("RGB")).getbbox() is None:
                return None
        self.prev = img
        d = self.out_dir.get().strip()
        os.makedirs(d, exist_ok=True)
        ext = ".jpg" if self.fmt.get() == "JPG" else ".png"
        name = f"{self.prefix.get().strip() or '캡쳐'}_{datetime.now():%Y%m%d}_{self.seq:04d}{ext}"
        path = core._unique(os.path.join(d, name))
        if ext == ".jpg":
            img.convert("RGB").save(path, "JPEG", quality=92)
        else:
            img.save(path, "PNG")
        self.seq += 1
        self.last_lbl.config(text=f"저장: {os.path.basename(path)}")
        return True

    def capture_once(self):
        try:
            self._remember()
            self._save_shot()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"캡쳐 실패: {e}")

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        if not self._bbox():
            messagebox.showinfo(APP_NAME, "'영역 선택'으로 캡쳐할 부분을 먼저 정해주세요.")
            return
        try:
            self._remember()
        except Exception:
            messagebox.showwarning(APP_NAME, "간격·장수 숫자를 확인해주세요.")
            return
        self.running = True
        self.count = 0
        self.prev = None
        self.start_btn.config(text="  멈춤  ")
        self.state_lbl.config(text="캡쳐 중...", foreground="#d00")
        if self.minimize.get():
            self.app.root.iconify()
        self.job = self.after(400, self._tick)

    def _tick(self):
        if not self.running:
            return
        try:
            r = self._save_shot(check_same=self.skip_same.get())
            if r:
                self.count += 1
            self.state_lbl.config(text=f"캡쳐 중... {self.count}장")
        except Exception as e:
            self.stop()
            messagebox.showerror(APP_NAME, f"캡쳐 실패: {e}")
            return
        mx = int(self.max_n.get() or 0)
        if mx and self.count >= mx:
            self.stop()
            return
        ms = max(200, int(float(self.interval.get()) * 1000))
        self.job = self.after(ms, self._tick)

    def stop(self):
        self.running = False
        if self.job:
            self.after_cancel(self.job)
            self.job = None
        self.start_btn.config(text="  반복 캡쳐 시작  ")
        self.state_lbl.config(text=f"멈춤 · {self.count}장 저장", foreground="")
        self._remember()
        self.app.root.deiconify()


# ════════════════════════════ 메인 창 ════════════════════════════

class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        root.title(f"{APP_NAME} {VERSION}")
        root.geometry(self.settings.get("geometry", "1100x720"))
        root.minsize(900, 600)

        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            pass
        root.option_add("*Font", FONT)
        style.configure(".", font=FONT)
        style.configure("Treeview.Heading", font=FONT_B)
        style.configure("TNotebook.Tab", padding=(14, 6))

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.text_tab = TextTab(nb, self)
        self.image_tab = ImageTab(nb, self)
        self.capture_tab = CaptureTab(nb, self)
        nb.add(self.text_tab, text="   텍스트 정리   ")
        nb.add(self.image_tab, text="   이미지 관리   ")
        nb.add(self.capture_tab, text="   화면 캡쳐   ")
        nb.select(self.settings.get("tab", 0))
        self.nb = nb

        self.status_lbl = ttk.Label(root, text="준비", anchor="w", padding=(10, 4))
        self.status_lbl.pack(fill="x")

        self.hk_q = queue.Queue()
        self.listener = None
        if pkeyboard:
            try:
                self.listener = pkeyboard.GlobalHotKeys({
                    "<f9>": lambda: self.hk_q.put("once"),
                    "<f10>": lambda: self.hk_q.put("toggle"),
                })
                self.listener.daemon = True
                self.listener.start()
            except Exception:
                self.listener = None
        self._poll_hotkeys()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _poll_hotkeys(self):
        try:
            while True:
                cmd = self.hk_q.get_nowait()
                if cmd == "once":
                    self.capture_tab.capture_once()
                elif cmd == "toggle":
                    self.capture_tab.toggle()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_hotkeys)

    def status(self, msg):
        self.status_lbl.config(text=msg)

    def on_close(self):
        try:
            if self.capture_tab.running:
                self.capture_tab.stop()
            self.capture_tab._remember()
            self.image_tab._remember()
        except Exception:
            pass
        self.settings["geometry"] = self.root.geometry()
        try:
            self.settings["tab"] = self.nb.index(self.nb.select())
        except Exception:
            pass
        save_settings(self.settings)
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    if "--selftest" in sys.argv:
        # 빌드 확인용: 창을 띄웠다가 각 기능을 한 번씩 돌리고 종료
        def test():
            app.text_tab.count_text.insert("1.0", "테스트 문장입니다. 키워드 테스트.")
            app.text_tab._update_count()
            app.text_tab.wrap_in.insert("1.0", "첫 문장입니다. 두 번째 문장은 조금 길게 써서 줄이 나뉘는지 봅니다.")
            app.text_tab._do_wrap()
            app.text_tab._do_report()
            img = grab(primary_screen())
            print("selftest ok", img.size, flush=True)
            root.destroy()
        root.after(800, test)
    root.mainloop()


if __name__ == "__main__":
    main()
