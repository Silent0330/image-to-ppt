"""ImageToPPT 桌面介面（customtkinter，亮色 Apple 風格）。

架構：``ConverterTab`` 提供共用的檔案清單、選項與進度流程；各頁籤以
宣告式 ``Choice`` 描述設定，並實作 ``_prepare_output``／``_convert`` 兩個策略方法。
"""

from __future__ import annotations

import io
import tkinter as tk
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

from . import exporters, imaging
from .layout import (
    MODE_FIT,
    MODE_HEIGHT_FIRST,
    MODE_LABELS,
    MODE_WIDTH_FIRST,
    MODES,
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
    compute_layout,
)
from .worker import BackgroundJob, Failed, Progress, Succeeded

APP_NAME = "ImageToPPT"
POLL_MS = 100

# --- 亮色色票（接近 macOS 淺色模式）---------------------------------------
FONT = "Segoe UI"
FONT_SCALE = 1.0  # 全域字級縮放；customtkinter 會再依螢幕 DPI 自動放大
PAGE_BG = "#F2F2F7"  # 視窗底色
CARD_BG = "#FFFFFF"  # 卡片
TEXT = "#1D1D1F"  # 主要文字
SUBTEXT = "#8A8A8E"  # 次要文字
ACCENT = "#0071E3"  # Apple 藍
ACCENT_HOVER = "#0077ED"
FIELD_BG = "#F2F2F7"  # 次要按鈕／欄位
FIELD_HOVER = "#E8E8ED"
TRACK_BG = "#E9E9EE"  # 分段控制軌道
TRACK_HOVER = "#DEDEE3"
BORDER = "#E5E5EA"


def _font(size: int, weight: str = "normal") -> ctk.CTkFont:
    """建立會隨螢幕 DPI 自動縮放的字型（供 customtkinter 元件使用）。"""
    return ctk.CTkFont(family=FONT, size=round(size * FONT_SCALE), weight=weight)


def _tk_font(widget: tk.Misc, size: int, weight: str = "normal") -> tuple[str, int, str]:
    """供原生 tk 元件（Listbox／Canvas）使用的字型；以像素為單位配合 DPI 縮放。"""
    scaling = ctk.ScalingTracker.get_widget_scaling(widget)
    return (FONT, -round(size * FONT_SCALE * scaling), weight)


BACKGROUND_OPTIONS = {
    "白色": "FFFFFF",
    "黑色": "000000",
    "淺灰": "F2F2F2",
    "深藍": "1F3864",
    "米白": "FDF6E3",
}
DPI_OPTIONS = (100, 150, 200, 300, 600)
MODE_SHORT_LABELS = {
    MODE_HEIGHT_FIRST: "高度優先",
    MODE_FIT: "完整顯示",
    MODE_WIDTH_FIRST: "寬度優先",
}


@dataclass(frozen=True)
class Choice:
    """一個設定欄位：標籤與實際值的對應，以及呈現方式。"""

    key: str
    title: str
    options: tuple[tuple[str, str], ...]
    kind: str = "combo"  # "combo" | "segmented"
    hint: str = ""
    hints: tuple[tuple[str, str], ...] = ()
    default: str | None = None

    @property
    def initial(self) -> str:
        return self.default if self.default is not None else self.options[0][0]


MODE_CHOICE = Choice(
    key="mode",
    title="圖片排版方式",
    options=tuple((MODE_SHORT_LABELS[mode], mode) for mode in MODES),
    kind="segmented",
    hints=tuple((MODE_SHORT_LABELS[mode], MODE_LABELS[mode]) for mode in MODES),
)
BACKGROUND_CHOICE = Choice(
    key="background",
    title="背景顏色",
    options=tuple(BACKGROUND_OPTIONS.items()),
)
DPI_CHOICE = Choice(
    key="dpi",
    title="PDF 解析度（DPI）",
    options=tuple((str(dpi), str(dpi)) for dpi in DPI_OPTIONS),
    hint="數值越高越清晰，檔案也越大（預設 150）",
    default=str(imaging.DEFAULT_PDF_DPI),
)
FORMAT_CHOICE = Choice(
    key="format",
    title="輸出格式",
    options=tuple((name, name) for name in exporters.OUTPUT_IMAGE_FORMATS),
)


def _contiguous_runs(indices: list[int]) -> list[list[int]]:
    """把已排序的索引群組成連續區段（例如 [1,3,4] → [[1,1],[3,4]]）。"""
    runs: list[list[int]] = []
    for index in indices:
        if runs and index == runs[-1][1] + 1:
            runs[-1][1] = index
        else:
            runs.append([index, index])
    return runs


