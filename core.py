"""업무 도우미 - 화면과 상관없는 가공 로직 모음"""
import os
import re
import shutil
from datetime import datetime, timedelta

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


# ── 순위 정리: "키워드<탭>링크<탭>순위<탭>병원명" → "링크 [병원명] 키워드" ──

def convert_rank(text):
    out = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("\t")] if "\t" in line else line.split()
        parts = [p for p in parts if p]
        link_i = next((i for i, p in enumerate(parts) if p.lower().startswith("http")), None)
        if link_i is None:
            continue  # 머리글 등 링크 없는 줄은 건너뜀
        link = parts[link_i]
        keyword = " ".join(parts[:link_i]).strip()
        rest = parts[link_i + 1:]
        # 순위(숫자) 뒤에 오는 것이 병원명
        if rest and re.fullmatch(r"[\d.\-위]+", rest[0]):
            rest = rest[1:]
        hospital = " ".join(rest).strip()
        out.append(f"{link} [{hospital}] {keyword}" if hospital else f"{link} {keyword}")
    return "\n".join(out)


# ── 원고 검사 ──

_LEAD_NUM = re.compile(r"^[\s\d._\-()\[\]#]+")
_SPLIT = re.compile(r"[\s_\-.,()\[\]{}+]+")


def guess_keyword(filename, text):
    """키워드 추정: 파일명 첫 단어가 본문에 있으면 그것, 아니면 본문 첫 단어"""
    stem = os.path.splitext(os.path.basename(filename))[0]
    stem = _LEAD_NUM.sub("", stem)
    cands = [t for t in _SPLIT.split(stem) if len(t) >= 2]
    for c in cands:
        if c in text:
            return c
    for line in text.splitlines():
        line = line.strip()
        if line:
            first = re.sub(r"^[^\w가-힣]+|[^\w가-힣]+$", "", line.split()[0])
            if len(first) >= 2:
                return first
            break
    return cands[0] if cands else stem


def count_keywords(text, keyword_field):
    """'서울역피부과, 수술흉터제거' → [('서울역피부과', 5), ...]"""
    res = []
    for k in re.split(r"[,，]", keyword_field):
        k = k.strip()
        if k:
            res.append((k, text.count(k)))
    return res


def count_forbidden(text, words):
    res = []
    for w in words:
        w = w.strip()
        if w:
            n = text.count(w)
            if n:
                res.append((w, n))
    return res


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


# ─────────────────────────── 랜덤 캡쳐(병원 이미지·썸네일) ───────────────────────────

def _tone_lut(rng):
    """감마 1~3%, 채널별 아주 미세한 색 틀어짐"""
    g = 1 + rng.choice((-1, 1)) * rng.uniform(0.01, 0.03)
    lut = []
    for ch in range(3):
        tint = 1 + rng.uniform(-0.006, 0.006)
        for v in range(256):
            x = (v / 255.0) ** (1 / g) * 255.0 * tint
            lut.append(max(0, min(255, int(round(x)))))
    return lut, g


