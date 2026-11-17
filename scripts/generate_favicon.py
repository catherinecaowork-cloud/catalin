"""从 Catalin 标记语义生成多尺寸 PNG / ICO（像素对齐，不依赖 inkscape）。"""

from __future__ import annotations

import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
WEB_PUBLIC = ROOT / "apps" / "control-plane" / "web" / "public"
STATIC = ROOT / "apps" / "control-plane" / "autotest_control" / "static"
MEDIA_PREVIEW = Path(
    r"C:\Users\EDY\AppData\Local\Cursor\AgentStores\cursor_agent_stores"
    r"\bc-4930ab8c-9294-4fbb-a03d-ca415a2f7842\files\media\favicon"
)

BG = (0x14, 0x53, 0x2D, 255)
FG = (0xF4, 0xFB, 0xF6, 255)
ACCENT = (0x86, 0xEF, 0xAC, 255)


def _draw_mark(size: int) -> Image.Image:
    """像素对齐绘制，保证 16/32 仍清晰。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 小尺寸少圆一点，避免 16px 看起来像圆点
    radius = 3 if size <= 16 else 5 if size <= 32 else max(6, round(size * 7 / 32))
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=BG)

    cx = cy = (size - 1) / 2
    outer_r = size * 0.355
    stroke = max(2.0, size * 3.6 / 32)
    inner_r = max(outer_r - stroke, size * 0.12)

    # 开口朝右的 C：从下唇 52° 逆时针扫到上唇 308°
    start_deg = 52.0
    end_deg = 308.0
    span = end_deg - start_deg
    steps = max(32, size * 4)
    for i in range(steps):
        t0 = i / steps
        t1 = (i + 1) / steps
        a0 = math.radians(start_deg + t0 * span)
        a1 = math.radians(start_deg + t1 * span)
        poly = [
            (cx + outer_r * math.cos(a0), cy + outer_r * math.sin(a0)),
            (cx + outer_r * math.cos(a1), cy + outer_r * math.sin(a1)),
            (cx + inner_r * math.cos(a1), cy + inner_r * math.sin(a1)),
            (cx + inner_r * math.cos(a0), cy + inner_r * math.sin(a0)),
        ]
        draw.polygon(poly, fill=FG)

    mid_r = (outer_r + inner_r) / 2
    cap_r = stroke / 2
    for ang in (start_deg, end_deg):
        a = math.radians(ang)
        hx = cx + mid_r * math.cos(a)
        hy = cy + mid_r * math.sin(a)
        draw.ellipse((hx - cap_r, hy - cap_r, hx + cap_r, hy + cap_r), fill=FG)

    # 运行三角（自动化回放）
    left = size * 0.56
    top = size * 0.37
    bottom = size * 0.63
    right = size * 0.79
    draw.polygon([(left, top), (right, size / 2), (left, bottom)], fill=ACCENT)
    return img


def _png_bytes(img: Image.Image) -> bytes:
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _ico_from_pngs(png_images: list[tuple[int, bytes]]) -> bytes:
    count = len(png_images)
    header = struct.pack("<HHH", 0, 1, count)
    entries: list[bytes] = []
    blobs: list[bytes] = []
    offset = 6 + 16 * count
    for size, data in png_images:
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        entries.append(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset))
        blobs.append(data)
        offset += len(data)
    return header + b"".join(entries) + b"".join(blobs)


def main() -> None:
    WEB_PUBLIC.mkdir(parents=True, exist_ok=True)
    STATIC.mkdir(parents=True, exist_ok=True)
    MEDIA_PREVIEW.mkdir(parents=True, exist_ok=True)

    for size, name in (
        (16, "favicon-16.png"),
        (32, "favicon-32.png"),
        (48, "favicon-48.png"),
        (180, "apple-touch-icon.png"),
        (192, "icon-192.png"),
        (512, "icon-512.png"),
    ):
        img = _draw_mark(size)
        path = WEB_PUBLIC / name
        img.save(path, format="PNG", optimize=True)
        print("wrote", path.relative_to(ROOT))

    ico_pngs = [
        (16, _png_bytes(_draw_mark(16))),
        (32, _png_bytes(_draw_mark(32))),
        (48, _png_bytes(_draw_mark(48))),
    ]
    ico = _ico_from_pngs(ico_pngs)
    for dest in (WEB_PUBLIC / "favicon.ico", STATIC / "favicon.ico"):
        dest.write_bytes(ico)
        print("wrote", dest.relative_to(ROOT), f"({len(ico)} bytes)")

    # 控制面 /favicon.* 直接从 static 提供；与 Vite public 保持同步
    svg_src = WEB_PUBLIC / "favicon.svg"
    if svg_src.is_file():
        (STATIC / "favicon.svg").write_bytes(svg_src.read_bytes())
        print("wrote", (STATIC / "favicon.svg").relative_to(ROOT))
    for name in (
        "favicon-16.png",
        "favicon-32.png",
        "favicon-48.png",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
    ):
        src = WEB_PUBLIC / name
        if src.is_file():
            (STATIC / name).write_bytes(src.read_bytes())

    _draw_mark(256).save(MEDIA_PREVIEW / "catalin-favicon-256.png", format="PNG")
    _draw_mark(32).resize((128, 128), Image.Resampling.NEAREST).save(
        MEDIA_PREVIEW / "catalin-favicon-32-nearest-128.png", format="PNG"
    )
    _draw_mark(16).resize((128, 128), Image.Resampling.NEAREST).save(
        MEDIA_PREVIEW / "catalin-favicon-16-nearest-128.png", format="PNG"
    )
    print("preview ->", MEDIA_PREVIEW)


if __name__ == "__main__":
    main()
