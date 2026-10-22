"""YT Download：以 yt-dlp 下載影片與音樂的桌面工具。"""

__version__ = "0.1.0"

__all__ = ["__version__", "main"]


def main() -> None:
    from .app import main as run_app

    run_app()