def _file_signature(path: Path) -> tuple[int, int] | None:
    """檔案的 (mtime, 大小) 指紋，用來判斷預覽快取是否過期。"""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _extract_suffixes(
    filetypes: tuple[tuple[str, str], ...],
) -> set[str] | None:
    """從 filetypes 取出可接受的副檔名集合；``None`` 代表不限。

    ``*.*``（檔案對話框的「所有檔案」）不列入拖放過濾，避免拖入明顯不符的檔。
    """
    suffixes: set[str] = set()
    for _name, pattern in filetypes:
        for token in pattern.split():
            if token.startswith("*.") and token != "*.*":
                suffixes.add(token[1:].lower())
    return suffixes or None


class ConverterTab(ctk.CTkFrame, TkinterDnD.DnDWrapper):
    title = ""
    filetypes: tuple[tuple[str, str], ...] = ()
    unit = "投影片"
    size_note = f"投影片尺寸：{SLIDE_WIDTH} × {SLIDE_HEIGHT}（16:9，固定）"
    choices: tuple[Choice, ...] = (MODE_CHOICE, BACKGROUND_CHOICE)
    show_preview = True
    expand_pages = False
    single_file = False
    add_label = "加入檔案"

    def __init__(self, master: tk.Widget, status) -> None:
        super().__init__(master, fg_color="transparent")
        self._status = status
        self._refs: list[imaging.SlideRef] = []
        self._preview_cache: (
            tuple[imaging.SlideRef, tuple[int, int] | None, imaging.SlideImage | None]
            | None
        ) = None
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._job: BackgroundJob | None = None
        self._drag_press: int | None = None
        self._dragging: list[int] | None = None

        self._choice_map = {
            choice.key: dict(choice.options) for choice in self.choices
        }
        self._vars = {
            choice.key: tk.StringVar(value=choice.initial)
            for choice in self.choices
        }

        self._build()
        for key in ("mode", "background"):
            if key in self._vars:
                self._vars[key].trace_add("write", lambda *_: self._update_preview())
        self._register_drop_target()

    def _register_drop_target(self) -> None:
        """註冊檔案拖放目標；若 tkdnd 未載入則靜默略過。"""
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except tk.TclError:
            pass

    # --- 版面 ---------------------------------------------------------------

    def _build(self) -> None:
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        if self.size_note:
            ctk.CTkLabel(
                self,
                text=self.size_note,
                font=_font(12),
                text_color=SUBTEXT,
                anchor="w",
            ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 2))

        self._build_file_list()
        side = ctk.CTkFrame(self, fg_color="transparent")
        side.grid(row=1, column=1, sticky="nsew", padx=(14, 0), pady=(10, 0))

        settings = ctk.CTkFrame(
            side, fg_color=CARD_BG, corner_radius=16, border_width=1, border_color=BORDER
        )
        settings.pack(fill="x")
        for index, choice in enumerate(self.choices):
            self._build_choice(settings, choice, first=index == 0)

        if self.show_preview:
            self._build_preview(side)

        self._build_footer()

    def _build_file_list(self) -> None:
        card = ctk.CTkFrame(
            self, fg_color=CARD_BG, corner_radius=16, border_width=1, border_color=BORDER
        )
        card.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text=self.title,
            font=_font(13, "bold"),
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 8))

        list_area = ctk.CTkFrame(card, fg_color="transparent")
        list_area.grid(row=1, column=0, sticky="nsew", padx=(16, 6), pady=(0, 16))
        list_area.columnconfigure(0, weight=1)
        list_area.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_area,
            selectmode=tk.EXTENDED,
            exportselection=False,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            bg=CARD_BG,
            fg=TEXT,
            selectbackground=ACCENT,
            selectforeground="#FFFFFF",
            font=_tk_font(self, 13),
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", lambda *_: self._update_preview())
        self.listbox.bind("<ButtonPress-1>", self._on_drag_start)
        self.listbox.bind("<B1-Motion>", self._on_drag_motion)
        self.listbox.bind("<ButtonRelease-1>", self._on_drag_release)

        scrollbar = ctk.CTkScrollbar(
            list_area,
            command=self.listbox.yview,
            fg_color="transparent",
            button_color="#C7C7CC",
            button_hover_color="#AEAEB2",
            width=10,
        )
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.listbox.configure(yscrollcommand=scrollbar.set)

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=1, column=1, sticky="n", padx=(0, 16), pady=(0, 16))
        actions = (
            (self.add_label, self._add_files),
            ("移除選取", self._remove_selected),
            ("上移", lambda: self._move(-1)),
            ("下移", lambda: self._move(1)),
            ("反轉順序", self._reverse),
        )
        for index, (label, command) in enumerate(actions):
            self._secondary_button(buttons, label, command).pack(
                pady=(0 if index == 0 else 6)
            )

        ctk.CTkLabel(
            card,
            text="提示：可拖曳項目排序，或從檔案總管拖入檔案新增",
            font=_font(11),
            text_color=SUBTEXT,
            anchor="w",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))

    def _secondary_button(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=FIELD_BG,
            hover_color=FIELD_HOVER,
            text_color=TEXT,
            corner_radius=9,
            width=96,
            height=32,
            font=_font(12),
        )

    def _build_choice(self, parent, choice: Choice, *, first: bool) -> None:
        if not first:
            ctk.CTkFrame(parent, height=1, fg_color=BORDER).pack(fill="x", padx=16)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=10)
        row.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            row,
            text=choice.title,
            font=_font(13),
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        variable = self._vars[choice.key]
        values = [label for label, _value in choice.options]

        if choice.kind == "segmented":
            control = ctk.CTkSegmentedButton(
                row,
                values=values,
                variable=variable,
                fg_color=TRACK_BG,
                unselected_color=TRACK_BG,
                unselected_hover_color=TRACK_HOVER,
                selected_color=CARD_BG,
                selected_hover_color=CARD_BG,
                text_color=TEXT,
                corner_radius=9,
                border_width=2,
                font=_font(12),
            )
        else:
            control = ctk.CTkOptionMenu(
                row,
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
                width=120,
                font=_font(12),
                dropdown_font=_font(12),
            )
        control.grid(row=0, column=1, sticky="e")

        hints = dict(choice.hints)
        if hints:
            hint = ctk.CTkLabel(
                row,
                text="",
                font=_font(11),
                text_color=SUBTEXT,
                anchor="w",
                justify="left",
                wraplength=560,
            )
            hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

            def _sync(*_args: object) -> None:
                hint.configure(text=hints.get(variable.get(), ""))

            variable.trace_add("write", _sync)
            _sync()
        elif choice.hint:
            ctk.CTkLabel(
                row,
                text=choice.hint,
                font=_font(11),
                text_color=SUBTEXT,
                anchor="w",
                justify="left",
                wraplength=560,
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _build_preview(self, parent) -> None:
        card = ctk.CTkFrame(
            parent, fg_color=CARD_BG, corner_radius=16, border_width=1, border_color=BORDER
        )
        card.pack(fill="both", expand=True, pady=(12, 0))
        ctk.CTkLabel(
            card, text="預覽", font=_font(13, "bold"), text_color=TEXT, anchor="w"
        ).pack(fill="x", padx=16, pady=(14, 8))
        # Canvas 不指定固定尺寸：由容器決定大小，並在尺寸變化時重新繪製。
        self.canvas = tk.Canvas(
            card,
            bg=CARD_BG,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.canvas.bind("<Configure>", lambda _event: self._update_preview())

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(
            footer, height=6, corner_radius=3, progress_color=ACCENT, fg_color=FIELD_BG
        )
        self.progress.set(0)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 14))
        self.start_button = ctk.CTkButton(
            footer,
            text="開始轉換",
            command=self._start,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            corner_radius=12,
            width=150,
            height=42,
            font=_font(15, "bold"),
        )
        self.start_button.grid(row=0, column=1)

    # --- 檔案清單 -----------------------------------------------------------

    def _reload_list(self, selection: list[int] | None = None) -> None:
        """重建清單；同名來源加上上層資料夾以利區分，並保留選取。"""
        if selection is None:
            selection = list(self.listbox.curselection())
        self.listbox.delete(0, tk.END)
        labels = [ref.label for ref in self._refs]
        duplicates = Counter(labels)
        for ref, label in zip(self._refs, labels):
            if duplicates[label] > 1:
                label = f"{ref.path.parent.name}/{label}"
            self.listbox.insert(tk.END, label)
        self.listbox.selection_clear(0, tk.END)
        for index in selection:
            if index < len(self._refs):
                self.listbox.selection_set(index)
        self._update_preview()

    def _refs_for(self, path: Path) -> list[imaging.SlideRef]:
        return imaging.expand_refs([path]) if self.expand_pages else [imaging.SlideRef(path)]

    def _load_single(self, path: Path) -> bool:
        """單檔頁籤：載入一份來源並取代現有清單。"""
        try:
            new_refs = self._refs_for(path)
        except Exception as error:  # noqa: BLE001 - 讀取失敗提示後維持原狀
            messagebox.showwarning(APP_NAME, f"無法讀取 {path.name}：\n{error}")
            return False
        self._refs = new_refs
        self._preview_cache = None
        self._reload_list([0])
        return True

    def _pick_single_file(self) -> None:
        """單檔頁籤：只選一份來源，選到新檔就整個取代。"""
        raw = filedialog.askopenfilename(filetypes=self.filetypes)
        if isinstance(raw, (tuple, list)):
            raw = raw[0] if raw else ""
        if not raw:
            return
        self._load_single(Path(raw))

    def _add_paths(self, paths: list[Path]) -> int:
        """附加檔案（自動去重）；回傳實際新增的檔案數。"""
        known = {ref.path for ref in self._refs}
        added = 0
        for path in paths:
            if path in known:
                continue
            try:
                self._refs.extend(self._refs_for(path))
            except Exception as error:  # noqa: BLE001 - 讀取失敗提示後跳過
                messagebox.showwarning(APP_NAME, f"無法讀取 {path.name}：\n{error}")
                continue
            known.add(path)
            added += 1
        if added:
            self._preview_cache = None
            self._reload_list()
        return added

    def _add_files(self) -> None:
        if self.single_file:
            self._pick_single_file()
            return
        paths = [Path(raw) for raw in filedialog.askopenfilenames(filetypes=self.filetypes)]
        self._add_paths(paths)

    def _dropped_paths(self, data: str) -> list[Path]:
        """解析拖放資料中的檔案路徑，並依此頁籤的型別過濾。"""
        try:
            items = self.tk.splitlist(data)
        except tk.TclError:
            items = (data,)
        suffixes = _extract_suffixes(self.filetypes)
        paths: list[Path] = []
        for item in items:
            path = Path(item)
            if path.is_dir():
                continue
            if suffixes is not None and path.suffix.lower() not in suffixes:
                continue
            paths.append(path)
        return paths

    def _on_drop(self, event: tk.Event) -> str:
        """處理 OS 檔案拖放：單檔頁籤取代、多檔頁籤附加。"""
        paths = self._dropped_paths(str(getattr(event, "data", "")))
        if not paths:
            messagebox.showwarning(APP_NAME, "拖入的檔案類型不符合此頁籤。")
            return "refuse_drop"
        if self.single_file:
            self._load_single(paths[0])
        else:
            self._add_paths(paths)
        return "copy"

    def _remove_selected(self) -> None:
        for index in sorted(self.listbox.curselection(), reverse=True):
            del self._refs[index]
        self._preview_cache = None
        self._reload_list()

    def _move(self, direction: int) -> None:
        selection = sorted(self.listbox.curselection())
        if not selection:
            return
        runs = _contiguous_runs(selection)
        last = len(self._refs) - 1
        new_selection: list[int] = []

        if direction < 0:
            for start, end in runs:
                if start == 0:
                    new_selection.extend(range(start, end + 1))
                    continue
                for index in range(start - 1, end):
                    self._refs[index], self._refs[index + 1] = (
                        self._refs[index + 1],
                        self._refs[index],
                    )
                new_selection.extend(range(start - 1, end))
        else:
            for start, end in reversed(runs):
                if end == last:
                    new_selection.extend(range(start, end + 1))
                    continue
                for index in range(end + 1, start, -1):
                    self._refs[index], self._refs[index - 1] = (
                        self._refs[index - 1],
                        self._refs[index],
                    )
                new_selection.extend(range(start + 1, end + 2))

        self._reload_list(sorted(new_selection))

    def _reverse(self) -> None:
        """反轉清單順序（選取範圍亦一併對應）。"""
        if not self._refs:
            return
        count = len(self._refs)
        selection = sorted(count - 1 - index for index in self.listbox.curselection())
        self._refs.reverse()
        self._reload_list(selection)

    # --- 拖曳排序 -----------------------------------------------------------

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_press = self.listbox.nearest(event.y)
        self._dragging = None

    def _on_drag_motion(self, event: tk.Event) -> str:
        """把選取區塊拖到游標所在的項目位置（支援整段搬移）。"""
        if self._drag_press is None:
            return "break"
        if self._dragging is None:
            self._dragging = sorted(self.listbox.curselection()) or [self._drag_press]
        hover = self.listbox.nearest(event.y)
        if not 0 <= hover < len(self._refs) or hover in self._dragging:
            return "break"

        selected = set(self._dragging)
        block = [self._refs[index] for index in self._dragging]
        remaining = [
            ref for index, ref in enumerate(self._refs) if index not in selected
        ]
        shift = sum(1 for index in self._dragging if index < hover)
        insert_at = hover - shift + (1 if hover > self._dragging[-1] else 0)
        self._refs = remaining[:insert_at] + block + remaining[insert_at:]
        new_selection = list(range(insert_at, insert_at + len(block)))
        self._dragging = new_selection
        self._reload_list(new_selection)
        return "break"

    def _on_drag_release(self, _event: tk.Event) -> None:
        self._drag_press = None
        self._dragging = None

    # --- 預覽 ---------------------------------------------------------------

    def _selected_preview(self) -> imaging.SlideImage | None:
        selection = self.listbox.curselection()
        if not selection:
            return None
        ref = self._refs[selection[0]]
        signature = _file_signature(ref.path)
        if self._preview_cache is not None:
            cached_ref, cached_signature, image = self._preview_cache
            if cached_ref == ref and cached_signature == signature:
                return image
        image = imaging.preview_ref(ref)
        self._preview_cache = (ref, signature, image)
        return image

    def _resolved(self, key: str, default: str) -> str:
        if key not in self._vars:
            return default
        return self._choice_map[key][self._vars[key].get()]

    def _update_preview(self) -> None:
        if not self.show_preview:
            return
        self.canvas.delete("all")
        background = self._resolved("background", exporters.DEFAULT_BACKGROUND)
        self.canvas.configure(bg=CARD_BG)
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        # 投影片為 16:9，置中放置，多餘空間留白
        slide_scale = min(cw / SLIDE_WIDTH, ch / SLIDE_HEIGHT)
        sw, sh = SLIDE_WIDTH * slide_scale, SLIDE_HEIGHT * slide_scale
        ox, oy = (cw - sw) / 2, (ch - sh) / 2
        self.canvas.create_rectangle(
            ox, oy, ox + sw, oy + sh, fill=f"#{background}", outline="", width=0
        )

        source = self._selected_preview()
        if source is None:
            self.canvas.create_text(
                ox + sw / 2,
                oy + sh / 2,
                text="尚未選擇檔案",
                fill=SUBTEXT,
                font=_tk_font(self.canvas, 13),
            )
            return

        mode = self._resolved("mode", MODE_FIT)
        rect = compute_layout(source.width, source.height, mode)
        x = ox + rect.x * slide_scale
        y = oy + rect.y * slide_scale
        w = rect.w * slide_scale
        h = rect.h * slide_scale

        try:
            with Image.open(io.BytesIO(source.data)) as image:
                thumb = image.convert("RGB").resize((max(1, round(w)), max(1, round(h))))
            self._preview_photo = ImageTk.PhotoImage(thumb)
            self.canvas.create_image(x, y, anchor="nw", image=self._preview_photo)
        except Exception:  # noqa: BLE001 - 無法顯示時改用外框
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=ACCENT)
        self.canvas.create_rectangle(ox, oy, ox + sw, oy + sh, outline=BORDER)

    # --- 轉換流程 -----------------------------------------------------------

    def _settings(self) -> dict[str, str]:
        return {
            key: self._choice_map[key][variable.get()]
            for key, variable in self._vars.items()
        }

    def _prepare_output(self) -> Path | None:
        output = filedialog.asksaveasfilename(
            defaultextension=".pptx",
            filetypes=[("PowerPoint", "*.pptx")],
            initialfile="output.pptx",
        )
        return Path(output) if output else None

    def _convert(
        self, refs: list[imaging.SlideRef], output: Path, settings: dict[str, str], report
    ) -> tuple[Path, int]:
        dpi = int(settings.get("dpi", imaging.DEFAULT_PDF_DPI))
        images = imaging.render_refs(refs, dpi=dpi)
        if not images:
            raise ValueError("沒有可轉換的內容。")
        exporters.build_presentation(
            images,
            output,
            mode=settings["mode"],
            background=settings.get("background", exporters.DEFAULT_BACKGROUND),
            progress=report,
        )
        return output, len(images)

    def _start(self) -> None:
        if not self._refs:
            messagebox.showwarning(APP_NAME, "請先加入檔案。")
            return
        output = self._prepare_output()
        if output is None:
            return

        refs = list(self._refs)
        settings = self._settings()
        self.start_button.configure(state="disabled")
        self.progress.set(0)
        self._status("讀取檔案中…")

        self._job = BackgroundJob(
            lambda report: self._convert(refs, output, settings, report)
        )
        self._job.start()
        self.after(POLL_MS, self._poll)

    def _poll(self) -> None:
        for event in self._job.drain():
            if isinstance(event, Progress):
                self.progress.set(event.done / event.total if event.total else 0)
                self._status(f"轉換中… {event.done}/{event.total}")
            elif isinstance(event, Succeeded):
                output, count = event.result
                self.progress.set(1)
                self._status(f"完成：{output.name}（共 {count} 張{self.unit}）")
                self.start_button.configure(state="normal")
                messagebox.showinfo(
                    APP_NAME, f"已輸出 {count} 張{self.unit}：\n{output}"
                )
                return
            elif isinstance(event, Failed):
                self._status("轉換失敗")
                self.start_button.configure(state="normal")
                messagebox.showerror(APP_NAME, event.message)
                return
        self.after(POLL_MS, self._poll)


