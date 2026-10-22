# ImageToPPT

將 PDF 每一頁或每張圖片轉換成一張 16:9 的 PowerPoint 投影片。轉換完全在本機進行，不需要網路。

## 功能

- **PDF 轉 PPT**：每頁 PDF 對應一張投影片。每次只能選一份 PDF（選到新的會直接取代原本的）；選取後展開成每一頁，清單、預覽與排序都以「頁」為單位。
- **圖片轉 PPT**：每張圖片對應一張投影片，可加入多張並自由排序。
- **PDF 轉圖片**：將 PDF 每頁輸出成圖片檔到指定資料夾，依頁碼命名（例如 `001.png`、`002.png`）；每次只能選一份 PDF。可選 PNG／JPEG 與 DPI。
- 投影片固定 16:9（13.333 × 7.5 英吋），排版以 1920 × 1080 為基準。
- 三種排版模式，一律維持原始長寬比例、不變形：
  - **模式 A：高度優先、水平置中**（預設）— 圖片高度等於投影片高度，超出左右邊界的部分由投影片視窗裁切。
  - **模式 B：完整顯示、不裁切、置中** — 整張圖片放入投影片並水平、垂直置中。
  - **模式 C：寬度優先、垂直置中** — 圖片寬度等於投影片寬度，超出上下邊界的部分由投影片視窗裁切。
- 背景顏色可選（預設白色）。
- 檔案排序：可上移／下移調整投影片順序（逐頁調整；PDF 展開後每頁為一個項目）。
- 即時預覽（以目前選取的頁面為準）與轉換進度顯示。

## 開發環境

需要 [uv](https://docs.astral.sh/uv/)。

```powershell
uv sync
uv run image-to-ppt      # 啟動介面
uv run pytest            # 執行測試
```

## 排版計算

| 模式 | scale | W | H | X | Y |
| --- | --- | --- | --- | --- | --- |
| A 高度優先 | SH / IH | IW × scale | SH | (SW − W) / 2 | 0 |
| B 完整顯示 | min(SW / IW, SH / IH) | IW × scale | IH × scale | (SW − W) / 2 | (SH − H) / 2 |
| C 寬度優先 | SW / IW | SW | IH × scale | 0 | (SH − H) / 2 |

其中 SW = 1920、SH = 1080、IW／IH 為原始圖片尺寸。模式 A、C 只將圖片等比例放大並設定位置，不額外產生裁切後的圖片，由 PowerPoint 於播放／匯出時裁切，因此保留原始畫質並共用同一套產生模組。

## 打包

```powershell
# Windows：產生 dist\ImageToPPT-Windows.zip，解壓後直接執行 ImageToPPT.exe
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

```bash
# macOS：共用相同程式碼，另外打包成 .app
bash scripts/build_macos.sh
```
