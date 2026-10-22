# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包設定：將 ImageToPPT 打包成單一可執行檔目錄。"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules("pymupdf")
datas = collect_data_files("customtkinter")

a = Analysis(
    ["launcher.py"],
    pathex=["src"],
    hiddenimports=hiddenimports,
    datas=datas,
    excludes=["pytest"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ImageToPPT",
    console=False,
    onefile=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="ImageToPPT",
)
