"""업무 도우미 - PC에 깔린 엣지(없으면 크롬)를 프로그램이 직접 조종 (DevTools 프로토콜, 추가 설치 없음)"""
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request


class WS:
    """아주 작은 웹소켓 클라이언트 (DevTools 연결용)"""

    def __init__(self, url, timeout=60):
        u = urllib.parse.urlparse(url)
        self.s = socket.create_connection((u.hostname, u.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path + ("?" + u.query if u.query else "")
        req = (f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.s.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.s.recv(4096)
            if not chunk:
                raise ConnectionError("브라우저 연결이 끊겼습니다")
            resp += chunk
        head, rest = resp.split(b"\r\n\r\n", 1)
        if b" 101" not in head.split(b"\r\n")[0]:
            raise ConnectionError("브라우저에 연결하지 못했습니다: " + head[:80].decode("latin1"))
        self.buf = bytearray(rest)

    def send(self, text):
        data = text.encode("utf-8")
        n = len(data)
        hdr = bytearray([0x81])
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        hdr += mask
        masked = bytearray(data)
        for i in range(n):
            masked[i] ^= mask[i & 3]
        self.s.sendall(bytes(hdr) + bytes(masked))

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(262144)
            if not chunk:
                raise ConnectionError("브라우저 연결이 끊겼습니다")
            self.buf += chunk
        d = bytes(self.buf[:n])
        del self.buf[:n]
        return d

    def recv(self):
        msg = bytearray()
        while True:
            b1, b2 = self._read(2)
            fin, op, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            payload = bytearray(self._read(n))
            if mask:
                for i in range(n):
                    payload[i] ^= mask[i & 3]
            if op == 8:
                raise ConnectionError("브라우저가 연결을 닫았습니다")
            if op == 9:   # ping → pong
                self.s.sendall(bytes([0x8A, 0x80]) + os.urandom(4))
                continue
            if op == 10:
                continue
            msg += payload
            if fin:
                return msg.decode("utf-8", "replace")

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def find_browser():
    env = os.environ
    cands = []
    for base in (env.get("ProgramFiles(x86)"), env.get("ProgramFiles"), env.get("LOCALAPPDATA")):
        if base:
            cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    for p in cands:
        if os.path.exists(p):
            return p
    return None


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Browser:
    def __init__(self, profile_dir, visible=False, width=1280, height=1000):
        exe = find_browser()
        if not exe:
            raise RuntimeError("엣지(Edge)나 크롬을 찾지 못했습니다")
        os.makedirs(profile_dir, exist_ok=True)
        self.port = _free_port()
        args = [exe, f"--remote-debugging-port={self.port}", f"--user-data-dir={profile_dir}",
                "--remote-allow-origins=*", "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-sync", "--lang=ko-KR",
                f"--window-size={width},{height}", "about:blank"]
        if not visible:
            args.insert(1, "--headless=new")
        flags = 0x08000000 if sys.platform == "win32" else 0   # 콘솔 창 없이
        self.proc = subprocess.Popen(args, creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        for _ in range(150):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=2) as r:
                    pages = [t for t in json.load(r) if t.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            time.sleep(0.1)
        if not ws_url:
            self.close()
            raise RuntimeError("브라우저를 띄우지 못했습니다")
        self.ws = WS(ws_url)
        self.id = 0
        self.call("Page.enable")
        self.call("Runtime.enable")
        ua = self.call("Browser.getVersion").get("userAgent", "")
        ua = ua.replace("HeadlessChrome", "Chrome").replace("Headless", "")
        self.call("Network.setUserAgentOverride", userAgent=ua, acceptLanguage="ko-KR,ko;q=0.9")
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)

    def call(self, method, **params):
        self.id += 1
        mid = self.id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error'].get('message')}")
                return m.get("result", {})

    def eval(self, js):
        r = self.call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            raise RuntimeError("페이지 스크립트 오류: " + str(r["exceptionDetails"].get("exception", {}).get("description", ""))[:200])
        return r.get("result", {}).get("value")

    def goto(self, url, timeout=25):
        self.call("Page.navigate", url=url)
        t0 = time.time()
        time.sleep(0.3)
        while time.time() - t0 < timeout:
            try:
                if self.eval("document.readyState") == "complete":
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        return False

    def screenshot(self, x, y, w, h, scale=0.8, quality=55):
        r = self.call("Page.captureScreenshot", format="jpeg", quality=quality, captureBeyondViewport=True,
                      clip={"x": max(0, x), "y": max(0, y), "width": max(50, w), "height": max(50, h), "scale": scale})
        return base64.b64decode(r["data"])

    def close(self):
        try:
            self.call("Browser.close")
        except Exception:
            pass
        try:
            self.ws.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
