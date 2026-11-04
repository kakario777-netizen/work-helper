"""업무 도우미 - 원고 이미지 배치 (텍스트 정리 세부 탭)"""
import os
import shutil
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import core
import imgplace
from common import (APP_NAME, GRAY, FONT_B, known_folder, open_folder, text_box, help_label,
                    enable_drop, drop_hint, Paned, WrapLabel)

NONE = "(병원 선택 안 함 · 기본 샘플)"


class PlacePanel(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        self.rows = {}        # path → {"group": 보관폴더 or None, "count": int}
        self._groups = {}     # 콤보 글자 → 보관폴더
        self._cur_group = None

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="파일 추가", command=self._add_files).pack(side="left")
        ttk.Button(top, text="폴더 추가", command=self._add_folder).pack(side="left", padx=3)
        ttk.Button(top, text="선택 삭제", command=self._remove_sel).pack(side="left")
        ttk.Button(top, text="비우기", command=self._clear).pack(side="left", padx=3)
        help_label(top, f"1) 원고(.txt)를 {drop_hint()}넣습니다.\n"
                        "2) 원고를 고르고 오른쪽에서 병원(이미지 생성 목록)을 고르면 이미지 수가 그 병원 장수로 채워집니다.\n"
                        "   숫자만 직접 넣어도 됩니다. 여러 원고를 한꺼번에 골라 적용할 수 있어요.\n"
                        "3) 병원마다 '샘플'을 한 번 넣어두면 저장됩니다. 이미지 번호가 들어간 완성 원고 한 편을 붙여넣으면\n"
                        "   번호 모양([사진 1], (1), 1 …)·위아래 빈 줄·제목 다음/맨 끝 이미지 여부를 따라 합니다.\n"
                        "   '[사진 1]' 처럼 한 줄만 넣으면 모양만 따릅니다.\n"
                        "4) '이미지 번호 넣기'를 누르면 원고 사이사이에 빈 줄과 번호 줄만 끼워 넣어 원고를 바꿉니다.\n\n"
                        "원고 글자는 절대 바꾸지 않습니다. 저장 전에 '넣은 줄을 빼면 원본과 똑같은지' 검사하고,\n"
                        "원본은 바탕화면\\원고 수정 원본\\ 폴더에 '원본 원래제목 날짜 시분초.txt' 로 먼저 보관합니다."
                   ).pack(side="left", padx=10)
        ttk.Button(top, text="원본 보관 폴더", command=lambda: (os.makedirs(self._backup_dir(), exist_ok=True),
                                                           open_folder(self._backup_dir()))).pack(side="right")

        body = Paned(self, app, "place_main")
        body.pack(fill="both", expand=True, pady=8)

        lf = ttk.Frame(body)
        body.add(lf, weight=1, width=520, minsize=300)
        cols = (("file", "원고", 220), ("grp", "병원·시술", 170), ("cnt", "이미지", 60),
                ("para", "문단", 50), ("st", "상태", 110))
        self.tree = ttk.Treeview(lf, columns=[c[0] for c in cols], show="headings", selectmode="extended")
        for cid, t, w in cols:
            self.tree.heading(cid, text=t)
            self.tree.column(cid, width=w, anchor="w" if cid in ("file", "grp", "st") else "center")
        self.tree.tag_configure("done", foreground="#0a5")
        self.tree.tag_configure("has", foreground="#b70")
        sb = ttk.Scrollbar(lf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        for w in (self.tree, lf):
            enable_drop(w, self._drop)

        right = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(right, weight=1, minsize=320)

        g1 = ttk.LabelFrame(right, text=" 선택한 원고 ", padding=8)
        g1.pack(fill="x")
        ttk.Label(g1, text="병원").grid(row=0, column=0, sticky="w")
        self.grp = tk.StringVar(value=NONE)
        self.combo = ttk.Combobox(g1, textvariable=self.grp, state="readonly", postcommand=self._fill_groups)
        self.combo.grid(row=0, column=1, columnspan=2, sticky="we", padx=6, pady=2)
        self.combo.bind("<<ComboboxSelected>>", lambda e: self._group_picked())
        ttk.Label(g1, text="이미지 수").grid(row=1, column=0, sticky="w")
        self.cnt = tk.IntVar(value=0)
        ttk.Spinbox(g1, from_=0, to=200, textvariable=self.cnt, width=6).grid(row=1, column=1, sticky="w", padx=6, pady=2)
        ttk.Button(g1, text="선택한 원고에 적용", command=self._apply_sel).grid(row=1, column=2, sticky="e")
        g1.columnconfigure(1, weight=1)

        g2 = ttk.LabelFrame(right, text=" 샘플 ", padding=8)
        g2.pack(fill="x", pady=8)
        self.sample_for = ttk.Label(g2, text="", font=FONT_B)
        self.sample_for.pack(anchor="w")
        sbox, self.sample = text_box(g2, height=6)
        sbox.pack(fill="x", pady=4)
        sb2 = ttk.Frame(g2)
        sb2.pack(fill="x")
        ttk.Button(sb2, text="샘플 저장", command=self._save_sample).pack(side="left")
        self.rule_lbl = WrapLabel(sb2, text="", foreground="#0a5")
        self.rule_lbl.pack(side="left", fill="x", expand=True, padx=8)

        ttk.Label(right, text="미리보기 (주황 = 넣을 번호 줄)", foreground=GRAY).pack(anchor="w")
        pbox, self.preview = text_box(right, height=10)
        pbox.pack(fill="both", expand=True)
        self.preview.tag_configure("mark", background="#ffe2b8", foreground="#a40")

        bot = ttk.Frame(self)
        bot.pack(fill="x")
        self.run_btn = ttk.Button(bot, text="이미지 번호 넣기 (원고 교체)", style="Big.TButton", command=self._run)
        self.run_btn.pack(side="left", ipady=4, ipadx=10)
        self.result = ttk.Label(bot, text="")
        self.result.pack(side="left", padx=14)
        self._show_sample(None)

    # ── 목록 ──
    def _drop(self, paths):
        files = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, fs in os.walk(p):
                    files += [os.path.join(root, f) for f in fs if f.lower().endswith(".txt")]
            elif p.lower().endswith(".txt"):
                files.append(p)
        for p in core.natural_sorted(files):
            p = os.path.normpath(p)
            if p in self.rows:
                continue
            self.rows[p] = {"group": None, "count": 0, "done": False}
            self.tree.insert("", "end", iid=p)
            self._refresh(p)

    def _add_files(self):
        self._drop(filedialog.askopenfilenames(filetypes=[("메모장", "*.txt"), ("모든 파일", "*.*")]))

    def _add_folder(self):
        d = filedialog.askdirectory()
        if d:
            self._drop([d])

    def _remove_sel(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.rows.pop(iid, None)

    def _clear(self):
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.preview.delete("1.0", "end")

    def _refresh(self, p):
        r = self.rows[p]
        try:
            text, _ = imgplace.read_doc(p)
            info = imgplace.analyze(text)
            para = len(info["gaps"])
            has = info["markers"]
        except Exception:
            para, has = "?", 0
        st = "완료" if r.get("done") else (f"번호 {has}개 있음" if has else "")
        tags = ("done",) if r.get("done") else (("has",) if has else ())
        self.tree.item(p, tags=tags, values=(os.path.basename(p), self._group_name(r["group"]) if r["group"] else "-",
                                             r["count"] or "-", para, st))

    # ── 병원(이미지 생성 목록) ──
    def _lib(self):
        return getattr(self.app, "cap_tab", None)

    def _group_name(self, d):
        lib = self._lib()
        if not lib or not d:
            return ""
        m = lib._read_meta(d)
        return f"{m['hospital']} {m['procedure']}".strip()

    def _fill_groups(self):
        lib = self._lib()
        self._groups = {NONE: None}
        if lib:
            for d, h, p, n in getattr(lib, "procs", lib.groups):
                self._groups[f"{h} {p}".strip() + f"  ({n}장)"] = d
        self.combo["values"] = list(self._groups)

    def _group_picked(self):
        self._fill_groups() if not self._groups else None
        d = self._groups.get(self.grp.get())
        if d:
            self.cnt.set(len(core.list_images(d)))
        self._show_sample(d)

    def _apply_sel(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "왼쪽에서 원고를 먼저 골라주세요. (Ctrl·Shift+클릭으로 여러 개)")
            return
        if not self._groups:
            self._fill_groups()
        d = self._groups.get(self.grp.get())
        try:
            n = max(0, int(self.cnt.get()))
        except Exception:
            n = 0
        for p in sel:
            self.rows[p].update(group=d, count=n, done=False)
            self._refresh(p)
        self._on_select()

    def _on_select(self):
        sel = self.tree.selection()
        if not sel:
            return
        r = self.rows[sel[0]]
        if not self._groups:
            self._fill_groups()
        name = next((k for k, v in self._groups.items() if v == r["group"]), NONE)
        self.grp.set(name)
        self.cnt.set(r["count"])
        self._show_sample(r["group"])
        self._preview(sel[0])

    # ── 샘플 ──
    def _sample_text(self, d):
        lib = self._lib()
        if d and lib:
            return lib._meta_raw(d).get("img_sample", "")
        return self.app.settings.get("place_default_sample", "")

    def _rule(self, d):
        return imgplace.learn_sample(self._sample_text(d))

    def _show_sample(self, d):
        self._cur_group = d
        self.sample_for.config(text=f"{self._group_name(d)} 샘플" if d else "기본 샘플 (병원을 안 골랐을 때)")
        self.sample.delete("1.0", "end")
        self.sample.insert("1.0", self._sample_text(d))
        self._show_rule(self._rule(d))

    def _show_rule(self, r):
        bits = [f"모양: {imgplace.marker_text(r, 1)}"]
        if r.get("head"):
            bits.append("첫 이미지는 제목 다음")
        if r.get("tail"):
            bits.append("마지막 이미지는 본문 끝")
        bits.append(f"위 빈 줄 {r['before']} · 아래 빈 줄 {r['after']}")
        self.rule_lbl.config(text="  ·  ".join(bits))

    def _save_sample(self):
        txt = self.sample.get("1.0", "end-1c")
        lib = self._lib()
        if self._cur_group and lib:
            lib._write_meta(self._cur_group, img_sample=txt)
        else:
            self.app.settings["place_default_sample"] = txt
        self._show_rule(imgplace.learn_sample(txt))
        sel = self.tree.selection()
        if sel:
            self._preview(sel[0])
        self.app.status("샘플을 저장했습니다.")

    # ── 미리보기 ──
    def _build(self, p):
        r = self.rows[p]
        text, info = imgplace.read_doc(p)
        new, n = imgplace.place(text, r["count"], self._rule(r["group"]))
        return text, new, n, info

    def _preview(self, p):
        self.preview.delete("1.0", "end")
        try:
            if self.rows[p].get("done"):   # 이미 바꾼 원고는 파일 그대로 보여줌
                text, _ = imgplace.read_doc(p)
                for line in text.replace("\r\n", "\n").split("\n"):
                    self.preview.insert("end", line + "\n", ("mark",) if imgplace.is_marker(line) else ())
                return
            _, new, n, _ = self._build(p)
            flags = imgplace.place.last_inserted
        except Exception as e:
            self.preview.insert("1.0", f"미리보기 불가: {e}")
            return
        for line, ins in zip(new.replace("\r\n", "\n").split("\n"), flags):
            self.preview.insert("end", line + "\n", ("mark",) if ins and line.strip() else ())

    # ── 실행 ──
    def _backup_dir(self):
        return os.path.join(known_folder("desktop"), "원고 수정 원본")

    def _run(self):
        todo = [p for p in self.tree.get_children() if self.rows[p]["count"] > 0 and not self.rows[p].get("done")]
        if not todo:
            messagebox.showinfo(APP_NAME, "이미지 수가 정해진 원고가 없습니다.\n원고를 고르고 오른쪽에서 이미지 수를 적용해주세요.")
            return
        has = [p for p in todo if imgplace.analyze(imgplace.read_doc(p)[0])["markers"]]
        if has:
            ans = messagebox.askyesnocancel(
                APP_NAME, f"이미 이미지 번호가 있어 보이는 원고가 {len(has)}개 있습니다.\n\n"
                          "예: 그 원고는 건너뛰기\n아니요: 그래도 넣기\n취소: 그만두기")
            if ans is None:
                return
            if ans:
                todo = [p for p in todo if p not in has]
        if not todo:
            return
        if not messagebox.askyesno(APP_NAME, f"원고 {len(todo)}개에 이미지 번호를 넣어 원고 파일을 바꿉니다.\n"
                                             "원본은 바탕화면\\원고 수정 원본\\ 에 먼저 보관합니다.\n\n계속할까요?"):
            return
        bdir = self._backup_dir()
        os.makedirs(bdir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d %H시%M분%S초")
        ok, errors = 0, []
        for p in todo:
            try:
                text, new, n, info = self._build(p)
                stem = os.path.splitext(os.path.basename(p))[0]
                bk = os.path.join(bdir, f"원본 {stem} {stamp}.txt")
                k = 2
                while os.path.exists(bk):
                    bk = os.path.join(bdir, f"원본 {stem} {stamp} ({k}).txt")
                    k += 1
                shutil.copy2(p, bk)           # 원본 그대로(바이트 그대로) 보관
                imgplace.write_doc(p, new, info)
                # 저장한 파일을 다시 읽어 원본 글자가 그대로인지 한 번 더 확인
                back, _ = imgplace.read_doc(p)
                orig_lines = text.replace("\r\n", "\n").split("\n")
                it = iter(back.replace("\r\n", "\n").split("\n"))
                if not all(any(l == x for x in it) for l in orig_lines):
                    shutil.copy2(bk, p)
                    raise ValueError("저장 후 확인에서 원본과 달라 되돌렸습니다")
                self.rows[p]["done"] = True
                ok += 1
            except Exception as e:
                errors.append(f"{os.path.basename(p)}: {e}")
            self._refresh(p)
        self.result.config(text=f"완료 {ok}개" + (f" · 실패 {len(errors)}개" if errors else "")
                                + "  ·  원본: 바탕화면\\원고 수정 원본")
        if errors:
            messagebox.showwarning(APP_NAME, "일부 원고를 바꾸지 못했습니다. (그 원고는 그대로입니다)\n\n" + "\n".join(errors[:15]))
        sel = self.tree.selection()
        if sel:
            self._preview(sel[0])
