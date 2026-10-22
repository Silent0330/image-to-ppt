"""ImageToPPT：將 PDF 頁面或圖片轉換成 16:9 PowerPoint 投影片。"""

__version__ = "0.1.0"

__all__ = ["__version__", "main"]


def main() -> None:
    from .app import main as run_app

    run_app()
