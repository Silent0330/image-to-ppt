"""yt-dlp 的封裝：格式選擇、進度回報與輸出檔名處理。

對外只暴露 :func:`download` 與少數純函式（格式字串、cookie 檔搜尋），
方便 UI 與測試共用，不需要直接接觸 yt-dlp 的選項字典。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import yt_dlp

MODE_VIDEO = "video"
MODE_AUDIO = "audio"

# 顯示標籤 → 解析度上限（None 表示不限制）
VIDEO_QUALITIES: dict[str, int | None] = {
    "最佳畫質": None,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
}
# 顯示標籤 → MP3 位元率（kbps）
AUDIO_QUALITIES: dict[str, str] = {
    "320 kbps": "320",
    "192 kbps": "192",
    "128 kbps": "128",
}
COOKIE_BROWSERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi", "safari")

ProgressReport = Callable[["Progress"], None]

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class CancelledError(Exception):
    """使用者中途取消下載。"""


@dataclass(frozen=True)
class Progress:
    """單一影音項目的下載進度快照。"""

    percent: float
    speed: str
    eta: str
    stage: str
    filename: str


@dataclass(frozen=True)
class DownloadResult:
    """一筆完成的下載結果。"""

    title: str
    path: Path


def build_format(mode: str, height: int | None) -> str:
    """組出 yt-dlp 的 ``format`` 選擇字串。"""
    if mode == MODE_AUDIO:
        return "bestaudio/best"
    if height is None:
        return "bestvideo*+bestaudio/best"
    return f"bestvideo[height<=?{height}]+bestaudio/best[height<=?{height}]/best"


def find_cookie_file(explicit: Path | None = None) -> Path | None:
    """尋找可用的 cookies.txt。

    有明確指定時只用該路徑（不存在即回傳 ``None``）；否則依序找
    工作目錄與專案根目錄的預設檔名。
    """
    if explicit is not None:
        return explicit if explicit.is_file() else None
    candidates = [
        Path.cwd() / "youtube_cookies.txt",
        # src/yt_download/downloader.py → 專案根目錄
        Path(__file__).resolve().parents[2] / "youtube_cookies.txt",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def ffmpeg_location() -> str | None:
    """取得可用的 ffmpeg 執行檔路徑；優先使用隨附的 imageio-ffmpeg。"""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - 找不到就交給系統 PATH
        return None


def _human_speed(value: object) -> str:
    if not value:
        return ""
    return f"{float(value) / 1024 / 1024:.1f} MB/s"


def _human_eta(value: object) -> str:
    if value is None:
        return ""
    seconds = int(value)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _base_options(
    output_dir: Path,
    *,
    mode: str,
    quality: str,
    use_playlist: bool,
    cookies_file: Path | None,
    cookies_browser: str | None,
) -> dict:
    """組出下載用的 yt-dlp 選項（不含進度掛勾）。"""
    if mode == MODE_AUDIO:
        fmt = build_format(MODE_AUDIO, None)
        postprocessors: list[dict] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }
        ]
        merge_format = "mp3"
    else:
        fmt = build_format(MODE_VIDEO, VIDEO_QUALITIES.get(quality))
        postprocessors = [{"key": "FFmpegMetadata"}]
        merge_format = "mp4"

    options: dict = {
        "format": fmt,
        "paths": {"home": str(output_dir)},
        "outtmpl": "%(title)s.%(ext)s",
        "merge_output_format": merge_format,
        "noplaylist": not use_playlist,
        "ignoreerrors": False,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "consoletitle": False,
        "retries": 3,
        "fragment_retries": 3,
        "windowsfilenames": os.name == "nt",
        "postprocessors": postprocessors,
    }

    location = ffmpeg_location()
    if location:
        options["ffmpeg_location"] = location

    if cookies_browser:
        options["cookiesfrombrowser"] = (cookies_browser,)
    elif cookies_file is not None:
        options["cookiefile"] = str(cookies_file)

    return options


def download(
    url: str,
    *,
    output_dir: Path,
    mode: str = MODE_VIDEO,
    quality: str | None = None,
    use_playlist: bool = False,
    cookies_file: Path | None = None,
    cookies_browser: str | None = None,
    progress: ProgressReport | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> DownloadResult:
    """下載單一網址，回傳最後產出的檔案。

    ``progress`` 會在 yt-dlp 回報進度時被呼叫；``should_cancel`` 回傳 ``True``
    時會中止下載並丟出 :class:`CancelledError`。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if quality is None:
        quality = (
            next(iter(AUDIO_QUALITIES))
            if mode == MODE_AUDIO
            else next(iter(VIDEO_QUALITIES))
        )

    seen_paths: list[Path] = []

    def _emit(stage: str, data: dict) -> None:
        if progress is None:
            return
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
        downloaded = data.get("downloaded_bytes") or 0
        percent = (downloaded / total * 100) if total else 0.0
        filename = data.get("filename") or ""
        if filename:
            seen_paths.append(Path(filename))
        progress(
            Progress(
                percent=percent,
                speed=_human_speed(data.get("speed")),
                eta=_human_eta(data.get("eta")),
                stage=stage,
                filename=Path(filename).name if filename else "",
            )
        )

    def _hook(data: dict) -> None:
        if should_cancel is not None and should_cancel():
            raise CancelledError("已取消下載")
        status = data.get("status")
        if status == "downloading":
            _emit("下載中", data)
        elif status == "finished":
            _emit("合併中", data)

    options = _base_options(
        output_dir,
        mode=mode,
        quality=quality,
        use_playlist=use_playlist,
        cookies_file=cookies_file,
        cookies_browser=cookies_browser,
    )
    options["progress_hooks"] = [_hook]

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except CancelledError:
        raise
    except yt_dlp.utils.DownloadError as error:
        raise RuntimeError(_clean_error(str(error))) from error

    info = info or {}
    title = info.get("title") or url
    path = _resolve_output(info, output_dir, seen_paths)
    return DownloadResult(title=title, path=path)


def _clean_error(message: str) -> str:
    """移除 yt-dlp 訊息中的 ANSI 顏色碼與 ``ERROR:`` 前綴。"""
    return _ANSI.sub("", message).replace("ERROR: ", "").strip()


def _resolve_output(info: dict, output_dir: Path, seen_paths: Sequence[Path]) -> Path:
    """找出實際落地的檔案：優先採用 yt-dlp 回報的結果。"""
    requested = info.get("requested_downloads") or []
    if requested:
        candidate = requested[-1].get("filepath")
        if candidate:
            return Path(candidate)
    filepath = info.get("filepath")
    if filepath:
        return Path(filepath)
    for path in reversed(list(seen_paths)):
        if path.exists():
            return path
    return output_dir


def latest_file(output_dir: Path) -> Path | None:
    """輸出資料夾中最近修改的檔案（供「開啟檔案」使用）。"""
    files: Iterable[Path] = (p for p in output_dir.glob("*") if p.is_file())
    return max(files, key=lambda p: p.stat().st_mtime, default=None)
