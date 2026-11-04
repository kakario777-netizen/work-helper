"""업무 도우미 - 순위 체크 (텍스트 정리 세부 탭)  엑셀 표를 그대로 붙여넣고, 순위 칸을 채움"""
import hashlib
import os
import queue
import random
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import rankcheck
from common import APP_NAME, GRAY, FONT_B, help_label, copy_to_clipboard

AUTO = "자동"
MAG = "🔍"


def _data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "WorkHelper")


def shots_dir():
    return os.path.join(_data_dir(), "rankshots")


def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class RankPanel(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        s = app.settings
        self.data, self.ncols = [], 0
        self.status, self.shots = {}, {}
        self.q = queue.Queue()
        self.worker = None
        self.stop_flag = threading.Event()
        self._tip = None
        self._tip_row = None
        threading.Thread(target=rankcheck.cleanup_shots, args=(shots_dir(),), daemon=True).start()

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="붙여넣기 (Ctrl+V)", command=self.paste).pack(side="left")
        ttk.Button(top, text="비우기", command=self.clear).pack(side="left", padx=3)
        ttk.Button(top, text="표 전체 복사", command=lambda: self.copy(all_rows=True)).pack(side="left")
        ttk.Label(top, text="   순위 칸").pack(side="left")
        self.rank_choice = tk.StringVar(value=AUTO)
        self.rank_cb = ttk.Combobox(top, textvariable=self.rank_choice, width=6, state="readonly", values=[AUTO])
        self.rank_cb.pack(side="left", padx=4)
        self.rank_cb.bind("<<ComboboxSelected>>", lambda e: self._render())
        ttk.Label(top, text="   간격(초)").pack(side="left")
        self.gap_a = tk.DoubleVar(value=s.get("rank_gap_a", 2.0))
        self.gap_b = tk.DoubleVar(value=s.get("rank_gap_b", 4.0))
        ttk.Spinbox(top, from_=1, to=60, increment=0.5, textvariable=self.gap_a, width=4).pack(side="left", padx=2)
        ttk.Label(top, text="~").pack(side="left")
        ttk.Spinbox(top, from_=1, to=60, increment=0.5, textvariable=self.gap_b, width=4).pack(side="left", padx=2)
        self.visible = tk.BooleanVar(value=s.get("rank_visible", False))
        ttk.Checkbutton(top, text="검색 창 보이기", variable=self.visible).pack(side="left", padx=(10, 0))
        help_label(top, "엑셀 표를 그대로 긁어 Ctrl+V 하면 같은 칸 모양으로 들어옵니다.\n"
                        "링크 칸 바로 왼쪽을 키워드로 보고, 순위는 '순위 칸'에 채웁니다.\n"
                        "  · 자동: 오른쪽에서 두 번째 칸이 비어 있으면 그 칸, 아니면 링크 오른쪽 첫 빈 칸\n"
                        "순위는 광고·클립·브랜드 콘텐츠·함께 많이 찾는·이미지 같은 주제 칸은 빼고,\n"
                        "블로그·카페·웹사이트가 모인 일반 결과 칸에서 위에서 몇 번째인지 셉니다.\n"
                        "카페 글은 링크로 먼저 찾고, 안 되면 제목으로 한 번 더 확인합니다. 못 찾으면 '-'.\n\n"
                        "🔍 에 마우스를 올리면 찾은 글에 빨간 테두리를 친 캡쳐가 뜹니다. (2주 뒤 자동 삭제)\n"
                        "표를 긁어 Ctrl+C (또는 '표 전체 복사') 하면 엑셀에 그대로 붙습니다.\n"
                        "네이버가 보안문자를 띄우면 멈춥니다. '검색 창 보이기'를 켜고 직접 풀어준 뒤 다시 시작하세요.").pack(side="left", padx=10)
        self.stop_btn = ttk.Button(top, text="멈춤", command=self.stop, state="disabled")
        self.stop_btn.pack(side="right")
        self.run_btn = ttk.Button(top, text="순위 체크 시작", style="Big.TButton", command=self.start)
        self.run_btn.pack(side="right", padx=6, ipady=2)

        tf = ttk.Frame(self)
        tf.pack(fill="both", expand=True, pady=8)
        self.tree = ttk.Treeview(tf, show="headings", selectmode="extended")
        ys = ttk.Scrollbar(tf, command=self.tree.yview)
        xs = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        self.tree.tag_configure("found", background="#eaf7ea")
        self.tree.tag_configure("miss", background="#fff4e5")
        self.tree.tag_configure("work", background="#e8f0ff")
        self.tree.tag_configure("err", background="#ffe3e3")
        for w in (self.tree, self):
            w.bind("<Control-v>", lambda e: (self.paste(), "break")[1])
            w.bind("<Control-V>", lambda e: (self.paste(), "break")[1])
        self.tree.bind("<Control-c>", lambda e: (self.copy(), "break")[1])
        self.tree.bind("<Control-C>", lambda e: (self.copy(), "break")[1])
        self.tree.bind("<Control-a>", lambda e: (self.tree.selection_set(self.tree.get_children()), "break")[1])
        self.tree.bind("<Double-1>", self._edit)
        self.tree.bind("<Motion>", self._hover)
        self.tree.bind("<Leave>", lambda e: self._hide_tip())

        bot = ttk.Frame(self)
        bot.pack(fill="x")
        self.prog = ttk.Progressbar(bot, mode="determinate", length=260)
        self.prog.pack(side="left")
        self.info = ttk.Label(bot, text="")
        self.info.pack(side="left", padx=10)
        self._render()

    # ══ 표 ══
    def _link_col(self):
        best, bi = -1, None
        for c in range(self.ncols):
            n = sum(1 for r in self.data if "http" in r[c] or "naver.me" in r[c] or "naver.com/" in r[c])
            if n > best:
                best, bi = n, c
        return bi if best > 0 else None

    def _empty(self, c):
        return all(not r[c].strip() for r in self.data)

    def rank_col(self):
        ch = self.rank_choice.get()
        if ch and ch != AUTO:
            i = 0
            for k in ch:
                i = i * 26 + (ord(k) - 64)
            return i - 1
        lc = self._link_col()
        if lc is None:
            return None
        if self.ncols >= 2 and self.ncols - 2 > lc and self._empty(self.ncols - 2):
            return self.ncols - 2
        for c in range(lc + 1, self.ncols):
            if self._empty(c):
                return c
        return self.ncols   # 빈 칸이 없으면 맨 오른쪽에 새 칸

    def _render(self):
        rc = self.rank_col()
        n = max(self.ncols, (rc + 1) if rc is not None else 0)
        for r in self.data:
            while len(r) < n:
                r.append("")
        self.ncols = n
        cols = [f"c{i}" for i in range(n)] + ["st", "mag"]
        self.tree.configure(columns=cols)
        lc = self._link_col()
        for i in range(n):
            head = col_letter(i) + (" (순위)" if i == rc else " (키워드)" if lc is not None and i == lc - 1
                                    else " (링크)" if i == lc else "")
            self.tree.heading(f"c{i}", text=head)
            w = 300 if i == lc else 70 if i == rc else 50 if i == 0 and lc and lc > 1 else 150
            self.tree.column(f"c{i}", width=w, anchor="center" if i == rc else "w", stretch=False)
        self.tree.heading("st", text="확인 내용")
        self.tree.column("st", width=180, stretch=True)
        self.tree.heading("mag", text="노출 확인")
        self.tree.column("mag", width=70, anchor="center", stretch=False)
        self.rank_cb["values"] = [AUTO] + [col_letter(i) for i in range(n + 1)]
        self.tree.delete(*self.tree.get_children())
        for ri, r in enumerate(self.data):
            self.tree.insert("", "end", iid=str(ri), values=r + [self.status.get(ri, ("", ""))[0],
                                                               MAG if self.shots.get(ri) else ""],
                             tags=(self.status.get(ri, ("", ""))[1],))

    def _set_row(self, ri):
        r = self.data[ri]
        st = self.status.get(ri, ("", ""))
        self.tree.item(str(ri), values=r + [st[0], MAG if self.shots.get(ri) and os.path.exists(self.shots[ri]) else ""],
                       tags=(st[1],))

    def paste(self):
        try:
            text = self.app.root.clipboard_get()
        except Exception:
            return
        lines = [l for l in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        while lines and not lines[-1].strip():
            lines.pop()
        rows = [l.split("\t") for l in lines if l.strip()]
        if not rows:
            return
        if self.data and not messagebox.askyesno(APP_NAME, "지금 표를 지우고 새로 붙여넣을까요?\n(아니요: 아래에 이어 붙이기)"):
            pass
        else:
            self.data, self.status, self.shots = [], {}, {}
        self.data += rows
        self.ncols = max([self.ncols] + [len(r) for r in rows])
        for r in self.data:
            while len(r) < self.ncols:
                r.append("")
        self._render()
        lc = self._link_col()
        self.info.config(text=f"{len(rows)}줄 붙여넣음" + ("" if lc is not None else "  · 링크 칸을 찾지 못했습니다"))

    def clear(self):
        if self.worker and self.worker.is_alive():
            return
        self.data, self.status, self.shots, self.ncols = [], {}, {}, 0
        self._render()
        self.info.config(text="")

    def copy(self, all_rows=False):
        ids = self.tree.get_children() if all_rows else (self.tree.selection() or self.tree.get_children())
        rows = ["\t".join(self.data[int(i)]) for i in ids]
        copy_to_clipboard(self.app.root, "\n".join(rows))
        self.app.status(f"{len(rows)}줄 복사했습니다. 엑셀에 그대로 붙여넣으세요.")

    def _edit(self, e):
        iid = self.tree.identify_row(e.y)
        col = self.tree.identify_column(e.x)
        if not iid or not col:
            return
        ci = int(col[1:]) - 1
        if ci >= self.ncols:
            return
        x, y, w, h = self.tree.bbox(iid, col)
        ent = ttk.Entry(self.tree)
        ent.insert(0, self.data[int(iid)][ci])
        ent.select_range(0, "end")
        ent.place(x=x, y=y, width=max(w, 80), height=h)
        ent.focus_set()

        def done(save):
            if save:
                self.data[int(iid)][ci] = ent.get()
                self._set_row(int(iid))
            ent.destroy()
        ent.bind("<Return>", lambda ev: done(True))
        ent.bind("<FocusOut>", lambda ev: done(True))
        ent.bind("<Escape>", lambda ev: done(False))

    # ══ 🔍 캡쳐 미리보기 ══
    def _hover(self, e):
        iid = self.tree.identify_row(e.y)
        col = self.tree.identify_column(e.x)
        on_mag = iid and col == f"#{self.ncols + 2}" and self.shots.get(int(iid))
        if not on_mag:
            self._hide_tip()
            return
        if self._tip_row == iid and self._tip:
            return
        self._hide_tip()
        path = self.shots.get(int(iid))
        if not path or not os.path.exists(path):
            return
        try:
            from PIL import Image, ImageTk
            im = Image.open(path)
            im.thumbnail((760, 560))
            self._tip_img = ImageTk.PhotoImage(im)
        except Exception:
            return
        tw = tk.Toplevel(self)
        tw.wm_overrideredirect(True)
        try:
            tw.attributes("-topmost", True)
        except Exception:
            pass
        tk.Label(tw, image=self._tip_img, bd=1, relief="solid").pack()
        st = self.status.get(int(iid), ("", ""))[0]
        tk.Label(tw, text=st, bg="#fff8d6", font=("맑은 고딕", 9), anchor="w").pack(fill="x")
        tw.update_idletasks()
        x = e.x_root - tw.winfo_reqwidth() - 12
        y = e.y_root - tw.winfo_reqheight() // 2
        x = max(0, x)
        y = max(0, min(y, tw.winfo_screenheight() - tw.winfo_reqheight() - 40))
        tw.wm_geometry(f"+{x}+{y}")
        self._tip, self._tip_row = tw, iid

    def _hide_tip(self):
        if self._tip:
            self._tip.destroy()
        self._tip, self._tip_row = None, None

    # ══ 실행 ══
    def remember(self):
        try:
            self.app.settings.update(rank_gap_a=float(self.gap_a.get()), rank_gap_b=float(self.gap_b.get()),
                                     rank_visible=self.visible.get())
        except Exception:
            pass

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        lc = self._link_col()
        if not self.data or lc is None or lc == 0:
            messagebox.showinfo(APP_NAME, "엑셀 표(키워드·링크가 있는 칸)를 먼저 붙여넣어 주세요.")
            return
        rc = self.rank_col()
        self._render()
        kc = lc - 1
        sel = self.tree.selection()
        rows = [int(i) for i in sel] if len(sel) > 1 else list(range(len(self.data)))
        jobs = [(ri, self.data[ri][kc].strip(), self.data[ri][lc].strip()) for ri in rows
                if self.data[ri][kc].strip() and self.data[ri][lc].strip()]
        if not jobs:
            messagebox.showinfo(APP_NAME, "키워드와 링크가 모두 있는 줄이 없습니다.")
            return
        self.remember()
        try:
            a, b = sorted((float(self.gap_a.get()), float(self.gap_b.get())))
        except Exception:
            a, b = 2.0, 4.0
        # 같은 키워드는 한 번만 검색
        order, by_kw = [], {}
        for ri, kw, link in jobs:
            if kw not in by_kw:
                by_kw[kw] = []
                order.append(kw)
            by_kw[kw].append((ri, link))
        self.stop_flag.clear()
        self.prog.config(maximum=len(jobs), value=0)
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.info.config(text="브라우저 준비 중...")
        visible = self.visible.get()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        def work():
            done = found = 0
            ck = None
            try:
                ck = rankcheck.Checker(os.path.join(_data_dir(), "browser"), visible=visible)
                for ki, kw in enumerate(order):
                    if self.stop_flag.is_set():
                        break
                    for ri, _ in by_kw[kw]:
                        self.q.put(("row", ri, None, f"'{kw}' 검색 중...", "work", None))
                    page = ck.search(kw)
                    if page.get("captcha"):
                        for ri, _ in by_kw[kw]:
                            self.q.put(("row", ri, None, "네이버 보안문자 — 멈춤", "err", None))
                        self.q.put(("captcha",))
                        break
                    sec = page.get("title") or "일반 결과"
                    total = len(page.get("items", []))
                    for ri, link in by_kw[kw]:
                        try:
                            rank, how = ck.find(link)
                        except Exception as e:
                            rank, how = None, f"오류: {e}"
                        h = hashlib.md5(f"{kw}|{link}|{stamp}".encode()).hexdigest()[:10]
                        shot = ck.shot(rank, os.path.join(shots_dir(), f"{stamp}_{h}.jpg"))
                        if rank:
                            found += 1
                            msg = f"{rank}위 / {total}개 ({how})" + (f" · {sec}" if page.get("title") else "")
                            self.q.put(("row", ri, str(rank), msg, "found", shot))
                        else:
                            msg = f"못 찾음 ({total}개 중)" if total else "일반 결과 칸을 못 찾음"
                            self.q.put(("row", ri, "-", msg, "miss", shot))
                        done += 1
                        self.q.put(("prog", done, found))
                    if ki < len(order) - 1 and not self.stop_flag.is_set():
                        time.sleep(random.uniform(a, b))
            except Exception as e:
                self.q.put(("fatal", str(e)))
            finally:
                if ck:
                    ck.close()
                self.q.put(("done", done, found))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self._poll(rc)

    def stop(self):
        self.stop_flag.set()
        self.info.config(text="이번 키워드까지만 하고 멈춥니다...")

    def _poll(self, rc):
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "row":
                    _, ri, rank, msg, tag, shot = m
                    if rank is not None:
                        self.data[ri][rc] = rank
                    self.status[ri] = (msg, tag)
                    if shot:
                        self.shots[ri] = shot
                    self._set_row(ri)
                    self.tree.see(str(ri))
                elif m[0] == "prog":
                    self.prog["value"] = m[1]
                    self.info.config(text=f"{m[1]} / {int(self.prog['maximum'])}  ·  찾음 {m[2]}개")
                elif m[0] == "captcha":
                    messagebox.showwarning(APP_NAME, "네이버가 보안문자(자동입력 방지)를 띄워 멈췄습니다.\n\n"
                                                     "'검색 창 보이기'를 켜고 다시 시작하면 창이 뜹니다. 보안문자를 직접 풀어주시고,\n"
                                                     "간격을 조금 늘려 주세요. (몇 분 쉬었다 해도 대부분 풀립니다)")
                elif m[0] == "fatal":
                    messagebox.showerror(APP_NAME, f"순위 체크를 진행하지 못했습니다.\n{m[1]}")
                elif m[0] == "done":
                    self.run_btn.config(state="normal")
                    self.stop_btn.config(state="disabled")
                    self.info.config(text=f"완료: {m[1]}줄 확인 · 찾음 {m[2]}개   (표를 긁어 Ctrl+C → 엑셀에 붙여넣기)")
                    return
        except queue.Empty:
            pass
        self.after(150, lambda: self._poll(rc))
