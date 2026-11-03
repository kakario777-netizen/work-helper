"""업무 도우미 - 텍스트 정리 탭"""
import os
import tkinter as tk
from tkinter import ttk, filedialog

import core
from common import (GRAY, FONT_B, text_box, copy_to_clipboard, enable_drop, drop_hint, read_text_file, Paned, help_label)


class TextTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.nb = nb
        self.check = CheckPanel(nb, app)
        # 세부 탭: 키 → (화면, 이름)   설정에서 순서·숨기기 조절
        self.subs = {
            "check": (self.check, "원고 검사"),
            "report": (self._build_rank(nb), "보고서 정리"),
            "nate": (self._build_nate(nb), "네이트온 보고서 정리"),
            "wrap": (self._build_wrap(nb), "줄바꿈 정리"),
        }
        self.apply_layout(app.settings.get("sub_order"), app.settings.get("sub_hidden"))

    def apply_layout(self, order=None, hidden=None):
        order = [k for k in (order or []) if k in self.subs] + [k for k in self.subs if k not in (order or [])]
        hidden = set(hidden or [])
        for w in self.nb.tabs():
            self.nb.forget(w)
        shown = [k for k in order if k not in hidden] or order[:1]
        for k in shown:
            w, name = self.subs[k]
            self.nb.add(w, text=f"  {name}  ")

    # ── 네이트온 보고서 정리 (링크·키워드 → 키워드<탭>링크) ──
    def _build_nate(self, nb):
        f = ttk.Frame(nb, padding=8)
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Label(bar, text="네이트온 긁어서 삽입", font=FONT_B).pack(side="left")
        help_label(bar, "네이트온 대화에서 링크와 키워드를 그대로 긁어 왼쪽에 붙여넣고 '변환 ▶'을 누르세요.\n"
                        "링크 바로 뒤(같은 줄) 또는 그 다음 줄의 글자를 키워드로 봅니다.\n"
                        "오른쪽 결과는 '키워드 [탭] 링크' 형태라 엑셀에 붙이면 두 칸으로 나뉩니다.\n"
                        "결과도 직접 고칠 수 있어요.").pack(side="left", padx=8)
        ttk.Label(bar, text="결과 (수정 가능)", font=FONT_B).pack(side="right")

        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=(6, 0))
        lf, self.nate_in = text_box(body)
        rf, self.nate_out = text_box(body)
        self.nate_in.configure(wrap="none")
        self.nate_out.configure(wrap="none", tabs=("200",))
        mid = ttk.Frame(body, padding=8)
        lf.pack(side="left", fill="both", expand=True)
        mid.pack(side="left", fill="y")
        rf.pack(side="left", fill="both", expand=True)
        ttk.Button(mid, text="변환 ▶", style="Big.TButton", command=self._do_nate).pack(pady=(80, 10), ipady=4)
        ttk.Button(mid, text="결과 복사", command=lambda: self._copy(self.nate_out)).pack(fill="x")
        ttk.Button(mid, text="모두 지우기", command=self._clear_nate).pack(fill="x", pady=6)
        self.nate_info = ttk.Label(f, text="", width=20, anchor="e")
        self.nate_info.pack(anchor="e", pady=(4, 0))
        return f

    def _do_nate(self):
        res = core.convert_nateon(self.nate_in.get("1.0", "end-1c"))
        self.nate_out.delete("1.0", "end")
        self.nate_out.insert("1.0", res)
        n = len(res.splitlines()) if res else 0
        self.nate_info.config(text=f"{n}줄 변환")

    def _clear_nate(self):
        self.nate_in.delete("1.0", "end")
        self.nate_out.delete("1.0", "end")
        self.nate_info.config(text="")

    # ── 보고서 정리(순위표 → 링크 [병원명] 키워드) ──
    def _build_rank(self, nb):
        f = ttk.Frame(nb, padding=8)
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Label(bar, text="왼쪽에 '키워드  링크  순위  병원명' 표를 붙여넣으면 오른쪽에 '링크 [병원명] 키워드'로 바로 바뀝니다.",
                  foreground=GRAY).pack(side="left")
        ttk.Button(bar, text="결과 복사", command=lambda: self._copy(self.rank_out)).pack(side="right")
        ttk.Button(bar, text="지우기", command=lambda: self.rank_in.delete("1.0", "end")).pack(side="right", padx=4)
        body = Paned(f, self.app, "text_report")
        body.pack(fill="both", expand=True, pady=(6, 0))
        lf, self.rank_in = text_box(body)
        rf, self.rank_out = text_box(body)
        self.rank_in.configure(wrap="none")
        self.rank_out.configure(wrap="none")
        body.add(lf, weight=1)
        body.add(rf, weight=1)
        self.rank_info = ttk.Label(f, text="", width=14, anchor="e")
        self.rank_info.pack(anchor="e", pady=(4, 0))
        self.rank_in.bind("<<Modified>>", self._rank_changed)
        return f

    def _rank_changed(self, _e=None):
        # 타자 칠 때마다 바로 다시 그리면 화면이 흔들리므로, 손을 멈추면 한 번만 변환
        if not self.rank_in.edit_modified():
            return
        self.rank_in.edit_modified(False)
        if getattr(self, "_rank_job", None):
            self.after_cancel(self._rank_job)
        self._rank_job = self.after(300, self._do_rank)

    def _do_rank(self):
        self._rank_job = None
        res = core.convert_rank(self.rank_in.get("1.0", "end-1c"))
        if res != self.rank_out.get("1.0", "end-1c"):
            y = self.rank_out.yview()[0]
            self.rank_out.delete("1.0", "end")
            self.rank_out.insert("1.0", res)
            self.rank_out.yview_moveto(y)
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
        self.wrap_first = tk.BooleanVar(value=self.app.settings.get("wrap_first", True))
        ttk.Checkbutton(opt, text="문단 첫 문장은 한 줄 유지", variable=self.wrap_first).pack(side="left", padx=4)
        self.wrap_sent = tk.BooleanVar(value=self.app.settings.get("wrap_sent", False))
        ttk.Checkbutton(opt, text="문장마다 빈 줄", variable=self.wrap_sent).pack(side="left", padx=4)
        ttk.Button(opt, text="정리하기 ▶", command=self._do_wrap).pack(side="left", padx=12)
        ttk.Button(opt, text="결과 복사", command=lambda: self._copy(self.wrap_out)).pack(side="left")
        ttk.Label(f, text="'-', '#', '[' 로 시작하는 줄(요약·소제목·이미지 표시)은 그대로 둡니다.",
                  foreground=GRAY).pack(anchor="w", pady=(6, 0))
        body = Paned(f, self.app, "text_wrap")
        body.pack(fill="both", expand=True, pady=(6, 0))
        lf, self.wrap_in = text_box(body)
        rf, self.wrap_out = text_box(body)
        body.add(lf, weight=1)
        body.add(rf, weight=1)
        self.wrap_info = ttk.Label(f, text="", width=34, anchor="e")
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

    def remember(self):
        try:
            self.app.settings["wrap_width"] = int(self.wrap_w.get())
            self.app.settings["wrap_first"] = self.wrap_first.get()
            self.app.settings["wrap_sent"] = self.wrap_sent.get()
            self.app.settings["forbidden"] = self.check.forbid.get()
        except Exception:
            pass

    def _copy(self, box):
        copy_to_clipboard(self.app.root, box.get("1.0", "end-1c"))
        self.app.status("클립보드에 복사했습니다.")


