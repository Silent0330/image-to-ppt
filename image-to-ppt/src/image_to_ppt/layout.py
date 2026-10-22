"""投影片排版計算（基準 1920 x 1080，16:9）。"""

from __future__ import annotations

from dataclasses import dataclass

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080

MODE_HEIGHT_FIRST = "height_first"  # 模式 A：高度優先、水平置中（預設）
MODE_FIT = "fit"  # 模式 B：完整顯示、不裁切、置中
MODE_WIDTH_FIRST = "width_first"  # 模式 C：寬度優先、垂直置中

MODES = (MODE_HEIGHT_FIRST, MODE_FIT, MODE_WIDTH_FIRST)

MODE_LABELS = {
    MODE_HEIGHT_FIRST: "高度優先、水平置中（預設）",
    MODE_FIT: "完整顯示、不裁切、置中",
    MODE_WIDTH_FIRST: "寬度優先、垂直置中",
}


@dataclass(frozen=True)
class Rect:
    """圖片在投影片座標（像素）上的位置與尺寸，可能超出投影片邊界。"""

    x: float
    y: float
    w: float
    h: float


def compute_layout(
    image_width: float,
    image_height: float,
    mode: str = MODE_HEIGHT_FIRST,
    slide_width: float = SLIDE_WIDTH,
    slide_height: float = SLIDE_HEIGHT,
) -> Rect:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("圖片尺寸必須為正數")
    if mode not in MODES:
        raise ValueError(f"未知的排版模式: {mode}")

    if mode == MODE_HEIGHT_FIRST:
        scale = slide_height / image_height
        w = image_width * scale
        h = slide_height
        x = (slide_width - w) / 2
        y = 0.0
    elif mode == MODE_FIT:
        scale = min(slide_width / image_width, slide_height / image_height)
        w = image_width * scale
        h = image_height * scale
        x = (slide_width - w) / 2
        y = (slide_height - h) / 2
    else:  # MODE_WIDTH_FIRST
        scale = slide_width / image_width
        w = slide_width
        h = image_height * scale
        x = 0.0
        y = (slide_height - h) / 2

    return Rect(x=x, y=y, w=w, h=h)
