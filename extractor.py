"""업무 도우미 - 링크로 원고 추출 (네이버 블로그·카페, AI 없이 페이지를 직접 읽어 제목·본문만)"""
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class ExtractError(Exception):
    pass


def _get(url, referer=None, timeout=15):
    h = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        cs = r.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(cs, "replace"), r.geturl()
    except LookupError:
        return raw.decode("utf-8", "replace"), r.geturl()


# ───────────────────── 본문 HTML → 글자 ─────────────────────

BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "tr", "table", "ul", "ol"}
SKIP = {"script", "style", "noscript", "button", "select", "textarea", "svg", "iframe"}


class _SEParser(HTMLParser):
    """스마트에디터 ONE(se-*) 은 문단(se-text-paragraph)·제목(se-title-text) 단위로,
    그 밖의 편집기는 블록 태그 단위로 글자를 모음"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # (tag, classes)
        self.title = []
        self.lines = []          # 본문 줄
        self.cur = None          # 지금 모으는 문단 글자 (None = 문단 밖)
        self.in_title = 0
        self.skip = 0
        self.se = False          # 스마트에디터 ONE 문단을 하나라도 봤는지
        self.generic = []        # 편집기 표시가 없을 때 쓰는 일반 글자
        self.comp_gap = False

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class") or ""
        if tag in SKIP:
            self.skip += 1
        self.stack.append((tag, cls))
        if "se-title-text" in cls or "se_title" in cls or "se_textarea_title" in cls:
            self.in_title += 1
        if "se-component" in cls and "se-documentTitle" not in cls and self.lines:
            self.comp_gap = True
        if tag == "p" and ("se-text-paragraph" in cls or "se_textarea" in cls) and not self.in_title:
            self.se = True
            self.cur = []
        if tag == "br":
            if self.cur is not None:
                self.cur.append("\n")
            self.generic.append("\n")
        elif tag in BLOCK:
            self.generic.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            if self.cur is not None:
                self.cur.append("\n")
            self.generic.append("\n")

    def handle_endtag(self, tag):
        # 열린 태그를 거꾸로 찾아 닫음 (잘못 닫힌 HTML 대비)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for t, c in self.stack[i:]:
                    if t in SKIP:
                        self.skip = max(0, self.skip - 1)
                    if "se-title-text" in c or "se_title" in c or "se_textarea_title" in c:
                        self.in_title = max(0, self.in_title - 1)
                del self.stack[i:]
                break
        if tag == "p" and self.cur is not None:
            text = "".join(self.cur)
            if self.comp_gap:
                self.lines.append("")
                self.comp_gap = False
            self.lines.extend(text.split("\n"))
            self.cur = None
        if tag in BLOCK:
            self.generic.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title.append(data)
            return
        if self.cur is not None:
            self.cur.append(data)
        self.generic.append(data)


def _clean_lines(lines):
    out = []
    for ln in lines:
        ln = ln.replace("​", "").replace("﻿", "").replace("\xa0", " ").rstrip()
        if not ln.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(ln.strip())
    while out and out[-1] == "":
        out.pop()
    while out and out[0] == "":
        out.pop(0)
    return "\n".join(out)


def html_to_text(fragment):
    """본문 HTML 조각 → (제목, 본문)"""
    p = _SEParser()
    p.feed(fragment)
    p.close()
    title = re.sub(r"\s+", " ", "".join(p.title).replace("​", "")).strip()
    body = _clean_lines(p.lines) if p.se else _clean_lines("".join(p.generic).split("\n"))
    return title, body


def _meta(page, prop):
    m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*content=["\']([^"\']*)' % re.escape(prop), page)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']%s["\']' % re.escape(prop), page)
    return html.unescape(m.group(1)).strip() if m else ""


def _cut_block(page, marker):
    """marker(클래스·id) 가 붙은 태그부터 그 태그가 닫히는 곳까지 잘라냄"""
    i = page.find(marker)
    if i < 0:
        return ""
    start = page.rfind("<", 0, i)
    m = re.match(r"<(\w+)", page[start:])
    if not m:
        return ""
    tag = m.group(1)
    depth = 0
    for t in re.finditer(r"<(/?)%s\b[^>]*?(/?)>" % tag, page[start:]):
        if t.group(2):
            continue
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return page[start:start + t.end()]
    return page[start:]


# ───────────────────── 네이버 블로그 ─────────────────────

def _blog_ids(url):
    u = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(u.query)
    if "blogId" in q and "logNo" in q:
        return q["blogId"][0], q["logNo"][0]
    parts = [p for p in u.path.split("/") if p]
    if len(parts) >= 2 and parts[1].isdigit():
        return parts[0], parts[1]
    if len(parts) == 1 and "logNo" in q:
        return parts[0], q["logNo"][0]
    return None, None


def extract_blog(url):
    bid, no = _blog_ids(url)
    if not bid:   # 짧은 주소(naver.me 등)는 따라가서 다시
        page, final = _get(url)
        bid, no = _blog_ids(final)
        if not bid:
            m = re.search(r"blogId=([\w-]+)[^\"']*?logNo=(\d+)", page)
            if not m:
                raise ExtractError("블로그 글 주소를 알아보지 못했습니다")
            bid, no = m.group(1), m.group(2)
    page, _ = _get(f"https://blog.naver.com/PostView.naver?blogId={bid}&logNo={no}"
                   f"&redirect=Dlog&widgetTypeCall=true&directAccess=false",
                   referer=f"https://blog.naver.com/{bid}/{no}")
    title, body = "", ""
    main = _cut_block(page, "se-main-container") or _cut_block(page, 'id="postViewArea"') \
        or _cut_block(page, "se_component_wrap")
    if main:
        t_block = _cut_block(page, "se-documentTitle") or _cut_block(page, "se_title")
        title = html_to_text(t_block)[0] if t_block else ""
        _, body = html_to_text(main)
    if not body:   # 모바일 페이지로 한 번 더
        page, _ = _get(f"https://m.blog.naver.com/{bid}/{no}")
        main = _cut_block(page, "se-main-container") or _cut_block(page, 'id="viewTypeSelector"')
        if main:
            _, body = html_to_text(main)
        t_block = _cut_block(page, "se-documentTitle")
        if t_block and not title:
            title = html_to_text(t_block)[0]
    if not title:
        title = _meta(page, "og:title")
        title = re.sub(r"\s*:\s*네이버 블로그\s*$", "", title)
    if not body:
        if "비공개" in page or "권한이 없" in page or "서로이웃" in page:
            raise ExtractError("비공개 또는 이웃 공개 글이라 볼 수 없습니다")
        raise ExtractError("본문을 찾지 못했습니다")
    return title or "제목없음", body


# ───────────────────── 네이버 카페 ─────────────────────

def _cafe_ids(url):
    u = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(u.query)
    club = q.get("clubid", [None])[0]
    art = q.get("articleid", [None])[0]
    parts = [p for p in u.path.split("/") if p]
    if "cafes" in parts and "articles" in parts:
        try:
            club = parts[parts.index("cafes") + 1]
            art = parts[parts.index("articles") + 1]
        except IndexError:
            pass
    name = None
    if not art and len(parts) >= 2 and parts[1].isdigit():
        name, art = parts[0], parts[1]
    if "iframe_url_utf8" in q:   # cafe.naver.com/xxx?iframe_url_utf8=/ArticleRead...
        return _cafe_ids("https://cafe.naver.com" + urllib.parse.unquote(q["iframe_url_utf8"][0]))
    return club, art, name


def extract_cafe(url):
    club, art, name = _cafe_ids(url)
    if not art:
        raise ExtractError("카페 글 주소를 알아보지 못했습니다")
    if not club:
        page, _ = _get(f"https://cafe.naver.com/{name}")
        m = re.search(r"g_sClubId\s*=\s*\"?(\d+)", page) or re.search(r"clubid=(\d+)", page) \
            or re.search(r'"cafeId"\s*:\s*(\d+)', page)
        if not m:
            raise ExtractError("카페 번호를 찾지 못했습니다")
        club = m.group(1)
    api = (f"https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/{club}/articles/{art}"
           f"?query=&useCafeId=true&requestFrom=A")
    try:
        txt, _ = _get(api, referer=f"https://cafe.naver.com/ca-fe/cafes/{club}/articles/{art}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8", "replace")).get("result", {}).get("errorCode", "")
        except Exception:
            msg = ""
        if e.code in (401, 403) or "MEMBER" in msg.upper() or "LOGIN" in msg.upper():
            raise ExtractError("멤버 공개 글이라 로그인 없이 볼 수 없습니다")
        raise ExtractError(f"카페 글을 가져오지 못했습니다 (HTTP {e.code})")
    data = json.loads(txt).get("result", {})
    a = data.get("article") or {}
    title = (a.get("subject") or "").strip()
    content = a.get("contentHtml") or ""
    if not content:
        raise ExtractError("멤버 공개 글이거나 본문이 없습니다")
    _, body = html_to_text(content)
    if not body:
        raise ExtractError("본문을 찾지 못했습니다")
    return title or "제목없음", body


# ───────────────────── 공통 ─────────────────────

def extract(url):
    """반환: (제목, 본문)   실패하면 ExtractError"""
    url = url.strip()
    if not url:
        raise ExtractError("링크가 비어 있습니다")
    if not re.match(r"https?://", url):
        url = "https://" + url
    host = urllib.parse.urlparse(url).netloc.lower()
    try:
        if "cafe.naver.com" in host:
            t, b = extract_cafe(url)
            return t, _drop_title_line(t, b)
        if "blog.naver.com" in host or "naver.me" in host:
            t, b = extract_blog(url)
            return t, _drop_title_line(t, b)
    except ExtractError:
        raise
    except urllib.error.HTTPError as e:
        raise ExtractError(f"페이지를 열지 못했습니다 (HTTP {e.code})")
    except urllib.error.URLError as e:
        raise ExtractError(f"인터넷 연결을 확인해주세요 ({e.reason})")
    except Exception as e:
        raise ExtractError(f"추출 중 오류: {e}")
    raise ExtractError("네이버 블로그·카페 링크만 지원합니다")


def _drop_title_line(title, body):
    """본문 맨 앞에 제목이 한 번 더 들어 있으면 뺌"""
    norm = lambda x: re.sub(r"\s+", "", x or "")
    lines = body.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and norm(lines[0]) == norm(title):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines)


def as_text(title, body):
    return f"{title}\n\n{body}\n"


def safe_filename(name, limit=80):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', " ", name or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name[:limit].rstrip(" .") or "제목없음")


URL_RE = re.compile(r"https?://[^\s<>\"']+|(?:m\.)?(?:blog|cafe)\.naver\.com/[^\s<>\"']+|naver\.me/\S+")


def find_links(text):
    return [m.group(0).rstrip(".,)") for m in URL_RE.finditer(text or "")]