class CheckPanel(ttk.Frame):
    """메모장 원고 여러 개를 끌어다 놓으면 파일별 글자수·키워드 수·금지어를 표로"""
    COLS = (("file", "파일", 180, "w"), ("kw", "키워드 (더블클릭해서 수정)", 170, "w"),
            ("title", "제목", 300, "w"), ("kwn", "키워드 수", 110, "center"), ("ns", "공백 제외", 80, "center"),
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
        self._ref_job = None
        self.forbid.trace_add("write", lambda *a: self._refresh_later())

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(8, 4))
        ttk.Label(bar, text=f"메모장(.txt) 파일이나 폴더를 {drop_hint()}버튼으로 추가하세요.",
                  foreground=GRAY).pack(side="left")
        for txt, cmd in (("표 복사", self.copy_table), ("다시 읽기", self.reload), ("비우기", self.clear),
                         ("선택 삭제", self.remove_sel), ("폴더 추가", self.add_folder), ("파일 추가", self.add_files)):
            ttk.Button(bar, text=txt, command=cmd).pack(side="right", padx=2)

        pw = Paned(self, app, "text_check", orient="vertical")
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
        pw.add(tf, weight=1, height=330)

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
        pw.add(pf, weight=1)

        self.summary = ttk.Label(self, text="", width=40, anchor="w")
        self.summary.pack(anchor="w", pady=(4, 0))

        for w in (self.tree, self):
            enable_drop(w, self.add_paths)

    # ── 파일 추가 ──
    def add_paths(self, paths):
        files = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, fs in os.walk(p):
                    files += [os.path.join(root, f) for f in core.natural_sorted(fs) if f.lower().endswith(".txt")]
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
        self.tree.item(iid, values=(os.path.basename(d["path"]), d["kw"], core.guess_title(d["text"]), kwn,
                                    f"{st['no_space']:,}", f"{st['with_space']:,}", badtxt), tags=tags)

    def _refresh_later(self):
        if self._ref_job:
            self.after_cancel(self._ref_job)
        self._ref_job = self.after(400, self.refresh_all)

    def refresh_all(self):
        self._ref_job = None
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
        if not sel or sel[0] not in self.docs:
            self.preview.delete("1.0", "end")
            self._shown = None
            return
        d = self.docs[sel[0]]
        self.kw_edit.set(d["kw"])
        # 같은 원고면 글은 그대로 두고 색칠만 다시 (깜빡임 방지)
        if getattr(self, "_shown", None) != (sel[0], d["text"]):
            self.preview.delete("1.0", "end")
            self.preview.insert("1.0", d["text"])
            self._shown = (sel[0], d["text"])
        for tag in ("kw", "bad"):
            self.preview.tag_remove(tag, "1.0", "end")
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

