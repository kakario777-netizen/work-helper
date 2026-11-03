"""업무 도우미 - 화면과 상관없는 가공 로직 모음"""
import os
import re
import shutil
from datetime import datetime

# ─────────────────────────── 텍스트 ───────────────────────────

def count_stats(text, keywords):
    """글자수와 키워드 등장 횟수"""
    no_space = len(re.sub(r"\s", "", text))
    with_space = len(text.replace("\r", "").replace("\n", ""))
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    lines = [l for l in text.splitlines() if l.strip()]
    kw = []
    for k in keywords:
        k = k.strip()
        if k:
            kw.append((k, text.count(k)))
    return {
        "no_space": no_space,
        "with_space": with_space,
        "paragraphs": len(paragraphs),
        "lines": len(lines),
        "keywords": kw,
    }


SPECIAL_LINE = re.compile(r"^\s*([-#\[(※*•▶]|\d+[.)]\s)")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+")


def _wrap_one(s, width, tol=2):
    words = s.split()
    lines, cur = [], ""
    for w in words:
        cand = f"{cur} {w}" if cur else w
        if len(cand) <= width + tol or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def wrap_text(text, width=20, sentence_blank=False, keep_first=True, tol=2):
    """문단을 한 줄 width자 안팎으로 다시 끊어 줌.
    - 줄이 '-', '#', '[' 등으로 시작하면 손대지 않음
    - keep_first: 문단 첫 문장(소제목 역할)은 한 줄로 유지
    - sentence_blank: 문장마다 뒤에 빈 줄
    """
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return ""
    out_blocks = []
    for para in re.split(r"\n\s*\n", text):
        blocks = []  # 각 블록은 줄 목록
        buf = []

        def flush():
            if not buf:
                return
            joined = " ".join(x.strip() for x in buf if x.strip())
            buf.clear()
            sentences = [s for s in SENTENCE_SPLIT.split(joined) if s.strip()]
            first_done = False
            if keep_first and sentences and not blocks:
                blocks.append([sentences[0].strip()])
                sentences = sentences[1:]
                first_done = True
            if sentence_blank:
                for s in sentences:
                    blocks.append(_wrap_one(s, width, tol))
            elif sentences:
                body = _wrap_one(" ".join(sentences), width, tol)
                if first_done:
                    blocks[-1].extend(body)
                else:
                    blocks.append(body)

        special_group = []
        for line in para.split("\n"):
            if not line.strip():
                continue
            if SPECIAL_LINE.match(line):
                flush()
                special_group.append(line.strip())
            else:
                if special_group:
                    blocks.append(special_group)
                    special_group = []
                buf.append(line)
        flush()
        if special_group:
            blocks.append(special_group)

        if sentence_blank:
            out_blocks.append("\n\n".join("\n".join(b) for b in blocks))
        else:
            out_blocks.append("\n".join("\n".join(b) for b in blocks))
    return "\n\n".join(out_blocks)


REPORT_KINDS = {
    "업무 보고서": ("【업무 보고서】", "주요 내용", "이상 보고드립니다."),
    "일일 업무일지": ("【일일 업무일지】", "오늘 한 일", "이상입니다."),
    "회의록": ("【회의록】", "논의 내용", "이상 회의 내용 정리입니다."),
}

BULLET_PREFIX = re.compile(r"^\s*(?:[-*•·□■▶>]+|\d+[.)])\s*")


