# YT Download

以 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 下載 YouTube 影片與音樂的桌面小工具，
使用 customtkinter 打造亮色 Apple 風格介面。

## 功能

- 一次貼上多筆網址，逐筆排隊下載
- 影片：輸出 MP4，可選最佳畫質／1080p／720p／480p
- 音樂：轉成 MP3，可選 320／192／128 kbps
- 自動偵測本次上一層目錄或工作目錄的 `youtube_cookies.txt`
- 登入 Cookie 可改用瀏覽器（Chrome、Edge、Firefox…）或指定檔案
- 內含 `imageio-ffmpeg`，不需另裝 FFmpeg 也能合併與轉檔
- 即時進度（百分比、速度、剩餘時間）與下載紀錄

## 安裝與執行

```powershell
uv run yt-download
```

或安裝成命令列工具：

```powershell
uv tool install .
yt-download
```

## 打包執行檔

```powershell
uv run pyinstaller --noconfirm --windowed --name YTDownload `
  --collect-all customtkinter --collect-all imageio_ffmpeg `
  --collect-all yt_dlp launcher.py
```

## 開發

```powershell
uv sync            # 建立虛擬環境與鎖定版本
uv run pytest      # 執行測試
```
