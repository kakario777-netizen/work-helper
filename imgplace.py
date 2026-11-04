"""업무 도우미 - 원고 사이사이에 이미지 번호 넣기 (원고 글자는 절대 바꾸지 않고 줄만 끼워 넣음)"""
import re

# 이미지 번호 줄로 보는 모양: 1 / (1) / [1] / <1> / 사진1 / [이미지 2] / img_3 / 1번 …
MARK_RE = re.compile(
    r"^\s*[\[\(<【{〔]?\s*(?:사진|이미지|그림|img|image|IMG|Image|pic)?\s*[_\-#.]?\s*(\d{1,3})\s*(?:번)?\s*[\]\)>】}〕]?\s*$")

DEFAULT_RULE = {"template": "{n}", "width": 0, "before": 1, "after": 1, "head": False, "tail": False}


# ───────────── 파일 읽기·쓰기 (인코딩·줄바꿈·BOM 그대로) ─────────────

def read_doc(path):
    raw = open(path, "rb").read()
    for enc, bom in (("utf-8", b"\xef\xbb\xbf"), ("utf-16", b"\xff\xfe"), ("utf-16", b"\xfe\xff")):
        if raw.startswith(bom):
            text = raw.decode("utf-8-sig" if enc == "utf-8" else "utf-16")
            return text, {"enc": "utf-8-sig" if enc == "utf-8" else "utf-16", "nl": _nl(text)}
    for enc in ("utf-8", "cp949"):
        try:
            text = raw.decode(enc)
            return text, {"enc": enc, "nl": _nl(text)}
        except UnicodeDecodeError:
            continue
    text = raw.decode("utf-8", "replace")
    return text, {"enc": "utf-8", "nl": _nl(text)}


def _nl(text):
    return "\r\n" if "\r\n" in text else "\n"


def write_doc(path, text, info):
    data = text.replace("\r\n", "\n")
    if info["nl"] == "\r\n":
        data = data.replace("\n", "\r\n")
    with open(path, "w", encoding=info["enc"], newline="") as f:
        f.write(data)


# ───────────── 샘플에서 규칙 배우기 ─────────────

def is_marker(line):
    return bool(MARK_RE.match(line or ""))


def learn_sample(sample):
    """샘플(이미지 번호가 들어간 원고 한 편, 또는 '[사진 1]' 같은 한 줄) → 규칙"""
    rule = dict(DEFAULT_RULE)
    lines = (sample or "").replace("\r\n", "\n").split("\n")
    marks = [i for i, l in enumerate(lines) if is_marker(l)]
    nonempty = [i for i, l in enumerate(lines) if l.strip()]
    if not marks:
        one = (sample or "").strip()
        if one and "\n" not in one:
            if "{n}" in one:
                rule["template"] = one
            elif re.search(r"\d+", one):
                m = re.search(r"\d+", one)
                rule["template"] = one[:m.start()] + "{n}" + one[m.end():]
                rule["width"] = len(m.group(0)) if m.group(0).startswith("0") else 0
        return rule
    first = marks[0]
    ln = lines[first].strip()
    m = re.search(r"\d+", ln)
    rule["template"] = ln[:m.start()] + "{n}" + ln[m.end():]
    rule["width"] = len(m.group(0)) if m.group(0).startswith("0") and len(m.group(0)) > 1 else 0

    def blanks(i, step):
        c, j = 0, i + step
        while 0 <= j < len(lines) and not lines[j].strip():
            c += 1
            j += step
        return c
    rule["before"] = max(1, min(3, blanks(first, -1)))
    rule["after"] = max(1, min(3, blanks(first, 1)))
    body = [i for i in nonempty if i not in marks and not is_tail_line(lines[i])]
    # 첫 이미지가 제목(첫 줄) 바로 다음이면 head
    rule["head"] = bool(body) and len([i for i in body if i < first]) <= 1
    # 마지막 이미지 뒤에 본문이 없으면 tail
    rule["tail"] = bool(body) and not [i for i in body if i > marks[-1]]
    return rule


def marker_text(rule, n):
    num = str(n).zfill(rule.get("width") or 0)
    t = rule.get("template") or "{n}"
    return t.replace("{n}", num)


