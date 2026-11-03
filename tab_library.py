"""업무 도우미 - 이미지 캡쳐 / 썸네일 탭"""
import json
import os
import queue
import random
import re
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import core
from common import (APP_NAME, GRAY, FONT, FONT_B, known_folder, enable_drop, drop_hint, open_folder,
                    ScrollFrame, AdjustPanel, Preview, Paned, RandomRangeDialog)

META = "_정보.json"
TILE_MIN = 130
SEL_BG, NORM_BG, ADD_BG = "#cfe3ff", "#f4f4f4", "#ffffff"


class LibraryTab(ttk.Frame):
    """폴더를 끌어다 놓으면 '내 문서\\업무도우미'에 보관.
    이미지 캡쳐: 폴더 개수만큼, 폴더마다 원본 전부를 변형해 채움
    썸네일   : 이미지 장수만큼 만들어 한 폴더에"""

    def __init__(self, master, app, kind):
        super().__init__(master, padding=8)
        self.app = app
        self.is_img = kind == "image"
        self.k = "img" if self.is_img else "th"
        sub = "병원이미지" if self.is_img else "썸네일"
        self.lib = os.path.join(known_folder("documents"), "업무도우미", sub)
        os.makedirs(self.lib, exist_ok=True)
        self.q = queue.Queue()
        self.worker = None
        self.last_out = None
        self.sel = []          # 선택된 보관 폴더 경로들
        self.groups = []       # [(경로, 병원명, 시술명, 장수)]
        self._cols = 0
        s = app.settings

        body = Paned(self, app, f"{self.k}_main")
        body.pack(fill="both", expand=True)

        # ══ 왼쪽: 보관 목록 (그리드 / 리스트) ══
        left = ttk.Frame(body)
        body.add(left, weight=1, width=360, minsize=220)
        lh = ttk.Frame(left)
        lh.pack(fill="x")
        what = "병원·시술별 이미지 폴더" if self.is_img else "병원별 썸네일 폴더"
        ttk.Label(lh, text=f"{what}를 {drop_hint()}추가", foreground=GRAY).pack(side="left")
        self.view = tk.StringVar(value=s.get(f"{self.k}_view", "grid"))
        ttk.Radiobutton(lh, text="리스트", value="list", variable=self.view, style="Toolbutton",
                        command=self._switch_view).pack(side="right")
        ttk.Radiobutton(lh, text="그리드", value="grid", variable=self.view, style="Toolbutton",
                        command=self._switch_view).pack(side="right", padx=2)

        self.stack = ttk.Frame(left)
        self.stack.pack(fill="both", expand=True, pady=6)
        # 그리드
        self.grid_sf = ScrollFrame(self.stack)
        self.grid_sf.canvas.configure(background="#fafafa")
        self.grid_sf.canvas.bind("<Configure>", self._grid_resized, add="+")
        # 리스트
        self.list_f = ttk.Frame(self.stack)
        cols = [("h", "병원명", 150)] + ([("p", "시술명", 150)] if self.is_img else []) + [("n", "이미지 수", 70)]
        self.tree = ttk.Treeview(self.list_f, columns=[c[0] for c in cols], show="headings", selectmode="extended")
        for cid, t, w in cols:
            self.tree.heading(cid, text=t)
            self.tree.column(cid, width=w, anchor="center" if cid == "n" else "w")
        tsb = ttk.Scrollbar(self.list_f, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._tree_selected)
        for w in (self.tree, self.grid_sf.canvas, self.grid_sf.inner, left):
            enable_drop(w, self._dropped)

        lb = ttk.Frame(left)
        lb.pack(fill="x")
        ttk.Button(lb, text="폴더 추가", command=self._add_folder).pack(side="left")
        ttk.Button(lb, text="사진 추가", command=self._add_to_selected).pack(side="left", padx=3)
        ttk.Button(lb, text="삭제", command=self._delete).pack(side="left")
        ttk.Button(lb, text="보관 폴더", command=lambda: open_folder(self.lib)).pack(side="right")

        # ══ 가운데: 랜덤 · 크기 · 색감 ══
        mid = ttk.Frame(body, padding=(10, 0))
        body.add(mid, weight=0, width=340, minsize=260)
        mh = ttk.Frame(mid)
        mh.pack(fill="x")
        ttk.Button(mh, text="  랜덤  ", command=self._randomize).pack(side="left")
        ttk.Button(mh, text="랜덤 범위…", command=self._range_dialog).pack(side="left", padx=4)
        ttk.Button(mh, text="모두 0", command=self._reset).pack(side="right")

        self.preview = Preview(mid, height=120)
        self.preview.pack(fill="x", pady=6)

        g = ttk.LabelFrame(mid, text=" 크기 · 자르기 ", padding=6)
        g.pack(fill="x")
        dmin, dmax = (800, 900) if self.is_img else (750, 950)
        self.lmin = tk.IntVar(value=s.get(f"{self.k}_min", dmin))
        self.lmax = tk.IntVar(value=s.get(f"{self.k}_max", dmax))
        self.tmin = tk.IntVar(value=s.get(f"{self.k}_tmin", 2))
        self.tmax = tk.IntVar(value=s.get(f"{self.k}_tmax", 8))
        self.aspect = tk.DoubleVar(value=s.get(f"{self.k}_aspect", 3.0))
        self.micro = tk.BooleanVar(value=s.get(f"{self.k}_micro", False))
        self._range_row(g, 0, "긴 변 크기(확대·축소)", self.lmin, self.lmax, 100, 5000)
        self._range_row(g, 1, "테두리 자르기(원본 px)", self.tmin, self.tmax, 0, 60)
        ttk.Label(g, text="가로·세로 비율 흔들림(%)").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Spinbox(g, from_=0, to=15, increment=0.5, textvariable=self.aspect, width=6).grid(row=2, column=1, sticky="w", padx=4)
        ttk.Label(g, text="순서: 원본 테두리를 변마다 다르게 잘라냄(한 변 최대 4%)\n→ 이미지 전체를 키우거나 줄여 긴 변을 맞춤",
                  foreground=GRAY).grid(row=4, column=0, columnspan=4, sticky="w")

        ttk.Label(mid, text="색감 기본값", font=FONT_B).pack(anchor="w", pady=(8, 2))
        self.adjust = AdjustPanel(mid, app, f"{self.k}_adjust", on_change=self._update_preview)
        self.adjust.pack(fill="both", expand=True)

        # ══ 오른쪽: 이름 · 만들기 ══
        right = ttk.Frame(body, padding=(10, 0))
        body.add(right, weight=1, minsize=240)
        g1 = ttk.LabelFrame(right, text=" 선택한 항목 ", padding=8)
        g1.pack(fill="x")
        self.h_var = tk.StringVar()
        self.p_var = tk.StringVar()
        ttk.Label(g1, text="병원명").grid(row=0, column=0, sticky="w")
        ttk.Entry(g1, textvariable=self.h_var, width=18).grid(row=0, column=1, sticky="we", padx=6, pady=2)
        if self.is_img:
            ttk.Label(g1, text="시술명").grid(row=1, column=0, sticky="w")
            ttk.Entry(g1, textvariable=self.p_var, width=18).grid(row=1, column=1, sticky="we", padx=6, pady=2)
        ttk.Button(g1, text="이름 저장", command=self._rename).grid(row=2, column=0, columnspan=2, sticky="we", pady=(6, 0))
        self.info_lbl = ttk.Label(g1, text="", foreground=GRAY)
        self.info_lbl.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        g1.columnconfigure(1, weight=1)

        g2 = ttk.LabelFrame(right, text=" 만들기 ", padding=8)
        g2.pack(fill="x", pady=10)
        label = "폴더 개수" if self.is_img else "이미지 장수"
        ttk.Label(g2, text=label, font=FONT_B).grid(row=0, column=0, sticky="w")
        self.count = tk.IntVar(value=s.get(f"{self.k}_count", 5 if self.is_img else 10))
        ttk.Spinbox(g2, from_=1, to=500, textvariable=self.count, width=6).grid(row=0, column=1, sticky="w", padx=6)
        self.vary = tk.BooleanVar(value=s.get(f"{self.k}_vary", False))
        ttk.Checkbutton(g2, text=("폴더마다 다른 랜덤값" if self.is_img else "장마다 다른 랜덤값"),
                        variable=self.vary).grid(row=0, column=2, sticky="w", padx=(4, 0))
        hint = ("폴더 하나에 원본 이미지 전부가 한 장씩 변형되어 들어갑니다.\n"
                "'폴더마다 다른 랜덤값'을 켜면 폴더를 만들 때마다 '랜덤'을 새로 누른 것처럼\n"
                "색감·크기·테두리·비율이 바뀝니다. (한 폴더 안은 같은 값)" if self.is_img
                else "보관된 이미지에서 무작위로 골라 만듭니다. 이미지 수 이하로 요청하면 중복 없음.\n"
                     "'장마다 다른 랜덤값'을 켜면 한 장마다 '랜덤'을 새로 누른 것처럼\n"
                     "색감·크기·테두리·비율이 바뀝니다.")
        ttk.Label(g2, text=hint, foreground=GRAY, justify="left", wraplength=250).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.where = ttk.Label(g2, text="", foreground="#0a5", justify="left", wraplength=240)
        self.where.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.run_btn = ttk.Button(right, text="선택 항목 만들기", style="Big.TButton", command=self._run)
        self.run_btn.pack(fill="x", ipady=4)
        ttk.Label(right, text="여러 개 선택(Ctrl+클릭) 시 항목마다 따로 만듭니다.",
                  foreground=GRAY, wraplength=240).pack(anchor="w", pady=(4, 8))
        self.prog = ttk.Progressbar(right, mode="determinate")
        self.prog.pack(fill="x")
        self.result = ttk.Label(right, text="", justify="left", wraplength=240)
        self.result.pack(anchor="w", pady=6)
        self.open_btn = ttk.Button(right, text="결과 폴더 열기", state="disabled",
                                   command=lambda: self.last_out and open_folder(self.last_out))
        self.open_btn.pack(anchor="w")

        self._switch_view()
        self.reload()

    def _range_row(self, g, r, name, v1, v2, lo, hi):
        ttk.Label(g, text=name).grid(row=r, column=0, sticky="w", pady=2)
        ttk.Spinbox(g, from_=lo, to=hi, textvariable=v1, width=6).grid(row=r, column=1, sticky="w", padx=4)
        ttk.Label(g, text="~").grid(row=r, column=2)
        ttk.Spinbox(g, from_=lo, to=hi, textvariable=v2, width=6).grid(row=r, column=3, sticky="w", padx=4)

    # ══ 보관 데이터 ══
    def _read_meta(self, d):
        try:
            with open(os.path.join(d, META), encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            m = {}
        return {"hospital": m.get("hospital", os.path.basename(d)), "procedure": m.get("procedure", "")}

    def _write_meta(self, d, h, p):
        with open(os.path.join(d, META), "w", encoding="utf-8") as f:
            json.dump({"hospital": h, "procedure": p}, f, ensure_ascii=False)

    def reload(self, select=None):
        self.groups = []
        for name in core.natural_sorted(os.listdir(self.lib)):
            d = os.path.join(self.lib, name)
            if os.path.isdir(d):
                m = self._read_meta(d)
                self.groups.append((d, m["hospital"], m["procedure"], len(core.list_images(d))))
        alive = {g[0] for g in self.groups}
        self.sel = [d for d in ([select] if select else self.sel) if d in alive]
        self.tree.delete(*self.tree.get_children())
        for d, h, p, n in self.groups:
            self.tree.insert("", "end", iid=d, values=(h, p, n) if self.is_img else (h, n))
        self._build_grid(force=True)
        self._sync_selection()

    # ══ 보기 전환 ══
    def _switch_view(self):
        self.app.settings[f"{self.k}_view"] = self.view.get()
        self.grid_sf.pack_forget()
        self.list_f.pack_forget()
        if self.view.get() == "grid":
            self.grid_sf.pack(fill="both", expand=True)
        else:
            self.list_f.pack(fill="both", expand=True)
        self._sync_selection()

    def _grid_resized(self, e):
        # 창 크기를 바꾸는 동안엔 계산을 미루고, 멈추면 한 번만 다시 배치
        self._grid_w = e.width
        if getattr(self, "_grid_job", None):
            self.after_cancel(self._grid_job)
        self._grid_job = self.after(90, self._layout_grid)

    def _build_grid(self, force=False):
        """타일 만들기(목록이 바뀔 때만). 배치는 _layout_grid"""
        inner = self.grid_sf.inner
        for w in inner.winfo_children():
            w.destroy()
        self.tiles = {}
        self._tile_list = []
        for g in list(self.groups) + [None]:   # 마지막은 '추가' 빈칸
            if g is None:
                t = tk.Label(inner, text="+\n\n폴더를 끌어다 놓거나\n클릭해서 추가", bg=ADD_BG, fg="#888",
                             relief="groove", bd=2, width=1, height=6, font=FONT, cursor="hand2")
                t.bind("<Button-1>", lambda e: self._add_folder())
                enable_drop(t, self._dropped)
            else:
                d, h, p, n = g
                sub = p if self.is_img else "썸네일"
                t = tk.Label(inner, text=f"{h}\n{sub}\n\n{n}장", bg=NORM_BG, relief="raised", bd=2,
                             width=1, height=6, font=FONT, cursor="hand2", wraplength=TILE_MIN - 12)
                t.bind("<Button-1>", lambda e, d=d: self._tile_click(e, d))
                enable_drop(t, lambda paths, d=d: self._dropped(paths, target=d))
                self.tiles[d] = t
            self._tile_list.append(t)
        self._cols = 0
        self._layout_grid()
        self._paint_tiles()

    def _layout_grid(self):
        """칸 너비에 맞춰 열 개수를 정하고, 타일이 빈틈없이 가로를 채우게"""
        self._grid_job = None
        inner = self.grid_sf.inner
        w = getattr(self, "_grid_w", 0) or self.grid_sf.canvas.winfo_width()
        cols = max(1, (w - 4) // (TILE_MIN + 8)) if w > 50 else 4
        if cols == self._cols:
            return
        old = self._cols
        self._cols = cols
        for c in range(max(cols, old)):
            if c < cols:
                inner.columnconfigure(c, weight=1, uniform="tile", minsize=TILE_MIN)
            else:
                inner.columnconfigure(c, weight=0, uniform="", minsize=0)
        for i, t in enumerate(self._tile_list):
            r, c = divmod(i, cols)
            t.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")

    def _paint_tiles(self):
        for d, t in getattr(self, "tiles", {}).items():
            on = d in self.sel
            t.config(bg=SEL_BG if on else NORM_BG, relief="sunken" if on else "raised")

    def _tile_click(self, e, d):
        ctrl = e.state & 0x0004
        if ctrl:
            if d in self.sel:
                self.sel.remove(d)
            else:
                self.sel.append(d)
        else:
            self.sel = [d]
        self._sync_selection()

    def _tree_selected(self, _e=None):
        if self.view.get() != "list":
            return
        new = list(self.tree.selection())
        if new != self.sel:
            self.sel = new
            self._sync_selection(from_tree=True)

    def _sync_selection(self, from_tree=False):
        if not from_tree:
            cur = [d for d in self.sel if self.tree.exists(d)]
            if list(self.tree.selection()) != cur:
                self.tree.selection_set(cur)
        self._paint_tiles()
        self._on_select()

    # ══ 추가 · 삭제 · 이름 ══
    def _guess_names(self, folder_name):
        name = folder_name.strip()
        if self.is_img:
            parts = [x for x in re.split(r"\s*[-_]\s*|\s+", name) if x]
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
            shutil.copy2(f, core._unique(os.path.join(d, os.path.basename(f))))

    def _dropped(self, paths, target=None):
        groups, loose = [], []
        for p in paths:
            if os.path.isdir(p):
                imgs = core.list_images(p)
                if imgs:
                    groups.append((os.path.basename(os.path.normpath(p)), imgs))
                else:  # 상위 폴더를 넣으면 하위 폴더 하나하나를 항목으로
                    for sub in core.natural_sorted(os.listdir(p)):
                        sp = os.path.join(p, sub)
                        if os.path.isdir(sp):
                            si = core.list_images(sp, recursive=True)
                            if si:
                                groups.append((sub, si))
            elif os.path.splitext(p)[1].lower() in core.IMAGE_EXT:
                loose.append(p)
        if loose and target:
            self._copy_into(target, loose)
            if not groups:
                self.reload(select=target)
                self.app.status(f"사진 {len(loose)}장을 추가했습니다.")
                return
        elif loose:
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
        if len(self.sel) != 1:
            messagebox.showinfo(APP_NAME, "사진을 넣을 항목 하나를 먼저 선택해주세요.")
            return
        fs = filedialog.askopenfilenames(filetypes=[("이미지", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"), ("모든 파일", "*.*")])
        if fs:
            self._copy_into(self.sel[0], fs)
            self.reload(select=self.sel[0])

    def _delete(self):
        if not self.sel:
            return
        if not messagebox.askyesno(APP_NAME, f"선택한 {len(self.sel)}개 항목을 보관함에서 지울까요?\n(처음 넣었던 원본 폴더는 그대로 남습니다)"):
            return
        for d in self.sel:
            shutil.rmtree(d, ignore_errors=True)
        self.sel = []
        self.reload()

    def _on_select(self):
        if len(self.sel) == 1:
            m = self._read_meta(self.sel[0])
            self.h_var.set(m["hospital"])
            self.p_var.set(m["procedure"])
            n = len(core.list_images(self.sel[0]))
            self.info_lbl.config(text=f"원본 이미지 {n}장")
        else:
            self.h_var.set("")
            self.p_var.set("")
            self.info_lbl.config(text=f"{len(self.sel)}개 선택됨" if self.sel else "")
        self.where.config(text=self._where_text())
        self._update_preview()

    def _out_base(self, d):
        m = self._read_meta(d)
        if self.is_img:
            return self._safe(f"{m['hospital']} {m['procedure']}".strip())
        return self._safe(f"{m['hospital']} 썸넬")

    def _where_text(self):
        if not self.sel:
            return "항목을 선택하면 저장 위치가 여기 표시됩니다."
        desk = known_folder("desktop")
        if self.is_img:
            ex = os.path.basename(core.next_numbered_dir(desk, self._out_base(self.sel[0])))
            tail = "\\output\\"
        else:
            ex = os.path.basename(core.next_numbered_file(desk, self._out_base(self.sel[0])))
            tail = ""
        more = f"\n외 {len(self.sel) - 1}개 항목" if len(self.sel) > 1 else ""
        return f"바탕화면\\{ex}{tail} 부터{more}"

    def _rename(self):
        if len(self.sel) != 1:
            messagebox.showinfo(APP_NAME, "이름을 바꿀 항목 하나를 선택해주세요.")
            return
        d = self.sel[0]
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

    # ══ 랜덤 · 미리보기 ══
    def _range_cfg(self):
        d = core.DEFAULT_RANDOM_RANGE["image" if self.is_img else "thumb"]
        cfg = {k: list(v) for k, v in d.items()}
        cfg.update(self.app.settings.get(f"{self.k}_rrange", {}))
        return d, cfg

    def _range_dialog(self):
        d, _ = self._range_cfg()
        RandomRangeDialog(self, self.app, f"{self.k}_rrange", d)

    def _randomize(self):
        rng = random.Random()
        self.adjust.randomize(rng)
        _, cfg = self._range_cfg()
        use = cfg.get("use", {})
        size = core.random_size(rng, cfg)
        if use.get("len", True):
            self.lmin.set(size["lmin"])
            self.lmax.set(size["lmax"])
        if use.get("trim", True):
            self.tmin.set(size["tmin"])
            self.tmax.set(size["tmax"])
        if use.get("aspect", True):
            self.aspect.set(size["aspect"])
        self.remember()

    def remember(self):
        try:
            self.app.settings.update({
                f"{self.k}_count": int(self.count.get()), f"{self.k}_min": int(self.lmin.get()),
                f"{self.k}_max": int(self.lmax.get()), f"{self.k}_tmin": int(self.tmin.get()),
                f"{self.k}_tmax": int(self.tmax.get()), f"{self.k}_aspect": float(self.aspect.get()),
                f"{self.k}_micro": False, f"{self.k}_vary": self.vary.get(),
                f"{self.k}_view": self.view.get()})
        except Exception:
            pass

    def _reset(self):
        self.adjust.reset()

    def _update_preview(self):
        src = None
        if self.sel:
            imgs = core.list_images(self.sel[0])
            src = imgs[0] if imgs else None
        self.preview.show(src, self.adjust.get, imgs if self.sel else [])

    # ══ 만들기 ══
    def _params(self):
        lo, hi = sorted((int(self.lmin.get()), int(self.lmax.get())))
        return {"lmin": lo, "lmax": hi, "tmin": int(self.tmin.get()), "tmax": int(self.tmax.get()),
                "aspect": float(self.aspect.get()), "base": self.adjust.get(), "micro": False}

    def _run(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.sel:
            messagebox.showinfo(APP_NAME, "만들 항목을 먼저 선택해주세요.")
            return
        try:
            count = int(self.count.get())
            kw = self._params()
        except Exception:
            messagebox.showwarning(APP_NAME, "숫자 칸을 확인해주세요.")
            return
        self.remember()
        jobs = [(d, core.list_images(d)) for d in self.sel]
        jobs = [(d, f) for d, f in jobs if f]
        if not jobs:
            messagebox.showinfo(APP_NAME, "선택한 항목에 이미지가 없습니다.")
            return
        vary = self.vary.get()
        rnd_keys = [k for k, rv in self.adjust.rnd.items() if rv.get()]
        _, cfg = self._range_cfg()

        def fresh(rng):
            """'랜덤'을 새로 누른 것과 같은 값 (체크된 항목·범위 설정 그대로)"""
            k2 = dict(kw)
            base = dict(kw["base"])
            base.update(core.random_adjust(rng, rnd_keys))
            k2["base"] = base
            size = core.random_size(rng, cfg)
            use = cfg.get("use", {})
            if use.get("len", True):
                k2["lmin"], k2["lmax"] = size["lmin"], size["lmax"]
            if use.get("trim", True):
                k2["tmin"], k2["tmax"] = size["tmin"], size["tmax"]
            if use.get("aspect", True):
                k2["aspect"] = size["aspect"]
            return k2

        desktop = known_folder("desktop")
        total = sum(len(f) * count for d, f in jobs) if self.is_img else count * len(jobs)
        self.prog.config(maximum=total, value=0)
        self.run_btn.config(state="disabled")
        self.result.config(text="만드는 중...")

        def work():
            rng = random.Random()
            done = [0]
            outs = []

            def tick():
                done[0] += 1
                self.q.put(("prog", done[0]))
            try:
                for d, files in jobs:
                    if self.is_img:
                        for _ in range(count):
                            top = core.next_numbered_dir(desktop, self._out_base(d))
                            out = os.path.join(top, "output")
                            core.make_folder_set(files, out, rng, progress=tick, **(fresh(rng) if vary else kw))
                            outs.append(top)
                    else:
                        # 썸네일은 폴더 없이 바탕화면에 '병원명 썸넬 1.jpg' 처럼 바로 저장
                        outs += core.make_count_set(files, desktop, count, rng, progress=tick,
                                                    kw_fn=(lambda: fresh(rng)) if vary else None,
                                                    base_name=self._out_base(d), **kw)
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
                    names = [os.path.basename(o) for o in outs]
                    shown = "\n".join(names[:8]) + (f"\n… 외 {len(names) - 8}개" if len(names) > 8 else "")
                    what = f"폴더 {len(outs)}개" if self.is_img else f"이미지 {len(outs)}장"
                    self.result.config(text=(f"완료: 바탕화면에 {what}\n{shown}" if outs else "") +
                                       (f"\n오류: {err}" if err else ""))
                    if outs:
                        self.last_out = outs[-1] if (len(outs) == 1 and self.is_img) else known_folder("desktop")
                        self.open_btn.config(state="normal")
                    self.where.config(text=self._where_text())
                    if err:
                        messagebox.showerror(APP_NAME, f"만드는 중 문제가 생겼습니다.\n{err}")
                    return
        except queue.Empty:
            pass
        self.after(80, self._poll)
