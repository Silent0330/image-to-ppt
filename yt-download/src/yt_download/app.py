"""YT Download 桌面介面（customtkinter，亮色 Apple 風格）。

單一視窗流程：貼上網址 → 選擇輸出與格式 → 開始下載。下載在背景執行，
透過 :class:`~yt_download.worker.BackgroundJob` 回報進度，主執行緒只負責更新畫面。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import downloader
from .worker import BackgroundJob, Failed, Message, Progress, Succeeded

APP_NAME = "YT Download"
POLL_MS = 100

# --- 亮色色票（接近 macOS 淺色模式）---------------------------------------
FONT = "Segoe UI"
PAGE_BG = "#F2F2F7"
CARD_BG = "#FFFFFF"
TEXT = "#1D1D1F"
SUBTEXT = "#8A8A8E"
ACCENT = "#0071E3"
ACCENT_HOVER = "#0077ED"
FIELD_BG = "#F2F2F7"
FIELD_HOVER = "#E8E8ED"
TRACK_BG = "#E9E9EE"
TRACK_HOVER = "#DEDEE3"
BORDER = "#E5E5EA"

MODE_LABELS = {"影片 MP4": downloader.MODE_VIDEO, "音樂 MP3": downloader.MODE_AUDIO}
COOKIE_LABELS = {"不使用": "none", "瀏覽器": "browser", "檔案": "file"}
BROWSER_LABELS = {name.capitalize(): name for name in downloader.COOKIE_BROWSERS}


def _font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


def _default_output_dir() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.cwd()


class App(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("light")
        super().__init__()
        self.title(APP_NAME)
        self.configure(fg_color=PAGE_BG)

        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = max(760, min(920, screen_w - 80))
        height = max(640, min(880, screen_h - 80))
        x = (screen_w - width) // 2
        y = max(0, (screen_h - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(760, 640)

        self._job: BackgroundJob | None = None
        self._toggles: dict = {"rows": {}}

        self._build()
        self._on_mode_change()
        self._on_cookie_change()

    # --- 版面 ---------------------------------------------------------------

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        self._build_header()
        self._build_url_card()
        self._build_settings_card()
        self._build_progress_card()
        self._build_log_card()
        self._build_footer()

    def _card(self, row: int, *, sticky: str = "ew") -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self, fg_color=CARD_BG, corner_radius=16, border_width=1, border_color=BORDER
        )
        card.grid(row=row, column=0, sticky=sticky, padx=24, pady=(10, 0))
        card.columnconfigure(0, weight=1)
        return card

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 4))
        header.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text=APP_NAME, font=_font(24, "bold"), text_color=TEXT
        ).grid(row=0, column=0, sticky="w")
        self._status_var = tk.StringVar(value="待機中")
        ctk.CTkLabel(
            header, textvariable=self._status_var, font=_font(13), text_color=SUBTEXT
        ).grid(row=0, column=1, sticky="e")

    def _build_url_card(self) -> None:
        card = self._card(1)
        ctk.CTkLabel(
            card,
            text="影片或音樂網址（一行一個，可同時多筆）",
            font=_font(13, "bold"),
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        self.url_box = ctk.CTkTextbox(
            card,
            height=92,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            fg_color=FIELD_BG,
            text_color=TEXT,
            font=_font(13),
            wrap="none",
        )
        self.url_box.grid(row=1, column=0, sticky="ew", padx=16)

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 14))
        self._secondary_button(buttons, "從剪貼簿貼上", self._paste_clipboard).pack(side="left")
        self._secondary_button(buttons, "清空", self._clear_urls).pack(side="left", padx=8)

    def _build_settings_card(self) -> None:
        card = self._card(2)

        self.mode_var = tk.StringVar(value=next(iter(MODE_LABELS)))
        self._choice_row(
            card,
            row=0,
            title="下載類型",
            factory=lambda parent: ctk.CTkSegmentedButton(
                parent,
                values=list(MODE_LABELS),
                variable=self.mode_var,
                command=lambda _value: self._on_mode_change(),
                fg_color=TRACK_BG,
                unselected_color=TRACK_BG,
                unselected_hover_color=TRACK_HOVER,
                selected_color=CARD_BG,
                selected_hover_color=CARD_BG,
                text_color=TEXT,
                corner_radius=9,
                border_width=2,
                font=_font(12),
            ),
        )

        self.quality_var = tk.StringVar(value=next(iter(downloader.VIDEO_QUALITIES)))
        self.quality_label, self.quality_menu = self._value_row(
            card,
            row=1,
            title="畫質",
            values=list(downloader.VIDEO_QUALITIES),
            variable=self.quality_var,
        )

        self.folder_var = tk.StringVar(value=str(_default_output_dir()))
        self._entry_row(
            card, row=2, title="輸出資料夾", variable=self.folder_var, command=self._pick_folder
        )

        self.cookie_var = tk.StringVar(value=next(iter(COOKIE_LABELS)))
        self._choice_row(
            card,
            row=4,
            title="登入 Cookie",
            factory=lambda parent: ctk.CTkSegmentedButton(
                parent,
                values=list(COOKIE_LABELS),
                variable=self.cookie_var,
                command=lambda _value: self._on_cookie_change(),
                fg_color=TRACK_BG,
                unselected_color=TRACK_BG,
                unselected_hover_color=TRACK_HOVER,
                selected_color=CARD_BG,
                selected_hover_color=CARD_BG,
                text_color=TEXT,
                corner_radius=9,
                border_width=2,
                font=_font(12),
            ),
        )

        self.browser_var = tk.StringVar(value=next(iter(BROWSER_LABELS)))
        _, self.browser_menu = self._value_row(
            card,
            row=5,
            title="讀取瀏覽器",
            values=list(BROWSER_LABELS),
            variable=self.browser_var,
            toggle=True,
        )

        default_cookie = downloader.find_cookie_file()
        self.cookie_file_var = tk.StringVar(value=str(default_cookie) if default_cookie else "")
        self._entry_row(
            card,
            row=6,
            title="cookies.txt 路徑",
            variable=self.cookie_file_var,
            command=self._pick_cookie_file,
            toggle=True,
        )

        self.playlist_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            card,
            text="若網址為播放清單，下載整份清單",
            variable=self.playlist_var,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=TEXT,
            font=_font(12),
            border_color=BORDER,
            checkmark_color="#FFFFFF",
            corner_radius=6,
        ).grid(row=8, column=0, sticky="w", padx=16, pady=(4, 14))

    def _choice_row(self, card, *, row: int, title: str, factory):
        frame = ctk.CTkFrame(card, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=6)
        frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=title, font=_font(13), text_color=TEXT, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        control = factory(frame)
        control.grid(row=0, column=1, sticky="e")
        return control

    def _value_row(self, card, *, row: int, title: str, values, variable, toggle: bool = False):
        """標籤 + 下拉選單的列；``toggle`` 為真時保留控制項供日後顯示/隱藏。"""
        frame = ctk.CTkFrame(card, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=6)
        frame.columnconfigure(0, weight=1)
        label = ctk.CTkLabel(frame, text=title, font=_font(13), text_color=TEXT, anchor="w")
        label.grid(row=0, column=0, sticky="w")
        menu = ctk.CTkOptionMenu(
            frame,
            values=values,
            variable=variable,
            fg_color=FIELD_BG,
            button_color=FIELD_BG,
            button_hover_color=FIELD_HOVER,
            text_color=TEXT,
            dropdown_fg_color=CARD_BG,
            dropdown_text_color=TEXT,
            dropdown_hover_color=FIELD_BG,
            corner_radius=9,
            width=140,
            font=_font(12),
            dropdown_font=_font(12),
        )
        menu.grid(row=0, column=1, sticky="e")
        if toggle:
            self._toggles["rows"][row] = frame
        return label, menu

    def _entry_row(self, card, *, row: int, title: str, variable, command, toggle: bool = False):
        frame = ctk.CTkFrame(card, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=6)
        frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=title, font=_font(13), text_color=TEXT, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkButton(
            frame,
            text="瀏覽",
            command=command,
            fg_color=FIELD_BG,
            hover_color=FIELD_HOVER,
            text_color=TEXT,
            corner_radius=9,
            width=72,
            height=30,
            font=_font(12),
        ).grid(row=0, column=1, sticky="e")
        entry = ctk.CTkEntry(
            card,
            textvariable=variable,
            fg_color=FIELD_BG,
            border_width=0,
            text_color=TEXT,
            corner_radius=9,
            height=32,
            font=_font(12),
        )
        entry.grid(row=row + 1, column=0, sticky="ew", padx=16, pady=(0, 12))
        if toggle:
            self._toggles.setdefault("rows", {})[row] = (frame, entry)
        return frame, entry

    def _build_progress_card(self) -> None:
        card = self._card(3)
        self.file_var = tk.StringVar(value="尚未開始")
        ctk.CTkLabel(
            card, textvariable=self.file_var, font=_font(12), text_color=TEXT, anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        self.progress = ctk.CTkProgressBar(
            card, height=8, corner_radius=4, progress_color=ACCENT, fg_color=FIELD_BG
        )
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", padx=16)
        self.detail_var = tk.StringVar(value="")
        ctk.CTkLabel(
            card, textvariable=self.detail_var, font=_font(11), text_color=SUBTEXT, anchor="w"
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 14))

    def _build_log_card(self) -> None:
        card = self._card(4, sticky="nsew")
        card.rowconfigure(1, weight=1)
        ctk.CTkLabel(
            card, text="紀錄", font=_font(13, "bold"), text_color=TEXT, anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        self.log_box = ctk.CTkTextbox(
            card,
            corner_radius=10,
            border_width=0,
            fg_color=FIELD_BG,
            text_color=TEXT,
            font=_font(12),
            wrap="word",
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.log_box.configure(state="disabled")

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=5, column=0, sticky="ew", padx=24, pady=(14, 18))
        footer.columnconfigure(0, weight=1)

        self._secondary_button(
            footer, "開啟資料夾", self._open_folder, width=120, height=42
        ).grid(row=0, column=0, sticky="w")

        self.cancel_button = ctk.CTkButton(
            footer,
            text="取消",
            command=self._cancel,
            fg_color=FIELD_BG,
            hover_color=FIELD_HOVER,
            text_color=TEXT,
            corner_radius=12,
            width=110,
            height=42,
            font=_font(14),
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=1, padx=(0, 10))

        self.start_button = ctk.CTkButton(
            footer,
            text="開始下載",
            command=self._start,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            corner_radius=12,
            width=160,
            height=42,
            font=_font(15, "bold"),
        )
        self.start_button.grid(row=0, column=2)

    def _secondary_button(
        self, parent, text: str, command, *, width: int = 110, height: int = 32
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=FIELD_BG,
            hover_color=FIELD_HOVER,
            text_color=TEXT,
            corner_radius=9,
            width=width,
            height=height,
            font=_font(12),
        )

    # --- 互動 ---------------------------------------------------------------

    def _on_mode_change(self) -> None:
        audio = MODE_LABELS[self.mode_var.get()] == downloader.MODE_AUDIO
        values = list(downloader.AUDIO_QUALITIES if audio else downloader.VIDEO_QUALITIES)
        self.quality_label.configure(text="音質" if audio else "畫質")
        self.quality_menu.configure(values=values)
        self.quality_var.set(values[0])

    def _on_cookie_change(self) -> None:
        source = COOKIE_LABELS[self.cookie_var.get()]
        rows = self._toggles.get("rows", {})
        self._show_toggle(rows.get(5), source == "browser")
        self._show_toggle(rows.get(6), source == "file")

    def _show_toggle(self, widgets, visible: bool) -> None:
        if widgets is None:
            return
        items = widgets if isinstance(widgets, tuple) else (widgets,)
        for widget in items:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def _paste_clipboard(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            self._log("剪貼簿沒有可用文字。")
            return
        current = self.url_box.get("1.0", "end").strip()
        merged = f"{current}\n{text}" if current else text
        self.url_box.delete("1.0", "end")
        self.url_box.insert("1.0", merged.strip())

    def _clear_urls(self) -> None:
        self.url_box.delete("1.0", "end")

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="選擇輸出資料夾", initialdir=self.folder_var.get()
        )
        if folder:
            self.folder_var.set(folder)

    def _pick_cookie_file(self) -> None:
        path = filedialog.askopenfilename(
            title="選擇 cookies.txt",
            filetypes=[("Netscape cookies", "*.txt"), ("所有檔案", "*.*")],
        )
        if path:
            self.cookie_file_var.set(path)

    def _open_folder(self) -> None:
        folder = Path(self.folder_var.get())
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(folder))  # noqa: S606 - 開啟使用者選擇的資料夾
            elif sys.platform == "darwin":
                subprocess.run(["open", str(folder)], check=False)
            else:
                subprocess.run(["xdg-open", str(folder)], check=False)
        except OSError as error:
            messagebox.showerror(APP_NAME, f"無法開啟資料夾：\n{error}")

    def _log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # --- 下載流程 -----------------------------------------------------------

    def _start(self) -> None:
        urls = [line.strip() for line in self.url_box.get("1.0", "end").splitlines()]
        urls = [url for url in urls if url]
        if not urls:
            messagebox.showwarning(APP_NAME, "請先輸入至少一個網址。")
            return

        folder = Path(self.folder_var.get().strip() or str(_default_output_dir()))
        mode = MODE_LABELS[self.mode_var.get()]
        quality = self.quality_var.get()
        source = COOKIE_LABELS[self.cookie_var.get()]
        cookies_browser = BROWSER_LABELS[self.browser_var.get()] if source == "browser" else None
        cookies_file = None
        if source == "file":
            cookies_file = downloader.find_cookie_file(
                Path(self.cookie_file_var.get()) if self.cookie_file_var.get().strip() else None
            )
            if cookies_file is None:
                messagebox.showwarning(APP_NAME, "找不到指定的 cookies.txt。")
                return
        playlist = self.playlist_var.get()

        self._set_running(True)
        self.progress.set(0)
        self.detail_var.set("")
        self.file_var.set("準備中…")
        self._status_var.set(f"下載中 0/{len(urls)}")
        self._log(f"開始下載 {len(urls)} 筆到 {folder}")

        def work(emit):
            results = []
            for index, url in enumerate(urls, start=1):
                if self._is_cancelled():
                    raise downloader.CancelledError("已取消下載")
                emit(Message(f"[{index}/{len(urls)}] {url}"))

                def report(inner, index=index):
                    emit(Progress(index=index, total=len(urls), inner=inner))

                result = downloader.download(
                    url,
                    output_dir=folder,
                    mode=mode,
                    quality=quality,
                    use_playlist=playlist,
                    cookies_file=cookies_file,
                    cookies_browser=cookies_browser,
                    progress=report,
                    should_cancel=self._is_cancelled,
                )
                results.append(result)
                emit(Message(f"完成：{result.path.name}"))
            return results

        self._job = BackgroundJob(work)
        self._job.start()
        self.after(POLL_MS, self._poll)

    def _is_cancelled(self) -> bool:
        return self._job is not None and self._job.cancelled

    def _cancel(self) -> None:
        if self._job is not None:
            self._job.cancel()
            self._status_var.set("取消中…")

    def _set_running(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")

    def _poll(self) -> None:
        if self._job is None:
            return
        for event in self._job.drain():
            if isinstance(event, Progress):
                inner = event.inner
                fraction = (event.index - 1 + inner.percent / 100) / event.total
                self.progress.set(min(1.0, max(0.0, fraction)))
                self.file_var.set(inner.filename or "…")
                detail = f"{inner.percent:5.1f}%"
                if inner.speed:
                    detail += f"　{inner.speed}"
                if inner.eta:
                    detail += f"　剩餘 {inner.eta}"
                self.detail_var.set(f"{inner.stage}　{detail}")
                self._status_var.set(f"下載中 {event.index}/{event.total}")
            elif isinstance(event, Message):
                self._log(event.text)
            elif isinstance(event, Succeeded):
                self._finish_ok(event.result)
                return
            elif isinstance(event, Failed):
                self._finish_error(event.message)
                return
        self.after(POLL_MS, self._poll)

    def _finish_ok(self, results) -> None:
        self._set_running(False)
        self._job = None
        self.progress.set(1)
        self.detail_var.set("")
        count = len(results)
        self.file_var.set(f"完成 {count} 筆")
        self._status_var.set(f"完成：{count} 筆")
        for result in results:
            self._log(f"✔ {result.title}")
        messagebox.showinfo(APP_NAME, f"已下載 {count} 筆檔案：\n{self.folder_var.get()}")

    def _finish_error(self, message: str) -> None:
        self._set_running(False)
        self._job = None
        self._status_var.set("下載失敗")
        self.file_var.set("失敗")
        self.detail_var.set("")
        self._log(f"錯誤：{message}")
        messagebox.showerror(APP_NAME, message)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