def is_tail_line(line):
    s = line.strip()
    return s.startswith("#") or s.startswith("[") or s.startswith("(지도") or s.startswith("지도")


# ───────────── 배치 ─────────────

def analyze(text):
    """반환: dict(lines, title, gaps, end, tail_start, markers)"""
    lines = text.replace("\r\n", "\n").split("\n")
    n = len(lines)
    nonempty = [i for i, l in enumerate(lines) if l.strip()]
    if not nonempty:
        return {"lines": lines, "title": None, "gaps": [], "end": None, "markers": 0}
    title = nonempty[0]
    # 끝부분의 해시태그·[지도] 같은 꼬리 줄 묶음
    tail_start = n
    for i in reversed(nonempty):
        if is_tail_line(lines[i]):
            tail_start = i
        else:
            break
    body_last = max([i for i in nonempty if i < tail_start] or [title])
    # 문단 끝 = 글자 줄 다음이 빈 줄인 곳 (제목 줄 포함, 마지막 본문 줄 앞까지)
    gaps = [i for i in range(title, body_last)
            if lines[i].strip() and i + 1 < n and not lines[i + 1].strip()]
    markers = sum(1 for i in nonempty if is_marker(lines[i]) and i != title)
    return {"lines": lines, "title": title, "gaps": gaps, "end": body_last, "markers": markers}


def plan(info, count, rule):
    """이미지 count 개를 놓을 위치(이 줄 '뒤에') 목록. 같은 위치가 여러 번 나올 수 있음"""
    if count <= 0 or info["title"] is None:
        return []
    gaps = list(info["gaps"])
    head_gap = info["title"] if gaps and gaps[0] == info["title"] else None
    inner = [g for g in gaps if g != head_gap]
    slots = []
    left = count
    if rule.get("head") and head_gap is not None and left:
        slots.append(head_gap)
        left -= 1
    end_slot = []
    if rule.get("tail") and left:
        end_slot = [info["end"]]
        left -= 1
    if left:
        pool = inner or ([head_gap] if head_gap is not None else []) or [info["end"]]
        k = len(pool)
        for j in range(left):
            if left < k:   # 문단 사이 빈자리에 고르게 하나씩
                idx = (j + 1) * k // (left + 1)
            else:          # 자리가 모자라면 한 자리에 여러 장
                idx = j * k // left
            slots.append(pool[max(0, min(k - 1, idx))])
    slots += end_slot
    return sorted(slots)


def place(text, count, rule, start=1):
    """원고에 번호 줄을 끼워 넣은 새 글. 원래 글자는 한 줄도 바꾸지 않음.
    반환: (새 글, 넣은 번호 수)   — 원본 보존 검사 실패 시 ValueError"""
    info = analyze(text)
    lines = info["lines"]
    slots = plan(info, count, rule)
    place.last_inserted = [False] * len(lines)
    if not slots:
        return text, 0
    before, after = int(rule.get("before", 1)), int(rule.get("after", 1))
    out, inserted = [], []
    num = start
    by_pos = {}
    for p in slots:
        by_pos[p] = by_pos.get(p, 0) + 1
    for i, line in enumerate(lines):
        out.append(line)
        inserted.append(False)
        times = by_pos.get(i, 0)
        for t in range(times):
            # 이미지 위 빈 줄: 첫 번호는 샘플대로, 연달아 붙는 번호는 1줄
            for _ in range(before if t == 0 else 1):
                out.append("")
                inserted.append(True)
            out.append(marker_text(rule, num))
            inserted.append(True)
            num += 1
        if times:
            # 이미지 아래 빈 줄: 원래 있던 빈 줄을 쓰고, 모자라면 채움
            existing = 0
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                existing += 1
                j += 1
            has_next = j < len(lines)
            for _ in range(max(0, after - existing) if has_next else 0):
                out.append("")
                inserted.append(True)
    # 원본 보존 검사: 넣은 줄을 빼면 원래 글과 완전히 같아야 함
    kept = [l for l, ins in zip(out, inserted) if not ins]
    if kept != lines:
        raise ValueError("원본 보존 검사 실패")
    place.last_inserted = inserted
    return "\n".join(out), num - start
