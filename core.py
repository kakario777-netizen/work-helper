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


def natural_key(path):
    """사람이 보는 순서: 1, 2, 3 … 10, 11 (글자 순 1, 10, 11, 2 가 아니라)"""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower())
            for t in re.split(r"(\d+)", str(path)) if t]


def natural_sorted(items):
    return sorted(items, key=natural_key)


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
    return natural_sorted(found)


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

    adj = opts.get("adjust") or {}
    has_adj = any(float(v or 0) for v in adj.values())

    # 크기·형식·색감 변경이 없으면 원본 그대로 복사(화질 손실 없음)
    if not opts.get("resize") and not fmt_info and not has_adj:
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
        if has_adj:
            alpha = im.getchannel("A") if im.mode in ("RGBA", "LA") else None
            im = apply_adjust(im.convert("RGB"), adj)
            if alpha is not None and pil_fmt != "JPEG":
                im.putalpha(alpha)
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


# ─────────────────────────── 색감 조절 ───────────────────────────

# (키, 이름, 최소, 최대)  값 단위는 대부분 %
ADJUSTS = [
    ("brightness", "밝기", -50, 50),
    ("contrast", "대비", -50, 50),
    ("saturation", "채도", -100, 100),
    ("gamma", "감마", -50, 50),
    ("highlights", "하이라이트", -50, 50),
    ("shadows", "그림자", -50, 50),
    ("temperature", "색온도(파랑↔주황)", -50, 50),
    ("tint", "색조(초록↔자홍)", -50, 50),
    ("hue", "색상 회전", -30, 30),
    ("red", "빨강", -30, 30),
    ("green", "초록", -30, 30),
    ("blue", "파랑", -30, 30),
    ("sharpness", "선명도", -100, 100),
    ("blur", "흐림", 0, 30),
    ("noise", "노이즈", 0, 30),
    ("vignette", "가장자리 어둡게", 0, 50),
]


