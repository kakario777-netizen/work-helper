"""업무 도우미 - 파일 이름 변경 (가공 없음, 이름만)  폴더마다 탐색기 순서 그대로 번호 매기기"""
import functools
import json
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import core
from common import APP_NAME, GRAY, FONT_B, help_label, enable_drop, drop_hint, Paned, settings_path

_cmp = None
if sys.platform == "win32":
    try:
        import ctypes
        _f = ctypes.windll.shlwapi.StrCmpLogicalW
        _f.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        _f.restype = ctypes.c_int
        _cmp = _f
    except Exception:
        _cmp = None


def explorer_sorted(names):
    """윈도우 탐색기와 똑같은 순서 (1, 2, 3 … 10, 11)"""
    if _cmp:
        return sorted(names, key=functools.cmp_to_key(lambda a, b: _cmp(a, b)))
    return core.natural_sorted(names)


def undo_path():
    return os.path.join(os.path.dirname(settings_path()), "rename_undo.json")


class RenamePanel(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        s = app.settings
        self.folders = []
        self.plan = {}   # folder → [(옛 경로, 새 경로)]

        body = Paned(self, app, "rename_main")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        body.add(left, weight=2, minsize=360)
        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Button(top, text="폴더 추가", command=self._add_folder).pack(side="left")
        ttk.Button(top, text="선택 삭제", command=self._remove).pack(side="left", padx=3)
        ttk.Button(top, text="비우기", command=self._clear).pack(side="left")
        help_label(top, f"폴더를 {drop_hint()}'폴더 추가'로 여러 개 넣으세요.\n"
                        "폴더 안 파일의 이름만 바꿉니다. 이미지 내용·확장자는 그대로입니다.\n"
                        "순서는 윈도우 탐색기 이름순과 똑같이(1, 2, 3 … 10, 11) 매기고, 폴더마다 시작 번호부터 다시 셉니다.\n"
                        "아래 목록에서 '현재 이름 → 새 이름'을 확인한 뒤 '이름 바꾸기'를 누르세요.").pack(side="left", padx=8)
        self.count_lbl = ttk.Label(top, text="")
        self.count_lbl.pack(side="right")
        tf = ttk.Frame(left)
        tf.pack(fill="both", expand=True, pady=6)
        self.tree = ttk.Treeview(tf, columns=("old", "new"), show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="폴더")
        self.tree.heading("old", text="현재 이름")
        self.tree.heading("new", text="새 이름")
        self.tree.column("#0", width=200)
        self.tree.column("old", width=240)
        self.tree.column("new", width=200)
        self.tree.tag_configure("same", foreground="#999")
        self.tree.tag_configure("done", foreground="#0a5")
        sb = ttk.Scrollbar(tf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for w in (self.tree, left):
            enable_drop(w, self._drop)

        right = ttk.Frame(body, padding=(12, 0))
        body.add(right, weight=1, minsize=280)
        g = ttk.LabelFrame(right, text=" 이름 규칙 ", padding=10)
        g.pack(fill="x")
        ttk.Label(g, text="새 이름").grid(row=0, column=0, sticky="w")
        self.pat = tk.StringVar(value=s.get("rn_pat", "{번호}"))
        ttk.Entry(g, textvariable=self.pat, width=18).grid(row=0, column=1, columnspan=2, sticky="we", padx=6)
        ttk.Label(g, text="자릿수").grid(row=1, column=0, sticky="w", pady=4)
        self.dig = tk.IntVar(value=s.get("rn_dig", 3))
        ttk.Spinbox(g, from_=1, to=6, textvariable=self.dig, width=5).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(g, text="시작 번호").grid(row=2, column=0, sticky="w")
        self.start = tk.IntVar(value=s.get("rn_start", 1))
        ttk.Spinbox(g, from_=0, to=99999, textvariable=self.start, width=7).grid(row=2, column=1, sticky="w", padx=6)
        quick = ttk.Frame(g)
        quick.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(quick, text="빠른 선택:").pack(side="left")
        for label, p, d in (("t1~", "t{번호}", 1), ("001~", "{번호}", 3), ("이미지001~", "이미지{번호}", 3),
                            ("image001~", "image{번호}", 3)):
            ttk.Button(quick, text=label, command=lambda p=p, d=d: (self.pat.set(p), self.dig.set(d))).pack(side="left", padx=2)
        self.only_img = tk.BooleanVar(value=s.get("rn_only_img", True))
        ttk.Checkbutton(g, text="이미지·GIF 파일만 (txt 등 다른 파일은 그대로)", variable=self.only_img).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.sub = tk.BooleanVar(value=s.get("rn_sub", False))
        ttk.Checkbutton(g, text="하위 폴더도 (하위 폴더마다 따로 번호)", variable=self.sub).grid(
            row=5, column=0, columnspan=3, sticky="w")
        help_label(g, "{번호} 자리에 1, 2, 3 … 이 들어갑니다. 자릿수만큼 앞에 0을 채워요.\n"
                      "· t{번호} + 자릿수 1 → t1, t2 … t10\n· {번호} + 자릿수 3 → 001, 002 …\n"
                      "· 이미지{번호} + 자릿수 3 → 이미지001, 이미지002 …\n"
                      "{번호} 를 안 쓰면 이름 끝에 번호를 붙입니다. 확장자(.jpg 등)는 원래 그대로 둡니다.").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.ex = ttk.Label(g, text="", foreground="#0a5")
        self.ex.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))
        g.columnconfigure(1, weight=1)
        for v in (self.pat, self.dig, self.start, self.only_img, self.sub):
            v.trace_add("write", lambda *a: self._later())

        self.run_btn = ttk.Button(right, text="이름 바꾸기", style="Big.TButton", command=self._run)
        self.run_btn.pack(fill="x", pady=(14, 4), ipady=4)
        self.undo_btn = ttk.Button(right, text="방금 바꾼 것 되돌리기", command=self._undo)
        self.undo_btn.pack(fill="x")
        self.result = ttk.Label(right, text="", wraplength=260, justify="left")
        self.result.pack(anchor="w", pady=8)
        self._job = None
        self._refresh()

    def remember(self):
        try:
            self.app.settings.update(rn_pat=self.pat.get(), rn_dig=int(self.dig.get()), rn_start=int(self.start.get()),
                                     rn_only_img=self.only_img.get(), rn_sub=self.sub.get())
        except Exception:
            pass

    # ── 폴더 ──
    def _drop(self, paths):
        for p in paths:
            p = os.path.normpath(p)
            if os.path.isdir(p) and p not in self.folders:
                self.folders.append(p)
        self._refresh()

    def _add_folder(self):
        d = filedialog.askdirectory()
        if d:
            self._drop([d])

    def _remove(self):
        for iid in self.tree.selection():
            if iid in self.folders:
                self.folders.remove(iid)
        self._refresh()

    def _clear(self):
        self.folders = []
        self._refresh()

    # ── 계획 ──
    def _targets(self):
        dirs = []
        for f in self.folders:
            dirs.append(f)
            if self.sub.get():
                for root, ds, _ in os.walk(f):
                    for d in explorer_sorted(ds):
                        dirs.append(os.path.join(root, d))
        return dirs

    def _files(self, d):
        try:
            names = [n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n))]
        except OSError:
            return []
        if self.only_img.get():
            names = [n for n in names if os.path.splitext(n)[1].lower() in core.IMAGE_EXT]
        return explorer_sorted(names)

    def _make_plan(self):
        try:
            pat, dig, start = self.pat.get(), int(self.dig.get()), int(self.start.get())
        except Exception:
            return {}
        plan = {}
        for d in self._targets():
            pairs = []
            for i, n in enumerate(self._files(d)):
                ext = os.path.splitext(n)[1]
                pairs.append((os.path.join(d, n), os.path.join(d, core.numbered_name(pat, start + i, dig) + ext)))
            plan[d] = pairs
        return plan

    def _later(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(250, self._refresh)

    def _refresh(self):
        self._job = None
        self.remember()
        self.plan = self._make_plan()
        self.tree.delete(*self.tree.get_children())
        total = 0
        for d, pairs in self.plan.items():
            rel = os.path.basename(d) if d in self.folders else os.path.relpath(d, os.path.dirname(
                next((f for f in self.folders if d.startswith(f)), d)))
            node = self.tree.insert("", "end", iid=d, text=f"{rel}  ({len(pairs)}개)", open=len(self.plan) <= 3)
            for old, new in pairs:
                same = os.path.basename(old) == os.path.basename(new)
                self.tree.insert(node, "end", values=(os.path.basename(old), os.path.basename(new)),
                                 tags=("same",) if same else ())
            total += len(pairs)
        self.count_lbl.config(text=f"폴더 {len(self.plan)}개 · 파일 {total}개")
        try:
            self.ex.config(text="예: " + core.numbered_name(self.pat.get(), int(self.start.get()), int(self.dig.get())) + ".jpg")
        except Exception:
            pass

    # ── 실행 ──
    def _run(self):
        self.plan = self._make_plan()
        jobs = [(o, n) for pairs in self.plan.values() for o, n in pairs if o != n]
        if not jobs:
            messagebox.showinfo(APP_NAME, "바꿀 파일이 없습니다. 폴더를 넣어주세요.")
            return
        # 같은 폴더에 새 이름이 겹치면 안 됨 (규칙 확인)
        for d, pairs in self.plan.items():
            news = [os.path.normcase(n) for _, n in pairs]
            if len(news) != len(set(news)):
                messagebox.showwarning(APP_NAME, f"'{os.path.basename(d)}' 폴더에서 새 이름이 겹칩니다. 규칙을 확인해주세요.")
                return
        if not messagebox.askyesno(APP_NAME, f"폴더 {len(self.plan)}개, 파일 {len(jobs)}개의 이름을 바꿉니다.\n"
                                             "(내용은 그대로, 이름만. '되돌리기'로 원래 이름으로 돌릴 수 있습니다)\n\n계속할까요?"):
            return
        done, errors = self._rename_all(jobs)
        try:
            with open(undo_path(), "w", encoding="utf-8") as f:
                json.dump([[n, o] for o, n in done], f, ensure_ascii=False)
        except Exception:
            pass
        self._refresh()
        for node in self.tree.get_children():
            for c in self.tree.get_children(node):
                self.tree.item(c, tags=("done",))
        self.result.config(text=f"완료: {len(done)}개 이름을 바꿨습니다." + (f"\n실패 {len(errors)}개" if errors else ""))
        if errors:
            messagebox.showwarning(APP_NAME, "일부 파일 이름을 바꾸지 못했습니다.\n\n" + "\n".join(errors[:15]))

    def _rename_all(self, jobs):
        """두 단계로 바꿈: 먼저 임시 이름 → 그다음 새 이름 (서로 이름이 겹쳐도 안전)"""
        tmp, errors, done = [], [], []
        for i, (old, new) in enumerate(jobs):
            t = os.path.join(os.path.dirname(old), f"~wh_tmp_{os.getpid()}_{i}{os.path.splitext(old)[1]}")
            try:
                os.rename(old, t)
                tmp.append((old, t, new))
            except OSError as e:
                errors.append(f"{os.path.basename(old)}: {e}")
        for old, t, new in tmp:
            try:
                if os.path.exists(new):   # 이 폴더의 다른(대상 아닌) 파일과 이름이 겹치면 원래대로
                    raise OSError("같은 이름 파일이 이미 있음")
                os.rename(t, new)
                done.append((old, new))
            except OSError as e:
                try:
                    os.rename(t, old)
                except OSError:
                    pass
                errors.append(f"{os.path.basename(old)}: {e}")
        return done, errors

    def _undo(self):
        try:
            with open(undo_path(), encoding="utf-8") as f:
                pairs = json.load(f)
        except Exception:
            messagebox.showinfo(APP_NAME, "되돌릴 기록이 없습니다.")
            return
        pairs = [(a, b) for a, b in pairs if os.path.exists(a)]
        if not pairs:
            messagebox.showinfo(APP_NAME, "되돌릴 파일이 없습니다. (이미 옮겨졌거나 되돌렸습니다)")
            return
        if not messagebox.askyesno(APP_NAME, f"방금 바꾼 {len(pairs)}개 파일을 원래 이름으로 돌릴까요?"):
            return
        done, errors = self._rename_all(pairs)
        try:
            os.remove(undo_path())
        except OSError:
            pass
        self._refresh()
        self.result.config(text=f"되돌림: {len(done)}개" + (f" · 실패 {len(errors)}개" if errors else ""))