def make_variant(src_path, long_min, long_max, rng, aspect_jitter=0.05):
    """원본을 사람이 캡쳐한 것처럼 무작위로 잘라 크기를 바꾸고 색감을 아주 살짝 틀어 줌.
    반환: (PIL 이미지, 적용값 설명)"""
    from PIL import Image, ImageOps, ImageEnhance
    with Image.open(src_path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        W, H = im.size

        # 1) 자르기: 원본의 82~97%, 비율은 원본에서 살짝만 어긋나게, 위치는 랜덤
        a = (W / H) * rng.uniform(1 - aspect_jitter, 1 + aspect_jitter)
        scale = rng.uniform(0.82, 0.97)
        cw = W * scale
        ch = cw / a
        if ch > H * 0.98:
            ch = H * rng.uniform(0.85, 0.98)
            cw = min(W, ch * a)
        x = rng.uniform(0, max(0, W - cw))
        y = rng.uniform(0, max(0, H - ch))
        box = (int(x), int(y), int(x + cw), int(y + ch))
        im = im.crop(box)
        cw, ch = im.size

        # 2) 크기: 긴 변을 long_min~long_max에서 랜덤, 짧은 변은 비율 따라 + 몇 픽셀 엇나감
        L = rng.randint(long_min, long_max)
        if cw >= ch:
            ow, oh = L, round(L * ch / cw) + rng.randint(-6, 6)
        else:
            oh, ow = L, round(L * cw / ch) + rng.randint(-6, 6)
        im = im.resize((max(50, ow), max(50, oh)), Image.LANCZOS)

        # 3) 색감: 밝기 ~1%, 대비 ~1%, 채도 1~2%, 감마 1~3%
        sign = lambda: rng.choice((-1, 1))
        br = 1 + sign() * rng.uniform(0.004, 0.012)
        co = 1 + sign() * rng.uniform(0.004, 0.012)
        sa = 1 + sign() * rng.uniform(0.01, 0.02)
        im = ImageEnhance.Brightness(im).enhance(br)
        im = ImageEnhance.Contrast(im).enhance(co)
        im = ImageEnhance.Color(im).enhance(sa)
        lut, g = _tone_lut(rng)
        im = im.point(lut)
        if rng.random() < 0.5:
            im = ImageEnhance.Sharpness(im).enhance(1 + rng.uniform(-0.08, 0.08))
        info = f"{im.size[0]}x{im.size[1]} 밝기{br:.3f} 대비{co:.3f} 채도{sa:.3f} 감마{g:.3f}"
        return im, info


def save_with_new_meta(im, path, rng):
    """원본 메타데이터는 버리고 새 날짜·고유ID로 저장, 인코딩 설정도 매번 다르게"""
    from PIL import Image
    t = datetime.now() - timedelta(seconds=rng.randint(0, 3 * 24 * 3600))
    stamp = t.strftime("%Y:%m:%d %H:%M:%S")
    exif = Image.Exif()
    exif[0x0132] = stamp                         # DateTime
    exif[0x0131] = rng.choice(["", "Windows Photo Editor", "Snipping Tool", "Microsoft Windows"])
    exif[0x0131] = exif[0x0131] or None
    if exif[0x0131] is None:
        del exif[0x0131]
    ifd = exif.get_ifd(0x8769)
    ifd[0x9003] = stamp                          # DateTimeOriginal
    ifd[0x9004] = stamp                          # DateTimeDigitized
    ifd[0xA420] = "%032x" % rng.getrandbits(128)  # ImageUniqueID
    ifd[0xA002] = im.size[0]
    ifd[0xA003] = im.size[1]
    im.save(path, "JPEG", quality=rng.randint(89, 96), subsampling=rng.choice((0, 1, 2)),
            optimize=rng.random() < 0.5, progressive=rng.random() < 0.4, exif=exif.tobytes())
    ts = t.timestamp()
    os.utime(path, (ts, ts))


def next_numbered_dir(parent, base):
    n = 1
    while os.path.exists(os.path.join(parent, f"{base} {n}")):
        n += 1
    return os.path.join(parent, f"{base} {n}")


def generate_set(src_files, out_dir, count, long_min, long_max, seed=None, progress=None):
    """src_files에서 count장 만들어 out_dir에 1.jpg~ 로 저장. 원본을 고르게 돌아가며 사용"""
    import random
    rng = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)
    order = []
    made = []
    for i in range(count):
        if not order:
            order = list(src_files)
            rng.shuffle(order)
        src = order.pop()
        im, info = make_variant(src, long_min, long_max, rng)
        p = os.path.join(out_dir, f"{i + 1}.jpg")
        save_with_new_meta(im, p, rng)
        made.append((p, os.path.basename(src), info))
        if progress:
            progress(i + 1)
    return made
