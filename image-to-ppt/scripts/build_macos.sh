#!/usr/bin/env bash
# 建置 macOS 執行檔：共用相同程式碼，另外打包。
# 用法： bash scripts/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --group dev
uv run pyinstaller --noconfirm --clean --windowed --name ImageToPPT \
    --paths src --collect-submodules pymupdf launcher.py

# 打包成 ZIP
app="dist/ImageToPPT.app"
zip="dist/ImageToPPT-macOS.zip"
if [[-e "$zip" ]]; then
    rm "$zip"
fi
cd dist
zip -r "$(basename "$zip")" "$(basename "$app")"
cd ..

echo "完成建置 macOS 執行檔，輸出檔案：$zip"
