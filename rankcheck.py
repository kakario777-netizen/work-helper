"""업무 도우미 - 네이버 통합검색 첫 화면 순위 확인
주제 칸(광고·클립·브랜드 콘텐츠·함께 많이 찾는·이미지 …)은 빼고, 블로그·카페·웹사이트가 모인 일반 결과 칸에서
위에서 몇 번째인지 셈"""
import os
import random
import re
import time
import urllib.parse
import urllib.request

import extractor

SEARCH = "https://search.naver.com/search.naver?where=nexearch&sm=top_hty&fbm=0&ie=utf8&query={q}"
EXCLUDE = r"AI\s*브리핑|함께\s*찾는|질병|광고|클립|브랜드\s*콘텐츠|함께\s*많이\s*찾|연관|이미지|동영상|뉴스|쇼핑|지식\s*iN|플레이스|인플루언서|지도|함께\s*보면|관련\s*검색|추천|숏폼|오픈사전|어학|사전|웹툰|도서"


# ───────────────────── 내 링크 알아보기 ─────────────────────

_resolved = {}


def resolve(url):
    """naver.me 같은 짧은 주소 → 실제 주소 (검색 화면이 아니라 링크 주소만 따라감)"""
    url = url.strip()
    if not re.match(r"https?://", url):
        url = "https://" + url
    if "naver.me/" not in url:
        return url
    if url in _resolved:
        return _resolved[url]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": extractor.UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            final = r.geturl()
            body = r.read(200000).decode("utf-8", "replace")
        if "naver.me" in final:   # 자바스크립트로 넘기는 경우
            m = re.search(r"(https?://(?:m\.)?(?:blog|cafe)\.naver\.com/[^\"'<>\s]+)", body)
            if m:
                final = m.group(1)
    except Exception:
        final = url
    _resolved[url] = final
    return final


def target_of(url):
    """반환: dict(kind=blog|cafe|web, …)"""
    real = resolve(url)
    u = urllib.parse.urlparse(real)
    host = u.netloc.lower()
    if "blog.naver.com" in host:
        bid, no = extractor._blog_ids(real)
        if bid and no:
            return {"kind": "blog", "bid": bid, "no": no, "url": real}
    if "cafe.naver.com" in host:
        club, art, name = extractor._cafe_ids(real)
        q = urllib.parse.parse_qs(u.query)
        art = art or q.get("articleid", [None])[0] or q.get("art", [None])[0]
        if art and art.isdigit():
            return {"kind": "cafe", "club": club, "art": art, "name": name, "url": real, "title": None}
    norm = re.sub(r"^https?://(www\.)?", "", real).rstrip("/").lower()
    return {"kind": "web", "norm": norm, "url": real}


def cafe_title(t):
    """카페 글 제목 (제목으로도 찾기 위해). 멤버 공개면 None"""
    if t.get("title") is None:
        try:
            t["title"] = extractor.extract_cafe(t["url"])[0]
        except Exception:
            t["title"] = ""
    return t["title"]


def _norm_text(s):
    return re.sub(r"[\s\W_]+", "", (s or "")).lower()


def match(item, t):
    """item: {"hrefs": [...], "text": "..."} → (맞는지, 방법)"""
    hrefs = [urllib.parse.unquote(h) for h in item.get("hrefs", [])]
    if t["kind"] == "blog":
        for h in hrefs:
            if f"/{t['bid']}/{t['no']}" in h or (f"blogId={t['bid']}" in h and f"logNo={t['no']}" in h):
                return True, "링크"
        return False, ""
    if t["kind"] == "cafe":
        art = t["art"]
        for h in hrefs:
            if "cafe.naver.com" not in h:
                continue
            if re.search(rf"(?:/|articleid=|/articles/){art}(?:\D|$)", h):
                if (t.get("name") and f"/{t['name']}/" in h) or (t.get("club") and str(t["club"]) in h) \
                        or not (t.get("name") or t.get("club")) or "articleid=" in h or "/articles/" in h:
                    return True, "링크"
        title = cafe_title(t)
        if title and len(_norm_text(title)) >= 6 and _norm_text(title)[:30] in _norm_text(item.get("text")):
            # 제목이 같으면 그 글 링크의 글 번호까지 한 번 더 확인
            for h in hrefs:
                if "cafe.naver.com" in h and re.search(rf"{art}(?:\D|$)", h):
                    return True, "제목+글번호"
            if any("cafe.naver.com" in h for h in hrefs):
                return True, "제목"
        return False, ""
    for h in hrefs:
        n = re.sub(r"^https?://(www\.)?", "", h).rstrip("/").lower()
        if n.startswith(t["norm"]) or t["norm"].startswith(n) and len(n) > 12:
            return True, "링크"
    return False, ""