class PdfTab(ConverterTab):
    title = "PDF 檔案（每頁一張投影片）"
    filetypes = (("PDF", "*.pdf"),)
    choices = (MODE_CHOICE, BACKGROUND_CHOICE, DPI_CHOICE)
    expand_pages = True
    single_file = True
    add_label = "選擇檔案"


class ImageTab(ConverterTab):
    title = "圖片檔案（每張一張投影片）"
    filetypes = (
        ("圖片", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp"),
        ("所有檔案", "*.*"),
    )
    expand_pages = True


class PdfToImageTab(ConverterTab):
    title = "PDF 檔案（每頁輸出一張圖片）"
    filetypes = (("PDF", "*.pdf"),)
    unit = "圖片"
    size_note = "每頁 PDF 輸出成圖片，依頁碼命名"
    choices = (DPI_CHOICE, FORMAT_CHOICE)
    expand_pages = True
    single_file = True
    add_label = "選擇檔案"

    def _prepare_output(self) -> Path | None:
        folder = filedialog.askdirectory(title="選擇輸出資料夾")
        return Path(folder) if folder else None

    def _convert(
        self, refs: list[imaging.SlideRef], output: Path, settings: dict[str, str], report
    ) -> tuple[Path, int]:
        files = exporters.export_pdf_images(
            refs[0].path,
            output,
            dpi=int(settings["dpi"]),
            image_format=settings["format"],
            progress=report,
        )
        return output, len(files)


class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self) -> None:
        ctk.set_appearance_mode("light")
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.title(APP_NAME)
        self.configure(fg_color=PAGE_BG)

        # 依螢幕解析度自適應視窗大小，並置中
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = max(1000, min(1400, screen_w - 80))
        height = max(660, min(900, screen_h - 80))
        x = (screen_w - width) // 2
        y = max(0, (screen_h - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(1000, 660)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 4))
        ctk.CTkLabel(
            header, text=APP_NAME, font=_font(24, "bold"), text_color=TEXT
        ).pack(side="left")
        self._status_var = tk.StringVar(value="待機中")
        ctk.CTkLabel(
            header, textvariable=self._status_var, font=_font(13), text_color=SUBTEXT
        ).pack(side="right")

        self._tabview = ctk.CTkTabview(
            self,
            fg_color=PAGE_BG,
            corner_radius=14,
            border_width=0,
            segmented_button_fg_color=TRACK_BG,
            segmented_button_selected_color=CARD_BG,
            segmented_button_selected_hover_color=CARD_BG,
            segmented_button_unselected_color=TRACK_BG,
            segmented_button_unselected_hover_color=TRACK_HOVER,
            segmented_button_font=_font(13, "bold"),
            text_color=TEXT,
        )
        self._tabview.pack(fill="both", expand=True, padx=24, pady=(6, 18))

        tabs = (
            ("PDF 轉 PPT", PdfTab),
            ("圖片轉 PPT", ImageTab),
            ("PDF 轉圖片", PdfToImageTab),
        )
        for label, tab_class in tabs:
            frame = self._tabview.add(label)
            tab_class(frame, self._status_var.set).pack(fill="both", expand=True)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
