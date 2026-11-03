"""업무 도우미 - 메인 창 · 설정"""
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import core
from common import (APP_NAME, FONT, FONT_B, GRAY, TkinterDnD, known_folder, load_settings, save_settings)
from tab_text import TextTab
from tab_image import ImageTab
from tab_library import LibraryTab

VERSION = "1.2.0"


class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        root.title(f"{APP_NAME} {VERSION}")
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

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.text_tab = TextTab(self.nb, self)
        self.image_tab = ImageTab(self.nb, self)
        self.cap_tab = LibraryTab(self.nb, self, "image")
        self.thumb_tab = LibraryTab(self.nb, self, "thumb")
        # 메인 탭: 키 → (화면, 이름)
        self.tabs = {
            "text": (self.text_tab, "텍스트 정리"),
            "image": (self.image_tab, "이미지 관리"),
            "capture": (self.cap_tab, "이미지 캡쳐"),
            "thumb": (self.thumb_tab, "썸네일"),
        }
        self.apply_layout()
        try:
            self.nb.select(self.settings.get("tab", 0))
        except Exception:
            pass

        # 오른쪽 위 설정 버튼
        ttk.Button(root, text="⚙ 설정", command=self.open_settings).place(relx=1.0, x=-12, y=8, anchor="ne")

        self.status_lbl = ttk.Label(root, text="준비", anchor="w", padding=(10, 4))
        self.status_lbl.pack(fill="x")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

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
        try:
            self.image_tab._remember()
        except Exception:
            pass
        self.settings["geometry"] = self.root.geometry()
        try:
            self.settings["tab"] = self.nb.index(self.nb.select())
        except Exception:
            pass
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


def main():
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    app = App(root)
    if "--selftest" in sys.argv:
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
            app.text_tab._rank_changed()
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
            o = app.image_tab._opts()
            o["adjust"] = app.image_tab.adjust.get()
            print("imgtab:", core.process_image(core.list_images(src)[0], os.path.join(src, "output"), 1, o)[0], flush=True)
            # 이미지 캡쳐: 보관 → 그리드 → 랜덤 → 폴더 2개
            cap = app.cap_tab
            cap.lib = os.path.join(tmp, "lib")
            os.makedirs(cap.lib)
            cap._dropped([src])
            print("grid tiles:", len(cap.tiles), "sel:", [os.path.basename(x) for x in cap.sel], flush=True)
            cap._randomize()
            kw = cap._params()
            rng = random.Random()
            for _ in range(2):
                top = core.next_numbered_dir(tmp, cap._out_base(cap.sel[0]))
                core.make_folder_set(core.list_images(cap.sel[0]), os.path.join(top, "output"), rng, **kw)
            dirs = sorted(x for x in os.listdir(tmp) if x.startswith("나음피부과 수술흉터제거 "))
            print("capture:", dirs, [len(os.listdir(os.path.join(tmp, x, "output"))) for x in dirs], flush=True)
            cap.view.set("list")
            cap._switch_view()
            print("list sel:", cap.tree.selection() == tuple(cap.sel), flush=True)
            # 썸네일
            th = os.path.join(tmp, "th")
            core.make_count_set(core.list_images(src), th, 4, rng, **app.thumb_tab._params())
            from PIL import Image as I
            print("thumbs:", [I.open(os.path.join(th, f)).size for f in sorted(os.listdir(th))], flush=True)
            print("dnd:", bool(TkinterDnD), "docs:", known_folder("documents"), flush=True)
            print("selftest ok", flush=True)
        root.after(800, test)
    root.mainloop()
    if getattr(sys, "exitcode", 0):
        sys.exit(1)


if __name__ == "__main__":
    main()