# ───────────────────── 검색 화면 읽기 ─────────────────────

SCROLL_JS = r"""
(async () => {
  const H = () => document.documentElement.scrollHeight;
  let y = 0;
  while (y < Math.min(H(), 14000)) {
    y += 650 + Math.floor(Math.random() * 250);
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 90 + Math.random() * 80));
  }
  await new Promise(r => setTimeout(r, 400));
  window.scrollTo(0, 0);
  return H();
})()
"""

ANALYZE_JS = r"""
(() => {
  const EXCL = new RegExp(%s);
  const txt = (document.body && document.body.innerText) || '';
  if (/자동입력\s*방지|보안\s*확인|비정상적인\s*접근|captcha/i.test(txt.slice(0, 3000)) || /captcha|nid\.naver\.com/.test(location.href))
    return {captcha: true};
  const root = document.querySelector('#main_pack') || document.body;
  let secs = Array.from(root.children);
  for (const s of root.querySelectorAll('section, .api_subject_bx, [class*="sc_new"]')) if (!secs.includes(s)) secs.push(s);
  const realHrefs = (a) => {
    const out = [];
    const push = (h) => {
      if (!h) return;
      try {
        const u = new URL(h, location.href);
        for (const k of ['u', 'url', 'rurl', 'cru', 'link']) {
          const v = u.searchParams.get(k);
          if (v) { const d = decodeURIComponent(v); if (/^https?:/.test(d)) out.push(d); }
        }
        out.push(u.href);
      } catch (e) {}
    };
    push(a.getAttribute('href')); push(a.getAttribute('data-url')); push(a.getAttribute('cru'));
    push(a.getAttribute('data-cru')); push(a.getAttribute('data-link'));
    return out;
  };
  const okLink = (h) => /^https?:/.test(h) && !/search\.naver\.com|help\.naver|keep\.naver|nid\.naver|ader\.naver|adcr\.naver|\/\/ad\.|\.ad\.naver|terms\.naver|notice\.naver|talk\.naver|nv\.naver|cr\.naver|\/\/n\.news|map\.naver|tv\.naver/.test(h);
  const goodHrefs = (a) => realHrefs(a).filter(okLink);
  const itemOf = (a, sec) => {
    let n = a;
    while (n && n !== sec && n.parentElement) {
      const p = n.parentElement;
      const same = Array.from(p.children).filter(c => c.tagName === n.tagName && c.className === n.className);
      if (same.length >= 3 && n.tagName !== 'A' && n.tagName !== 'SPAN') return n;
      if (p === sec) break;
      n = p;
    }
    return null;
  };
  const titleOf = (sec, items) => {
    for (const h of sec.querySelectorAll('h2, h3, [class*="title_area"], [class*="headline"], [class*="api_title"], [class*="header"] strong')) {
      if (items.some(it => it.contains(h))) continue;
      const t = (h.innerText || '').replace(/\s+/g, ' ').trim();
      if (t) return t.slice(0, 40);
    }
    return '';
  };
  const summary = [];
  let best = null;
  secs.forEach((sec, si) => {
    const items = [], seen = new Set();
    for (const a of sec.querySelectorAll('a[href]')) {
      if (!goodHrefs(a).length) continue;
      const it = itemOf(a, sec);
      if (!it || seen.has(it)) continue;
      seen.add(it); items.push(it);
    }
    const title = titleOf(sec, items);
    const hasAdMark = Array.from(sec.querySelectorAll('i, span, em')).slice(0, 80).some(e => e.innerText && e.innerText.trim() === '광고');
    const excluded = EXCL.test(title) || (hasAdMark && items.length < 8);
    const web = items.filter(it => Array.from(it.querySelectorAll('a[href]')).some(a => goodHrefs(a).some(h => /blog\.naver|cafe\.naver|^https?:\/\/(?!.*naver\.com)/.test(h)))).length;
    summary.push({si, title, n: items.length, web, excluded});
    if (!excluded && web >= 3 && (!best || web > best.web)) best = {sec, items, title, web, si};
  });
  if (!best) return {captcha: false, sections: summary, items: [], title: ''};
  window.__wh_items = best.items;
  const r0 = best.sec.getBoundingClientRect();
  window.__wh_sec = best.sec;
  const items = best.items.map((it, i) => ({
    hrefs: Array.from(new Set(Array.from(it.querySelectorAll('a[href]')).flatMap(goodHrefs))).slice(0, 16),
    text: (it.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 300)
  }));
  return {captcha: false, sections: summary, items, title: best.title, si: best.si,
          secY: r0.top + window.scrollY, pageW: document.documentElement.scrollWidth};
})()
""" % repr(EXCLUDE).replace("'", '"')

