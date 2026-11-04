"""업무 도우미 - 링크로 원고 추출 (텍스트 정리 세부 탭)"""
import os
import queue
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import core
import extractor
from common import (APP_NAME, GRAY, FONT_B, known_folder, open_folder, text_box, help_label,
                    ScrollFrame, WrapLabel)


def out_dir():
    return os.path.join(known_folder("desktop"), f"원고 추출 {datetime.now():%Y%m%d}")


def save_text(folder, base, text, numbered):
    """numbered=True → '키워드 1.txt, 키워드 2.txt …' (빈 번호), False → '제목.txt' (겹치면 '제목 (2).txt')"""
    os.makedirs(folder, exist_ok=True)
    base = extractor.safe_filename(base)
    if numbered:
        path = core.next_numbered_file(folder, base, ".txt")
    else:
        path = os.path.join(folder, base + ".txt")
        n = 2
        while os.path.exists(path):
            path = os.path.join(folder, f"{base} ({n}).txt")
            n += 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class ExtractPanel(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=8)
        self.app = app
        s = app.settings
        self.q = queue.Queue()
        self.worker = None

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="링크", font=FONT_B).pack(side="left")
        self.url = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.url)
        e.pack(side="left", fill="x", expand=True, padx=6)
        e.bind("<Return>", lambda ev: self._run())
        self.run_btn = ttk.Button(top, text="원고 추출하기", style="Big.TButton", command=self._run)
        self.run_btn.pack(side="left", ipady=2)
        ttk.Button(top, text="대량 추출하기", command=lambda: BulkDialog(self)).pack(side="left", padx=(6, 0), ipady=6)

        opt = ttk.Frame(self)
        opt.pack(fill="x", pady=(8, 0))
        ttk.Label(opt, text="파일명").pack(side="left")
        self.mode = tk.StringVar(value=s.get("ex_mode", "title"))
        ttk.Radiobutton(opt, text="제목으로", value="title", variable=self.mode).pack(side="left", padx=(8, 4))
        ttk.Radiobutton(opt, text="키워드로", value="kw", variable=self.mode).pack(side="left")
        self.kw = tk.StringVar(value=s.get("ex_kw", ""))
        ttk.Entry(opt, textvariable=self.kw, width=22).pack(side="left", padx=6)
        help_label(opt, "네이버 블로그·카페 링크를 넣고 '원고 추출하기'를 누르면 제목과 본문 글자만 뽑아\n"
                        "바탕화면\\원고 추출 오늘날짜\\ 폴더에 메모장으로 저장합니다.\n\n"
                        "· 제목으로: '글 제목.txt'\n· 키워드로: '키워드 1.txt', '키워드 2.txt' … (빈 번호부터)\n\n"
                        "비공개·이웃 공개 블로그 글, 멤버 공개 카페 글은 로그인이 필요해서 가져올 수 없습니다.\n"
                        "'대량 추출하기'는 키워드마다 링크를 여러 개 넣어 한 번에 저장합니다.").pack(side="left", padx=8)
        ttk.Button(opt, text="저장 폴더 열기", command=self._open).pack(side="right")

        self.info = WrapLabel(self, text="", foreground="#0a5")
        self.info.pack(fill="x", pady=(8, 4))
        box, self.out = text_box(self, height=16)
        box.pack(fill="both", expand=True)
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(6, 0))
        ttk.Label(bar, text="추출한 내용은 위에서 고칠 수 있어요.", foreground=GRAY).pack(side="left")
        ttk.Button(bar, text="고친 내용으로 다시 저장", command=self._resave).pack(side="right")
        self.last_path = None

    def remember(self):
        self.app.settings.update(ex_mode=self.mode.get(), ex_kw=self.kw.get())

    def _open(self):
        d = out_dir()
        os.makedirs(d, exist_ok=True)
        open_folder(d)

    def _run(self):
        if self.worker and self.worker.is_alive():
            return
        links = extractor.find_links(self.url.get()) or [self.url.get().strip()]
        url = links[0]
        if not url:
            messagebox.showinfo(APP_NAME, "링크를 넣어주세요.")
            return
        if self.mode.get() == "kw" and not self.kw.get().strip():
            messagebox.showinfo(APP_NAME, "파일명으로 쓸 키워드를 적어주세요.")
            return
        self.remember()
        self.run_btn.config(state="disabled")
        self.info.config(text="가져오는 중...", foreground=GRAY)
        mode, kw = self.mode.get(), self.kw.get().strip()

        def work():
            try:
                title, body = extractor.extract(url)
                text = extractor.as_text(title, body)
                path = save_text(out_dir(), kw if mode == "kw" else title, text, numbered=(mode == "kw"))
                self.q.put(("ok", title, body, text, path))
            except extractor.ExtractError as e:
                self.q.put(("err", str(e)))
            except Exception as e:
                self.q.put(("err", f"저장 중 오류: {e}"))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self._poll()

    def _poll(self):
        try:
            msg = self.q.get_nowait()
        except queue.Empty:
            self.after(100, self._poll)
            return
        self.run_btn.config(state="normal")
        if msg[0] == "ok":
            _, title, body, text, path = msg
            self.last_path = path
            self.out.delete("1.0", "end")
            self.out.insert("1.0", text)
            n = len("".join(body.split()))
            self.info.config(text=f"저장: 바탕화면\\{os.path.basename(os.path.dirname(path))}\\{os.path.basename(path)}"
                                  f"   ·   본문 공백 제외 {n:,}자", foreground="#0a5")
        else:
            self.info.config(text=f"실패: {msg[1]}", foreground="#c00")

    def _resave(self):
        if not self.last_path:
            messagebox.showinfo(APP_NAME, "먼저 원고를 추출해주세요.")
            return
        with open(self.last_path, "w", encoding="utf-8") as f:
            f.write(self.out.get("1.0", "end-1c").rstrip("\n") + "\n")
        self.info.config(text=f"다시 저장했습니다: {os.path.basename(self.last_path)}", foreground="#0a5")


