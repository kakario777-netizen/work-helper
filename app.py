"""업무 도우미 - 메인 창 · 설정"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import core
import json
import updater
from common import (APP_NAME, FONT, FONT_B, GRAY, TkinterDnD, PANES, install_wheel, known_folder, load_settings, save_settings)
from version import VERSION
from tab_text import TextTab
from tab_image import ImageArea
from tab_library import LibraryTab
from tab_rename import RenamePanel



class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        if not self.settings.get("color_tame_v1"):   # 붉게/푸르게 되던 저장값 정리 (한 번만)
            for key in ("im_adjust", "img_adjust", "th_adjust"):
                adj = self.settings.get(key)
                if isinstance(adj, dict):
                    for k in core.COLOR_SHIFT_KEYS:
                        adj[k] = 0.0
            self.settings["color_tame_v1"] = True
        root.title(f"{APP_NAME} {VERSION}")
        try:   # 창 왼쪽 위·작업 표시줄 아이콘 (새 창들도 같은 아이콘)
            root.iconbitmap(default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
        except Exception:
            pass
        root.geometry(self.settings.get("geometry", "1400x820"))
        root.minsize(1100, 680)

        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            pass
        root.option_add("*Font", FONT)
        style.configure(".", font=FONT)
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", font=FONT_B)
        style.configure("TNotebook.Tab", padding=(14, 6))
        style.configure("Big.TButton", font=("맑은 고딕", 12, "bold"), padding=(10, 10))

        install_wheel(root)
        self._lib_tabs = []
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.text_tab = TextTab(self.nb, self)
        self.image_area = ImageArea(self.nb, self)
        self.image_tab = self.image_area.main
        self.cap_tab = LibraryTab(self.nb, self, "image")
        self.thumb_tab = LibraryTab(self.nb, self, "thumb")
        self.raw_tab = LibraryTab(self.nb, self, "image_raw")
        self.open_tab = LibraryTab(self.nb, self, "thumb_open")
        self.rename_tab = RenamePanel(self.nb, self)
        self._lib_tabs = [self.cap_tab, self.thumb_tab, self.raw_tab, self.open_tab]
        self.nb.bind("<<NotebookTabChanged>>", self._tab_changed)
        # 메인 탭: 키 → (화면, 이름)
        self.tabs = {
            "text": (self.text_tab, "텍스트 정리"),
            "image": (self.image_area, "이미지 가공"),
            "capture": (self.cap_tab, "이미지 생성"),
            "thumb": (self.thumb_tab, "썸네일 생성"),
            "capture_raw": (self.raw_tab, "이미지 생성 (원본)"),
            "thumb_open": (self.open_tab, "썸네일 실행"),
            "rename": (self.rename_tab, "파일 이름 변경"),
        }
        self.apply_layout()
        try:
            self.nb.select(self.settings.get("tab", 0))
        except Exception:
            pass

        # 오른쪽 위: 업데이트 확인 · 설정
        top = ttk.Frame(root)
        top.place(relx=1.0, x=-12, y=6, anchor="ne")
        self.upd_btn = ttk.Button(top, text="업데이트 확인", command=self.open_update)
        self.upd_btn.pack(side="left", padx=4)
        ttk.Button(top, text="⚙ 설정", command=self.open_settings).pack(side="left")

        self.status_lbl = ttk.Label(root, text="준비", anchor="w", padding=(10, 4))
        self.status_lbl.pack(fill="x")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._last_saved = ""
        root.after(3000, self._autosave)
        threading.Thread(target=self._quiet_check, daemon=True).start()

    # ── 설정 자동 저장 (2초마다 바뀐 게 있으면) ──
    def collect(self):
        for t in (self.text_tab, self.image_tab, self.cap_tab, self.thumb_tab, self.raw_tab, self.open_tab,
                  self.rename_tab):
            try:
                t.remember()
            except Exception:
                pass
        for p in PANES:
            p.remember()
        self.settings["geometry"] = self.root.geometry()
        try:
            self.settings["tab"] = self.nb.index(self.nb.select())
        except Exception:
            pass

    def _autosave(self):
        try:
            self.collect()
            snap = json.dumps(self.settings, ensure_ascii=False, sort_keys=True)
            if snap != self._last_saved:
                save_settings(self.settings)
                self._last_saved = snap
        except Exception:
            pass
        self.root.after(2000, self._autosave)

    # ── 업데이트 ──
    def _quiet_check(self):
        try:
            info = updater.latest_release(timeout=8)
            if updater.is_newer(info["tag"], VERSION):
                self.root.after(0, lambda: self.upd_btn.config(text=f"새 버전 {info['tag']} 있음!"))
        except Exception:
            pass

    def open_update(self):
        UpdateDialog(self)

    def _tab_changed(self, _e=None):
        try:
            cur = self.nb.nametowidget(self.nb.select())
        except Exception:
            return
        if cur in self._lib_tabs:
            try:
                cur.reload()
            except Exception:
                pass

    def apply_layout(self):
        s = self.settings
        order = [k for k in s.get("tab_order", []) if k in self.tabs]
        order += [k for k in self.tabs if k not in order]
        hidden = set(s.get("tab_hidden", []))
        for w in self.nb.tabs():
            self.nb.forget(w)
        shown = [k for k in order if k not in hidden] or order[:1]
        for k in shown:
            w, name = self.tabs[k]
            self.nb.add(w, text=f"   {name}   ")
        self.text_tab.apply_layout(s.get("sub_order"), s.get("sub_hidden"))

    def open_settings(self):
        SettingsDialog(self)

    def status(self, msg):
        self.status_lbl.config(text=msg)

    def on_close(self):
        self.collect()
        save_settings(self.settings)
        self.root.destroy()


class SettingsDialog(tk.Toplevel):
    """탭 보이기/숨기기 · 순서 바꾸기 (세부 탭 포함)"""
    ON, OFF = "☑", "☐"

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("설정")
        self.transient(app.root)
        self.resizable(False, False)
        s = app.settings
        ttk.Label(self, text="탭 보이기 · 숨기기 · 순서", font=FONT_B).pack(anchor="w", padx=14, pady=(12, 2))
        ttk.Label(self, text="항목을 고르고 오른쪽 버튼으로 순서를 바꾸거나 숨기세요. 더블클릭해도 켜고 끌 수 있습니다.",
                  foreground=GRAY).pack(anchor="w", padx=14)

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(body, show="tree", height=10, selectmode="browse")
        self.tree.column("#0", width=280)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.toggle())

        order = [k for k in s.get("tab_order", []) if k in app.tabs] + [k for k in app.tabs if k not in s.get("tab_order", [])]
        hidden = set(s.get("tab_hidden", []))
        subs = app.text_tab.subs
        sub_order = [k for k in s.get("sub_order", []) if k in subs] + [k for k in subs if k not in s.get("sub_order", [])]
        sub_hidden = set(s.get("sub_hidden", []))
        self.names = {}
        for k in order:
            self.names[k] = app.tabs[k][1]
            self.tree.insert("", "end", iid=k, text=self._label(k, k not in hidden), open=True)
            if k == "text":
                for sk in sub_order:
                    iid = f"sub:{sk}"
                    self.names[iid] = subs[sk][1]
                    self.tree.insert(k, "end", iid=iid, text=self._label(iid, sk not in sub_hidden))
        self.vis = {iid: self.tree.item(iid, "text").startswith(self.ON) for iid in self._all()}

        side = ttk.Frame(body, padding=(10, 0))
        side.pack(side="left", fill="y")
        ttk.Button(side, text="▲ 위로", command=lambda: self.move(-1)).pack(fill="x")
        ttk.Button(side, text="▼ 아래로", command=lambda: self.move(1)).pack(fill="x", pady=4)
        ttk.Button(side, text="보이기/숨기기", command=self.toggle).pack(fill="x", pady=(10, 0))
        ttk.Button(side, text="처음대로", command=self.reset).pack(fill="x", pady=(24, 0))

        bar = ttk.Frame(self, padding=(14, 0, 14, 12))
        bar.pack(fill="x")
        ttk.Button(bar, text="닫기", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="적용", command=self.apply).pack(side="right", padx=6)
        self.grab_set()

    def _label(self, iid, on):
        return f"{self.ON if on else self.OFF}  {self.names[iid]}"

    def _all(self):
        out = []
        for k in self.tree.get_children(""):
            out.append(k)
            out += list(self.tree.get_children(k))
        return out

    def move(self, d):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        parent = self.tree.parent(iid)
        idx = self.tree.index(iid) + d
        if 0 <= idx < len(self.tree.get_children(parent)):
            self.tree.move(iid, parent, idx)

    def toggle(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        parent = self.tree.parent(iid)
        siblings = self.tree.get_children(parent)
        if self.vis[iid] and sum(self.vis[x] for x in siblings) <= 1:
            messagebox.showinfo("설정", "적어도 하나는 보여야 합니다.", parent=self)
            return
        self.vis[iid] = not self.vis[iid]
        self.tree.item(iid, text=self._label(iid, self.vis[iid]))

    def reset(self):
        for k in list(self.app.tabs):
            self.tree.move(k, "", "end")
        for sk in self.app.text_tab.subs:
            self.tree.move(f"sub:{sk}", "text", "end")
        for iid in self._all():
            self.vis[iid] = True
            self.tree.item(iid, text=self._label(iid, True))

    def apply(self):
        s = self.app.settings
        mains = list(self.tree.get_children(""))
        subs = [x.split(":", 1)[1] for x in self.tree.get_children("text")]
        s["tab_order"] = mains
        s["tab_hidden"] = [k for k in mains if not self.vis[k]]
        s["sub_order"] = subs
        s["sub_hidden"] = [k for k in subs if not self.vis[f"sub:{k}"]]
        self.app.apply_layout()
        save_settings(s)
        self.app.status("탭 설정을 적용했습니다.")


class UpdateDialog(tk.Toplevel):
    """새 버전 확인 → 있으면 바로 내려받아 교체 후 다시 시작"""

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("업데이트 확인")
        self.transient(app.root)
        self.resizable(False, False)
        f = ttk.Frame(self, padding=18)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=f"지금 버전: {VERSION}", font=FONT_B).pack(anchor="w")
        self.msg = ttk.Label(f, text="새 버전을 확인하는 중...", wraplength=380, justify="left")
        self.msg.pack(anchor="w", pady=(10, 6))
        self.prog = ttk.Progressbar(f, mode="indeterminate", length=380)
        self.prog.pack(fill="x")
        self.prog.start(12)
        self.notes = tk.Text(f, height=7, width=52, wrap="word", font=("맑은 고딕", 9), relief="solid", bd=1)
        self.btns = ttk.Frame(f)
        self.btns.pack(fill="x", pady=(12, 0))
        self.close_btn = ttk.Button(self.btns, text="닫기", command=self.destroy)
        self.close_btn.pack(side="right")
        self.q = []
        threading.Thread(target=self._check, daemon=True).start()
        self.after(100, self._poll)

    def _post(self, *m):
        self.q.append(m)

    def _check(self):
        try:
            info = updater.latest_release()
        except Exception as e:
            self._post("err", f"새 버전을 확인하지 못했습니다. 인터넷 연결을 확인해주세요.\n({e})")
            return
        if not updater.is_newer(info["tag"], VERSION):
            self._post("latest", f"최신 버전을 쓰고 있습니다. ({info['tag'] or VERSION})")
            return
        if not info["url"]:
            self._post("err", f"새 버전 {info['tag']}이 있지만 설치 파일이 아직 준비되지 않았습니다. 잠시 뒤 다시 눌러주세요.")
            return
        self._post("found", info)
        if not updater.is_frozen():
            self._post("err", "개발용 실행이라 자동 적용은 건너뜁니다.")
            return
        try:
            z = updater.download(info["url"], lambda g, t: self._post("prog", g, t or info["size"]))
            self._post("apply", z)
        except Exception as e:
            self._post("err", f"업데이트 중 문제가 생겼습니다.\n{e}")

    def _poll(self):
        while self.q:
            m = self.q.pop(0)
            kind = m[0]
            if kind in ("err", "latest"):
                self.prog.stop()
                self.prog.config(mode="determinate", value=100 if kind == "latest" else 0)
                self.msg.config(text=m[1])
                if kind == "latest":
                    self.app.upd_btn.config(text="업데이트 확인")
            elif kind == "found":
                info = m[1]
                self.msg.config(text=f"새 버전 {info['tag']}이 있습니다. 자동으로 내려받아 적용합니다.")
                if info["notes"].strip():
                    self.notes.insert("1.0", "바뀐 점\n" + info["notes"].strip())
                    self.notes.config(state="disabled")
                    self.notes.pack(fill="x", pady=(8, 0), before=self.btns)
                self.prog.stop()
                self.prog.config(mode="determinate", value=0, maximum=100)
            elif kind == "prog":
                g, t = m[1], m[2]
                if t:
                    self.prog.config(value=g * 100 / t)
                    self.msg.config(text=f"내려받는 중... {g / 1048576:.1f} / {t / 1048576:.1f} MB")
            elif kind == "msg":
                self.msg.config(text=m[1])
            elif kind == "apply":
                self.msg.config(text="설치 중입니다. 관리자 확인 창이 뜨면 '예'를 눌러주세요.\n설치가 끝나면 자동으로 다시 켜집니다.")
                self.update()
                try:
                    updater.run_setup(m[1])
                except Exception as e:
                    self.msg.config(text=f"새 버전을 실행하지 못했습니다.\n{e}")
                    return
                self.app.on_close()
                return
        if self.winfo_exists():
            self.after(100, self._poll)


def main():
    # 새 버전 쪽: 설치 폴더에 덮어쓰고 다시 실행한 뒤 종료
    if "--apply-update" in sys.argv:
        ok, msg = updater.apply_update(sys.argv)
        if not ok:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror(APP_NAME, msg + "\n\n프로그램 폴더를 바탕화면·문서 같은 곳으로 옮긴 뒤 다시 해주세요.")
            r.destroy()
            sys.exit(1)
        return
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    app = App(root)
    if "--updated" in sys.argv:
        threading.Thread(target=updater.cleanup_later, daemon=True).start()
        app.status(f"{VERSION} 버전으로 업데이트했습니다.")
    if "--selftest" in sys.argv:
        if "--selftest-out" in sys.argv:
            out = open(sys.argv[sys.argv.index("--selftest-out") + 1], "w", encoding="utf-8")
            sys.stdout = sys.stderr = out
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

        def test():
            try:
                run_test()
            except Exception:
                import traceback
                traceback.print_exc()
                sys.exitcode = 1
            finally:
                root.destroy()

        def run_test():
            import random
            import tempfile
            from PIL import Image
            tmp = tempfile.mkdtemp()
            # 원고 검사
            p = os.path.join(tmp, "01_서울역피부과 원고.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("서울역피부과 안내입니다. 전문 상담과 자료를 준비했어요. 서울역피부과")
            chk = app.text_tab.check
            chk.add_paths([tmp])
            print("check:", chk.tree.item(chk.tree.get_children()[0], "values"), flush=True)
            # 보고서 정리
            app.text_tab.rank_in.insert("1.0", "서울역피부과\thttps://blog.naver.com/a/1\t8\t나음피부과")
            app.text_tab._do_rank()
            app.text_tab.nate_in.insert("1.0", "https://blog.naver.com/a/1\n\n일산백옥주사\n\nhttps://blog.naver.com/b/2 65세이상 임플란트\n")
            app.text_tab._do_nate()
            print("nate:", app.text_tab.nate_out.get("1.0", "end-1c").replace("\t", " | ").replace("\n", " // "), flush=True)
            print("report:", app.text_tab.rank_out.get("1.0", "end-1c"), flush=True)
            # 설정: 탭 숨기기·순서
            d = SettingsDialog(app)
            d.vis["thumb"] = False
            d.tree.move("sub:wrap", "text", 0)
            d.apply()
            d.destroy()
            print("tabs:", [app.nb.tab(t, "text").strip() for t in app.nb.tabs()],
                  [app.text_tab.nb.tab(t, "text").strip() for t in app.text_tab.nb.tabs()], flush=True)
            app.settings.pop("tab_hidden")
            app.settings.pop("sub_order")
            app.apply_layout()
            # 이미지 관리 색감 + output
            src = os.path.join(tmp, "나음피부과-수술흉터제거")
            os.makedirs(src)
            for i in range(3):
                Image.effect_mandelbrot((1400 - i * 100, 1000), (-2, -1.5, 1, 1.5), 60 + i).convert("RGB").save(
                    os.path.join(src, f"{i}.jpg"))
            app.image_tab._add(core.list_images(src))
            app.image_tab.adjust.set({"brightness": 3, "hue": 2, "vignette": 10})
            app.image_tab._preview()
            from common import CompareWindow
            kwp = app.image_tab._proc_kw()
            cw = CompareWindow(app.root, app.image_tab.files, 0, lambda im, sc: core.preview_process(im, sc, **kwp))
            cw.update()
            cw.render()
            cw.step(1)
            print("compare:", cw.i, "/", len(cw.files), flush=True)
            cw.destroy()
            o = app.image_tab._opts()
            o["adjust"] = app.image_tab.adjust.get()
            os.makedirs(os.path.join(src, "output"), exist_ok=True)
            print("imgtab:", core.process_image(core.list_images(src)[0], os.path.join(src, "output"), 1, o)[0], flush=True)
            # 이미지 캡쳐: 보관 → 그리드 → 랜덤 → 폴더 2개
            cap = app.cap_tab
            cap.lib = os.path.join(tmp, "lib")
            os.makedirs(cap.lib)
            cap._dropped([src])
            cap._grid_w = 760
            cap._cols = 0
            cap._layout_grid()
            print("grid tiles:", len(cap.tiles), "cols@760px:", cap._cols, "sel:", [os.path.basename(x) for x in cap.sel], flush=True)
            cap._randomize()
            kw = cap._params()
            print("random:", kw["width"], kw["trim"], kw["aspect"], flush=True)
            app.collect()
            print("saved keys:", sorted(k for k in app.settings if k.startswith(("img_", "panes", "im_")))[:12], flush=True)
            try:   # 빌드 서버는 GitHub 요청 횟수 제한에 걸릴 수 있어 실패해도 넘어감
                print("update check:", updater.latest_release().get("tag"), "ver", VERSION, flush=True)
            except Exception as e:
                print("update check skipped:", e, flush=True)
            rng = random.Random()
            for _ in range(2):
                top = core.next_numbered_dir(tmp, cap._out_base(cap.sel[0]))
                core.make_folder_set(core.list_images(cap.sel[0]), os.path.join(top, "output"), rng, **kw)
            dirs = sorted(x for x in os.listdir(tmp) if x.startswith("나음피부과 수술흉터제거 "))
            print("capture:", dirs, [len(os.listdir(os.path.join(tmp, x, "output"))) for x in dirs], flush=True)
            from PIL import Image as _I
            o1 = os.path.join(tmp, dirs[0], "output")
            # 키워드 다중 생성 창
            from tab_library import KeywordDialog
            cap.name_pat.set("image{번호}")
            cap.name_dig.set(3)
            kd = KeywordDialog(cap, cap.sel[0])
            kd.rows[0][1].set("일산백옥주사")
            kd.rows[1][1].set("일산코필러")
            kd.rows[1][0].set(False)
            kd.rows[2][1].set("65세이상 임플란트")
            kd.times.set(2)
            kd._save()
            kd.out_root = os.path.join(tmp, "kwout")
            kd._out_root = lambda: os.path.join(tmp, "kwout")
            kd._run()
            kd.worker.join(60)
            kd._poll()
            kws = sorted(os.listdir(os.path.join(tmp, "kwout")))
            print("keyword folders:", kws, sorted(os.listdir(os.path.join(tmp, "kwout", kws[0]))), flush=True)
            print("keywords saved:", [k["kw"] for k in cap._meta_raw(cap.sel[0]).get("keywords", [])], flush=True)
            kd.destroy()
            print("same width in folder:", sorted({_I.open(os.path.join(o1, f)).size[0] for f in os.listdir(o1)}), flush=True)
            cap.view.set("list")
            cap._switch_view()
            print("list sel:", cap.tree.selection() == tuple(cap.sel), flush=True)
            # 썸네일
            th = os.path.join(tmp, "th")
            tk_ = app.thumb_tab
            keys = [k for k, rv in tk_.adjust.rnd.items() if rv.get()]
            _, cfg = tk_._range_cfg()

            def fresh():
                k2 = dict(tk_._params())
                k2["base"] = core.random_adjust(rng, keys)
                k2.update(core.random_size(rng, cfg))
                return k2
            core.make_count_set(core.list_images(src), th, 4, rng, kw_fn=fresh, **tk_._params())
            from PIL import Image as I
            print("thumbs:", [I.open(os.path.join(th, f)).size for f in sorted(os.listdir(th))], flush=True)
            print("dnd:", bool(TkinterDnD), "docs:", known_folder("documents"), flush=True)
            junk = os.path.join(tmp, "지울파일.jpg")
            open(junk, "wb").write(b"x")
            print("recycle:", core.recycle([junk]), os.path.exists(junk), flush=True)
            bl = app.image_area.blank
            for nm in ("서울리더스 치아교정", "밝은눈 라식"):
                os.makedirs(os.path.join(tmp, "blank", nm), exist_ok=True)
            open(os.path.join(tmp, "blank", "밝은눈 라식.txt"), "w").close()
            bl._drop([os.path.join(tmp, "blank", n) for n in os.listdir(os.path.join(tmp, "blank"))])
            bl._run()
            print("blank txt:", sorted(os.listdir(os.path.join(tmp, "blank"))), bl.result.cget("text"), flush=True)
            # 묶음 칸: 한 병원 폴더(시술 3개) → 칸 하나 + 세부 선택
            from tab_library import BundleDialog
            hosp = os.path.join(tmp, "밝은눈")
            for proc in ("라식", "백내장", "노안"):
                os.makedirs(os.path.join(hosp, proc))
                for k in range(2):
                    Image.effect_mandelbrot((900, 700), (-2, -1.5, 1, 1.5), 40 + k).convert("RGB").save(
                        os.path.join(hosp, proc, f"{k + 1}.jpg"))
            n_before = len(cap.groups)
            cap._dropped([hosp])
            b = cap.sel[0]
            print("bundle:", cap._is_bundle(b), len(cap.groups) - n_before, "칸,",
                  [os.path.basename(x) for x in cap._bundle_subs(b)], flush=True)
            bd = BundleDialog(cap, b)
            bd._toggle([k for k in bd.checks if k.endswith("노안")][0], False)
            bd.count.set(2)
            desk = os.path.join(tmp, "desk")
            os.makedirs(desk)
            import tab_library as _tlb
            _kf0 = _tlb.known_folder
            _tlb.known_folder = lambda w: desk if w == "desktop" else _kf0(w)
            bd._run()
            bd.worker.join(120)
            bd._poll()
            _tlb.known_folder = _kf0
            print("bundle out:", sorted(os.listdir(desk)), sorted(os.listdir(os.path.join(desk, sorted(os.listdir(desk))[0], "output"))), flush=True)
            bd._close()
            cap.sel = [x for x in cap.sel if x != b] or [g[0] for g in cap.groups if not cap._is_bundle(g[0])][:1]
            cap._sync_selection()
            # 특수 가공: 워터마크 + GIF
            import special
            gsrc = os.path.join(tmp, "sp")
            os.makedirs(gsrc)
            frames = [Image.effect_mandelbrot((400, 200), (-2, -1, 1, 1), 20 + k).convert("RGB") for k in range(6)]
            frames[0].save(os.path.join(gsrc, "b.gif"), save_all=True, append_images=frames[1:], duration=90, loop=0)
            Image.effect_mandelbrot((900, 700), (-2, -1.5, 1, 1.5), 50).convert("RGB").save(os.path.join(gsrc, "a.jpg"))
            from tab_library import SpecialDialog
            sd = SpecialDialog(cap)
            sd._drop([gsrc])
            sd.tree.move(os.path.join(gsrc, "b.gif"), "", 0)
            sd._renumber()
            sd.h_var.set("닥터케빈")
            sd.p_var.set("특수")
            sd.img_wm["tracking"].set(20)
            sd._save_new()
            spd = [g[0] for g in cap.groups if cap._is_special(g[0])][0]
            print("special tile:", os.path.basename(spd), "first:", cap.groups[0][0] == spd,
                  "order", cap._meta_raw(spd).get("order"), flush=True)
            so = os.path.join(tmp, "special out")
            cap._make_files(spd, cap._files_of(spd), so, random.Random(), cap._params(), lambda: None)
            outs = sorted(os.listdir(so))
            g = Image.open(os.path.join(so, outs[0]))
            print("special:", outs, "gif", g.size, g.n_frames, g.info.get("duration"),
                  "font", special._font_file(special.FONTS[0], "Dr.Kevin"), flush=True)
            # 병원 묶음 안에 넣기
            bun = [g[0] for g in cap.groups if cap._is_bundle(g[0])]
            if bun:
                sd2 = SpecialDialog(cap)
                sd2._drop([gsrc])
                sd2.p_var.set("워터마크")
                sd2.bundle_var.set([k for k, v in sd2.bundle_map.items() if v == bun[0]][0])
                sd2._save_into()
                print("special in bundle:", [os.path.basename(x) for x in cap._bundle_subs(bun[0])],
                      [cap._is_special(x) for x in cap._bundle_subs(bun[0])], flush=True)
            cap.sel = [g[0] for g in cap.groups if not cap._is_special(g[0]) and not cap._is_bundle(g[0])][:1]
            cap._sync_selection()
            # 이미지 생성 (원본): 원본 그대로 복사, 키워드 목록대로
            rt = app.raw_tab
            rt.lib = cap.lib
            rt.reload()
            one = [g[0] for g in rt.groups if not rt._is_bundle(g[0]) and not rt._is_special(g[0])][0]
            rt.sel = [one]
            rt._sync_selection()
            rt._write_meta(one, raw_keywords=["오스템임플란트 가격 비용", "전체임플란트", "강남역치과 임플란트수술"])
            rt._raw_kw_label()
            rawdesk = os.path.join(tmp, "rawdesk")
            os.makedirs(rawdesk)
            import tab_library as _tl
            _orig_kf = _tl.known_folder
            _tl.known_folder = lambda w: rawdesk if w == "desktop" else _orig_kf(w)
            rt._run()
            rt.worker.join(60)
            rt._poll()
            _tl.known_folder = _orig_kf
            rr = os.listdir(rawdesk)[0]
            print("raw copy:", rr, sorted(os.listdir(os.path.join(rawdesk, rr))), rt.kw_lbl.cget("text"),
                  sorted(os.listdir(os.path.join(rawdesk, rr, os.listdir(os.path.join(rawdesk, rr))[0]))), flush=True)
            print("tabs:", [app.nb.tab(t, "text").strip() for t in app.nb.tabs()], flush=True)
            # 파일 이름 변경: 탐색기 순서(1,2,10,11) 그대로
            rn = app.rename_tab
            rdir = os.path.join(tmp, "이름바꾸기")
            os.makedirs(rdir)
            for nm in ("10.jpg", "2.jpg", "1.jpg", "11.png", "메모.txt"):
                open(os.path.join(rdir, nm), "wb").write(nm.encode())
            rn._drop([rdir])
            rn.pat.set("t{번호}")
            rn.dig.set(1)
            rn._refresh()
            print("rename plan:", [(os.path.basename(o), os.path.basename(n)) for o, n in rn.plan[rdir]], flush=True)
            import tkinter.messagebox as _mb2
            _ok = _mb2.askyesno
            _mb2.askyesno = lambda *a, **k: True
            rn._run()
            after = sorted(os.listdir(rdir))
            same = open(os.path.join(rdir, "t4.png"), "rb").read() == b"11.png"
            rn._undo()
            _mb2.askyesno = _ok
            print("rename done:", after, "content kept:", same, "undo:", sorted(os.listdir(rdir)), flush=True)
            # 칸 묶기 / 풀기
            singles = [g[0] for g in cap.groups if not cap._is_bundle(g[0]) and not cap._is_special(g[0])]
            if len(singles) >= 1:
                import tkinter.simpledialog as _sdg
                _ask = _sdg.askstring
                _sdg.askstring = lambda *a, **k: "묶음병원"
                extra = cap._new_group("임시", "시술B", core.list_images(singles[0]))
                cap.reload()
                cap.sel = [singles[0], extra]
                cap._group_selected()
                _sdg.askstring = _ask
                gb = cap.sel[0]
                print("group:", cap._is_bundle(gb), [os.path.basename(x) for x in cap._bundle_subs(gb)], flush=True)
                import tkinter.messagebox as _mb3
                _yes = _mb3.askyesno
                _mb3.askyesno = lambda *a, **k: True
                cap.sel = [gb]
                cap._ungroup_selected()
                _mb3.askyesno = _yes
                print("ungroup:", os.path.exists(gb), [g[1] + " " + g[2] for g in cap.groups if not cap._is_bundle(g[0])][:6], flush=True)
                cap.sel = [g[0] for g in cap.groups if not cap._is_special(g[0]) and not cap._is_bundle(g[0])][:1]
                cap._sync_selection()
            # 원고 이미지 배치
            pl = app.text_tab.place
            mdir = os.path.join(tmp, "원고")
            os.makedirs(mdir)
            orig = "서울역피부과 레이저 안내\r\n\r\n안녕하세요\r\n\r\n문단1 줄1\r\n문단1 줄2\r\n\r\n문단2\r\n\r\n문단3\r\n\r\n#태그\r\n"
            mp = os.path.join(mdir, "서울역 원고.txt")
            open(mp, "w", encoding="utf-8", newline="").write(orig)
            pl._drop([mdir])
            pl._fill_groups()
            gname = [k for k, v in pl._groups.items() if v == cap.sel[0]][0]
            pl._cur_group = cap.sel[0]
            pl.sample.delete("1.0", "end")
            pl.sample.insert("1.0", "제목\n\n[사진 1]\n\n문단\n\n[사진 2]\n\n#태그")
            pl._save_sample()
            pl.tree.selection_set(mp)
            pl.grp.set(gname)
            pl._group_picked()
            pl.cnt.set(3)
            pl._apply_sel()
            import tkinter.messagebox as _mb
            _old = (_mb.askyesno, _mb.askyesnocancel)
            _mb.askyesno = lambda *a, **k: True
            _mb.askyesnocancel = lambda *a, **k: False
            pl._backup_dir = lambda: os.path.join(tmp, "원고 수정 원본")
            pl._run()
            _mb.askyesno, _mb.askyesnocancel = _old
            after = open(mp, "rb").read().decode("utf-8")
            bks = os.listdir(os.path.join(tmp, "원고 수정 원본"))
            print("place:", after.replace("\r\n", " / "), flush=True)
            print("place backup:", bks, open(os.path.join(tmp, "원고 수정 원본", bks[0]), "rb").read().decode() == orig, flush=True)
            # 순위 체크: 표 붙여넣기 + 실제 네이버 검색
            rp = app.text_tab.rank
            app.root.clipboard_clear()
            app.root.clipboard_append("1\t거제치과\thttps://blog.naver.com/jannypooh/224464524715\t\t서울연세탑\n"
                                      "2\t서면스마일라식\thttps://naver.me/GuCJYWB2\t\t밝은눈\n"
                                      "3\t하지정맥류원인\thttps://cafe.naver.com/cantsb/3692588\t\t에스메디\n")
            rp.data = []
            rp.paste()
            from tab_rank import col_letter
            print("rank paste:", rp.ncols, "칸, 순위 칸 =", col_letter(rp.rank_col()), flush=True)
            import rankcheck, time as _t
            print("naver.me →", rankcheck.resolve("https://naver.me/GuCJYWB2"), flush=True)
            try:
                ck = rankcheck.Checker(os.path.join(tmp, "browser"))
                for kw, link in (("거제치과", "https://blog.naver.com/jannypooh/224464524715"),
                                 ("서면스마일라식", "https://naver.me/GuCJYWB2"),
                                 ("하지정맥류원인", "https://cafe.naver.com/cantsb/3692588")):
                    t0 = _t.time()
                    pg = ck.search(kw)
                    if pg.get("captcha"):
                        print("rank", kw, "CAPTCHA", flush=True)
                        continue
                    print("rank sections", kw, [(x["title"], x["n"], x["web"], x["excluded"]) for x in pg.get("sections", [])
                                                if x["n"]][:14], flush=True)
                    print("rank items", kw, "→ parts", pg.get("parts"), len(pg.get("items", [])), "개:",
                          [it["text"][:28] for it in pg.get("items", [])[:6]], flush=True)
                    print("rank hrefs", kw, [it["hrefs"][:2] for it in pg.get("items", [])[:4]], flush=True)
                    rk, how = ck.find(link)
                    print("rank same hospital", kw, ck.find_hospital({"거제치과": "서울연세탑", "서면스마일라식": "밝은눈", "하지정맥류원인": "에스메디"}[kw]), flush=True)
                    shp = ck.shot(rk, os.path.join(tmp, "shots", kw + ".jpg"))
                    print("rank result", kw, rk, how, "shot", shp and os.path.getsize(shp), f"{_t.time() - t0:.1f}s", flush=True)
                ck.close()
            except Exception as e:
                import traceback
                print("rank live fail:", e, traceback.format_exc()[-600:], flush=True)
            import extractor
            for u in ("https://blog.naver.com/aaipfteejc4n/224463697294",
                      "https://blog.naver.com/y9tfzmtbzxz/224463718647"):
                try:
                    t_, b_ = extractor.extract(u)
                    print("extract:", u.rsplit("/", 1)[-1], "|", t_, "|", len("".join(b_.split())), "자 |",
                          b_[:120].replace("\n", " / "), flush=True)
                except Exception as e:
                    print("extract fail:", u, e, flush=True)
            from tab_extract import BulkDialog
            bd = BulkDialog(app.text_tab.extract)
            bd.rows[0][1].set("일산백옥주사")
            bd.rows[0][2].insert("1.0", "https://blog.naver.com/aaipfteejc4n/224463697294\nhttps://blog.naver.com/aaipfteejc4n/224463701057")
            bd._save()
            print("bulk saved:", app.settings.get("ex_bulk"), flush=True)
            bd.destroy()
            print("frozen:", updater.is_frozen(), flush=True)
            print("selftest ok", flush=True)
        root.after(800, test)
    root.mainloop()
    if getattr(sys, "exitcode", 0):
        sys.exit(1)


if __name__ == "__main__":
    main()
