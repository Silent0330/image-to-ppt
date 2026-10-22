"""圖片來源：載入圖片檔，以及將 PDF 頁面算繪成圖片。"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import pymupdf
from PIL import Image

DEFAULT_PDF_DPI = 150
PREVIEW_DPI = 100

IMAGE_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
)
PDF_EXTENSIONS = frozenset({".pdf"})


@dataclass(frozen=True)
class SlideImage:
    """一張要放進投影片的圖片（記憶體中的資料，不落地）。"""

    data: bytes
    width: int
    height: int
    name: str


@dataclass(frozen=True)
class PdfPage:
    """PDF 的單一頁面與其算繪結果（``pixmap`` 只在該次迭代內有效）。"""

    number: int  # 1 起算
    total: int
    pixmap: pymupdf.Pixmap


@dataclass(frozen=True)
class SlideRef:
    """一張投影片的來源參照（不持有像素）：整張圖，或 PDF 的某一頁。"""

    path: Path
    page: int | None = None  # 1 起算；None 代表整份檔案

    @property
    def is_pdf_page(self) -> bool:
        return self.page is not None

    @property
    def label(self) -> str:
        if self.page is None:
            return self.path.name
        return f"{self.path.name} 第 {self.page} 頁"


def _slide_image(data: bytes, name: str) -> SlideImage:
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
    return SlideImage(data=data, width=width, height=height, name=name)


def render_matrix(dpi: int) -> pymupdf.Matrix:
    zoom = dpi / 72
    return pymupdf.Matrix(zoom, zoom)


def load_image(path: str | Path) -> SlideImage:
    path = Path(path)
    return _slide_image(path.read_bytes(), path.name)


def iter_pdf_pages(
    path: str | Path, dpi: int = DEFAULT_PDF_DPI
) -> Iterator[PdfPage]:
    """只開啟 PDF 一次，逐頁算繪並附帶頁碼與總頁數。"""
    matrix = render_matrix(dpi)
    with pymupdf.open(Path(path)) as document:
        total = document.page_count
        for number, page in enumerate(document, start=1):
            yield PdfPage(number, total, page.get_pixmap(matrix=matrix, alpha=False))


def pdf_page_count(path: str | Path) -> int:
    with pymupdf.open(Path(path)) as document:
        return document.page_count


def render_pdf_page(
    path: str | Path, page_index: int = 0, dpi: int = DEFAULT_PDF_DPI
) -> SlideImage | None:
    """只算繪 PDF 的某一頁（預設第一頁）。"""
    path = Path(path)
    matrix = render_matrix(dpi)
    with pymupdf.open(path) as document:
        if not 0 <= page_index < document.page_count:
            return None
        page = document[page_index]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return _slide_image(
            pixmap.tobytes("png"), f"{path.name} - 第 {page_index + 1} 頁"
        )


def preview_slide_image(path: str | Path) -> SlideImage | None:
    """取得預覽用的單張圖片（PDF 只算繪第一頁，且用低解析度）。"""
    path = Path(path)
    if path.suffix.lower() in PDF_EXTENSIONS:
        return preview_ref(SlideRef(path, 1))
    return preview_ref(SlideRef(path))


def expand_refs(paths: Iterable[str | Path]) -> list[SlideRef]:
    """把來源檔展成投影片參照：PDF 展開成每一頁，圖片則一張一個。

    只讀取頁數，不算繪像素，因此成本極低。
    """
    refs: list[SlideRef] = []
    for raw in paths:
        path = Path(raw)
        suffix = path.suffix.lower()
        if suffix in PDF_EXTENSIONS:
            refs.extend(
                SlideRef(path, page) for page in range(1, pdf_page_count(path) + 1)
            )
        elif suffix in IMAGE_EXTENSIONS:
            refs.append(SlideRef(path))
        else:
            raise ValueError(f"不支援的檔案格式: {path.name}")
    return refs


def slide_image(ref: SlideRef, dpi: int = DEFAULT_PDF_DPI) -> SlideImage:
    """依參照算繪出投影片要用的圖片。"""
    if ref.page is None:
        return load_image(ref.path)
    image = render_pdf_page(ref.path, ref.page - 1, dpi)
    if image is None:
        raise ValueError(f"PDF 頁面不存在：{ref.path.name} 第 {ref.page} 頁")
    return image


def render_refs(
    refs: Iterable[SlideRef], dpi: int = DEFAULT_PDF_DPI
) -> list[SlideImage]:
    """依序算繪所有參照。"""
    return [slide_image(ref, dpi) for ref in refs]


def preview_ref(ref: SlideRef, dpi: int = PREVIEW_DPI) -> SlideImage | None:
    """低解析度算繪單一參照，失敗時回傳 None（預覽不應中斷操作）。"""
    try:
        return slide_image(ref, dpi)
    except Exception:  # noqa: BLE001 - 預覽失敗不應中斷操作
        return None


def collect_slide_images(
    paths: Iterable[str | Path], dpi: int = DEFAULT_PDF_DPI
) -> list[SlideImage]:
    """依序讀取 PDF（展開頁面）與圖片檔，回傳投影片要用的圖片清單。"""
    return render_refs(expand_refs(paths), dpi)