class BulkDialog(tk.Toplevel):
    """키워드 30칸 × 링크 여러 개 → 바탕화면\\원고 추출 날짜\\키워드 1.txt …"""
    N = 30

    def __init__(self, panel):
        super().__init__(panel.app.root)
        self.panel, self.app = panel, panel.app
        self.title("대량 추출하기")
        self.transient(self.app.root)
        self.geometry("860x700")
        self.minsize(700, 480)
        self.q = queue.Queue()
        self.worker = None
        saved = self.app.settings.get("ex_bulk", [])

        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text="키워드별 링크", font=FONT_B).pack(side="left")
        help_label(top, "왼쪽에 키워드, 오른쪽 칸에 그 키워드의 링크를 여러 개(줄마다 하나, 또는 띄어쓰기로) 넣으세요.\n"
                        "적어둔 내용은 자동으로 기억됩니다.\n\n"
                        "저장: 바탕화면\\원고 추출 오늘날짜\\키워드 1.txt, 키워드 2.txt …\n"
                        "같은 키워드로 다시 돌리면 이어지는 번호로 저장됩니다.").pack(side="left", padx=8)
        ttk.Button(top, text="모두 지우기", command=self._clear).pack(side="right")

        mid = ttk.Frame(self, padding=(12, 0))
        mid.pack(fill="both", expand=True)
        sf = ScrollFrame(mid)
        sf.pack(side="left", fill="both", expand=True)
        self.rows = []
        for i in range(self.N):
            it = saved[i] if i < len(saved) else {}
            r = ttk.Frame(sf.inner, padding=(0, 3))
            r.pack(fill="x")
            on = tk.BooleanVar(value=it.get("on", True))
            ttk.Checkbutton(r, variable=on, command=self._save_later).pack(side="left", anchor="n")
            ttk.Label(r, text=f"{i + 1:>2}", width=3, foreground=GRAY).pack(side="left", anchor="n")
            kw = tk.StringVar(value=it.get("kw", ""))
            ttk.Entry(r, textvariable=kw, width=18).pack(side="left", anchor="n", padx=(0, 6))
            t = tk.Text(r, height=3, wrap="none", font=("맑은 고딕", 9), relief="solid", bd=1, undo=True)
            t.insert("1.0", it.get("links", ""))
            t.pack(side="left", fill="x", expand=True, padx=(0, 6))
            kw.trace_add("write", lambda *a: self._save_later())
            t.bind("<<Modified>>", lambda e, t=t: (t.edit_modified(False), self._save_later()))
            self.rows.append((on, kw, t))

        right = ttk.Frame(mid, padding=(12, 0, 0, 0), width=220)
        right.pack(side="left", fill="y")
        self.run_btn = ttk.Button(right, text="대량 추출하기", style="Big.TButton", command=self._run)
        self.run_btn.pack(fill="x", ipady=4)
        WrapLabel(right, text=f"바탕화면\\{os.path.basename(out_dir())}\\ 안에 저장됩니다.",
                  foreground="#0a5").pack(fill="x", pady=(6, 0))
        self.prog = ttk.Progressbar(right, mode="determinate")
        self.prog.pack(fill="x", pady=(12, 4))
        self.result = WrapLabel(right, text="")
        self.result.pack(fill="x")
        ttk.Button(right, text="저장 폴더 열기", command=self.panel._open).pack(anchor="w", pady=(8, 0))
        ttk.Label(right, text="실패한 링크", foreground=GRAY).pack(anchor="w", pady=(14, 2))
        self.fail = tk.Text(right, height=14, width=30, wrap="word", font=("맑은 고딕", 9), relief="solid", bd=1)
        self.fail.pack(fill="both", expand=True)
        self._sjob = None
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _save_later(self):
        if self._sjob:
            self.after_cancel(self._sjob)
        self._sjob = self.after(600, self._save)

    def _save(self):
        self._sjob = None
        data = [{"on": bool(on.get()), "kw": kw.get().strip(), "links": t.get("1.0", "end-1c").strip()}
                for on, kw, t in self.rows]
        while data and not data[-1]["kw"] and not data[-1]["links"] and data[-1]["on"]:
            data.pop()
        self.app.settings["ex_bulk"] = data

    def _close(self):
        self._save()
        self.destroy()

    def _clear(self):
        if not messagebox.askyesno(APP_NAME, "키워드와 링크를 모두 지울까요?", parent=self):
            return
        for on, kw, t in self.rows:
            on.set(True)
            kw.set("")
            t.delete("1.0", "end")
        self._save()

    def _run(self):
        if self.worker and self.worker.is_alive():
            return
        self._save()
        jobs = []
        for on, kw, t in self.rows:
            k = kw.get().strip()
            links = extractor.find_links(t.get("1.0", "end-1c"))
            if on.get() and k and links:
                jobs += [(k, u) for u in links]
        if not jobs:
            messagebox.showinfo(APP_NAME, "키워드와 링크를 넣어주세요. (왼쪽 체크된 줄만 추출합니다)", parent=self)
            return
        folder = out_dir()
        self.prog.config(maximum=len(jobs), value=0)
        self.run_btn.config(state="disabled")
        self.fail.delete("1.0", "end")
        self.result.config(text=f"0 / {len(jobs)}")

        def work():
            ok = 0
            for i, (k, u) in enumerate(jobs):
                try:
                    title, body = extractor.extract(u)
                    save_text(folder, k, extractor.as_text(title, body), numbered=True)
                    ok += 1
                    self.q.put(("prog", i + 1, ok, None))
                except Exception as e:
                    self.q.put(("prog", i + 1, ok, f"[{k}] {u}\n → {e}"))
                time.sleep(0.4)   # 네이버에 너무 빠르게 요청하지 않게
            self.q.put(("done", ok, len(jobs)))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self._poll()

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "prog":
                    _, i, ok, err = msg
                    self.prog["value"] = i
                    self.result.config(text=f"{i} / {int(self.prog['maximum'])}  ·  성공 {ok}개")
                    if err:
                        self.fail.insert("end", err + "\n\n")
                else:
                    _, ok, total = msg
                    self.run_btn.config(state="normal")
                    self.result.config(text=f"완료: {total}개 중 {ok}개 저장" + (f" · 실패 {total - ok}개" if total - ok else ""))
                    return
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll)
