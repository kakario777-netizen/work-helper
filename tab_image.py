"""업무 도우미 - 이미지 관리 탭 (대량 크기·포맷·이름·색감)"""
import os
import queue
import random
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import core
from common import (APP_NAME, GRAY, FONT_B, enable_drop, drop_hint, open_folder, AdjustPanel, Preview, Paned)


class ImageTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.files = []
        self.worker = None
        self.q = queue.Queue()
        s = app.settings

        body = Paned(self, app, "image_main")
        body.pack(fill="both", expand=True)

        # ── 왼쪽: 파일 목록 ──
        left = ttk.Frame(body)
        body.add(left, weight=1, width=330, minsize=220)
        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Button(top, text="파일 추가", command=self._add_files).pack(side="left")
        ttk.Button(top, text="폴더 추가", command=self._add_folder).pack(side="left", padx=3)
        self.sub_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="하위 폴더", variable=self.sub_var).pack(side="left")
        self.count_lbl = ttk.Label(top, text="0개")
        self.count_lbl.pack(side="right")
        ttk.Label(left, text=f"이미지·폴더를 {drop_hint()}버튼으로 추가", foreground=GRAY).pack(anchor="w", pady=(4, 0))
        lf = ttk.Frame(left)
        lf.pack(fill="both", expand=True, pady=4)
        self.tree = ttk.Treeview(lf, columns=("name", "size"), show="headings", selectmode="extended")
        self.tree.heading("name", text="파일명")
        self.tree.heading("size", text="용량")
        self.tree.column("name", width=200)
        self.tree.column("size", width=70, anchor="center")
        sb = ttk.Scrollbar(lf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._preview())
        bb = ttk.Frame(left)
        bb.pack(fill="x")
        ttk.Button(bb, text="선택 삭제", command=self._remove_sel).pack(side="left")
        ttk.Button(bb, text="목록 비우기", command=self._clear).pack(side="left", padx=3)
        enable_drop(self.tree, self._drop)
        enable_drop(left, self._drop)

        # ── 가운데: 색감 조절 ──
        mid = ttk.Frame(body, padding=(10, 0))
        body.add(mid, weight=0, width=330, minsize=240)
        mh = ttk.Frame(mid)
        mh.pack(fill="x")
        ttk.Label(mh, text="색감 조절", font=FONT_B).pack(side="left")
        self.adj_on = tk.BooleanVar(value=s.get("im_adj_on", False))
        ttk.Checkbutton(mh, text="적용", variable=self.adj_on).pack(side="left", padx=8)
        ttk.Button(mh, text="모두 0", command=lambda: self.adjust.reset()).pack(side="right")
        ttk.Button(mh, text="랜덤", command=lambda: (self.adjust.randomize(random.Random()), self.adj_on.set(True))).pack(side="right", padx=3)
        self.preview = Preview(mid, height=140)
        self.preview.pack(fill="x", pady=6)
        ttk.Label(mid, text="왼쪽: 원본  ·  오른쪽: 조절 결과", foreground=GRAY).pack(anchor="w")
        self.adjust = AdjustPanel(mid, app, "im_adjust", on_change=self._preview)
        self.adjust.pack(fill="both", expand=True, pady=(4, 0))

        # ── 오른쪽: 파일 설정 ──
        opt = ttk.Frame(body, padding=(10, 0))
        body.add(opt, weight=1, minsize=260)

        g1 = ttk.LabelFrame(opt, text=" 크기 조절·압축 ", padding=8)
        g1.pack(fill="x")
        self.rs_on = tk.BooleanVar(value=s.get("rs_on", True))
        ttk.Checkbutton(g1, text="크기 조절", variable=self.rs_on).grid(row=0, column=0, sticky="w")
        self.rs_mode = tk.StringVar(value=s.get("rs_mode", "가로 최대(px)"))
        ttk.Combobox(g1, textvariable=self.rs_mode, state="readonly", width=12,
                     values=["가로 최대(px)", "긴 변 최대(px)", "비율(%)"]).grid(row=0, column=1, padx=4)
        self.rs_val = tk.IntVar(value=s.get("rs_val", 1000))
        ttk.Spinbox(g1, from_=1, to=10000, textvariable=self.rs_val, width=6).grid(row=0, column=2)
        ttk.Label(g1, text="품질(JPG·WEBP)").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.quality = tk.IntVar(value=s.get("quality", 85))
        ttk.Spinbox(g1, from_=10, to=100, textvariable=self.quality, width=5).grid(row=1, column=1, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(g1, text="낮을수록 용량↓", foreground=GRAY).grid(row=1, column=2, sticky="w", pady=(6, 0))

        g2 = ttk.LabelFrame(opt, text=" 포맷 변환 ", padding=8)
        g2.pack(fill="x", pady=8)
        self.fmt = tk.StringVar(value=s.get("fmt", "원본 유지"))
        for i, name in enumerate(core.FORMATS):
            ttk.Radiobutton(g2, text=name, value=name, variable=self.fmt).grid(row=0, column=i, padx=3)

        g3 = ttk.LabelFrame(opt, text=" 파일명 일괄 변경 ", padding=8)
        g3.pack(fill="x")
        self.rn_on = tk.BooleanVar(value=s.get("rn_on", False))
        ttk.Checkbutton(g3, text="이름 바꾸기", variable=self.rn_on).grid(row=0, column=0, sticky="w")
        self.pattern = tk.StringVar(value=s.get("pattern", "{날짜}_{번호}"))
        ttk.Entry(g3, textvariable=self.pattern, width=20).grid(row=0, column=1, columnspan=3, sticky="we", padx=4)
        ttk.Label(g3, text="시작 번호").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.start_no = tk.IntVar(value=1)
        ttk.Spinbox(g3, from_=0, to=99999, textvariable=self.start_no, width=6).grid(row=1, column=1, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(g3, text="자릿수").grid(row=1, column=2, sticky="e", pady=(6, 0))
        self.digits = tk.IntVar(value=s.get("digits", 3))
        ttk.Spinbox(g3, from_=1, to=6, textvariable=self.digits, width=4).grid(row=1, column=3, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(g3, text="{이름} 원래 이름 · {번호} 순번 · {날짜} 오늘", foreground=GRAY).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.preview_lbl = ttk.Label(g3, text="", foreground="#0a5")
        self.preview_lbl.grid(row=3, column=0, columnspan=4, sticky="w")
        g3.columnconfigure(1, weight=1)
        for v in (self.pattern, self.start_no, self.digits, self.rn_on):
            v.trace_add("write", lambda *a: self._name_preview())

        g4 = ttk.LabelFrame(opt, text=" 저장 위치 ", padding=8)
        g4.pack(fill="x", pady=8)
        self.out_mode = tk.StringVar(value=s.get("img_out_mode", "output"))
        ttk.Radiobutton(g4, text="원본 폴더 안 'output' 폴더 (기본)", value="output",
                        variable=self.out_mode, command=self._mode_changed).pack(anchor="w")
        ttk.Radiobutton(g4, text="따로 지정한 폴더", value="custom",
                        variable=self.out_mode, command=self._mode_changed).pack(anchor="w")
        row = ttk.Frame(g4)
        row.pack(fill="x", pady=(4, 0))
        self.out_dir = tk.StringVar(value=s.get("img_out", ""))
        self.out_entry = ttk.Entry(row, textvariable=self.out_dir)
        self.out_entry.pack(side="left", fill="x", expand=True)
        self.out_btn = ttk.Button(row, text="찾기", command=self._pick_out)
        self.out_btn.pack(side="left", padx=4)
        ttk.Label(g4, text="원본 파일은 건드리지 않습니다.", foreground=GRAY).pack(anchor="w", pady=(4, 0))
        self._mode_changed()

        self.run_btn = ttk.Button(opt, text="  실행  ", command=self._run)
        self.run_btn.pack(fill="x", pady=(4, 6))
        self.prog = ttk.Progressbar(opt, mode="determinate")
        self.prog.pack(fill="x")
        self.result_lbl = ttk.Label(opt, text="", wraplength=280, justify="left")
        self.result_lbl.pack(anchor="w", pady=(6, 0))
        self._name_preview()

    # ── 목록 ──
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
            self.tree.insert("", "end", iid=p, values=(os.path.basename(p), sz))
        self.count_lbl.config(text=f"{len(self.files)}개")
        self._name_preview()
        if self.files and not self.tree.selection():
            self.tree.selection_set(self.files[0])

    def _drop(self, paths):
        out = []
        for p in paths:
            out += core.list_images(p, self.sub_var.get()) if os.path.isdir(p) else [p]
        self._add(out)

    def _add_files(self):
        self._add(filedialog.askopenfilenames(filetypes=[("이미지", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff"),
                                                         ("모든 파일", "*.*")]))

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
        self.preview.show(None, None)

    def _preview(self):
        sel = self.tree.selection()
        self.preview.show(sel[0] if sel else None, self.adjust.get, self.files)

    def _mode_changed(self):
        st = "normal" if self.out_mode.get() == "custom" else "disabled"
        self.out_entry.config(state=st)
        self.out_btn.config(state=st)

    def _pick_out(self):
        d = filedialog.askdirectory()
        if d:
            self.out_dir.set(d)

    def _name_preview(self):
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
                "pattern": self.pattern.get(), "digits": int(self.digits.get()),
                "adjust": self.adjust.get() if self.adj_on.get() else {}}

    def remember(self):
        s = self.app.settings
        try:
            s.update(rs_on=self.rs_on.get(), rs_mode=self.rs_mode.get(), rs_val=int(self.rs_val.get()),
                     quality=int(self.quality.get()), fmt=self.fmt.get(), rn_on=self.rn_on.get(),
                     pattern=self.pattern.get(), digits=int(self.digits.get()), img_out=self.out_dir.get(),
                     img_out_mode=self.out_mode.get(), im_adj_on=self.adj_on.get())
        except Exception:
            pass

    # ── 실행 ──
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
        custom = self.out_mode.get() == "custom"
        out = self.out_dir.get().strip()
        if custom and not out:
            messagebox.showinfo(APP_NAME, "저장할 폴더를 지정해주세요.")
            return
        self.remember()
        files = list(self.files)
        self.prog.config(maximum=len(files), value=0)
        self.run_btn.config(state="disabled")
        self.result_lbl.config(text="처리 중...")

        def work():
            before = after = ok = 0
            errors = []
            last_dir = None
            for i, src in enumerate(files):
                d = out if custom else os.path.join(os.path.dirname(src), "output")
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