def make_report(kind, title, author, date, memo, extra=""):
    """메모(한 줄에 하나씩)를 보고서 양식으로.
    '#'로 시작하거나 ':'로 끝나는 줄은 항목 제목이 됨."""
    head, default_sec, closing = REPORT_KINDS.get(kind, REPORT_KINDS["업무 보고서"])
    sections = []
    for raw in memo.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#") or line.endswith(":") or line.endswith("："):
            name = line.lstrip("#").rstrip(":：").strip()
            sections.append([name, []])
        else:
            item = BULLET_PREFIX.sub("", line).strip()
            if not item:
                continue
            if not sections:
                sections.append([default_sec, []])
            sections[-1][1].append(item)

    bar = "─" * 24
    out = [head, ""]
    if title.strip():
        out.append(f"제    목 : {title.strip()}")
    if author.strip():
        out.append(f"작 성 자 : {author.strip()}")
    out.append(f"작 성 일 : {date.strip() or datetime.now().strftime('%Y-%m-%d')}")
    if extra.strip():
        label = "참 석 자" if kind == "회의록" else "비    고"
        out.append(f"{label} : {extra.strip()}")
    out += ["", bar, ""]
    for i, (name, items) in enumerate(sections, 1):
        out.append(f"{i}. {name}")
        for it in items:
            out.append(f"   - {it}")
        out.append("")
    out += [bar, closing]
    return "\n".join(out)


# ─────────────────────────── 이미지 ───────────────────────────

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
FORMATS = {"원본 유지": None, "JPG": ("JPEG", ".jpg"), "PNG": ("PNG", ".png"), "WEBP": ("WEBP", ".webp")}
_EXT_TO_FMT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP",
               ".bmp": "BMP", ".gif": "GIF", ".tif": "TIFF", ".tiff": "TIFF"}


def list_images(folder, recursive=False):
    found = []
    if recursive:
        for root, _, files in os.walk(folder):
            for f in files:
                if os.path.splitext(f)[1].lower() in IMAGE_EXT:
                    found.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            p = os.path.join(folder, f)
            if os.path.isfile(p) and os.path.splitext(f)[1].lower() in IMAGE_EXT:
                found.append(p)
    return sorted(found)


def build_name(pattern, stem, index, digits):
    name = pattern
    name = name.replace("{이름}", stem)
    name = name.replace("{번호}", str(index).zfill(digits))
    name = name.replace("{날짜}", datetime.now().strftime("%Y%m%d"))
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or stem
    return name


def _unique(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{base}_{n}{ext}"):
        n += 1
    return f"{base}_{n}{ext}"


def process_image(src, out_dir, index, opts):
    """opts: resize(bool), resize_mode('width'|'percent'|'long'), resize_value(int),
    fmt(str), quality(int), rename(bool), pattern(str), digits(int)
    반환: (저장경로, 원본바이트, 결과바이트)"""
    from PIL import Image, ImageOps

    stem, src_ext = os.path.splitext(os.path.basename(src))
    fmt_info = FORMATS.get(opts.get("fmt", "원본 유지"))
    if fmt_info:
        pil_fmt, ext = fmt_info
    else:
        ext = src_ext.lower()
        pil_fmt = _EXT_TO_FMT.get(ext, "PNG")
    name = build_name(opts["pattern"], stem, index, opts.get("digits", 3)) if opts.get("rename") else stem
    dst = _unique(os.path.join(out_dir, name + ext))
    before = os.path.getsize(src)

    # 크기·형식 변경이 없으면 원본 그대로 복사(화질 손실 없음)
    if not opts.get("resize") and not fmt_info:
        shutil.copy2(src, dst)
        return dst, before, os.path.getsize(dst)

    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if opts.get("resize"):
            w, h = im.size
            v = max(1, int(opts.get("resize_value", 100)))
            mode = opts.get("resize_mode", "width")
            if mode == "percent":
                nw, nh = round(w * v / 100), round(h * v / 100)
            elif mode == "long":
                r = v / max(w, h)
                nw, nh = (round(w * r), round(h * r)) if r < 1 else (w, h)
            else:
                nw, nh = (v, round(h * v / w)) if w > v else (w, h)
            if (nw, nh) != (w, h):
                im = im.resize((max(1, nw), max(1, nh)), Image.LANCZOS)
        q = int(opts.get("quality", 85))
        kw = {}
        if pil_fmt == "JPEG":
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            kw = {"quality": q, "optimize": True, "progressive": True}
        elif pil_fmt == "WEBP":
            kw = {"quality": q, "method": 4}
        elif pil_fmt == "PNG":
            kw = {"optimize": True}
        im.save(dst, pil_fmt, **kw)
    return dst, before, os.path.getsize(dst)


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
