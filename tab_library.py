"""업무 도우미 - 이미지 생성 / 썸네일 생성 탭"""
import json
import os
import queue
import random
import re
import shutil
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import core
from common import (APP_NAME, GRAY, FONT, FONT_B, known_folder, enable_drop, drop_hint, open_folder,
                    ScrollFrame, AdjustPanel, Preview, Paned, RandomRangeDialog, SizeCropPanel, WrapLabel, help_label)

META = "_정보.json"
TILE_MIN = 130
SEL_BG, NORM_BG, ADD_BG = "#cfe3ff", "#f4f4f4", "#ffffff"
SPECIAL_BG, SPECIAL_SEL = "#dcecfb", "#9cc9f2"   # 특수 가공 칸: 연한 파랑


class LibraryTab(ttk.Frame):
    """폴더를 끌어다 놓으면 '내 문서\\업무도우미'에 보관.
    이미지 캡쳐: 폴더 개수만큼, 폴더마다 원본 전부를 변형해 채움
    썸네일   : 이미지 장수만큼 만들어 한 폴더에"""

    def __init__(self, master, app, kind):
        super().__init__(master, padding=8)
        self.app = app
        self.raw = kind == "image_raw"        # 이미지 생성 (원본): 가공 없이 원본 복사
        self.opener = kind == "thumb_open"    # 썸네일 실행: 칸을 누르면 원본 하나를 열어 줌
        self.is_img = kind in ("image", "image_raw")
        self.k = {"image": "img", "thumb": "th", "image_raw": "imgraw", "thumb_open": "thopen"}[kind]
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
        help_label(lh, f"{what}를 {drop_hint()}'폴더 추가'를 누르세요. 여러 개를 한 번에 넣어도 됩니다.\n"
                       "칸을 클릭하면 선택, Ctrl+클릭으로 여러 개 선택.\n사진을 칸 위에 끌어다 놓으면 그 항목에 추가됩니다."
                   ).pack(side="left")
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
        self.tree.bind("<Double-1>", lambda e: (self.tree.identify_row(e.y) and self._is_bundle(self.tree.identify_row(e.y))
                                                and self._open_bundle(self.tree.identify_row(e.y))))
        for w in (self.tree, self.grid_sf.canvas, self.grid_sf.inner, left):
            enable_drop(w, self._dropped)

        lb = ttk.Frame(left)
        lb.pack(fill="x")
        ttk.Button(lb, text="폴더 추가", command=self._add_folder).pack(side="left")
        ttk.Button(lb, text="사진 추가", command=self._add_to_selected).pack(side="left", padx=3)
        ttk.Button(lb, text="삭제", command=self._delete).pack(side="left")
        ttk.Button(lb, text="보관 폴더", command=lambda: open_folder(self.lib)).pack(side="right")

        # ══ 가운데: 랜덤 · 크기 · 색감 (길어지면 통째로 스크롤) ══
        mid = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(mid, weight=0, width=350, minsize=270)
        mh = ttk.Frame(mid)
        mh.pack(fill="x", padx=(0, 10))
        ttk.Button(mh, text="  랜덤  ", command=self._randomize).pack(side="left")
        ttk.Button(mh, text="랜덤 범위…", command=self._range_dialog).pack(side="left", padx=4)
        ttk.Button(mh, text="모두 0", command=self._reset).pack(side="right")
        msf = ScrollFrame(mid)
        msf.pack(fill="both", expand=True, pady=(6, 0))
        m = ttk.Frame(msf.inner, padding=(0, 0, 8, 0))
        m.pack(fill="both", expand=True)

        self.preview = Preview(m, height=120)
        self.preview.pack(fill="x", pady=(0, 6))
        self.sizer = SizeCropPanel(m, app, self.k, width=850, on_change=self._update_preview_later)
        self.sizer.pack(fill="x")

        ttk.Label(m, text="색감 기본값", font=FONT_B).pack(anchor="w", pady=(10, 2))
        self.adjust = AdjustPanel(m, app, f"{self.k}_adjust", on_change=self._update_preview, scroll=False)
        self.adjust.pack(fill="x")

        if self.raw or self.opener:   # 가공이 없으니 가공 설정 칸은 숨김
            body.forget(mid)

        # ══ 오른쪽: 이름 · 만들기 ══
        right = ttk.Frame(body, padding=(10, 0))
        body.add(right, weight=1, minsize=240)
        if self.is_img and not self.raw:
            ttk.Button(right, text="특수 가공 (워터마크 · GIF)", command=self._open_special).pack(
                fill="x", pady=(0, 10), ipady=3)
        if self.is_img and not self.raw:
            gn = ttk.LabelFrame(right, text=" 파일명 ", padding=8)
            gn.pack(fill="x", pady=(0, 10))
            self.name_pat = tk.StringVar(value=s.get("img_name_pat", "{번호}"))
            self.name_dig = tk.IntVar(value=s.get("img_name_dig", 1))
            ttk.Entry(gn, textvariable=self.name_pat, width=16).grid(row=0, column=0, sticky="we")
            ttk.Label(gn, text="자릿수").grid(row=0, column=1, padx=(8, 2))
            ttk.Spinbox(gn, from_=1, to=6, textvariable=self.name_dig, width=4).grid(row=0, column=2)
            self.name_ex = ttk.Label(gn, text="", foreground="#0a5")
            self.name_ex.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
            help_label(gn, "{번호} 자리에 1, 2, 3 … 이 들어갑니다. 자릿수만큼 앞에 0을 채워요.\n"
                           "예: image{번호} + 자릿수 3 → image001.jpg, image002.jpg …\n"
                           "{날짜} 는 오늘 날짜(20261103)로 바뀝니다.").grid(row=1, column=2, sticky="e", pady=(4, 0))
            gn.columnconfigure(0, weight=1)
            for v in (self.name_pat, self.name_dig):
                v.trace_add("write", lambda *a: self._name_example())
            self._name_example()

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
        if not self.opener:
            g2.pack(fill="x", pady=10)
        label = "폴더 개수" if self.is_img else "이미지 장수"
        ttk.Label(g2, text=label, font=FONT_B).grid(row=0, column=0, sticky="w")
        self.count = tk.IntVar(value=s.get(f"{self.k}_count", 5 if self.is_img else 10))
        ttk.Spinbox(g2, from_=1, to=500, textvariable=self.count, width=6).grid(row=0, column=1, sticky="w", padx=6)
        self.vary = tk.BooleanVar(value=s.get(f"{self.k}_vary", False))
        if self.raw:
            kf = ttk.Frame(g2)
            kf.grid(row=1, column=0, columnspan=2, sticky="we", pady=(6, 0))
            ttk.Button(kf, text="키워드 목록", command=self._raw_keywords).pack(side="left")
            self.kw_lbl = ttk.Label(kf, text="", foreground="#0a5")
            self.kw_lbl.pack(side="left", padx=8)
        else:
            ttk.Checkbutton(g2, text=("폴더마다 다른 랜덤값" if self.is_img else "장마다 다른 랜덤값"),
                            variable=self.vary).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        hint = ("폴더 하나에 원본 이미지 전부가 한 장씩 같은 조건으로 변형되어 들어갑니다.\n"
                "'폴더마다 다른 랜덤값'을 켜면 폴더를 만들 때마다 '랜덤'을 새로 누른 것처럼 "
                "가로 크기·테두리·비율·색감이 바뀝니다. (한 폴더 안은 모두 같은 값)\n\n"
                "여러 항목을 선택(Ctrl+클릭)하면 항목마다 따로 만듭니다." if self.is_img
                else "보관된 이미지에서 무작위로 골라 만듭니다. 이미지 수 이하로 요청하면 중복 없음.\n"
                     "'장마다 다른 랜덤값'을 켜면 한 장마다 '랜덤'을 새로 누른 것처럼 "
                     "가로 크기·테두리·비율·색감이 바뀝니다. (끄면 전부 같은 조건)\n\n"
                     "결과는 바탕화면에 '병원명 썸넬 1.jpg' 처럼 저장됩니다.")
        if self.raw:
            hint = ("가공 없이 원본 이미지 그대로(이름·내용 그대로) 복사합니다.\n\n"
                    "· 키워드 목록이 비어 있으면: 폴더 개수만큼 바탕화면\\병원 시술 1\\ (원본 순서·이름 그대로)\n"
                    "· 키워드 목록이 있으면: 키워드 수만큼, 바탕화면\\병원 시술 날짜\\키워드\\ 폴더마다 원본 전부\n"
                    "  (키워드 목록은 칸마다 따로 저장됩니다)")
        help_label(g2, hint).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.where = WrapLabel(g2, text="", foreground="#0a5")
        self.where.grid(row=3, column=0, columnspan=2, sticky="we", pady=(8, 0))
        g2.columnconfigure(1, weight=1)

        run_text = "선택 항목 원본 복사" if self.raw else "랜덤으로 하나 열기" if self.opener else "선택 항목 만들기"
        self.run_btn = ttk.Button(right, text=run_text, style="Big.TButton",
                                  command=(lambda: self.sel and self._open_random(self.sel[0])) if self.opener else self._run)
        self.run_btn.pack(fill="x", ipady=4)
        if self.opener:
            help_label(right, "칸을 누르면 그 병원 썸네일 중 하나를 무작위로 골라 윈도우 사진 앱으로 엽니다.\n"
                              "폴더에서 연 것처럼 사진 앱에서 ← → 로 다음·이전 사진으로 넘어갈 수 있어요.\n"
                              "(가공 없이 원본 그대로 엽니다)").pack(anchor="w", pady=(6, 0))
        if self.is_img and not self.raw:
            ttk.Button(right, text="키워드 생성하기", command=self._keyword_dialog).pack(fill="x", pady=(6, 0), ipady=2)
        ttk.Frame(right, height=8).pack()
        self.prog = ttk.Progressbar(right, mode="determinate")
        self.prog.pack(fill="x")
        self.result = WrapLabel(right, text="")
        self.result.pack(fill="x", pady=6)
        self.open_btn = ttk.Button(right, text="결과 폴더 열기", state="disabled",
                                   command=lambda: self.last_out and open_folder(self.last_out))
        self.open_btn.pack(anchor="w")

        self._switch_view()
        self.reload()

    # ══ 보관 데이터 ══
    def _read_meta(self, d):
        try:
            with open(os.path.join(d, META), encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            m = {}
        return {"hospital": m.get("hospital", os.path.basename(d)), "procedure": m.get("procedure", "")}

    def _meta_raw(self, d):
        try:
            with open(os.path.join(d, META), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_meta(self, d, h=None, p=None, **extra):
        m = self._meta_raw(d)
        if h is not None:
            m["hospital"] = h
        if p is not None:
            m["procedure"] = p
        m.update(extra)
        with open(os.path.join(d, META), "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)

    def reload(self, select=None):
        self.groups = []
        self.procs = []   # 시술 하나하나 (묶음 안 시술 포함) — 원고 이미지 배치에서 씀
        for name in core.natural_sorted(os.listdir(self.lib)):
            d = os.path.join(self.lib, name)
            if not os.path.isdir(d):
                continue
            m = self._read_meta(d)
            if self._is_bundle(d):
                subs = self._bundle_subs(d)
                total = 0
                for sd in subs:
                    sm = self._read_meta(sd)
                    k = len(core.list_images(sd))
                    total += k
                    self.procs.append((sd, m["hospital"], sm["procedure"], k))
                self.groups.append((d, m["hospital"], f"시술 {len(subs)}개", total))
            else:
                n = len(core.list_images(d))
                self.groups.append((d, m["hospital"], m["procedure"], n))
                self.procs.append((d, m["hospital"], m["procedure"], n))
        if self.is_img:   # 특수 가공 칸은 맨 앞에
            self.groups.sort(key=lambda g: 0 if self._is_special(g[0]) else 1)
        alive = {g[0] for g in self.groups}
        self.sel = [d for d in ([select] if select else self.sel) if d in alive]
        self.tree.delete(*self.tree.get_children())
        for d, h, p, n in self.groups:
            pp = ("★ " + p) if self.is_img and self._is_special(d) else p
            self.tree.insert("", "end", iid=d, values=(h, pp, n) if self.is_img else (h, n),
                             tags=("special",) if self.is_img and self._is_special(d) else ())
        self.tree.tag_configure("special", background=SPECIAL_BG)
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
            elif self.is_img and self._is_special(g[0]):
                d, h, p, n = g
                t = tk.Label(inner, text=f"★ 특수 가공\n{h}\n{p}\n{n}장", bg=SPECIAL_BG, relief="raised", bd=2,
                             width=1, height=6, font=FONT, cursor="hand2", wraplength=TILE_MIN - 12, fg="#14467a")
                t.bind("<Button-1>", lambda e, d=d: self._tile_click(e, d))
                t.bind("<Double-Button-1>", lambda e, d=d: SpecialDialog(self, d))
                self.tiles[d] = t
            elif self.is_img and self._is_bundle(g[0]):
                d, h, p, n = g
                t = tk.Frame(inner, bg="#b9c3cf", bd=0)
                lbl = tk.Label(t, text=f"{h}\n{p}\n{n}장", bg=NORM_BG, relief="raised", bd=2,
                               width=1, height=4, font=FONT, cursor="hand2", wraplength=TILE_MIN - 12)
                lbl.pack(fill="both", expand=True)
                btn = tk.Button(t, text="세부 선택", font=("맑은 고딕", 9, "bold"), bg="#e8eef7", relief="raised",
                                bd=2, cursor="hand2", command=lambda d=d: self._open_bundle(d))
                btn.pack(fill="x")
                lbl.bind("<Button-1>", lambda e, d=d: self._tile_click(e, d))
                lbl.bind("<Double-Button-1>", lambda e, d=d: self._open_bundle(d))
                for w in (t, lbl):
                    enable_drop(w, lambda paths, d=d: self._dropped(paths, target=d))
                self.tiles[d] = lbl
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
            sp = self.is_img and self._is_special(d)
            t.config(bg=(SPECIAL_SEL if sp else SEL_BG) if on else (SPECIAL_BG if sp else NORM_BG),
                     relief="sunken" if on else "raised")

    def _open_random(self, d):
        files = [f for f in self._files_of(d)]
        if not files and self._is_bundle(d):
            for sd in self._bundle_subs(d):
                files += self._files_of(sd)
        if not files:
            messagebox.showinfo(APP_NAME, "이 칸에 이미지가 없습니다.")
            return
        f = random.choice(files)
        open_folder(f)   # 윈도우 기본 사진 앱으로 열기
        self.app.status(f"열었습니다: {os.path.basename(f)}  ({len(files)}장 중)")

    def _tile_click(self, e, d):
        if self.opener:
            self.sel = [d]
            self._sync_selection()
            self._open_random(d)
            return
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
        parent_name = None
        for p in paths:
            if os.path.isdir(p):
                imgs = core.list_images(p)
                if imgs:
                    groups.append((os.path.basename(os.path.normpath(p)), imgs))
                else:  # 상위 폴더를 넣으면 하위 폴더 하나하나를 시술로
                    found = 0
                    for sub in core.natural_sorted(os.listdir(p)):
                        sp = os.path.join(p, sub)
                        if os.path.isdir(sp):
                            si = core.list_images(sp, recursive=True)
                            if si:
                                groups.append((sub, si))
                                found += 1
                    if found and len(paths) == 1:
                        parent_name = os.path.basename(os.path.normpath(p))
            elif os.path.splitext(p)[1].lower() in core.IMAGE_EXT:
                loose.append(p)
        # 묶음 칸 위에 폴더를 놓으면 그 병원의 시술로 추가
        if target and self.is_img and self._is_bundle(target) and groups:
            self._add_to_bundle(target, groups)
            self.reload(select=target)
            self.app.status(f"시술 {len(groups)}개를 추가했습니다.")
            return
        if loose and target and not self._is_bundle(target):
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
        bundle_name = None
        if self.is_img and len(groups) > 1:
            guesses = [self._guess_names(n)[0] for n, _ in groups]
            same = len(set(guesses)) == 1 and any(self._guess_names(n)[1] for n, _ in groups)
            bundle_name = parent_name or (guesses[0] if same else None)
            if not bundle_name:
                ans = messagebox.askyesnocancel(
                    APP_NAME, f"폴더 {len(groups)}개를 넣었습니다.\n\n"
                              "예: 한 병원으로 묶기 (칸 하나 + 세부 선택)\n아니요: 폴더마다 따로 칸 만들기")
                if ans is None:
                    return
                if ans:
                    bundle_name = os.path.commonprefix(guesses).strip(" -_") or guesses[0]
        self.app.root.config(cursor="watch")
        self.app.root.update()
        last = None
        try:
            if bundle_name:
                last = self._new_bundle(bundle_name, groups)
            else:
                for name, files in groups:
                    h, p = self._guess_names(name)
                    last = self._new_group(h, p, files)
        finally:
            self.app.root.config(cursor="")
        self.reload(select=last)
        if bundle_name:
            self.app.status(f"'{bundle_name}' 한 칸으로 시술 {len(groups)}개를 보관했습니다. 병원 이름이 맞는지 확인해주세요.")
        else:
            self.app.status(f"{len(groups)}개 항목을 보관했습니다. 이름이 맞는지 확인해주세요.")

    # ── 묶음(한 병원 · 여러 시술) ──
    def _is_special(self, d):
        return bool(d) and bool(self._meta_raw(d).get("special"))

    def _files_of(self, d):
        """만들 때 쓸 원본 목록 (특수 가공 칸은 정해 둔 순서대로)"""
        if not self._is_special(d):
            return core.list_images(d)
        order = self._meta_raw(d).get("order") or []
        files = [os.path.join(d, n) for n in order if os.path.exists(os.path.join(d, n))]
        return files + [f for f in core.list_images(d) if os.path.basename(f) not in order]

    def _make_files(self, d, files, out, rng, kw, tick, nk=None):
        """일반 칸: 기존 가공, 특수 칸: 저장된 워터마크·GIF 설정으로 특수 가공
        (작업 스레드에서 부르므로 화면 값은 nk 로 미리 받아 옴)"""
        if self.raw:   # 가공 없이 원본 그대로 복사
            os.makedirs(out, exist_ok=True)
            for f in files:
                shutil.copy2(f, core._unique(os.path.join(out, os.path.basename(f))))
                tick()
            return
        nk = nk if nk is not None else self._name_kw()
        if self._is_special(d):
            import special
            m = self._meta_raw(d).get("sp", {})
            img_wm = dict(special.DEFAULT_IMG_WM, **m.get("img_wm", {}))
            gif_wm = dict(special.DEFAULT_GIF_WM, **m.get("gif_wm", {}))
            use_kw = kw if m.get("base", True) else {"width": None, "trim": 0, "aspect": 0, "base": {}}
            special.run(files, out, use_kw, img_wm, gif_wm, m.get("gif_range", [103, 108]),
                        nk.get("name_pattern", "{번호}"), nk.get("digits", 1), progress=lambda i: tick(), rng=rng)
        else:
            core.make_folder_set(files, out, rng, progress=tick, **nk, **kw)

    def _open_special(self):
        if len(self.sel) == 1 and self._is_special(self.sel[0]):
            SpecialDialog(self, self.sel[0])
        else:
            SpecialDialog(self)

    def _is_bundle(self, d):
        return bool(d) and bool(self._meta_raw(d).get("bundle"))

    def _bundle_subs(self, d):
        try:
            names = core.natural_sorted(os.listdir(d))
        except OSError:
            return []
        return [os.path.join(d, x) for x in names
                if os.path.isdir(os.path.join(d, x)) and core.list_images(os.path.join(d, x))]

    def _new_bundle(self, hospital, groups):
        base = self._safe(hospital)
        d = os.path.join(self.lib, base)
        n = 2
        while os.path.exists(d):
            d = os.path.join(self.lib, f"{base} ({n})")
            n += 1
        os.makedirs(d)
        self._write_meta(d, hospital, "", bundle=True)
        self._add_to_bundle(d, groups)
        return d

    def _add_to_bundle(self, d, groups):
        hospital = self._read_meta(d)["hospital"]
        for name, files in groups:
            h, p = self._guess_names(name)
            proc = p if (h == hospital and p) else name
            sd = os.path.join(d, self._safe(proc))
            k = 2
            while os.path.exists(sd):
                sd = os.path.join(d, f"{self._safe(proc)} ({k})")
                k += 1
            os.makedirs(sd)
            self._write_meta(sd, hospital, proc)
            self._copy_into(sd, files)

    def _open_bundle(self, d):
        self.sel = [d]
        self._sync_selection()
        BundleDialog(self, d)

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
        if len(self.sel) == 1 and self._is_bundle(self.sel[0]):
            m = self._read_meta(self.sel[0])
            self.h_var.set(m["hospital"])
            self.p_var.set("")
            subs = self._bundle_subs(self.sel[0])
            tot = sum(len(core.list_images(x)) for x in subs)
            self.info_lbl.config(text=f"묶음 칸 · 시술 {len(subs)}개 · 총 {tot}장 (세부 선택에서 만들기)")
        elif len(self.sel) == 1:
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
        if self.raw:
            self._raw_kw_label()
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
            tail = "\\" if self.raw else "\\output\\"
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
        if self._is_bundle(d):
            p = ""
            for sd in self._bundle_subs(d):
                self._write_meta(sd, h)
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
        self.sizer.apply_random(rng, cfg)
        self.remember()

    def remember(self):
        try:
            self.app.settings.update({f"{self.k}_count": int(self.count.get()), f"{self.k}_vary": self.vary.get(),
                                      f"{self.k}_view": self.view.get()})
        except Exception:
            pass

    def _reset(self):
        self.adjust.reset()

    def _update_preview_later(self):
        if getattr(self, "_pv_job", None):
            self.after_cancel(self._pv_job)
        self._pv_job = self.after(300, self._update_preview)

    def _update_preview(self):
        self._pv_job = None
        imgs = core.list_images(self.sel[0]) if self.sel else []
        if self.sel and not imgs and self._is_bundle(self.sel[0]):
            subs = self._bundle_subs(self.sel[0])
            imgs = core.list_images(subs[0]) if subs else []
        kw = self._params()
        self.preview.show(imgs[0] if imgs else None, lambda im, sc: core.preview_process(im, sc, **kw), imgs)

    def _params(self):
        """지금 화면의 조건 (한 폴더/한 묶음에 그대로 적용)"""
        g = self.sizer.get()
        return {"width": g["width"], "trim": g["trim"], "aspect": g["aspect"], "base": self.adjust.get()}

    def _fresh_factory(self, kw):
        """'랜덤'을 새로 누른 것과 같은 값을 만드는 함수 (체크된 항목·범위 설정 그대로) — 한 묶음에 쓸 고정값"""
        rnd_keys = [k for k, rv in self.adjust.rnd.items() if rv.get()]
        _, cfg = self._range_cfg()

        def fresh(rng):
            k2 = dict(kw)
            base = dict(kw["base"])
            base.update(core.random_adjust(rng, rnd_keys))
            k2["base"] = base
            size = core.random_size(rng, cfg)
            use = cfg.get("use", {})
            for key, u in (("width", "len"), ("trim", "trim"), ("aspect", "aspect")):
                if use.get(u, True):
                    k2[key] = size[key]
            return k2
        return fresh

    def _name_kw(self):
        if not self.is_img or self.raw or not hasattr(self, "name_pat"):
            return {}
        try:
            dig = int(self.name_dig.get())
        except Exception:
            dig = 1
        return {"name_pattern": self.name_pat.get(), "digits": dig}

    def _name_example(self):
        try:
            nk = self._name_kw()
            ex = core.numbered_name(nk["name_pattern"], 1, nk["digits"])
            self.name_ex.config(text=f"예: {ex}.jpg")
            self.app.settings.update(img_name_pat=nk["name_pattern"], img_name_dig=nk["digits"])
        except Exception:
            pass

    def _raw_kw_list(self, d):
        return [k for k in self._meta_raw(d).get("raw_keywords", []) if k.strip()] if d else []

    def _raw_kw_label(self):
        if not self.raw:
            return
        if len(self.sel) == 1:
            n = len(self._raw_kw_list(self.sel[0]))
            self.kw_lbl.config(text=f"키워드 {n}개 → 폴더 {n}개" if n else "키워드 없음 → 폴더 개수만큼")
        else:
            self.kw_lbl.config(text="")

    def _raw_keywords(self):
        if len(self.sel) != 1:
            messagebox.showinfo(APP_NAME, "키워드 목록을 넣을 칸 하나를 먼저 골라주세요.")
            return
        RawKeywordDialog(self, self.sel[0])

    def _keyword_dialog(self):
        if len(self.sel) == 1 and self._is_bundle(self.sel[0]):
            messagebox.showinfo(APP_NAME, "묶음 칸은 '세부 선택'을 눌러 시술을 고른 뒤 만들어주세요.")
            return
        if len(self.sel) != 1:
            messagebox.showinfo(APP_NAME, "키워드를 만들 병원 항목 하나를 먼저 선택해주세요.")
            return
        if not core.list_images(self.sel[0]):
            messagebox.showinfo(APP_NAME, "선택한 항목에 이미지가 없습니다.")
            return
        KeywordDialog(self, self.sel[0])

    def _run(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.sel:
            messagebox.showinfo(APP_NAME, "만들 항목을 먼저 선택해주세요.")
            return
        bundles = [d for d in self.sel if self._is_bundle(d)]
        if bundles:
            if len(self.sel) == 1:
                BundleDialog(self, bundles[0])
                return
            self.sel = [d for d in self.sel if d not in bundles]
            self._sync_selection()
            messagebox.showinfo(APP_NAME, "묶음 칸(여러 시술)은 칸 아래 '세부 선택'에서 따로 만들어주세요.\n나머지 항목만 만듭니다.")
            if not self.sel:
                return
        try:
            count = int(self.count.get())
            kw = self._params()
        except Exception:
            messagebox.showwarning(APP_NAME, "숫자 칸을 확인해주세요.")
            return
        self.remember()
        jobs = [(d, self._files_of(d)) for d in self.sel]
        jobs = [(d, f) for d, f in jobs if f]
        if not jobs:
            messagebox.showinfo(APP_NAME, "선택한 항목에 이미지가 없습니다.")
            return
        vary = self.vary.get()
        fresh = self._fresh_factory(kw)
        nk = self._name_kw()
        raw_kws = {d: self._raw_kw_list(d) for d, _ in jobs} if self.raw else {}

        desktop = known_folder("desktop")
        total = sum(len(f) * (len(raw_kws.get(d) or []) or count) for d, f in jobs) if self.is_img else count * len(jobs)
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
                    if self.raw and raw_kws.get(d):
                        # 키워드 목록대로: 바탕화면\병원 시술 날짜\키워드\ 마다 원본 전부
                        base = f"{self._out_base(d)} {datetime.now():%Y%m%d}"
                        root = os.path.join(desktop, base)
                        n = 2
                        while os.path.exists(root):
                            root = os.path.join(desktop, f"{base} ({n})")
                            n += 1
                        for kwd in raw_kws[d]:
                            folder = os.path.join(root, self._safe(kwd))
                            k = 2
                            while os.path.exists(folder):
                                folder = os.path.join(root, f"{self._safe(kwd)} ({k})")
                                k += 1
                            self._make_files(d, files, folder, rng, kw, tick, nk)
                        outs.append(root)
                    elif self.is_img:
                        for _ in range(count):
                            top = core.next_numbered_dir(desktop, self._out_base(d))
                            out = top if self.raw else os.path.join(top, "output")   # 원본 복사는 output 없이 바로
                            self._make_files(d, files, out, rng, fresh(rng) if vary else kw, tick, nk)
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


class KeywordDialog(tk.Toplevel):
    """키워드 50칸(체크·항목별 저장) → 체크한 키워드 × 회차만큼
    바탕화면\\병원명 시술명 날짜\\키워드 폴더 에 이미지 세트 생성"""
    N = 50

    def __init__(self, tab, item_dir):
        super().__init__(tab.app.root)
        self.tab, self.item = tab, item_dir
        m = tab._read_meta(item_dir)
        self.title(f"키워드 생성 - {m['hospital']} {m['procedure']}".strip())
        self.transient(tab.app.root)
        self.geometry("640x680")
        self.minsize(560, 480)
        self.q = queue.Queue()
        self.worker = None
        saved = tab._meta_raw(item_dir).get("keywords", [])

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        # 왼쪽: 키워드 50칸
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        hdr = ttk.Frame(left)
        hdr.pack(fill="x")
        self.all_v = tk.BooleanVar(value=True)
        ttk.Checkbutton(hdr, text="전체", variable=self.all_v, command=self._toggle_all).pack(side="left")
        ttk.Label(hdr, text="키워드", font=FONT_B).pack(side="left", padx=8)
        help_label(hdr, "키워드를 적어두면 이 병원 항목에 자동으로 기억됩니다.\n"
                        "왼쪽 체크한 키워드만 만들어집니다.").pack(side="left")
        sf = ScrollFrame(left)
        sf.pack(fill="both", expand=True, pady=(6, 0))
        self.rows = []
        for i in range(self.N):
            it = saved[i] if i < len(saved) else {}
            r = ttk.Frame(sf.inner)
            r.pack(fill="x", pady=1)
            on = tk.BooleanVar(value=it.get("on", True))
            kw = tk.StringVar(value=it.get("kw", ""))
            ttk.Checkbutton(r, variable=on, command=self._save).pack(side="left")
            ttk.Label(r, text=f"{i + 1:>2}", width=3, foreground=GRAY).pack(side="left")
            e = ttk.Entry(r, textvariable=kw)
            e.pack(side="left", fill="x", expand=True, padx=(2, 6))
            kw.trace_add("write", lambda *a: self._save_later())
            self.rows.append((on, kw))

        # 오른쪽: 회차 · 다중 생성
        right = ttk.Frame(body, padding=(14, 0, 0, 0), width=210)
        right.pack(side="left", fill="y")
        ttk.Label(right, text="총 생성 회차", font=FONT_B).pack(anchor="w")
        self.times = tk.IntVar(value=tab._meta_raw(item_dir).get("kw_times", 1))
        ttk.Spinbox(right, from_=1, to=100, textvariable=self.times, width=8).pack(anchor="w", pady=(4, 2))
        help_label(right, "1 → 체크한 키워드마다 폴더 1개씩.\n"
                          "3 → 키워드마다 '키워드 1', '키워드 2', '키워드 3' 폴더 3개씩.").pack(anchor="w")
        self.vary = tk.BooleanVar(value=tab.vary.get())
        ttk.Checkbutton(right, text="폴더마다 다른 랜덤값", variable=self.vary).pack(anchor="w", pady=(10, 0))
        self.run_btn = ttk.Button(right, text="다중 생성하기", style="Big.TButton", command=self._run)
        self.run_btn.pack(fill="x", pady=(14, 4), ipady=4)
        self.where = WrapLabel(right, text="", foreground="#0a5")
        self.where.pack(fill="x")
        self.prog = ttk.Progressbar(right, mode="determinate")
        self.prog.pack(fill="x", pady=(12, 4))
        self.result = WrapLabel(right, text="")
        self.result.pack(fill="x")
        self.open_btn = ttk.Button(right, text="결과 폴더 열기", state="disabled",
                                   command=lambda: open_folder(self.out_root))
        self.open_btn.pack(anchor="w", pady=(6, 0))
        self.out_root = self._out_root()
        self.where.config(text=f"바탕화면\\{os.path.basename(self.out_root)}\\ 안에 생성됩니다.")
        self._sjob = None
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _out_root(self):
        return os.path.join(known_folder("desktop"),
                            f"{self.tab._out_base(self.item)} {datetime.now():%Y%m%d}")

    def _toggle_all(self):
        for on, _ in self.rows:
            on.set(self.all_v.get())
        self._save()

    def _save_later(self):
        if self._sjob:
            self.after_cancel(self._sjob)
        self._sjob = self.after(500, self._save)

    def _save(self):
        self._sjob = None
        data = [{"kw": kw.get().strip(), "on": bool(on.get())} for on, kw in self.rows]
        while data and not data[-1]["kw"] and data[-1]["on"]:
            data.pop()
        try:
            t = int(self.times.get())
        except Exception:
            t = 1
        try:
            self.tab._write_meta(self.item, keywords=data, kw_times=t)
        except Exception:
            pass

    def _close(self):
        self._save()
        self.destroy()

    def _run(self):
        if self.worker and self.worker.is_alive():
            return
        self._save()
        kws = [kw.get().strip() for on, kw in self.rows if on.get() and kw.get().strip()]
        if not kws:
            messagebox.showinfo(APP_NAME, "체크한 키워드가 없습니다.", parent=self)
            return
        try:
            times = max(1, int(self.times.get()))
            kw = self.tab._params()
        except Exception:
            messagebox.showwarning(APP_NAME, "숫자를 확인해주세요.", parent=self)
            return
        files = self.tab._files_of(self.item)
        vary = self.vary.get()
        fresh = self.tab._fresh_factory(kw)
        name_kw = self.tab._name_kw()
        root = self.out_root = self._out_root()
        safe = self.tab._safe
        self.prog.config(maximum=len(kws) * times * len(files), value=0)
        self.run_btn.config(state="disabled")
        self.result.config(text="만드는 중...")

        def work():
            rng = random.Random()
            done = [0]
            made = 0

            def tick():
                done[0] += 1
                self.q.put(("prog", done[0]))
            try:
                os.makedirs(root, exist_ok=True)
                for k in kws:
                    for _ in range(times):
                        base = safe(k)
                        if times == 1 and not os.path.exists(os.path.join(root, base)):
                            out = os.path.join(root, base)
                        else:
                            out = core.next_numbered_dir(root, base)
                        self.tab._make_files(self.item, files, out, rng, fresh(rng) if vary else kw, tick, name_kw)
                        made += 1
                self.q.put(("done", made, None))
            except Exception as e:
                self.q.put(("done", made, str(e)))

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
                    _, made, err = msg
                    self.run_btn.config(state="normal")
                    self.result.config(text=f"완료: 키워드 폴더 {made}개" + (f"\n오류: {err}" if err else ""))
                    if made:
                        self.open_btn.config(state="normal")
                    if err:
                        messagebox.showerror(APP_NAME, f"만드는 중 문제가 생겼습니다.\n{err}", parent=self)
                    return
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(80, self._poll)


class BundleDialog(tk.Toplevel):
    """묶음 칸 '세부 선택': 왼쪽 시술 목록(체크) → 오른쪽에서 체크한 것만 만들기
    결과: 바탕화면\\병원명\\시술 (n)\\output\\…   (바탕화면에 병원명 폴더가 있으면 '병원명 가공 1', '가공 2' …)"""
    ON, OFF = "☑", "☐"

    def __init__(self, tab, bundle_dir):
        super().__init__(tab.app.root)
        self.tab, self.bundle = tab, bundle_dir
        self.app = tab.app
        m = tab._read_meta(bundle_dir)
        raw = tab._meta_raw(bundle_dir)
        self.hospital = m["hospital"]
        self.title(f"세부 선택 - {self.hospital}")
        self.transient(self.app.root)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = int(sw * 0.75), int(sh * 0.75)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        self.minsize(820, 520)
        self.q = queue.Queue()
        self.worker = None
        checked = raw.get("checked")   # None = 처음 → 전부 체크
        opts = raw.get("bundle_opts", {})

        body = Paned(self, self.app, "bundle_main")
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # ── 왼쪽: 시술 목록 ──
        left = ttk.Frame(body)
        body.add(left, weight=1, width=int(w * 0.42), minsize=280)
        lh = ttk.Frame(left)
        lh.pack(fill="x")
        ttk.Label(lh, text=f"{self.hospital} · 시술 목록", font=FONT_B).pack(side="left")
        help_label(lh, "왼쪽 칸(☑/☐)을 클릭하면 체크가 바뀝니다. 체크한 시술만 만들어집니다.\n"
                       "줄을 클릭하면 오른쪽에 그 시술 미리보기가 나옵니다.\n"
                       "이 창에 시술 폴더를 더 끌어다 놓으면 이 병원에 추가됩니다.").pack(side="left", padx=8)
        ttk.Button(lh, text="전체 해제", command=lambda: self._set_all(False)).pack(side="right")
        ttk.Button(lh, text="전체 선택", command=lambda: self._set_all(True)).pack(side="right", padx=4)
        tf = ttk.Frame(left)
        tf.pack(fill="both", expand=True, pady=6)
        self.tree = ttk.Treeview(tf, columns=("chk", "proc", "n"), show="headings", selectmode="browse")
        for cid, t, cw, anc in (("chk", "선택", 50, "center"), ("proc", "시술", 260, "w"), ("n", "장수", 60, "center")):
            self.tree.heading(cid, text=t)
            self.tree.column(cid, width=cw, anchor=anc, stretch=cid == "proc")
        sb = ttk.Scrollbar(tf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("off", foreground="#999")
        self.tree.bind("<Button-1>", self._click)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._preview())
        for wdg in (self.tree, left):
            enable_drop(wdg, self._drop)
        self.count_lbl = ttk.Label(left, text="")
        self.count_lbl.pack(anchor="w")
        self.checks = {}
        self._fill(checked)

        # ── 오른쪽: 미리보기 · 출력 설정 ──
        rsf = ScrollFrame(body)
        body.add(rsf, weight=1, minsize=380)
        right = ttk.Frame(rsf.inner, padding=(12, 0, 8, 0))
        right.pack(fill="both", expand=True)
        self.prev = Preview(right, height=170)
        self.prev.pack(fill="x")

        g = ttk.LabelFrame(right, text=" 출력 ", padding=10)
        g.pack(fill="x", pady=10)
        ttk.Label(g, text="출력 폴더 이름").grid(row=0, column=0, sticky="w")
        self.out_name = tk.StringVar(value=opts.get("name") or self.hospital)
        ttk.Entry(g, textvariable=self.out_name).grid(row=0, column=1, columnspan=2, sticky="we", padx=6, pady=2)
        ttk.Label(g, text="폴더 개수 (시술마다)").grid(row=1, column=0, sticky="w")
        self.count = tk.IntVar(value=opts.get("count", 1))
        ttk.Spinbox(g, from_=1, to=100, textvariable=self.count, width=6).grid(row=1, column=1, sticky="w", padx=6, pady=2)
        self.use_output = tk.BooleanVar(value=opts.get("output", True))
        ttk.Checkbutton(g, text="각 폴더 안에 output 폴더 만들기", variable=self.use_output).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.rand_once = tk.BooleanVar(value=opts.get("rand_once", False))
        ttk.Checkbutton(g, text="랜덤 가공 (만들 때 '랜덤'을 새로 누른 값으로)", variable=self.rand_once).grid(
            row=3, column=0, columnspan=3, sticky="w")
        self.rand_folder = tk.BooleanVar(value=opts.get("rand_folder", tab.vary.get()))
        ttk.Checkbutton(g, text="폴더마다 다른 랜덤값", variable=self.rand_folder).grid(
            row=4, column=0, columnspan=3, sticky="w")
        help_label(g, "결과: 바탕화면\\출력 폴더 이름\\시술 1\\output\\image001.jpg …\n"
                      "· 폴더 개수 1이면 '시술' 폴더 하나, 2 이상이면 '시술 1', '시술 2' …\n"
                      "· 바탕화면에 같은 이름 폴더가 있으면 '병원명 가공 1', '병원명 가공 2' … 로 새로 만듭니다.\n"
                      "· 가공 값(가로 크기·테두리·비율·색감)과 파일명은 이미지 생성 탭에 맞춰둔 값을 씁니다.\n"
                      "· 랜덤 가공: 시작할 때 새 랜덤값을 한 번 정해 전체에 씀\n"
                      "· 폴더마다 다른 랜덤값: 폴더마다 새 랜덤값 (한 폴더 안은 같은 값)").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        g.columnconfigure(1, weight=1)
        self.where = WrapLabel(right, text="", foreground="#0a5")
        self.where.pack(fill="x")
        for v in (self.out_name,):
            v.trace_add("write", lambda *a: self._where())

        self.run_btn = ttk.Button(right, text="체크한 시술 만들기", style="Big.TButton", command=self._run)
        self.run_btn.pack(fill="x", pady=(10, 4), ipady=4)
        self.prog = ttk.Progressbar(right, mode="determinate")
        self.prog.pack(fill="x", pady=(6, 4))
        self.result = WrapLabel(right, text="")
        self.result.pack(fill="x")
        self.open_btn = ttk.Button(right, text="결과 폴더 열기", state="disabled",
                                   command=lambda: open_folder(self.last_root))
        self.open_btn.pack(anchor="w", pady=(6, 0))
        self.last_root = None
        self._where()
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[0])
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ── 목록 ──
    def _fill(self, checked=None):
        keep = {k: v for k, v in self.checks.items()}
        self.tree.delete(*self.tree.get_children())
        self.checks = {}
        for sd in self.tab._bundle_subs(self.bundle):
            name = self.tab._read_meta(sd)["procedure"] or os.path.basename(sd)
            key = os.path.basename(sd)
            on = keep.get(sd, True if checked is None else key in checked)
            self.checks[sd] = on
            self.tree.insert("", "end", iid=sd, tags=() if on else ("off",),
                             values=(self.ON if on else self.OFF, ("★ " + name) if self.tab._is_special(sd) else name,
                                     len(core.list_images(sd))))
        self._count()

    def _count(self):
        n = sum(self.checks.values())
        self.count_lbl.config(text=f"시술 {len(self.checks)}개 중 {n}개 선택")

    def _click(self, e):
        iid = self.tree.identify_row(e.y)
        if iid and self.tree.identify_column(e.x) == "#1":
            self._toggle(iid)
            return "break"

    def _toggle(self, iid, value=None):
        on = (not self.checks[iid]) if value is None else value
        self.checks[iid] = on
        v = list(self.tree.item(iid, "values"))
        v[0] = self.ON if on else self.OFF
        self.tree.item(iid, values=v, tags=() if on else ("off",))
        self._count()

    def _set_all(self, on):
        for iid in self.checks:
            self._toggle(iid, on)

    def _drop(self, paths):
        self.tab._dropped(paths, target=self.bundle)
        self._fill()

    def _preview(self):
        sel = self.tree.selection()
        imgs = core.list_images(sel[0]) if sel else []
        kw = self.tab._params()
        self.prev.show(imgs[0] if imgs else None, lambda im, sc: core.preview_process(im, sc, **kw), imgs)

    # ── 출력 위치 ──
    def _target_dir(self):
        desk = known_folder("desktop")
        base = self.tab._safe(self.out_name.get().strip() or self.hospital)
        if not os.path.exists(os.path.join(desk, base)):
            return os.path.join(desk, base)
        n = 1
        while os.path.exists(os.path.join(desk, f"{base} 가공 {n}")):
            n += 1
        return os.path.join(desk, f"{base} 가공 {n}")

    def _where(self):
        self.where.config(text=f"저장 위치: 바탕화면\\{os.path.basename(self._target_dir())}\\")

    def _save(self):
        try:
            cnt = int(self.count.get())
        except Exception:
            cnt = 1
        self.tab._write_meta(self.bundle, checked=[os.path.basename(k) for k, v in self.checks.items() if v],
                             bundle_opts={"name": self.out_name.get().strip(), "count": cnt,
                                          "output": self.use_output.get(), "rand_once": self.rand_once.get(),
                                          "rand_folder": self.rand_folder.get()})

    def _close(self):
        try:
            self._save()
        except Exception:
            pass
        self.destroy()

    # ── 만들기 ──
    def _run(self):
        if self.worker and self.worker.is_alive():
            return
        procs = [sd for sd, on in self.checks.items() if on]
        if not procs:
            messagebox.showinfo(APP_NAME, "만들 시술을 왼쪽에서 체크해주세요.", parent=self)
            return
        try:
            count = max(1, int(self.count.get()))
            kw = self.tab._params()
        except Exception:
            messagebox.showwarning(APP_NAME, "숫자를 확인해주세요.", parent=self)
            return
        self._save()
        jobs = [(sd, self.tab._read_meta(sd)["procedure"] or os.path.basename(sd), self.tab._files_of(sd)) for sd in procs]
        root = self.last_root = self._target_dir()
        fresh = self.tab._fresh_factory(kw)
        name_kw = self.tab._name_kw()
        use_out, once, per = self.use_output.get(), self.rand_once.get(), self.rand_folder.get()
        safe = self.tab._safe
        self.prog.config(maximum=sum(len(f) for _, _, f in jobs) * count, value=0)
        self.run_btn.config(state="disabled")
        self.result.config(text="만드는 중...")

        def work():
            rng = random.Random()
            done = [0]
            made = 0
            run_kw = fresh(rng) if once else kw

            def tick():
                done[0] += 1
                self.q.put(("prog", done[0]))
            try:
                os.makedirs(root, exist_ok=True)
                for sd, proc, files in jobs:
                    for k in range(count):
                        folder = os.path.join(root, safe(proc) if count == 1 else f"{safe(proc)} {k + 1}")
                        out = os.path.join(folder, "output") if (use_out and not self.tab.raw) else folder
                        self.tab._make_files(sd, files, out, rng, fresh(rng) if per else run_kw, tick, name_kw)
                        made += 1
                self.q.put(("done", made, None))
            except Exception as e:
                self.q.put(("done", made, str(e)))

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
                    _, made, err = msg
                    self.run_btn.config(state="normal")
                    self.result.config(text=f"완료: 바탕화면\\{os.path.basename(self.last_root)}\\ 에 폴더 {made}개"
                                            + (f"\\n오류: {err}" if err else ""))
                    if made:
                        self.open_btn.config(state="normal")
                    self._where()
                    if err:
                        messagebox.showerror(APP_NAME, f"만드는 중 문제가 생겼습니다.\\n{err}", parent=self)
                    return
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(80, self._poll)


class SpecialDialog(tk.Toplevel):
    """특수 가공: 이미지·GIF를 끌어다 놓고 순서 정하기 → 이미지는 기존 가공 + 워터마크, GIF는 크기 조절 + 워터마크(움직임 유지)"""

    def __init__(self, tab, item=None):
        super().__init__(tab.app.root)
        import special
        self.sp = special
        self.tab, self.app = tab, tab.app
        self.item = item
        s = dict(self.app.settings)
        if item:   # 저장된 버튼 고치기: 그 버튼의 설정을 불러옴
            m = tab._meta_raw(item).get("sp", {})
            s.update({"sp_img_wm": m.get("img_wm", {}), "sp_gif_wm": m.get("gif_wm", {}),
                      "sp_gif_range": m.get("gif_range", [103, 108]), "sp_base": m.get("base", True)})
        self._s = s
        self.title("특수 가공 - 워터마크 · GIF" + (" (저장된 버튼 고치기)" if item else ""))
        self.transient(self.app.root)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = int(sw * 0.8), int(sh * 0.8)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        self.minsize(900, 560)
        self.files = list(tab._files_of(item)) if item else []
        self.q = queue.Queue()
        self.worker = None
        self._drag = None
        self.last_out = None

        body = Paned(self, self.app, "special_main")
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # ── 왼쪽: 순서 목록 ──
        left = ttk.Frame(body)
        body.add(left, weight=1, width=int(w * 0.36), minsize=300)
        lh = ttk.Frame(left)
        lh.pack(fill="x")
        ttk.Label(lh, text="이미지 순서", font=FONT_B).pack(side="left")
        help_label(lh, f"이미지·GIF 파일이나 폴더를 {drop_hint()}'파일 추가'로 넣으세요.\n"
                       "줄을 마우스로 끌어 위아래로 옮기면 순서가 바뀝니다. (▲▼ 버튼도 가능)\n"
                       "이 순서대로 image001, image002 … 로 저장됩니다. (파일명 규칙은 이미지 생성 탭 설정)").pack(side="left", padx=8)
        bb = ttk.Frame(left)
        bb.pack(fill="x", pady=4)
        ttk.Button(bb, text="파일 추가", command=self._add_files).pack(side="left")
        ttk.Button(bb, text="▲", width=3, command=lambda: self._move(-1)).pack(side="left", padx=(8, 2))
        ttk.Button(bb, text="▼", width=3, command=lambda: self._move(1)).pack(side="left")
        ttk.Button(bb, text="이름순", command=self._sort).pack(side="left", padx=6)
        ttk.Button(bb, text="삭제", command=self._remove).pack(side="left")
        ttk.Button(bb, text="비우기", command=self._clear).pack(side="left", padx=3)
        tf = ttk.Frame(left)
        tf.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tf, columns=("no", "name", "kind", "size"), show="headings", selectmode="browse")
        for cid, t, cw, anc in (("no", "순서", 50, "center"), ("name", "파일", 220, "w"),
                                ("kind", "종류", 60, "center"), ("size", "크기", 90, "center")):
            self.tree.heading(cid, text=t)
            self.tree.column(cid, width=cw, anchor=anc, stretch=cid == "name")
        sb = ttk.Scrollbar(tf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("gif", foreground="#7a3cc2")
        self.tree.bind("<ButtonPress-1>", self._drag_start)
        self.tree.bind("<B1-Motion>", self._drag_move)
        self.tree.bind("<ButtonRelease-1>", lambda e: self._drag_end())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._preview())
        for wdg in (self.tree, left):
            enable_drop(wdg, self._drop)

        # ── 오른쪽: 미리보기 · 설정 ──
        rsf = ScrollFrame(body)
        body.add(rsf, weight=2, minsize=420)
        right = ttk.Frame(rsf.inner, padding=(12, 0, 8, 0))
        right.pack(fill="both", expand=True)
        self.prev = Preview(right, height=200)
        self.prev.pack(fill="x")

        g0 = ttk.LabelFrame(right, text=" 이미지 ", padding=8)
        g0.pack(fill="x", pady=(10, 0))
        self.base_on = tk.BooleanVar(value=s.get("sp_base", True))
        ttk.Checkbutton(g0, text="기존 가공도 적용 (이미지 생성 탭의 가로 크기·테두리·비율·색감)",
                        variable=self.base_on, command=self._preview_later).pack(anchor="w")
        self.img_wm = self._wm_frame(g0, "sp_img_wm", special.DEFAULT_IMG_WM)

        g1 = ttk.LabelFrame(right, text=" GIF (움직임·속도 그대로) ", padding=8)
        g1.pack(fill="x", pady=(10, 0))
        rr = ttk.Frame(g1)
        rr.pack(fill="x")
        ttk.Label(rr, text="크기 조절 (%)").pack(side="left")
        gr = s.get("sp_gif_range", [103, 108])
        self.g_lo, self.g_hi = tk.DoubleVar(value=gr[0]), tk.DoubleVar(value=gr[1])
        ttk.Spinbox(rr, from_=50, to=200, increment=0.5, textvariable=self.g_lo, width=6).pack(side="left", padx=4)
        ttk.Label(rr, text="~").pack(side="left")
        ttk.Spinbox(rr, from_=50, to=200, increment=0.5, textvariable=self.g_hi, width=6).pack(side="left", padx=4)
        help_label(rr, "GIF마다 이 범위 안에서 무작위로 크기를 키우거나 줄입니다.\n"
                       "100 = 그대로, 105 = 5% 크게, 95 = 5% 작게.\n재생 속도·반복·프레임 수는 그대로 둡니다.").pack(side="left", padx=6)
        self.gif_wm = self._wm_frame(g1, "sp_gif_wm", special.DEFAULT_GIF_WM)

        g2 = ttk.LabelFrame(right, text=" 버튼으로 저장 ", padding=8)
        g2.pack(fill="x", pady=(10, 0))
        m0 = tab._read_meta(item) if item else {}
        ttk.Label(g2, text="병원명").grid(row=0, column=0, sticky="w")
        self.h_var = tk.StringVar(value=m0.get("hospital", s.get("sp_last_h", "")))
        ttk.Entry(g2, textvariable=self.h_var, width=20).grid(row=0, column=1, sticky="we", padx=6, pady=2)
        ttk.Label(g2, text="시술명").grid(row=1, column=0, sticky="w")
        self.p_var = tk.StringVar(value=m0.get("procedure", "특수"))
        ttk.Entry(g2, textvariable=self.p_var, width=20).grid(row=1, column=1, sticky="we", padx=6, pady=2)
        help_label(g2, "저장하면 이미지 생성 탭에 연한 파란색 '★ 특수 가공' 칸이 맨 앞에 생깁니다.\n"
                       "그 칸을 고르고 '선택 항목 만들기'로 다른 칸처럼 폴더 개수만큼 만듭니다.\n"
                       "(이미지는 이 창의 순서대로, 워터마크·GIF 설정도 이 버튼에 저장)\n\n"
                       "'병원 버튼 안에 넣기'를 고르면 그 병원 칸의 '세부 선택' 안에 시술 하나로 들어갑니다.\n"
                       "저장한 칸을 더블클릭하면 이 창이 다시 열려 고칠 수 있어요.").grid(row=0, column=2, rowspan=2, padx=6)
        g2.columnconfigure(1, weight=1)
        bb2 = ttk.Frame(right)
        bb2.pack(fill="x", pady=(10, 0))
        if item:
            ttk.Button(bb2, text="이 버튼 저장 (고치기)", style="Big.TButton", command=self._save_edit).pack(fill="x", ipady=3)
        ttk.Button(bb2, text="새 버튼으로 추가", style="Big.TButton", command=self._save_new).pack(fill="x", ipady=3, pady=(6, 0))
        inr = ttk.Frame(bb2)
        inr.pack(fill="x", pady=(8, 0))
        self.bundle_map = {f"{h}  (시술 {p.split()[1] if len(p.split()) > 1 else ''})": d
                           for d, h, p, n in tab.groups if tab._is_bundle(d)}
        self.bundle_var = tk.StringVar(value=next(iter(self.bundle_map), ""))
        ttk.Combobox(inr, textvariable=self.bundle_var, values=list(self.bundle_map), state="readonly",
                     width=26).pack(side="left", fill="x", expand=True)
        ttk.Button(inr, text="병원 버튼 안에 넣기", command=self._save_into).pack(side="left", padx=(6, 0), ipady=2)
        if not self.bundle_map:
            ttk.Label(bb2, text="(병원 묶음 칸이 아직 없습니다)", foreground=GRAY).pack(anchor="w")
        self.result = WrapLabel(right, text="", foreground="#0a5")
        self.result.pack(fill="x", pady=(8, 0))
        self._refill()
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ── 워터마크 설정 칸 ──
    def _wm_frame(self, parent, key, default):
        sp = self.sp
        cur = dict(default)
        cur.update(self._s.get(key, {}))
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=(8, 0))
        v = {"on": tk.BooleanVar(value=cur["on"]), "text": tk.StringVar(value=cur["text"]),
             "style": tk.StringVar(value=cur["style"]), "size": tk.DoubleVar(value=cur["size"]),
             "opacity": tk.DoubleVar(value=cur["opacity"]), "angle": tk.DoubleVar(value=cur["angle"]),
             "color": tk.StringVar(value=cur["color"]), "font": tk.StringVar(value=cur["font"]),
             "tracking": tk.DoubleVar(value=cur.get("tracking", 0)), "gap": tk.DoubleVar(value=cur.get("gap", 40))}
        ttk.Checkbutton(f, text="워터마크 넣기", variable=v["on"]).grid(row=0, column=0, sticky="w")
        ttk.Label(f, text="문구").grid(row=0, column=1, sticky="e", padx=(10, 2))
        ttk.Entry(f, textvariable=v["text"], width=18).grid(row=0, column=2, sticky="w")
        ttk.Label(f, text="위치").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(f, textvariable=v["style"], values=sp.WM_STYLES, state="readonly", width=14).grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Label(f, text="크기 (가로 대비 %)").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(f, from_=2, to=90, increment=1, textvariable=v["size"], width=6).grid(row=2, column=1, sticky="w")
        ttk.Label(f, text="진하기 (%)").grid(row=2, column=2, sticky="w")
        ttk.Spinbox(f, from_=1, to=100, increment=1, textvariable=v["opacity"], width=6).grid(row=2, column=3, sticky="w")
        ttk.Label(f, text="기울기 (도)").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Spinbox(f, from_=-90, to=90, increment=5, textvariable=v["angle"], width=6).grid(row=3, column=1, sticky="w")
        ttk.Label(f, text="색").grid(row=3, column=2, sticky="w")
        ttk.Combobox(f, textvariable=v["color"], values=list(sp.COLORS), state="readonly", width=6).grid(row=3, column=3, sticky="w")
        ttk.Label(f, text="자간 (글자 간격 %)").grid(row=6, column=0, sticky="w", pady=3)
        ttk.Spinbox(f, from_=-20, to=150, increment=5, textvariable=v["tracking"], width=6).grid(row=6, column=1, sticky="w")
        ttk.Label(f, text="문구 사이 간격 (%)").grid(row=6, column=2, sticky="w")
        ttk.Spinbox(f, from_=0, to=90, increment=5, textvariable=v["gap"], width=6).grid(row=6, column=3, sticky="w")
        ttk.Label(f, text="글꼴").grid(row=4, column=0, sticky="w")
        ttk.Combobox(f, textvariable=v["font"], values=sp.FONTS, state="readonly", width=24).grid(row=4, column=1, columnspan=3, sticky="w")
        help_label(f, "위치: 대각선 2개(기울여서 위·아래 두 곳) / 위쪽 모서리 2개 / 네 모서리 / 가운데 / 바둑판 반복\n"
                      "크기: 글자 한 덩이 폭이 이미지 가로의 몇 % 인지\n진하기: 낮을수록 흐릿 (예: 이미지 10%, GIF 75%)\n"
                      "기울기는 대각선·가운데·바둑판에만 적용됩니다. 한글 문구는 맑은 고딕으로 씁니다.\n"
                      "자간: 글자와 글자 사이 (0 = 기본, 30 = 글자 크기의 30% 만큼 더 띄움)\n"
                      "문구 사이 간격: 대각선 두 문구가 서로 얼마나 떨어질지 (40 = 기본, 클수록 멀리) · 바둑판은 반복 간격").grid(
            row=7, column=0, columnspan=4, sticky="w", pady=(4, 0))
        for var in v.values():
            var.trace_add("write", lambda *a: self._preview_later())
        return v

    def _wm_get(self, v, key):
        o = {}
        for k, var in v.items():
            try:
                o[k] = var.get()
            except Exception:
                o[k] = self.sp.DEFAULT_IMG_WM.get(k)
        if not self.item:   # 새로 만들 때만 다음 기본값으로 기억
            self.app.settings[key] = o
        return o

    # ── 목록 ──
    def _drop(self, paths):
        out = []
        for p in paths:
            out += core.list_images(p) if os.path.isdir(p) else [p]
        for p in out:
            p = os.path.normpath(p)
            if p in self.files or os.path.splitext(p)[1].lower() not in core.IMAGE_EXT:
                continue
            self.files.append(p)
        self._refill()

    def _add_files(self):
        self._drop(filedialog.askopenfilenames(parent=self, filetypes=[("이미지·GIF", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"),
                                                                       ("모든 파일", "*.*")]))

    def _refill(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self.files):
            gif = self.sp.is_gif(p)
            try:
                from PIL import Image
                with Image.open(p) as im:
                    sz = f"{im.size[0]}×{im.size[1]}"
            except Exception:
                sz = "?"
            self.tree.insert("", "end", iid=p, values=(i + 1, os.path.basename(p), "GIF" if gif else "이미지", sz),
                             tags=("gif",) if gif else ())
        if select and self.tree.exists(select):
            self.tree.selection_set(select)
        elif self.files and not self.tree.selection():
            self.tree.selection_set(self.files[0])

    def _renumber(self):
        self.files = list(self.tree.get_children())
        for i, iid in enumerate(self.files):
            v = list(self.tree.item(iid, "values"))
            v[0] = i + 1
            self.tree.item(iid, values=v)

    def _move(self, d):
        sel = self.tree.selection()
        if not sel:
            return
        i = self.tree.index(sel[0]) + d
        if 0 <= i < len(self.files):
            self.tree.move(sel[0], "", i)
            self._renumber()

    def _drag_start(self, e):
        self._drag = self.tree.identify_row(e.y) or None

    def _drag_move(self, e):
        if not self._drag:
            return
        tgt = self.tree.identify_row(e.y)
        if tgt and tgt != self._drag:
            self.tree.move(self._drag, "", self.tree.index(tgt))
            self.tree.config(cursor="sb_v_double_arrow")

    def _drag_end(self):
        if self._drag:
            self.tree.config(cursor="")
            self._renumber()
        self._drag = None

    def _sort(self):
        self.files = core.natural_sorted(self.files)
        self._refill()

    def _remove(self):
        for iid in self.tree.selection():
            if iid in self.files:
                self.files.remove(iid)
        self._refill()

    def _clear(self):
        self.files = []
        self._refill()

    # ── 미리보기 ──
    def _preview_later(self):
        if getattr(self, "_pv", None):
            self.after_cancel(self._pv)
        self._pv = self.after(300, self._preview)

    def _preview(self):
        self._pv = None
        sel = self.tree.selection()
        if not sel:
            self.prev.show(None, None)
            return
        p = sel[0]
        gif = self.sp.is_gif(p)
        wm = self._wm_get(self.gif_wm if gif else self.img_wm, "sp_gif_wm" if gif else "sp_img_wm")
        base_kw = self.tab._params() if (self.base_on.get() and not gif) else None
        sp = self.sp

        def proc(im, sc):
            if base_kw:
                im = core.preview_process(im, sc, **base_kw)
            return sp.watermark(im, wm).convert("RGB")
        self.prev.show(p, proc, self.files)

    # ── 버튼으로 저장 ──
    def _blob(self):
        try:
            gr = [float(self.g_lo.get()), float(self.g_hi.get())]
        except Exception:
            gr = [103, 108]
        return {"img_wm": self._wm_get(self.img_wm, "sp_img_wm"), "gif_wm": self._wm_get(self.gif_wm, "sp_gif_wm"),
                "gif_range": gr, "base": bool(self.base_on.get())}

    def _check(self):
        if not self.tree.get_children():
            messagebox.showinfo(APP_NAME, "이미지나 GIF를 먼저 넣어주세요.", parent=self)
            return False
        return True

    def _write_item(self, d, hospital, procedure):
        """창의 순서대로 파일을 d 에 맞추고(새 파일 복사·빠진 파일 삭제) 설정 저장"""
        order, keep = [], set()
        dn = os.path.normcase(os.path.abspath(d))
        for p in self.tree.get_children():
            if os.path.normcase(os.path.dirname(os.path.abspath(p))) == dn:
                name = os.path.basename(p)
            else:
                dst = core._unique(os.path.join(d, os.path.basename(p)))
                shutil.copy2(p, dst)
                name = os.path.basename(dst)
            order.append(name)
            keep.add(name)
        for f in core.list_images(d):
            if os.path.basename(f) not in keep:
                try:
                    os.remove(f)
                except OSError:
                    pass
        self.tab._write_meta(d, hospital, procedure, special=True, order=order, sp=self._blob())
        self.app.settings["sp_last_h"] = hospital

    def _names(self):
        h, p = self.h_var.get().strip(), self.p_var.get().strip() or "특수"
        if not h:
            messagebox.showinfo(APP_NAME, "병원명을 적어주세요.", parent=self)
            return None
        return h, p

    def _save_new(self):
        if not self._check():
            return
        nm = self._names()
        if not nm:
            return
        base = self.tab._safe(f"{nm[0]} {nm[1]}")
        d = os.path.join(self.tab.lib, base)
        k = 2
        while os.path.exists(d):
            d = os.path.join(self.tab.lib, f"{base} ({k})")
            k += 1
        os.makedirs(d)
        self._write_item(d, *nm)
        self.tab.reload(select=d)
        self.result.config(text=f"'★ {nm[0]} {nm[1]}' 칸을 이미지 생성 탭 맨 앞에 추가했습니다.")
        self._close()

    def _save_into(self):
        if not self._check():
            return
        bd = self.bundle_map.get(self.bundle_var.get())
        if not bd:
            messagebox.showinfo(APP_NAME, "넣을 병원 칸을 골라주세요.", parent=self)
            return
        hospital = self.tab._read_meta(bd)["hospital"]
        proc = self.p_var.get().strip() or "특수"
        base = self.tab._safe(proc)
        d = os.path.join(bd, base)
        k = 2
        while os.path.exists(d):
            d = os.path.join(bd, f"{base} ({k})")
            k += 1
        os.makedirs(d)
        self._write_item(d, hospital, proc)
        self.tab.reload(select=bd)
        self.result.config(text=f"'{hospital}' 칸의 세부 선택 안에 '★ {proc}' 로 넣었습니다.")
        self._close()

    def _save_edit(self):
        if not self.item or not self._check():
            return
        nm = self._names()
        if not nm:
            return
        self._write_item(self.item, *nm)
        self.tab.reload(select=self.item if os.path.dirname(self.item) == self.tab.lib else None)
        self._close()

    def _close(self):
        try:
            if not self.item:
                self._wm_get(self.img_wm, "sp_img_wm")
                self._wm_get(self.gif_wm, "sp_gif_wm")
                self.app.settings.update(sp_base=self.base_on.get(),
                                         sp_gif_range=[float(self.g_lo.get()), float(self.g_hi.get())])
        except Exception:
            pass
        self.destroy()


class RawKeywordDialog(tk.Toplevel):
    """이미지 생성 (원본): 키워드 목록 (엑셀에서 한 줄씩 붙여넣기) — 키워드마다 원본 폴더 하나"""

    def __init__(self, tab, item):
        super().__init__(tab.app.root)
        self.tab, self.item = tab, item
        m = tab._read_meta(item)
        self.title(f"키워드 목록 - {m['hospital']} {m['procedure']}".strip())
        self.transient(tab.app.root)
        self.geometry("520x620")
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="키워드 (한 줄에 하나)", font=FONT_B).pack(side="left")
        help_label(top, "엑셀에서 키워드 칸을 긁어 그대로 붙여넣으세요 (Ctrl+V).\n"
                        "빈 줄은 무시합니다. 키워드 하나마다 원본 폴더 하나가 만들어집니다.\n"
                        "이 칸에 저장되어 다음에도 그대로 남아 있습니다.").pack(side="left", padx=8)
        self.cnt = ttk.Label(top, text="", foreground="#0a5", font=FONT_B)
        self.cnt.pack(side="right")
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=8)
        self.lines = tk.Text(body, width=4, padx=4, takefocus=0, bd=0, bg="#f0f0f0", fg="#888",
                             font=("맑은 고딕", 10), state="disabled")
        self.lines.pack(side="left", fill="y")
        self.txt = tk.Text(body, wrap="none", font=("맑은 고딕", 10), undo=True, relief="solid", bd=1)
        sb = ttk.Scrollbar(body, command=self._yview)
        self.txt.configure(yscrollcommand=lambda a, b: (sb.set(a, b), self.lines.yview_moveto(a)))
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.txt.insert("1.0", "\n".join(tab._meta_raw(item).get("raw_keywords", [])))
        self.txt.bind("<<Modified>>", self._changed)
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Button(bar, text="비우기", command=lambda: self.txt.delete("1.0", "end")).pack(side="left")
        ttk.Button(bar, text="닫기", command=self._close).pack(side="right")
        ttk.Button(bar, text="저장", style="Big.TButton", command=self._save).pack(side="right", padx=6)
        self._refresh()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _yview(self, *a):
        self.txt.yview(*a)
        self.lines.yview(*a)

    def _list(self):
        return [l.strip() for l in self.txt.get("1.0", "end-1c").replace("\t", " ").split("\n") if l.strip()]

    def _refresh(self):
        n_lines = int(self.txt.index("end-1c").split(".")[0])
        self.lines.config(state="normal")
        self.lines.delete("1.0", "end")
        self.lines.insert("1.0", "\n".join(str(i + 1) for i in range(n_lines)))
        self.lines.config(state="disabled")
        n = len(self._list())
        self.cnt.config(text=f"키워드 {n}개 → 폴더 {n}개" if n else "키워드 없음 → 폴더 개수만큼")

    def _changed(self, _e=None):
        if self.txt.edit_modified():
            self.txt.edit_modified(False)
            self._refresh()

    def _save(self):
        self.tab._write_meta(self.item, raw_keywords=self._list())
        self.tab._raw_kw_label()
        self.tab.app.status(f"키워드 {len(self._list())}개를 저장했습니다.")
        self.destroy()

    def _close(self):
        self._save()
