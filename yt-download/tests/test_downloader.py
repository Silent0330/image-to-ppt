"""downloader 純函式測試（不需連網）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from yt_download import downloader


def test_build_format_audio() -> None:
    assert downloader.build_format(downloader.MODE_AUDIO, 1080) == "bestaudio/best"


def test_build_format_video_best() -> None:
    assert downloader.build_format(downloader.MODE_VIDEO, None) == "bestvideo*+bestaudio/best"


def test_build_format_video_height() -> None:
    fmt = downloader.build_format(downloader.MODE_VIDEO, 720)
    assert "height<=?720" in fmt
    assert fmt.endswith("/best")


def test_find_cookie_file_explicit(tmp_path: Path) -> None:
    cookie = tmp_path / "youtube_cookies.txt"
    cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    assert downloader.find_cookie_file(cookie) == cookie


def test_find_cookie_file_missing(tmp_path: Path) -> None:
    assert downloader.find_cookie_file(tmp_path / "absent.txt") is None


def test_latest_file(tmp_path: Path) -> None:
    assert downloader.latest_file(tmp_path) is None
    first = tmp_path / "a.mp4"
    first.write_bytes(b"a")
    assert downloader.latest_file(tmp_path) == first


@pytest.mark.parametrize("quality", list(downloader.VIDEO_QUALITIES))
def test_base_options_video(quality: str, tmp_path: Path) -> None:
    options = downloader._base_options(
        tmp_path,
        mode=downloader.MODE_VIDEO,
        quality=quality,
        use_playlist=False,
        cookies_file=None,
        cookies_browser=None,
    )
    assert options["merge_output_format"] == "mp4"
    assert options["noplaylist"] is True
    assert options["paths"]["home"] == str(tmp_path)


def test_base_options_audio_with_cookies(tmp_path: Path) -> None:
    cookie = tmp_path / "cookies.txt"
    cookie.write_text("", encoding="utf-8")
    options = downloader._base_options(
        tmp_path,
        mode=downloader.MODE_AUDIO,
        quality="192",
        use_playlist=True,
        cookies_file=cookie,
        cookies_browser=None,
    )
    assert options["merge_output_format"] == "mp3"
    assert options["noplaylist"] is False
    assert options["cookiefile"] == str(cookie)
    assert options["postprocessors"][0]["key"] == "FFmpegExtractAudio"


def test_base_options_browser_cookies(tmp_path: Path) -> None:
    options = downloader._base_options(
        tmp_path,
        mode=downloader.MODE_VIDEO,
        quality="1080p",
        use_playlist=False,
        cookies_file=None,
        cookies_browser="chrome",
    )
    assert options["cookiesfrombrowser"] == ("chrome",)


def test_clean_error_strips_ansi_and_prefix() -> None:
    message = "\x1b[0;31mERROR: \x1b[0m影片不存在"
    assert downloader._clean_error(message) == "影片不存在"