MARK_JS = r"""
((i) => {
  const it = window.__wh_items[i];
  for (const e of document.querySelectorAll('[data-wh-mark]')) { e.style.outline = ''; e.removeAttribute('data-wh-mark'); }
  it.setAttribute('data-wh-mark', '1');
  it.style.outline = '4px solid #e8231a';
  it.style.outlineOffset = '3px';
  it.scrollIntoView({block: 'center'});
  const r = it.getBoundingClientRect();
  return {x: r.left + window.scrollX, y: r.top + window.scrollY, w: r.width, h: r.height};
})(%d)
"""


class Checker:
    """브라우저 한 번 띄워 여러 키워드 확인"""

    def __init__(self, profile_dir, visible=False):
        import cdp
        self.b = cdp.Browser(profile_dir, visible=visible)
        self.page = None
        self.kw = None

    def close(self):
        self.b.close()

    def search(self, keyword):
        """키워드 검색 → 일반 결과 칸 정보. captcha 면 {"captcha": True}"""
        self.b.goto(SEARCH.format(q=urllib.parse.quote(keyword)))
        time.sleep(0.6 + random.random() * 0.6)
        try:
            self.b.eval(SCROLL_JS)   # 사람처럼 아래로 쭉 내려 보며 늦게 뜨는 칸까지 불러옴
        except Exception:
            pass
        self.page = self.b.eval(ANALYZE_JS) or {}
        self.kw = keyword
        return self.page

    def find(self, link):
        """지금 화면에서 link 순위. 반환: (순위 or None, 방법)"""
        t = target_of(link)
        for i, it in enumerate((self.page or {}).get("items", [])):
            ok, how = match(it, t)
            if ok:
                return i + 1, how
        return None, ""

    def shot(self, rank, path):
        """찾은 글에 빨간 테두리를 그려 그 부분을 가볍게 캡쳐 (못 찾으면 일반 결과 칸 위쪽)"""
        try:
            if rank:
                r = self.b.eval(MARK_JS % (rank - 1))
                time.sleep(0.25)
                y = max(0, r["y"] - 170)
                img = self.b.screenshot(0, y, 1100, r["h"] + 360, scale=0.75)
            else:
                y = max(0, (self.page or {}).get("secY", 0) - 40)
                img = self.b.screenshot(0, y, 1100, 1100, scale=0.6)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(img)
            return path
        except Exception:
            return None


def cleanup_shots(folder, days=14):
    """2주 지난 캡쳐는 지움"""
    if not os.path.isdir(folder):
        return
    limit = time.time() - days * 86400
    for f in os.listdir(folder):
        p = os.path.join(folder, f)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) < limit:
                os.remove(p)
        except OSError:
            pass
