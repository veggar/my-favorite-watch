#!/usr/bin/env python3
"""PWA / favicon PNG 자산 생성 스크립트 (P2-1).

`static/icons/*.svg` 와 **동일한 기하 정의**를 Pillow 로 다시 그려 PNG 를 만든다.
SVG 래스터라이저(cairosvg, rsvg)는 시스템 라이브러리 의존이 커서 CI·컨테이너
환경마다 설치 상태가 달라지므로, 런타임 의존을 Pillow 하나로 제한했다.

    python3 scripts/generate_icons.py

SVG 를 수정하면 이 파일의 GEOMETRY 상수도 함께 맞춰야 한다. 실행에는 Pillow가
필요하며(`pip install Pillow`), 런타임 requirements 에는 포함하지 않았다 —
이 스크립트는 아이콘을 바꿀 때만 수동으로 실행하는 개발 도구다.
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

# ── 기하 정의 (SVG viewBox 512x512 기준) ──────────────────────────────────
CANVAS = 512
CORNER_RADIUS = 112

BG_TOP = (79, 70, 229)      # #4f46e5
BG_BOTTOM = (55, 48, 163)   # #3730a3
WHITE = (255, 255, 255)
ACCENT = (79, 70, 229)      # #4f46e5

FRAME = (112, 148, 288, 216)   # x, y, w, h
FRAME_RADIUS = 28

PERF_SIZE = (26, 22)
PERF_RADIUS = 6
PERF_X = (126, 360)
PERF_Y = (168, 212, 256, 300)

PLAY = ((232, 214), (232, 298), (306, 256))
PLAY_SIMPLE = ((214, 200), (214, 312), (322, 256))

# 안티에일리어싱용 초과 샘플링 배율 (그린 뒤 축소한다)
SUPERSAMPLE = 4

OUTPUTS = [
    # (파일명, 크기, 라운드 코너 적용, 단순화 버전)
    ("icon-192.png", 192, True, False),
    ("icon-512.png", 512, True, False),
    ("icon-maskable-512.png", 512, False, False),
    ("apple-touch-icon-180.png", 180, False, False),
    ("favicon-32.png", 32, True, True),
    ("favicon-16.png", 16, True, True),
]


def _vertical_gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    """세로 방향 선형 그라디언트 배경."""
    grad = Image.new("RGB", (1, size))
    px = grad.load()
    last = max(size - 1, 1)
    for y in range(size):
        t = y / last
        px[0, y] = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
    return grad.resize((size, size), Image.NEAREST)


def _scaled(value: float, scale: float) -> float:
    return value * scale


def render(size: int, rounded: bool, simple: bool) -> Image.Image:
    """지정 크기의 아이콘을 렌더링한다."""
    work = CANVAS * SUPERSAMPLE
    scale = work / CANVAS

    img = _vertical_gradient(work, BG_TOP, BG_BOTTOM).convert("RGBA")

    if rounded:
        # 라운드 코너 밖을 투명하게 잘라낸다.
        mask = Image.new("L", (work, work), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, work - 1, work - 1),
            radius=_scaled(CORNER_RADIUS, scale),
            fill=255,
        )
        img.putalpha(mask)

    draw = ImageDraw.Draw(img)

    fx, fy, fw, fh = FRAME
    draw.rounded_rectangle(
        (_scaled(fx, scale), _scaled(fy, scale),
         _scaled(fx + fw, scale), _scaled(fy + fh, scale)),
        radius=_scaled(FRAME_RADIUS, scale),
        fill=WHITE,
    )

    if not simple:
        pw, ph = PERF_SIZE
        for x in PERF_X:
            for y in PERF_Y:
                draw.rounded_rectangle(
                    (_scaled(x, scale), _scaled(y, scale),
                     _scaled(x + pw, scale), _scaled(y + ph, scale)),
                    radius=_scaled(PERF_RADIUS, scale),
                    fill=ACCENT,
                )

    points = PLAY_SIMPLE if simple else PLAY
    draw.polygon([(_scaled(px_, scale), _scaled(py_, scale)) for px_, py_ in points],
                 fill=ACCENT)

    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "static", "icons")
    os.makedirs(out_dir, exist_ok=True)

    for name, size, rounded, simple in OUTPUTS:
        path = os.path.join(out_dir, name)
        render(size, rounded, simple).save(path, "PNG", optimize=True)
        print(f"생성: static/icons/{name} ({size}x{size})")

    # favicon.ico 는 16/32 두 크기를 함께 담는다 (구형 브라우저·북마크바 대응)
    ico_path = os.path.join(root, "static", "favicon.ico")
    render(64, True, True).save(ico_path, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print("생성: static/favicon.ico (16/32/48)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
