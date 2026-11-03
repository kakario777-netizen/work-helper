"""업무 도우미 - 이미지 관리 탭 (대량 크기·포맷·이름·색감)"""
import os
import queue
import random
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import core
from common import (APP_NAME, GRAY, FONT_B, enable_drop, drop_hint, open_folder, AdjustPanel, Preview, Paned, ScrollFrame, SizeCropPanel, RandomRangeDialog, WrapLabel, help_label)


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
        help_label(left, f"이미지 파일이나 폴더를 {drop_hint()}버튼으로 추가하세요.\n"
                         "폴더를 여러 개 한꺼번에 넣어도 됩니다.").pack(anchor="w", pady=(4, 0))
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

        # ── 가운데: 미리보기 · 색감 (길어지면 통째로 스크롤) ──
        mid = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(mid, weight=0, width=340, minsize=260)
        mh = ttk.Frame(mid)
        mh.pack(fill="x", padx=(0, 10))
        ttk.Button(mh, text="  랜덤  ", command=self._randomize).pack(side="left")
        ttk.Button(mh, text="랜덤 범위…", command=self._range_dialog).pack(side="left", padx=4)
        ttk.Button(mh, text="모두 0", command=lambda: self.adjust.reset()).pack(side="right")
        self.per_folder = tk.BooleanVar(value=s.get("im_per_folder", False))
        pf = ttk.Frame(mid)
        pf.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(pf, text="폴더별 각각 랜덤", variable=self.per_folder).pack(side="left")
        help_label(pf, "폴더를 여러 개 넣었을 때 폴더마다 '랜덤'을 새로 누른 것처럼 색감·크기 값이 정해집니다.\n"
                       "한 폴더 안의 이미지는 모두 같은 값입니다.").pack(side="left", padx=6)
        msf = ScrollFrame(mid)
        msf.pack(fill="both", expand=True, pady=(6, 0))
        m = ttk.Frame(msf.inner, padding=(0, 0, 8, 0))
        m.pack(fill="both", expand=True)
        self.preview = Preview(m, height=130)
        self.preview.pack(fill="x", pady=(0, 6))
        ch = ttk.Frame(m)
        ch.pack(fill="x", pady=(4, 2))
        ttk.Label(ch, text="색감 조절", font=FONT_B).pack(side="left")
        self.adj_on = tk.BooleanVar(value=s.get("im_adj_on", False))
        ttk.Checkbutton(ch, text="적용", variable=self.adj_on, command=self._preview).pack(side="left", padx=8)
        self.adjust = AdjustPanel(m, app, "im_adjust", on_change=self._preview, scroll=False)
        self.adjust.pack(fill="x")

        # ── 오른쪽: 파일 설정 (길어지면 스크롤) ──
        osf = ScrollFrame(body)
        body.add(osf, weight=1, minsize=280)
        opt = ttk.Frame(osf.inner, padding=(10, 0, 8, 0))
        opt.pack(fill="both", expand=True)

        self.sizer = SizeCropPanel(opt, app, "im", width=900, enable=True, on_change=self._preview_later)
        self.sizer.pack(fill="x")

        g2 = ttk.LabelFrame(opt, text=" 포맷 변환 ", padding=8)
        g2.pack(fill="x", pady=8)
        self.fmt = tk.StringVar(value=s.get("fmt", "원본 유지"))
        for i, name in enumerate(core.FORMATS):
            ttk.Radiobutton(g2, text=name, value=name, variable=self.fmt).grid(row=0, column=i, padx=3)
        ttk.Label(g2, text="품질(JPG·WEBP)").grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.quality = tk.IntVar(value=s.get("quality", 90))
        ttk.Spinbox(g2, from_=10, to=100, textvariable=self.quality, width=5).grid(row=1, column=2, sticky="w", pady=(6, 0))

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
        help_label(g3, "{이름} 원래 파일 이름 · {번호} 순번 · {날짜} 오늘 날짜\n"
                       "예: image{번호} + 자릿수 3 → image001, image002 …\n\n"
                       "번호는 폴더마다 따로 시작 번호부터 다시 셉니다.").grid(
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
        help_label(g4, "기본: 각 원본 폴더 안에 'output' 폴더를 만들어 저장합니다.\n"
                       "폴더를 여러 개 넣으면 폴더마다 자기 output 에 따로 저장됩니다.\n"
                       "원본은 '원본 삭제'를 켜지 않는 한 그대로 둡니다.").pack(anchor="w", pady=(4, 0))
        self._mode_changed()

        self.run_btn = ttk.Button(opt, text="실행", style="Big.TButton", command=self._run)
        self.run_btn.pack(fill="x", pady=(4, 4), ipady=4)
        self.del_src = tk.BooleanVar(value=s.get("im_del_src", False))
        ttk.Checkbutton(opt, text="가공해서 저장한 뒤 원본은 삭제 (휴지통으로)",
                        variable=self.del_src).pack(anchor="w", pady=(0, 8))
        self.prog = ttk.Progressbar(opt, mode="determinate")
        self.prog.pack(fill="x")
        self.result_lbl = WrapLabel(opt, text="")
        self.result_lbl.pack(fill="x", pady=(6, 0))
        self._name_preview()

    # ── 목록 ──
    def _add(self, paths):
        known = set(self.files)
        for p in core.natural_sorted(paths):
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
            if os.path.isdir(p):
                imgs = core.list_images(p, self.sub_var.get())
                out += imgs or core.list_images(p, True)   # 바로 아래에 없으면 하위 폴더까지
            else:
                out.append(p)
        self._add(out)

    def _add_files(self):
        self._add(filedialog.askopenfilenames(filetypes=[("이미지", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff"),
                                                         ("모든 파일", "*.*")]))

    def _add_folder(self):
        d = filedialog.askdirectory()
        if d:
            self._drop([d])

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

    def _preview_later(self):
        if getattr(self, "_pv_job", None):
            self.after_cancel(self._pv_job)
        self._pv_job = self.after(300, self._preview)

    def _proc_kw(self):
        g = self.sizer.get()
        return {"crop_on": g["on"], "trim": g["trim"], "aspect": g["aspect"],
                "base": self.adjust.get() if self.adj_on.get() else {}}

    def _preview(self):
        self._pv_job = None
        sel = self.tree.selection()
        kw = self._proc_kw()
        self.preview.show(sel[0] if sel else None, lambda im, sc: core.preview_process(im, sc, **kw), self.files)

    def _range_cfg(self):
        d = core.DEFAULT_RANDOM_RANGE["manage"]
        cfg = {k: list(v) for k, v in d.items()}
        cfg.update(self.app.settings.get("im_rrange", {}))
        return d, cfg

    def _range_dialog(self):
        d, _ = self._range_cfg()
        RandomRangeDialog(self, self.app, "im_rrange", d)

    def _randomize(self):
        rng = random.Random()
        self.adjust.randomize(rng)
        self.adj_on.set(True)
        if self.sizer.get()["on"]:
            self.sizer.apply_random(rng, self._range_cfg()[1])
        self._preview()

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
        """한 번 실행하는 묶음 전체에 똑같이 쓰는 조건"""
        return {"resize": False, "crop": self.sizer.get(),
                "fmt": self.fmt.get(), "quality": int(self.quality.get()), "rename": self.rn_on.get(),
                "pattern": self.pattern.get(), "digits": int(self.digits.get()),
                "adjust": self.adjust.get() if self.adj_on.get() else {}}

    def remember(self):
        s = self.app.settings
        try:
            s.update(im_per_folder=self.per_folder.get(), im_del_src=self.del_src.get(), quality=int(self.quality.get()), fmt=self.fmt.get(), rn_on=self.rn_on.get(),
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
        del_src = self.del_src.get()
        per_folder = self.per_folder.get()
        rnd_keys = [k for k, rv in self.adjust.rnd.items() if rv.get()]
        _, rcfg = self._range_cfg()
        base_adj = self.adjust.get()
        folder_opts = {}

        def opts_for(folder, rng):
            """폴더마다 '랜덤'을 새로 누른 것처럼 한 번 정하고, 그 폴더 안에서는 계속 같은 값"""
            if folder not in folder_opts:
                o = dict(opts)
                adj = dict(base_adj)
                adj.update(core.random_adjust(rng, rnd_keys))
                o["adjust"] = adj
                crop = dict(opts.get("crop") or {})
                if crop.get("on"):
                    size = core.random_size(rng, rcfg)
                    use = rcfg.get("use", {})
                    for key, u in (("width", "len"), ("trim", "trim"), ("aspect", "aspect")):
                        if use.get(u, True):
                            crop[key] = size[key]
                    o["crop"] = crop
                folder_opts[folder] = o
            return folder_opts[folder]
        if del_src and not messagebox.askyesno(
                APP_NAME, f"가공해서 저장이 끝난 원본 {len(self.files)}개를 휴지통으로 보냅니다.\n"
                          "(저장에 실패한 파일은 지우지 않습니다. 휴지통에서 되살릴 수 있어요)\n\n계속할까요?"):
            return
        self.remember()
        files = list(self.files)
        self.prog.config(maximum=len(files), value=0)
        self.run_btn.config(state="disabled")
        self.result_lbl.config(text="처리 중...")

        def work():
            import random as _random
            rng = _random.Random()
            before = after = ok = 0
            errors = []
            last_dir = None
            done_src = []
            seq = {}   # 폴더마다 따로 번호를 셈
            for i, src in enumerate(files):
                folder_key = os.path.normcase(os.path.dirname(src))
                seq[folder_key] = seq.get(folder_key, -1) + 1
                d = out if custom else os.path.join(os.path.dirname(src), "output")
                try:
                    os.makedirs(d, exist_ok=True)
                    o = opts_for(os.path.dirname(src), rng) if per_folder else opts
                    dst, b, a = core.process_image(src, d, start + seq[folder_key], o)
                    before += b
                    after += a
                    ok += 1
                    last_dir = d
                    if os.path.normcase(os.path.abspath(dst)) != os.path.normcase(os.path.abspath(src)):
                        done_src.append(src)
                except Exception as e:
                    errors.append(f"{os.path.basename(src)}: {e}")
                self.q.put(("prog", i + 1))
            removed = []
            if del_src and done_src:
                core.recycle(done_src)
                removed = [p for p in done_src if not os.path.exists(p)]
            self.q.put(("done", ok, before, after, errors, last_dir, removed, len(folder_opts)))

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
                    _, ok, b, a, errors, last_dir, removed, nfold = msg
                    self.run_btn.config(state="normal")
                    for p in removed:   # 지운 원본은 목록에서도 뺌
                        if self.tree.exists(p):
                            self.tree.delete(p)
                        if p in self.files:
                            self.files.remove(p)
                    self.count_lbl.config(text=f"{len(self.files)}개")
                    pct = f" ({(1 - a / b) * 100:.0f}% 줄임)" if b and a < b else ""
                    self.result_lbl.config(
                        text=f"완료 {ok}개 · {core.human_size(b)} → {core.human_size(a)}{pct}"
                             + (f" · 실패 {len(errors)}개" if errors else "")
                             + (f" · 원본 {len(removed)}개 휴지통으로" if removed else "")
                             + (f" · 폴더 {nfold}개 각각 랜덤" if nfold else ""))
                    if errors:
                        messagebox.showwarning(APP_NAME, "일부 파일을 처리하지 못했습니다.\n\n" + "\n".join(errors[:15]))
                    if last_dir and messagebox.askyesno(APP_NAME, "완료했습니다. 결과 폴더를 열까요?"):
                        open_folder(last_dir)
                    return
        except queue.Empty:
            pass
        self.after(80, self._poll)