def apply_adjust(im, p):
    """RGB 이미지에 색감 값(p: {키: 값}) 적용"""
    from PIL import Image, ImageEnhance, ImageFilter, ImageChops

    def g(k):
        try:
            return float(p.get(k, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    if im.mode != "RGB":
        im = im.convert("RGB")
    if g("hue"):
        shift = int(round(g("hue") * 256 / 360)) % 256
        h, s_, v = im.convert("HSV").split()
        h = h.point(lambda x: (x + shift) % 256)
        im = Image.merge("HSV", (h, s_, v)).convert("RGB")
    if g("brightness"):
        im = ImageEnhance.Brightness(im).enhance(1 + g("brightness") / 100)
    if g("contrast"):
        im = ImageEnhance.Contrast(im).enhance(1 + g("contrast") / 100)
    if g("saturation"):
        im = ImageEnhance.Color(im).enhance(max(0.0, 1 + g("saturation") / 100))

    gam, hi, sh = 1 + g("gamma") / 100, g("highlights") / 100, g("shadows") / 100
    temp, tint = g("temperature") / 100, g("tint") / 100
    mult = (1 + temp * 0.5 + g("red") / 100,
            1 - tint * 0.5 + g("green") / 100,
            1 - temp * 0.5 + g("blue") / 100)
    if gam != 1 or hi or sh or any(m != 1 for m in mult):
        gam = max(0.1, gam)
        lut = []
        for ch in range(3):
            for x in range(256):
                n = (x / 255.0) ** (1 / gam)
                n += sh * 0.2 * 6.75 * n * (1 - n) ** 2
                n += hi * 0.2 * 6.75 * n * n * (1 - n)
                n *= mult[ch]
                lut.append(max(0, min(255, int(round(n * 255)))))
        im = im.point(lut)

    if g("sharpness"):
        im = ImageEnhance.Sharpness(im).enhance(max(0.0, 1 + g("sharpness") / 100))
    if g("blur") > 0:
        im = im.filter(ImageFilter.GaussianBlur(g("blur") / 10))
    if g("noise") > 0:
        noise = Image.effect_noise(im.size, g("noise")).convert("RGB")
        im = ImageChops.add(im, noise, 1.0, -128)
    if g("vignette") > 0:
        amt = g("vignette") / 100
        m = Image.radial_gradient("L").resize(im.size)
        m = m.point(lambda x: int(255 * (1 - amt * (min(x, 255) / 255) ** 2)))
        im = ImageChops.multiply(im, Image.merge("RGB", (m, m, m)))
    return im


def _r1(x):
    return round(x, 1)


# 랜덤 버튼 세기: (키 → (최대 변화량, 바뀔 확률))  아주 약하게
RANDOM_AMP = {
    "brightness": (2, 1), "contrast": (2, 1), "saturation": (3, 1), "gamma": (3, 1),
    "highlights": (4, 1), "shadows": (4, 1), "temperature": (3, 1), "tint": (2, 1),
    "hue": (1, 1), "red": (1.5, 1), "green": (1.5, 1), "blue": (1.5, 1),
    "sharpness": (10, 1), "blur": (3, 0.3), "noise": (3, 0.3), "vignette": (6, 0.4),
}
ONE_SIDED = {"blur", "noise", "vignette"}

DEFAULT_RANDOM_RANGE = {
    "image": {"len": [760, 940], "trim": [2, 12], "aspect": [2.0, 6.0]},
    "thumb": {"len": [720, 980], "trim": [2, 12], "aspect": [2.0, 6.0]},
}


def random_adjust(rng, keys):
    """체크된 색감 항목만 아주 약한 값으로 무작위"""
    out = {}
    for k in keys:
        amp, prob = RANDOM_AMP.get(k, (1, 1))
        if rng.random() > prob:
            out[k] = 0.0
        elif k in ONE_SIDED:
            out[k] = _r1(rng.uniform(0, amp))
        else:
            out[k] = _r1(rng.uniform(-amp, amp))
    return out


def random_size(rng, cfg):
    """긴 변(1px 단위)·테두리·비율 흔들림을 cfg 범위 안에서 무작위.
    cfg = {"len":[최소,최대], "trim":[최소,최대], "aspect":[최소,최대]}"""
    a, b = sorted(int(x) for x in cfg["len"])
    span = b - a
    lmin = rng.randint(a, a + span // 2)
    lmax = rng.randint(min(b, lmin + max(1, span // 10)), b) if span else a
    ta, tb = sorted(int(x) for x in cfg["trim"])
    tmin = rng.randint(ta, ta + (tb - ta) // 2)
    tmax = rng.randint(tmin, tb)
    aa, ab = sorted(float(x) for x in cfg["aspect"])
    return {"lmin": lmin, "lmax": lmax, "tmin": tmin, "tmax": tmax, "aspect": _r1(rng.uniform(aa, ab))}


def micro_jitter(rng):
    """장마다 덧붙는 아주 미세한 흔들림"""
    def pm(lo, hi):
        return rng.choice((-1, 1)) * rng.uniform(lo, hi)
    j = {"brightness": pm(0.3, 1.2), "contrast": pm(0.3, 1.2), "saturation": pm(1, 2),
         "gamma": pm(1, 3), "temperature": pm(0, 1.2), "tint": pm(0, 0.8),
         "red": pm(0, 0.6), "green": pm(0, 0.6), "blue": pm(0, 0.6),
         "highlights": pm(0, 2), "shadows": pm(0, 2)}
    if rng.random() < 0.5:
        j["sharpness"] = pm(0, 8)
    return j


def _load_rgb(src_path):
    from PIL import Image, ImageOps
    with Image.open(src_path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            return bg
        return im.convert("RGB")


def make_variant(src_path, rng, lmin=800, lmax=900, tmin=2, tmax=8, aspect=3.0, base=None, micro=True):
    """원본 테두리를 몇 픽셀씩(변마다 다르게) 먼저 잘라낸 뒤, 이미지 전체를 확대·축소해 긴 변을 lmin~lmax로 맞추되
    가로·세로 비율을 ±aspect% 안에서 살짝 어긋나게, 색감은 base + 미세 흔들림.
    반환: (이미지, 설명)"""
    from PIL import Image
    im = _load_rgb(src_path)
    W, H = im.size
    L = rng.randint(min(lmin, lmax), max(lmin, lmax))
    lo, hi = sorted((max(0, int(tmin)), max(0, int(tmax))))
    # 1) 원본에서 테두리를 변마다 다른 픽셀만큼 먼저 잘라냄 (한 변당 최대 4%까지만)
    cut = [min(rng.randint(lo, hi), (W if i % 2 == 0 else H) * 0.04) for i in range(4)]
    box = (int(cut[0]), int(cut[1]), int(W - cut[2]), int(H - cut[3]))
    if box[2] - box[0] > 10 and box[3] - box[1] > 10:
        im = im.crop(box)
    # 2) 자른 이미지를 통째로 확대·축소해서 긴 변을 L 픽셀로 (자르지 않음)
    cw, ch = im.size
    j = 1 + rng.uniform(-aspect, aspect) / 100
    if cw >= ch:
        ow, oh = L, round(L * ch / cw * j)
    else:
        oh, ow = L, round(L * cw / ch * j)
    im = im.resize((max(20, ow), max(20, oh)), Image.LANCZOS)
    params = dict(base or {})
    if micro:
        for k, v in micro_jitter(rng).items():
            params[k] = float(params.get(k, 0) or 0) + v
    im = apply_adjust(im, params)
    return im, f"{im.size[0]}x{im.size[1]}"


def save_with_new_meta(im, path, rng):
    """원본 메타데이터는 버리고 새 날짜·고유ID로 저장, 인코딩 설정도 매번 다르게"""
    from PIL import Image
    t = datetime.now() - timedelta(seconds=rng.randint(0, 3 * 24 * 3600))
    stamp = t.strftime("%Y:%m:%d %H:%M:%S")
    exif = Image.Exif()
    exif[0x0132] = stamp
    soft = rng.choice(["", "Windows Photo Editor", "Snipping Tool", "Microsoft Windows"])
    if soft:
        exif[0x0131] = soft
    ifd = exif.get_ifd(0x8769)
    ifd[0x9003] = stamp
    ifd[0x9004] = stamp
    ifd[0xA420] = "%032x" % rng.getrandbits(128)
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


def make_folder_set(src_files, out_dir, rng, progress=None, **kw):
    """원본 이미지 전부를 한 장씩 변형해 out_dir에 1.jpg~ (원본 순서대로)"""
    os.makedirs(out_dir, exist_ok=True)
    for i, src in enumerate(src_files):
        im, _ = make_variant(src, rng, **kw)
        save_with_new_meta(im, os.path.join(out_dir, f"{i + 1}.jpg"), rng)
        if progress:
            progress()


def next_numbered_file(parent, base, ext=".jpg"):
    """'base 1.jpg', 'base 2.jpg' … 중 아직 없는 첫 번호"""
    n = 1
    while os.path.exists(os.path.join(parent, f"{base} {n}{ext}")):
        n += 1
    return os.path.join(parent, f"{base} {n}{ext}")


def pick_random(src_files, count, rng):
    """가진 이미지에서 무작위로 count장 고르기.
    count가 이미지 수 이하이면 중복 없이, 넘으면 모든 이미지를 고르게 한 바퀴씩 돌려 씀(연달아 같은 장 X)"""
    src = list(src_files)
    if not src:
        return []
    picks = []
    while len(picks) < count:
        need = count - len(picks)
        batch = rng.sample(src, min(need, len(src)))
        if picks and len(batch) > 1 and batch[0] == picks[-1]:
            batch[0], batch[-1] = batch[-1], batch[0]
        picks += batch
    return picks


def make_count_set(src_files, out_dir, count, rng, progress=None, kw_fn=None, base_name=None, **kw):
    """보관된 이미지에서 무작위로 골라 count장 만들기.
    base_name 이 있으면 out_dir 에 '이름 1.jpg', '이름 2.jpg' … (이미 있는 번호는 건너뜀), 없으면 1.jpg~
    kw_fn 이 있으면 장마다 그 함수가 주는 새 설정값을 씀. 반환: 저장한 파일 경로들"""
    os.makedirs(out_dir, exist_ok=True)
    saved = []
    for i, src in enumerate(pick_random(src_files, count, rng)):
        im, _ = make_variant(src, rng, **(kw_fn() if kw_fn else kw))
        path = next_numbered_file(out_dir, base_name) if base_name else os.path.join(out_dir, f"{i + 1}.jpg")
        save_with_new_meta(im, path, rng)
        saved.append(path)
        if progress:
            progress()
    return saved
