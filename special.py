"""업무 도우미 - 특수 가공: 워터마크(이미지·GIF), GIF 크기 조절 (움직임 유지)"""
import os
import random
import re
import sys

from PIL import Image, ImageDraw, ImageFont, ImageSequence

import core

WM_STYLES = ["대각선 2개", "위쪽 모서리 2개", "네 모서리", "가운데 1개", "바둑판 반복"]

DEFAULT_IMG_WM = {"on": True, "text": "Dr.Kevin", "style": "대각선 2개", "size": 32.0, "opacity": 10,
                  "angle": 30, "color": "흰색", "font": "기본 (Montserrat ExtraBold)"}
DEFAULT_GIF_WM = {"on": True, "text": "Dr.Kevin", "style": "위쪽 모서리 2개", "size": 16.0, "opacity": 75,
                  "angle": 0, "color": "흰색", "font": "기본 (Montserrat ExtraBold)"}
COLORS = {"흰색": (255, 255, 255), "검정": (0, 0, 0), "회색": (128, 128, 128)}
FONTS = ["기본 (Montserrat ExtraBold)", "Arial Black", "Arial Bold", "맑은 고딕 Bold"]


def _base_dir():
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.dirname(os.path.abspath(__file__))


def _font_file(name, text):
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    has_ko = bool(re.search(r"[가-힣]", text or ""))
    order = []
    if has_ko or name == "맑은 고딕 Bold":
        order += [os.path.join(win, "malgunbd.ttf"), os.path.join(win, "malgun.ttf")]
    if name == "Arial Black":
        order.append(os.path.join(win, "ariblk.ttf"))
    if name == "Arial Bold":
        order.append(os.path.join(win, "arialbd.ttf"))
    order += [os.path.join(_base_dir(), "assets", "Montserrat-ExtraBold.ttf"),
              os.path.join(win, "ariblk.ttf"), os.path.join(win, "arialbd.ttf"),
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    for p in order:
        if os.path.exists(p):
            return p
    return None


def get_font(name, text, px):
    f = _font_file(name, text)
    if f:
        return ImageFont.truetype(f, max(6, int(px)))
    try:
        return ImageFont.load_default(size=max(6, int(px)))
    except TypeError:
        return ImageFont.load_default()


def _text_layer(text, font, rgb, alpha, angle):
    """글자 한 덩이(투명 배경)를 만들어 기울임"""
    l, t, r, b = font.getbbox(text)
    w, h = r - l + 8, b - t + 8
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((4 - l, 4 - t), text, font=font, fill=rgb + (alpha,))
    if angle:
        layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
    return layer


def watermark(im, o):
    """im 에 워터마크 o 를 얹은 RGBA 이미지"""
    if not o.get("on") or not (o.get("text") or "").strip():
        return im
    base = im.convert("RGBA")
    W, H = base.size
    text = o["text"].strip()
    # 크기 = 글자 한 덩이 폭이 이미지 가로의 몇 % 인지
    f100 = get_font(o.get("font"), text, 100)
    l, t, r, b = f100.getbbox(text)
    px = max(8, 100 * (W * float(o.get("size", 20)) / 100) / max(1, r - l))
    font = get_font(o.get("font"), text, px)
    rgb = COLORS.get(o.get("color"), (255, 255, 255))
    alpha = int(255 * max(0, min(100, float(o.get("opacity", 30)))) / 100)
    style = o.get("style", WM_STYLES[0])
    angle = float(o.get("angle", 0)) if style in ("대각선 2개", "가운데 1개", "바둑판 반복") else 0
    layer = _text_layer(text, font, rgb, alpha, angle)
    lw, lh = layer.size
    over = Image.new("RGBA", base.size, (0, 0, 0, 0))
    m = int(min(W, H) * 0.025)
    spots = []
    if style == "대각선 2개":
        spots = [(int(W * 0.30 - lw / 2), int(H * 0.30 - lh / 2)), (int(W * 0.70 - lw / 2), int(H * 0.70 - lh / 2))]
    elif style == "위쪽 모서리 2개":
        spots = [(m, m), (W - lw - m, m)]
    elif style == "네 모서리":
        spots = [(m, m), (W - lw - m, m), (m, H - lh - m), (W - lw - m, H - lh - m)]
    elif style == "가운데 1개":
        spots = [((W - lw) // 2, (H - lh) // 2)]
    else:
        sx, sy = int(lw * 1.6) + 1, int(lh * 2.4) + 1
        for yy in range(-lh, H + lh, sy):
            off = (yy // sy) % 2 * sx // 2
            for xx in range(-lw + off, W + lw, sx):
                spots.append((xx, yy))
    for x, y in spots:
        over.alpha_composite(layer, (max(-lw + 1, min(W - 1, x)), max(-lh + 1, min(H - 1, y))))
    return Image.alpha_composite(base, over)


def is_gif(path):
    try:
        with Image.open(path) as im:
            return im.format == "GIF" and getattr(im, "n_frames", 1) > 1
    except Exception:
        return False


def process_still(src, dst, kw, wm, rng):
    """이미지: 기존 가공(자르기·가로 크기·비율·색감) + 워터마크 → JPG, 새 메타데이터"""
    im, _ = core.make_variant(src, rng, **kw)
    im = watermark(im, wm).convert("RGB")
    core.save_with_new_meta(im, dst, rng)


def process_gif(src, dst, scale_pct, wm):
    """GIF: 프레임마다 크기 조절 + 워터마크, 재생 속도·반복은 그대로"""
    with Image.open(src) as g:
        loop = g.info.get("loop", 0)
        frames, durs = [], []
        W, H = g.size
        nw, nh = max(10, round(W * scale_pct / 100)), max(10, round(H * scale_pct / 100))
        for fr in ImageSequence.Iterator(g):
            durs.append(fr.info.get("duration", g.info.get("duration", 80)) or 80)
            f = fr.convert("RGBA")
            if (nw, nh) != (W, H):
                f = f.resize((nw, nh), Image.LANCZOS)
            f = watermark(f, wm)
            frames.append(f)
    # 투명 없이 저장 (GIF 팔레트로 변환)
    pal = [f.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG) for f in frames]
    pal[0].save(dst, save_all=True, append_images=pal[1:], duration=durs, loop=loop, disposal=1, optimize=False)


def run(items, out_dir, kw, img_wm, gif_wm, gif_range, name_pattern="{번호}", digits=1, progress=None, rng=None):
    """items: 순서대로의 파일 경로. 반환: 저장한 파일 목록"""
    rng = rng or random.Random()
    os.makedirs(out_dir, exist_ok=True)
    lo, hi = sorted(float(x) for x in gif_range)
    saved = []
    for i, src in enumerate(items):
        name = core.numbered_name(name_pattern, i + 1, digits)
        if is_gif(src):
            dst = os.path.join(out_dir, name + ".gif")
            process_gif(src, dst, rng.uniform(lo, hi), gif_wm)
        else:
            dst = os.path.join(out_dir, name + ".jpg")
            process_still(src, dst, kw, img_wm, rng)
        saved.append(dst)
        if progress:
            progress(i + 1)
    return saved
