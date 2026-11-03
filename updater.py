"""업무 도우미 - 자동 업데이트
흐름: GitHub 최신 릴리스 확인 → WorkHelper_Setup.exe 내려받기
     → 설치 파일을 조용히 실행(관리자 확인 창 1번) 하고 지금 프로그램 종료
     → 설치 파일이 Program Files 에 덮어쓴 뒤 프로그램을 다시 실행
(예전 zip 방식 '--apply-update' 도 넘어오는 사람을 위해 남겨 둠)"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

REPO = "kakario777-netizen/work-helper"
ASSET = "WorkHelper.zip"
SETUP = "WorkHelper_Setup.exe"
EXE = "WorkHelper.exe"
WORK = os.path.join(tempfile.gettempdir(), "WorkHelper_update")


def is_frozen():
    # PyInstaller는 sys.frozen, Nuitka는 모듈마다 __compiled__ 를 둠
    return bool(getattr(sys, "frozen", False) or "__compiled__" in globals())


def install_dir():
    exe = sys.argv[0] if "__compiled__" in globals() else sys.executable
    return os.path.dirname(os.path.abspath(exe))


def parse_ver(v):
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums) if nums else (0,)


def latest_release(timeout=15):
    """반환: {"tag","notes","url","size"}  (실패 시 예외)"""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "WorkHelper", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    asset = next((a for a in data.get("assets", []) if a.get("name") == SETUP), None)
    return {"tag": data.get("tag_name", ""), "notes": data.get("body") or "",
            "url": asset["browser_download_url"] if asset else None, "size": asset["size"] if asset else 0}


def is_newer(tag, current):
    return parse_ver(tag) > parse_ver(current)


def download(url, progress=None, name=SETUP):
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    zpath = os.path.join(WORK, name)
    req = urllib.request.Request(url, headers={"User-Agent": "WorkHelper"})
    with urllib.request.urlopen(req, timeout=60) as r, open(zpath, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress:
                progress(got, total)
    return zpath


def run_setup(path):
    """설치 파일을 조용히 실행(진행 막대만 보임). 끝나면 설치 파일이 프로그램을 다시 켬.
    관리자 확인 창은 윈도우가 띄움"""
    import ctypes
    params = "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /restart=1"
    r = ctypes.windll.shell32.ShellExecuteW(None, "open", path, params, os.path.dirname(path), 1)
    if r <= 32:
        raise RuntimeError("설치 파일을 실행하지 못했습니다. (관리자 확인을 취소했다면 다시 시도해주세요)")


def extract(zpath):
    dest = os.path.join(WORK, "new")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest)
    for root, _, files in os.walk(dest):
        if EXE in files:
            return root
    raise RuntimeError("내려받은 파일에서 프로그램을 찾지 못했습니다.")


def launch_apply(new_dir):
    """새 버전에게 교체를 맡기고 실행. 호출한 쪽은 곧바로 종료해야 함"""
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([os.path.join(new_dir, EXE), "--apply-update", install_dir(), str(os.getpid())],
                     cwd=new_dir, creationflags=flags, close_fds=True)


def _wait_pid(pid, timeout=60):
    if not pid or sys.platform != "win32":
        return
    import ctypes
    SYNCHRONIZE = 0x00100000
    h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if h:
        ctypes.windll.kernel32.WaitForSingleObject(h, int(timeout * 1000))
        ctypes.windll.kernel32.CloseHandle(h)


def apply_update(argv):
    """새 exe 쪽에서 실행: --apply-update <설치폴더> <옛PID> [--no-restart]
    반환: (성공여부, 메시지)"""
    i = argv.index("--apply-update")
    target, pid = argv[i + 1], int(argv[i + 2])
    _wait_pid(pid)
    src = install_dir()
    last = None
    for _ in range(40):   # 파일이 아직 잡혀 있으면 잠깐씩 기다리며 재시도
        try:
            os.makedirs(target, exist_ok=True)
            shutil.copytree(src, target, dirs_exist_ok=True)
            last = None
            break
        except Exception as e:
            last = e
            time.sleep(0.5)
    if last:
        return False, f"설치 폴더에 덮어쓰지 못했습니다.\n{target}\n\n{last}"
    if "--no-restart" not in argv:
        flags = subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
        subprocess.Popen([os.path.join(target, EXE), "--updated"], cwd=target, creationflags=flags, close_fds=True)
    return True, "ok"


def cleanup_later():
    """업데이트 뒤 첫 실행 때 임시 폴더 정리(몇 번 재시도)"""
    for _ in range(20):
        shutil.rmtree(WORK, ignore_errors=True)
        if not os.path.exists(WORK):
            return
        time.sleep(1)
