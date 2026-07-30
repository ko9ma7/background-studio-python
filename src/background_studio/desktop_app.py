from __future__ import annotations

import multiprocessing
import os
import queue
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from tkinter import (
    BooleanVar,
    Canvas,
    DoubleVar,
    IntVar,
    StringVar,
    Tk,
    colorchooser,
    filedialog,
    messagebox,
    ttk,
)
from uuid import uuid4

from PIL import Image, ImageDraw, ImageTk

from . import __version__
from .editing import (
    EditOptions,
    MaskStroke,
    apply_mask_strokes,
    compose,
    prepare_foreground,
    to_image_bytes,
    to_svg_outline,
)
from .engine import SUPPORTED_MODELS, RembgEngine
from .ffmpeg_manager import ensure as ensure_ffmpeg
from .ffmpeg_manager import is_available as ffmpeg_available
from .models import BackgroundMode, CanvasAspect, ForegroundFilter, RenderMode
from .video import VideoOptions, VideoProcessor

IMAGE_TYPES = (("이미지", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),)
VIDEO_TYPES = (("동영상", "*.mp4 *.mov *.webm *.mkv *.avi *.m4v"),)
FILTERS = {
    "원본": ForegroundFilter.ORIGINAL,
    "밝게": ForegroundFilter.BRIGHT,
    "선명하게": ForegroundFilter.VIVID,
    "따뜻하게": ForegroundFilter.WARM,
    "차갑게": ForegroundFilter.COOL,
    "흑백": ForegroundFilter.GRAYSCALE,
    "코믹 하이라이트": ForegroundFilter.COMIC,
    "고대비": ForegroundFilter.HIGH_CONTRAST,
    "포스터 컬러": ForegroundFilter.POSTERIZE,
    "세피아": ForegroundFilter.SEPIA,
    "네거티브": ForegroundFilter.INVERT,
    "연필 스케치": ForegroundFilter.PENCIL,
}
RENDER_MODES = {
    "완성 합성": RenderMode.COMPOSITE,
    "흑백 마스크": RenderMode.MASK,
    "외곽선만": RenderMode.OUTLINE,
}
CANVAS_ASPECTS = {
    "원본 비율": CanvasAspect.ORIGINAL,
    "정사각형 1:1": CanvasAspect.SQUARE,
    "세로형 4:5": CanvasAspect.PORTRAIT_45,
    "가로형 16:9": CanvasAspect.LANDSCAPE_169,
}


@dataclass
class DesktopJob:
    path: Path
    is_video: bool
    id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "대기"
    progress: int = 0
    result_path: Path | None = None
    original: Image.Image | None = None
    cutout: Image.Image | None = None
    result: Image.Image | None = None
    preview_original: Image.Image | None = None
    preview_cutout: Image.Image | None = None
    mask_strokes: list[MaskStroke] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name


class Cancelled(RuntimeError):
    pass


def unique_output_path(folder: Path, source: Path, extension: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{source.stem}-background-studio"
    candidate = folder / f"{stem}.{extension}"
    index = 2
    while candidate.exists():
        candidate = folder / f"{stem}-{index}.{extension}"
        index += 1
    return candidate


def runnable_desktop_jobs(jobs: list[DesktopJob]) -> list[DesktopJob]:
    runnable = {"대기", "대기 · 편집 변경", "대기 · 마스크 보정", "오류"}
    return [job for job in jobs if job.status in runnable]


class DesktopApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title(f"Background Studio Python {__version__}")
        self.root.geometry("1440x860")
        self.root.minsize(1160, 720)
        self.root.configure(bg="#f5f3ed")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.engine = RembgEngine()
        self.jobs: list[DesktopJob] = []
        self.selected_id: str | None = None
        self.background_path: Path | None = None
        self.output_folder = Path.home() / "Pictures" / "Background Studio Python"
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.events: queue.Queue[object] = queue.Queue()
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.preview_after: str | None = None
        self.preview_zoom = 1.0
        self.preview_fit_scale = 1.0
        self.preview_offset = [0.0, 0.0]
        self.preview_tool = "hand"
        self.preview_display_size = (1, 1)
        self.preview_source: Image.Image | None = None
        self.preview_job_id: str | None = None
        self.mask_points: list[tuple[float, float]] | None = None
        self.pan_start: tuple[int, int, float, float] | None = None

        self._create_variables()
        self._configure_style()
        self._build_ui()
        self._bind_variables()
        self._refresh_actions()
        self.root.after(80, self._drain_events)

    def _create_variables(self) -> None:
        self.mode = StringVar(value=BackgroundMode.TRANSPARENT.value)
        self.background_color = StringVar(value="#f2eee5")
        self.shadow = BooleanVar(value=False)
        self.filter_name = StringVar(value="원본")
        self.render_name = StringVar(value="완성 합성")
        self.auto_center = BooleanVar(value=True)
        self.subject_scale = DoubleVar(value=1.0)
        self.subject_x = DoubleVar(value=0.0)
        self.subject_y = DoubleVar(value=0.0)
        self.rotation = DoubleVar(value=0.0)
        self.flip_horizontal = BooleanVar(value=False)
        self.flip_vertical = BooleanVar(value=False)
        self.aspect_name = StringVar(value="원본 비율")
        self.brightness = DoubleVar(value=1.0)
        self.contrast = DoubleVar(value=1.0)
        self.saturation = DoubleVar(value=1.0)
        self.temperature = DoubleVar(value=0.0)
        self.hue = DoubleVar(value=0.0)
        self.opacity = DoubleVar(value=1.0)
        self.mask_threshold = DoubleVar(value=0.0)
        self.mask_feather = DoubleVar(value=0.0)
        self.mask_expansion = IntVar(value=0)
        self.outline_width = IntVar(value=3)
        self.outline_color = StringVar(value="#111111")
        self.model_name = StringVar(value="u2netp")
        self.image_format = StringVar(value="PNG")
        self.video_format = StringVar(value="WebM")
        self.video_fps = DoubleVar(value=2.0)
        self.video_dimension = IntVar(value=720)
        self.brush_size = IntVar(value=36)
        self.zoom_text = StringVar(value="맞춤")
        self.status_text = StringVar(value="파일을 추가하면 내 PC에서 처리합니다.")
        self.progress_value = DoubleVar(value=0)
        self.ffmpeg_text = StringVar(
            value="FFmpeg 준비됨" if ffmpeg_available() else "영상 처리 시 FFmpeg 자동 준비"
        )

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Malgun Gothic", 9), foreground="#173328")
        style.configure("Card.TFrame", background="#fffefa")
        style.configure("Panel.TFrame", background="#f3f5ef")
        style.configure("Header.TLabel", background="#fffefa", font=("Malgun Gothic", 17, "bold"))
        style.configure("Muted.TLabel", background="#fffefa", foreground="#6b786f")
        style.configure("Section.TLabel", background="#fffefa", font=("Malgun Gothic", 11, "bold"))
        style.configure(
            "Accent.TButton",
            background="#1c5a43",
            foreground="white",
            padding=(14, 9),
            font=("Malgun Gothic", 9, "bold"),
        )
        style.map("Accent.TButton", background=[("active", "#12372a"), ("disabled", "#a9bbb2")])
        style.configure("Quiet.TButton", padding=(10, 7))
        style.configure("Treeview", rowheight=28, fieldbackground="#fffefa", background="#fffefa")
        style.configure("Treeview.Heading", font=("Malgun Gothic", 9, "bold"))
        style.configure("TNotebook", background="#fffefa", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 8), font=("Malgun Gothic", 8, "bold"))
        style.map("TNotebook.Tab", foreground=[("selected", "#1c5a43")])

    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self.root, style="Card.TFrame", padding=(22, 13))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        ttk.Label(header, text="BG", style="Section.TLabel").grid(
            row=0, column=0, rowspan=2, padx=(0, 12)
        )
        ttk.Label(header, text="Background Studio Python", style="Header.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(
            header,
            text="이미지·동영상 배경 제거와 전문 편집을 한 화면에서 실행",
            style="Muted.TLabel",
        ).grid(row=1, column=1, sticky="w")
        ttk.Label(header, textvariable=self.ffmpeg_text, style="Muted.TLabel").grid(
            row=0, column=2, rowspan=2, padx=8
        )

        content = ttk.Frame(self.root, padding=12)
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        self._build_queue(content)
        self._build_preview(content)
        self._build_editor(content)

        footer = ttk.Frame(self.root, style="Card.TFrame", padding=(18, 9))
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_text, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Progressbar(footer, variable=self.progress_value, maximum=100, length=260).grid(
            row=0, column=1, padx=(12, 0)
        )

    def _build_queue(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=14, width=280)
        panel.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        panel.grid_propagate(False)
        panel.grid_rowconfigure(3, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        ttk.Label(panel, text="작업 대기열", style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        add_buttons = ttk.Frame(panel, style="Card.TFrame")
        add_buttons.grid(row=1, column=0, sticky="ew", pady=(10, 6))
        add_buttons.grid_columnconfigure((0, 1), weight=1)
        ttk.Button(add_buttons, text="이미지 추가", command=self.add_images).grid(
            row=0, column=0, sticky="ew", padx=(0, 3)
        )
        ttk.Button(add_buttons, text="동영상 추가", command=self.add_videos).grid(
            row=0, column=1, sticky="ew", padx=(3, 0)
        )

        edit_buttons = ttk.Frame(panel, style="Card.TFrame")
        edit_buttons.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        edit_buttons.grid_columnconfigure((0, 1), weight=1)
        self.remove_button = ttk.Button(
            edit_buttons, text="선택 삭제", command=self.remove_selected
        )
        self.remove_button.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.reset_button = ttk.Button(edit_buttons, text="전체 초기화", command=self.reset_all)
        self.reset_button.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        self.queue_tree = ttk.Treeview(
            panel,
            columns=("kind", "status"),
            show="tree headings",
            selectmode="browse",
            height=14,
        )
        self.queue_tree.heading("#0", text="파일")
        self.queue_tree.heading("kind", text="형식")
        self.queue_tree.heading("status", text="상태")
        self.queue_tree.column("#0", width=145, minwidth=100)
        self.queue_tree.column("kind", width=48, anchor="center")
        self.queue_tree.column("status", width=68, anchor="center")
        self.queue_tree.grid(row=3, column=0, sticky="nsew")
        self.queue_tree.bind("<<TreeviewSelect>>", self._queue_selected)

        output = ttk.LabelFrame(panel, text="자동 저장", padding=10)
        output.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        output.grid_columnconfigure(0, weight=1)
        self.output_label = ttk.Label(
            output,
            text=str(self.output_folder),
            wraplength=230,
            foreground="#6b786f",
        )
        self.output_label.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Button(
            output, text="폴더 변경", command=self.choose_output, style="Quiet.TButton"
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0), padx=(0, 3))
        ttk.Button(output, text="폴더 열기", command=self.open_output, style="Quiet.TButton").grid(
            row=1, column=1, sticky="ew", pady=(8, 0), padx=(3, 0)
        )

    def _build_preview(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=14)
        panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        head = ttk.Frame(panel, style="Card.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        head.grid_columnconfigure(0, weight=1)
        ttk.Label(head, text="미리보기", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.preview_name = ttk.Label(head, text="파일을 추가하세요.", style="Muted.TLabel")
        self.preview_name.grid(row=0, column=1, sticky="e")

        tools = ttk.Frame(panel, style="Panel.TFrame", padding=5)
        tools.grid(row=1, column=0, sticky="ew", pady=(0, 7))
        ttk.Button(
            tools, text="−", width=3, command=lambda: self._zoom_by(1 / 1.25)
        ).pack(side="left")
        ttk.Label(tools, textvariable=self.zoom_text, width=7, anchor="center").pack(side="left")
        ttk.Button(tools, text="+", width=3, command=lambda: self._zoom_by(1.25)).pack(side="left")
        ttk.Button(tools, text="맞춤", command=self._fit_preview).pack(side="left", padx=(5, 2))
        ttk.Button(tools, text="100%", command=self._actual_size).pack(side="left", padx=2)
        self.hand_button = ttk.Button(
            tools, text="손", command=lambda: self._set_preview_tool("hand")
        )
        self.hand_button.pack(side="left", padx=(10, 2))
        self.erase_button = ttk.Button(
            tools, text="지우기", command=lambda: self._set_preview_tool("erase")
        )
        self.erase_button.pack(side="left", padx=2)
        self.restore_button = ttk.Button(
            tools, text="복원", command=lambda: self._set_preview_tool("restore")
        )
        self.restore_button.pack(side="left", padx=2)
        ttk.Label(tools, text="크기").pack(side="left", padx=(10, 2))
        ttk.Scale(tools, from_=4, to=160, variable=self.brush_size, length=90).pack(side="left")
        self.undo_mask_button = ttk.Button(tools, text="마스크 실행 취소", command=self._undo_mask)
        self.undo_mask_button.pack(side="left", padx=(6, 0))

        self.preview_canvas = Canvas(
            panel,
            bg="#e8ece7",
            highlightthickness=1,
            highlightbackground="#dfe4dc",
        )
        self.preview_canvas.grid(row=2, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", lambda _event: self._schedule_preview())
        self.preview_canvas.bind("<MouseWheel>", self._preview_wheel)
        self.preview_canvas.bind("<ButtonPress-1>", self._preview_press)
        self.preview_canvas.bind("<B1-Motion>", self._preview_motion)
        self.preview_canvas.bind("<ButtonRelease-1>", self._preview_release)
        self.preview_canvas.bind("<ButtonPress-2>", self._preview_pan_press)
        self.preview_canvas.bind("<B2-Motion>", self._preview_pan_motion)
        self.preview_canvas.bind("<ButtonRelease-2>", self._preview_pan_release)
        self.preview_canvas.create_text(
            360,
            280,
            text="왼쪽에서 이미지 또는 동영상을 추가하세요.",
            fill="#6b786f",
            font=("Malgun Gothic", 12, "bold"),
            tags=("empty",),
        )
        self.preview_info = ttk.Label(
            panel,
            text="편집값은 분리된 원본 피사체에서 매번 다시 계산됩니다.",
            style="Muted.TLabel",
        )
        self.preview_info.grid(row=3, column=0, sticky="w", pady=(9, 0))

    def _build_editor(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=14, width=405)
        panel.grid(row=0, column=2, sticky="nse")
        panel.grid_propagate(False)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        ttk.Label(panel, text="편집 도구", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        notebook = ttk.Notebook(panel)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(10, 8))

        background = ttk.Frame(notebook, padding=12)
        filters = ttk.Frame(notebook, padding=12)
        position = ttk.Frame(notebook, padding=12)
        advanced = ttk.Frame(notebook, padding=12)
        output = ttk.Frame(notebook, padding=12)
        notebook.add(background, text="배경")
        notebook.add(filters, text="필터·외곽")
        notebook.add(position, text="위치·크기")
        notebook.add(advanced, text="고급")
        notebook.add(output, text="저장")
        self._background_tab(background)
        self._filter_tab(filters)
        self._position_tab(position)
        self._advanced_tab(advanced)
        self._output_tab(output)

        actions = ttk.Frame(panel, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="ew")
        actions.grid_columnconfigure((0, 1), weight=1)
        self.process_button = ttk.Button(
            actions,
            text="대기열 전체 변환",
            command=self.process_queue,
            style="Accent.TButton",
        )
        self.process_button.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.cancel_button = ttk.Button(actions, text="작업 취소", command=self.cancel)
        self.cancel_button.grid(row=1, column=0, sticky="ew", pady=(7, 0), padx=(0, 3))
        self.open_result_button = ttk.Button(
            actions, text="선택 결과 열기", command=self.open_selected_result
        )
        self.open_result_button.grid(row=1, column=1, sticky="ew", pady=(7, 0), padx=(3, 0))

    def _background_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, text="새 배경").pack(anchor="w")
        for text, value in (
            ("투명", BackgroundMode.TRANSPARENT.value),
            ("단색", BackgroundMode.COLOR.value),
            ("다른 이미지", BackgroundMode.IMAGE.value),
            ("원본 흐림", BackgroundMode.BLUR.value),
        ):
            ttk.Radiobutton(tab, text=text, value=value, variable=self.mode).pack(
                anchor="w", pady=3
            )
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(10, 3))
        ttk.Label(row, text="배경 색상").pack(side="left")
        ttk.Entry(row, textvariable=self.background_color, width=12).pack(side="left", padx=8)
        ttk.Button(row, text="색 선택", command=self.choose_color).pack(side="left")
        ttk.Button(tab, text="배경 이미지 선택", command=self.choose_background).pack(
            fill="x", pady=8
        )
        self.background_label = ttk.Label(tab, text="선택된 배경 이미지 없음", foreground="#6b786f")
        self.background_label.pack(anchor="w")
        ttk.Checkbutton(tab, text="자연스러운 그림자", variable=self.shadow).pack(
            anchor="w", pady=(12, 0)
        )

    def _filter_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, text="피사체 필터").pack(anchor="w")
        ttk.Combobox(
            tab,
            textvariable=self.filter_name,
            values=list(FILTERS),
            state="readonly",
        ).pack(fill="x", pady=(4, 10))
        ttk.Label(tab, text="출력 레이어").pack(anchor="w")
        ttk.Combobox(
            tab,
            textvariable=self.render_name,
            values=list(RENDER_MODES),
            state="readonly",
        ).pack(fill="x", pady=(4, 10))
        self._scale(tab, "외곽선 두께", self.outline_width, 1, 12, 1)
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=8)
        ttk.Label(row, text="외곽선 색상").pack(side="left")
        ttk.Entry(row, textvariable=self.outline_color, width=12).pack(side="left", padx=8)
        ttk.Button(row, text="색 선택", command=self.choose_outline_color).pack(side="left")
        ttk.Label(
            tab,
            text="마스크와 외곽선 결과는 Photoshop 선택 영역·패스 보정에 활용할 수 있습니다.",
            foreground="#6b786f",
            wraplength=340,
        ).pack(anchor="w", pady=12)

    def _position_tab(self, tab: ttk.Frame) -> None:
        ttk.Checkbutton(tab, text="피사체 자동 중앙 정렬", variable=self.auto_center).pack(
            anchor="w"
        )
        self._scale(tab, "크기", self.subject_scale, 0.3, 2.0, 0.01)
        self._scale(tab, "가로 위치", self.subject_x, -0.5, 0.5, 0.01)
        self._scale(tab, "세로 위치", self.subject_y, -0.5, 0.5, 0.01)
        self._scale(tab, "회전", self.rotation, -180, 180, 1)
        ttk.Checkbutton(tab, text="좌우 반전", variable=self.flip_horizontal).pack(anchor="w")
        ttk.Checkbutton(tab, text="상하 반전", variable=self.flip_vertical).pack(anchor="w")
        ttk.Label(tab, text="캔버스 비율").pack(anchor="w", pady=(10, 3))
        ttk.Combobox(
            tab,
            textvariable=self.aspect_name,
            values=list(CANVAS_ASPECTS),
            state="readonly",
        ).pack(fill="x")

    def _advanced_tab(self, tab: ttk.Frame) -> None:
        self._scale(tab, "밝기", self.brightness, 0.2, 2.0, 0.01)
        self._scale(tab, "대비", self.contrast, 0.2, 2.0, 0.01)
        self._scale(tab, "채도", self.saturation, 0.0, 2.0, 0.01)
        self._scale(tab, "색온도", self.temperature, -1.0, 1.0, 0.01)
        self._scale(tab, "색조", self.hue, -180, 180, 1)
        self._scale(tab, "불투명도", self.opacity, 0.0, 1.0, 0.01)
        self._scale(tab, "마스크 임계값", self.mask_threshold, 0.0, 0.95, 0.01)
        self._scale(tab, "마스크 페더", self.mask_feather, 0.0, 0.5, 0.01)
        self._scale(tab, "마스크 확장·축소", self.mask_expansion, -12, 12, 1)

    def _output_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, text="AI 모델").pack(anchor="w")
        ttk.Combobox(
            tab,
            textvariable=self.model_name,
            values=SUPPORTED_MODELS,
            state="readonly",
        ).pack(fill="x", pady=(4, 10))
        ttk.Label(tab, text="이미지 저장 형식").pack(anchor="w")
        ttk.Combobox(
            tab,
            textvariable=self.image_format,
            values=("PNG", "JPEG", "WebP", "BMP", "TIFF", "SVG"),
            state="readonly",
        ).pack(fill="x", pady=(4, 10))
        ttk.Label(tab, text="동영상 저장 형식").pack(anchor="w")
        ttk.Combobox(
            tab,
            textvariable=self.video_format,
            values=("WebM", "MP4", "MOV", "GIF"),
            state="readonly",
        ).pack(fill="x", pady=(4, 10))
        self._scale(tab, "동영상 분석 FPS", self.video_fps, 1, 12, 1)
        ttk.Label(tab, text="동영상 최대 크기").pack(anchor="w", pady=(10, 3))
        ttk.Combobox(
            tab,
            textvariable=self.video_dimension,
            values=(480, 720, 1080, 1280),
            state="readonly",
        ).pack(fill="x")
        ttk.Label(
            tab,
            text="영상 변환 시 FFmpeg 8.1.2를 앱 폴더에 자동 다운로드하고 SHA-256을 검증합니다.",
            foreground="#6b786f",
            wraplength=340,
        ).pack(anchor="w", pady=14)

    def _scale(
        self,
        parent: ttk.Frame,
        text: str,
        variable: DoubleVar | IntVar,
        start: float,
        end: float,
        resolution: float,
    ) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=5)
        ttk.Label(frame, text=text).pack(anchor="w")
        scale = ttk.Scale(frame, from_=start, to=end, variable=variable)
        scale.pack(fill="x")
        scale.bind("<ButtonRelease-1>", lambda _event: self._schedule_preview())
        if resolution >= 1:
            scale.configure(command=lambda value, var=variable: var.set(round(float(value))))

    def _bind_variables(self) -> None:
        variables = (
            self.mode,
            self.background_color,
            self.shadow,
            self.filter_name,
            self.render_name,
            self.auto_center,
            self.subject_scale,
            self.subject_x,
            self.subject_y,
            self.rotation,
            self.flip_horizontal,
            self.flip_vertical,
            self.aspect_name,
            self.brightness,
            self.contrast,
            self.saturation,
            self.temperature,
            self.hue,
            self.opacity,
            self.mask_threshold,
            self.mask_feather,
            self.mask_expansion,
            self.outline_width,
            self.outline_color,
        )
        for variable in variables:
            variable.trace_add("write", lambda *_args: self._editor_changed())

    def _editor_changed(self) -> None:
        job = self.selected_job()
        if job and job.status == "저장됨":
            job.status = "대기 · 편집 변경"
            job.result = None
            job.result_path = None
            self._refresh_queue()
        self._schedule_preview()

    def _edit_options(self) -> EditOptions:
        return EditOptions(
            mode=BackgroundMode(self.mode.get()),
            color=self.background_color.get(),
            blur_radius=18,
            shadow_blur=18 if self.shadow.get() else 0,
            shadow_opacity=80,
            shadow_offset_y=12,
            foreground_filter=FILTERS[self.filter_name.get()],
            render_mode=RENDER_MODES[self.render_name.get()],
            subject_scale=float(self.subject_scale.get()),
            subject_offset_x=float(self.subject_x.get()),
            subject_offset_y=float(self.subject_y.get()),
            auto_center=self.auto_center.get(),
            outline_width=int(self.outline_width.get()),
            outline_color=self.outline_color.get(),
            brightness=float(self.brightness.get()),
            contrast=float(self.contrast.get()),
            saturation=float(self.saturation.get()),
            temperature=float(self.temperature.get()),
            hue=float(self.hue.get()),
            foreground_opacity=float(self.opacity.get()),
            rotation=float(self.rotation.get()),
            flip_horizontal=self.flip_horizontal.get(),
            flip_vertical=self.flip_vertical.get(),
            mask_threshold=float(self.mask_threshold.get()),
            mask_feather=float(self.mask_feather.get()),
            mask_expansion=int(self.mask_expansion.get()),
            canvas_aspect=CANVAS_ASPECTS[self.aspect_name.get()],
        )

    def selected_job(self) -> DesktopJob | None:
        return next((job for job in self.jobs if job.id == self.selected_id), None)

    def add_images(self) -> None:
        self._add_files(
            filedialog.askopenfilenames(title="이미지 추가", filetypes=IMAGE_TYPES), False
        )

    def add_videos(self) -> None:
        self._add_files(
            filedialog.askopenfilenames(title="동영상 추가", filetypes=VIDEO_TYPES), True
        )

    def _add_files(self, paths: tuple[str, ...], is_video: bool) -> None:
        known = {job.path.resolve() for job in self.jobs}
        added = 0
        for raw in paths:
            path = Path(raw)
            if path.resolve() in known:
                continue
            job = DesktopJob(path=path, is_video=is_video)
            self.jobs.append(job)
            self.selected_id = job.id
            added += 1
        self._refresh_queue()
        if self.selected_id:
            self.queue_tree.selection_set(self.selected_id)
            self._select_job(self.selected_job())
        self.status_text.set(f"{added}개 파일을 추가했습니다. 편집 후 대기열 전체 변환을 누르세요.")

    def remove_selected(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        job = self.selected_job()
        if not job:
            return
        index = self.jobs.index(job)
        self.jobs.remove(job)
        self.selected_id = self.jobs[min(index, len(self.jobs) - 1)].id if self.jobs else None
        self._refresh_queue()
        self._select_job(self.selected_job())

    def reset_all(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.jobs.clear()
        self.selected_id = None
        self._refresh_queue()
        self._select_job(None)
        self.status_text.set(
            "대기열과 메모리 결과를 초기화했습니다. 저장된 파일은 그대로 남습니다."
        )

    def choose_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_folder)
        if not selected:
            return
        self.output_folder = Path(selected)
        self.output_label.configure(text=str(self.output_folder))

    def open_output(self) -> None:
        self.output_folder.mkdir(parents=True, exist_ok=True)
        os.startfile(self.output_folder)  # noqa: S606 - opens the app-owned result directory

    def open_selected_result(self) -> None:
        selected = self.selected_job()
        result = selected.result_path if selected else None
        if result and result.exists():
            os.startfile(result)  # noqa: S606 - opens a result path created by this app

    def choose_color(self) -> None:
        color = colorchooser.askcolor(self.background_color.get())[1]
        if color:
            self.background_color.set(color)

    def choose_outline_color(self) -> None:
        color = colorchooser.askcolor(self.outline_color.get())[1]
        if color:
            self.outline_color.set(color)

    def choose_background(self) -> None:
        selected = filedialog.askopenfilename(title="배경 이미지", filetypes=IMAGE_TYPES)
        if selected:
            self.background_path = Path(selected)
            self.background_label.configure(text=self.background_path.name)
            self.mode.set(BackgroundMode.IMAGE.value)

    def _queue_selected(self, _event: object) -> None:
        selected = self.queue_tree.selection()
        if selected:
            self.selected_id = selected[0]
            self._select_job(self.selected_job())

    def _select_job(self, job: DesktopJob | None) -> None:
        if (job.id if job else None) != self.preview_job_id:
            self.preview_job_id = job.id if job else None
            self.preview_zoom = 1.0
            self.preview_offset = [0.0, 0.0]
            self.preview_tool = "hand"
            self.preview_source = None
        self.preview_name.configure(text=job.name if job else "파일을 추가하세요.")
        self._show_preview(job)
        self._refresh_actions()

    def _refresh_queue(self) -> None:
        self.queue_tree.delete(*self.queue_tree.get_children())
        for job in self.jobs:
            self.queue_tree.insert(
                "",
                "end",
                iid=job.id,
                text=job.name,
                values=("영상" if job.is_video else "이미지", job.status),
            )
        if self.selected_id and self.queue_tree.exists(self.selected_id):
            self.queue_tree.selection_set(self.selected_id)
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        busy = bool(self.worker and self.worker.is_alive())
        self.process_button.configure(
            state="disabled" if busy or not runnable_desktop_jobs(self.jobs) else "normal"
        )
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self.remove_button.configure(
            state="disabled" if busy or not self.selected_job() else "normal"
        )
        self.reset_button.configure(state="disabled" if busy or not self.jobs else "normal")
        selected = self.selected_job()
        result = selected.result_path if selected else None
        self.open_result_button.configure(
            state="normal" if result and result.exists() and not busy else "disabled"
        )

    def _schedule_preview(self) -> None:
        if self.preview_after:
            self.root.after_cancel(self.preview_after)
        self.preview_after = self.root.after(120, lambda: self._show_preview(self.selected_job()))

    def _preview_strokes(self, job: DesktopJob) -> list[MaskStroke]:
        strokes = list(job.mask_strokes)
        if self.mask_points and self.preview_tool in {"erase", "restore"} and job.cutout:
            strokes.append(
                MaskStroke(
                    self.preview_tool,
                    self.brush_size.get() / 2 / max(1, min(job.cutout.size)),
                    tuple(self.mask_points),
                )
            )
        return strokes

    def _render_preview_source(self, job: DesktopJob) -> Image.Image | None:
        if job.is_video:
            return job.result
        if job.cutout and self.preview_tool in {"erase", "restore"}:
            return apply_mask_strokes(job.cutout, self._preview_strokes(job))
        if job.original and job.cutout:
            background = None
            if self.background_path:
                with Image.open(self.background_path) as opened:
                    background = opened.convert("RGBA")
            return compose(
                job.original,
                apply_mask_strokes(job.cutout, job.mask_strokes),
                self._edit_options(),
                background,
            )
        if job.result:
            return job.result
        with Image.open(job.path) as opened:
            return opened.convert("RGBA")

    def _show_preview(self, job: DesktopJob | None, *, rebuild: bool = True) -> None:
        self.preview_after = None
        self.preview_canvas.delete("all")
        width = max(320, self.preview_canvas.winfo_width())
        height = max(280, self.preview_canvas.winfo_height())
        if not job:
            self.preview_canvas.create_text(
                width / 2,
                height / 2,
                text="왼쪽에서 이미지 또는 동영상을 추가하세요.",
                fill="#6b786f",
                font=("Malgun Gothic", 12, "bold"),
            )
            return
        if job.is_video and job.result is None:
            self.preview_canvas.create_text(
                width / 2,
                height / 2,
                text="동영상은 대기열 변환 후 결과 파일로 저장됩니다.",
                fill="#6b786f",
                font=("Malgun Gothic", 12, "bold"),
            )
            return
        image = self.preview_source
        if rebuild or image is None:
            try:
                image = self._render_preview_source(job)
                self.preview_source = image
            except (OSError, ValueError) as exc:
                self.status_text.set(str(exc))
                return
        if image is None:
            return
        available_width = max(1, width - 24)
        available_height = max(1, height - 24)
        self.preview_fit_scale = min(
            available_width / image.width,
            available_height / image.height,
        )
        scale = max(0.02, min(32.0, self.preview_fit_scale * self.preview_zoom))
        display_size = (
            max(1, round(image.width * scale)),
            max(1, round(image.height * scale)),
        )
        self.preview_display_size = display_size
        resized = image.resize(display_size, Image.Resampling.LANCZOS)
        display = self._checkerboard(resized)
        self.preview_photo = ImageTk.PhotoImage(display)
        self.preview_canvas.create_image(
            width / 2 + self.preview_offset[0],
            height / 2 + self.preview_offset[1],
            image=self.preview_photo,
        )
        displayed_percent = round(scale * 100)
        self.zoom_text.set(
            "맞춤"
            if abs(self.preview_zoom - 1.0) < 0.001 and self.preview_offset == [0.0, 0.0]
            else f"{displayed_percent}%"
        )
        self.undo_mask_button.configure(state="normal" if job.mask_strokes else "disabled")
        cursor = "fleur" if self.preview_tool == "hand" else "crosshair"
        self.preview_canvas.configure(cursor=cursor)

    @staticmethod
    def _checkerboard(image: Image.Image) -> Image.Image:
        source = image.convert("RGBA").copy()
        background = Image.new("RGBA", source.size, "#fafbf8")
        draw = ImageDraw.Draw(background)
        tile = 16
        for y in range(0, source.height, tile):
            for x in range(0, source.width, tile):
                if (x // tile + y // tile) % 2 == 0:
                    draw.rectangle((x, y, x + tile, y + tile), fill="#e2e7e1")
        return Image.alpha_composite(background, source)

    def _zoom_by(self, factor: float, point: tuple[float, float] | None = None) -> None:
        if self.preview_source is None:
            return
        old_zoom = self.preview_zoom
        new_zoom = max(0.05, min(32.0, old_zoom * factor))
        ratio = new_zoom / old_zoom
        width = self.preview_canvas.winfo_width()
        height = self.preview_canvas.winfo_height()
        px, py = point or (width / 2, height / 2)
        self.preview_offset[0] = px - width / 2 - (px - width / 2 - self.preview_offset[0]) * ratio
        self.preview_offset[1] = (
            py - height / 2 - (py - height / 2 - self.preview_offset[1]) * ratio
        )
        self.preview_zoom = new_zoom
        self._show_preview(self.selected_job(), rebuild=False)

    def _fit_preview(self) -> None:
        self.preview_zoom = 1.0
        self.preview_offset = [0.0, 0.0]
        self._show_preview(self.selected_job(), rebuild=False)

    def _actual_size(self) -> None:
        if not self.preview_source:
            return
        width = max(1, self.preview_canvas.winfo_width() - 24)
        height = max(1, self.preview_canvas.winfo_height() - 24)
        fit_scale = min(width / self.preview_source.width, height / self.preview_source.height)
        self.preview_zoom = 1 / max(fit_scale, 0.0001)
        self.preview_offset = [0.0, 0.0]
        self._show_preview(self.selected_job(), rebuild=False)

    def _set_preview_tool(self, tool: str) -> None:
        job = self.selected_job()
        if tool != "hand" and (not job or job.is_video or not job.cutout):
            self.status_text.set(
                "지우기·복원 브러시는 배경 분리가 끝난 이미지에서 사용할 수 있습니다."
            )
            return
        self.preview_tool = tool
        self.mask_points = None
        self.preview_source = None
        self.preview_info.configure(
            text=(
                "브러시로 남은 배경을 지우거나, AI가 지운 피사체를 복원합니다."
                if tool != "hand"
                else "휠로 포인터 위치를 확대하고 드래그로 화면을 이동합니다."
            )
        )
        self._show_preview(job)

    def _undo_mask(self) -> None:
        job = self.selected_job()
        if not job or not job.mask_strokes:
            return
        job.mask_strokes.pop()
        self._mark_mask_changed(job)
        self._show_preview(job)

    def _preview_wheel(self, event: object) -> str:
        delta = getattr(event, "delta", 0)
        self._zoom_by(1.25 if delta > 0 else 1 / 1.25, (event.x, event.y))
        return "break"

    def _mask_point(self, event: object, job: DesktopJob) -> tuple[float, float] | None:
        display_width, display_height = self.preview_display_size
        left = (
            self.preview_canvas.winfo_width() / 2
            + self.preview_offset[0]
            - display_width / 2
        )
        top = (
            self.preview_canvas.winfo_height() / 2
            + self.preview_offset[1]
            - display_height / 2
        )
        x = (event.x - left) / max(1, display_width)
        y = (event.y - top) / max(1, display_height)
        if not (0 <= x <= 1 and 0 <= y <= 1) or not job.cutout:
            return None
        return x, y

    def _preview_press(self, event: object) -> None:
        if self.preview_tool == "hand":
            self._preview_pan_press(event)
            return
        job = self.selected_job()
        if not job or not job.cutout:
            return
        point = self._mask_point(event, job)
        if point:
            self.mask_points = [point]

    def _preview_motion(self, event: object) -> None:
        if self.preview_tool == "hand":
            self._preview_pan_motion(event)
            return
        job = self.selected_job()
        if not job or self.mask_points is None:
            return
        point = self._mask_point(event, job)
        if point:
            self.mask_points.append(point)
            self._show_preview(job)

    def _preview_release(self, event: object) -> None:
        if self.preview_tool == "hand":
            self._preview_pan_release(event)
            return
        job = self.selected_job()
        if not job or not job.cutout or not self.mask_points:
            self.mask_points = None
            return
        point = self._mask_point(event, job)
        if point:
            self.mask_points.append(point)
        job.mask_strokes.append(
            MaskStroke(
                self.preview_tool,
                self.brush_size.get() / 2 / max(1, min(job.cutout.size)),
                tuple(self.mask_points),
            )
        )
        self.mask_points = None
        self._mark_mask_changed(job)
        self._show_preview(job)

    def _mark_mask_changed(self, job: DesktopJob) -> None:
        job.status = "대기 · 마스크 보정"
        job.result = None
        job.result_path = None
        self.preview_source = None
        self._refresh_queue()

    def _preview_pan_press(self, event: object) -> None:
        self.pan_start = (
            event.x,
            event.y,
            self.preview_offset[0],
            self.preview_offset[1],
        )

    def _preview_pan_motion(self, event: object) -> None:
        if not self.pan_start:
            return
        x, y, offset_x, offset_y = self.pan_start
        self.preview_offset = [offset_x + event.x - x, offset_y + event.y - y]
        self._show_preview(self.selected_job(), rebuild=False)

    def _preview_pan_release(self, _event: object) -> None:
        self.pan_start = None

    def process_queue(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            edit = self._edit_options()
            edit.validate()
        except (ValueError, KeyError) as exc:
            messagebox.showerror("편집값 확인", str(exc))
            return
        targets = runnable_desktop_jobs(self.jobs)
        if not targets:
            self.status_text.set("새로 추가되었거나 편집이 바뀐 대기 항목이 없습니다.")
            return
        settings = {
            "edit": edit,
            "model": self.model_name.get(),
            "image_format": self.image_format.get().lower().replace("jpeg", "jpg"),
            "video_format": self.video_format.get().lower(),
            "fps": float(self.video_fps.get()),
            "dimension": int(self.video_dimension.get()),
            "background": self.background_path,
            "output": self.output_folder,
        }
        self.cancel_event.clear()
        self.worker = threading.Thread(
            target=self._process_jobs,
            args=(targets, settings),
            daemon=True,
        )
        self.worker.start()
        self.status_text.set("대기열을 순차 처리합니다. 이 창은 계속 사용할 수 있습니다.")
        self._refresh_actions()

    def _process_jobs(self, targets: list[DesktopJob], settings: dict[str, object]) -> None:
        try:
            total = len(targets)
            for index, job in enumerate(targets, start=1):
                self._check_cancel()
                job.status = "처리 중"
                job.progress = 0
                self._post(self._refresh_queue)
                self._post(
                    lambda i=index, count=total: self.status_text.set(f"전체 {i}/{count} 처리 중")
                )
                if job.is_video:
                    self._process_video(job, settings)
                else:
                    self._process_image(job, settings)
                job.status = "저장됨"
                job.progress = 100
                self._post(self._refresh_queue)
            self._post(lambda: self.status_text.set("모든 결과를 출력 폴더에 저장했습니다."))
            self._post(lambda: self.progress_value.set(100))
        except Cancelled:
            self._post(
                lambda: self.status_text.set(
                    "작업을 취소했습니다. 미완료 항목은 대기열에 남습니다."
                )
            )
        except Exception as exc:
            active = next((job for job in targets if job.status == "처리 중"), None)
            if active:
                active.status = "오류"
            self._post(self._refresh_queue)
            self._post(lambda message=str(exc): messagebox.showerror("변환 오류", message))
            self._post(lambda message=str(exc): self.status_text.set(message))
        finally:
            self._post(self._worker_finished)

    def _process_image(self, job: DesktopJob, settings: dict[str, object]) -> None:
        if job.original is None:
            with Image.open(job.path) as opened:
                job.original = opened.convert("RGBA")
        self._check_cancel()
        if job.cutout is None:
            job.cutout = self.engine.remove(job.original, model=str(settings["model"]))
        self._check_cancel()
        background = None
        background_path = settings["background"]
        if isinstance(background_path, Path):
            with Image.open(background_path) as opened:
                background = opened.convert("RGBA")
        edit = settings["edit"]
        if not isinstance(edit, EditOptions):
            raise TypeError("편집 설정을 읽지 못했습니다.")
        edited_cutout = apply_mask_strokes(job.cutout, job.mask_strokes)
        result = compose(job.original, edited_cutout, edit, background)
        image_format = str(settings["image_format"])
        output = unique_output_path(Path(settings["output"]), job.path, image_format)
        if image_format == "svg":
            output.write_text(
                to_svg_outline(
                    prepare_foreground(edited_cutout, edit),
                    stroke_color=edit.outline_color,
                    stroke_width=edit.outline_width,
                ),
                encoding="utf-8",
            )
        else:
            output.write_bytes(to_image_bytes(result, image_format))
        job.result = result
        job.result_path = output
        job.preview_original, job.preview_cutout = self._preview_pair(job.original, edited_cutout)
        self._post(
            lambda selected=job: (
                self._select_job(selected) if selected.id == self.selected_id else None
            )
        )

    def _process_video(self, job: DesktopJob, settings: dict[str, object]) -> None:
        self._post(lambda: self.ffmpeg_text.set("FFmpeg 확인 중"))
        ffmpeg, ffprobe = ensure_ffmpeg(lambda value: self._ffmpeg_progress(value))
        self._check_cancel()
        self._post(lambda: self.ffmpeg_text.set("FFmpeg 준비됨"))
        edit = settings["edit"]
        if not isinstance(edit, EditOptions):
            raise TypeError("편집 설정을 읽지 못했습니다.")
        video_format = str(settings["video_format"])
        if (
            video_format in {"mp4", "gif"}
            and edit.mode == BackgroundMode.TRANSPARENT
            and edit.render_mode == RenderMode.COMPOSITE
        ):
            edit = replace(edit, mode=BackgroundMode.COLOR, color="#ffffff")
        output = unique_output_path(Path(settings["output"]), job.path, video_format)
        processor = VideoProcessor(self.engine, ffmpeg, ffprobe)
        processor.process(
            job.path,
            output,
            VideoOptions(
                model=str(settings["model"]),
                edit=edit,
                max_dimension=int(settings["dimension"]),
                fps=float(settings["fps"]),
                output_format=video_format,
            ),
            background_path=settings["background"]
            if isinstance(settings["background"], Path)
            else None,
            on_progress=lambda value: self._video_progress(job, value),
        )
        job.result_path = output

    @staticmethod
    def _preview_pair(
        original: Image.Image, cutout: Image.Image
    ) -> tuple[Image.Image, Image.Image]:
        preview = original.copy()
        preview.thumbnail((1000, 700), Image.Resampling.LANCZOS)
        foreground = cutout.resize(preview.size, Image.Resampling.LANCZOS)
        return preview, foreground

    def _ffmpeg_progress(self, value: float) -> None:
        self._check_cancel()
        self._post(lambda progress=value: self.progress_value.set(round(progress * 100)))
        self._post(lambda: self.ffmpeg_text.set("FFmpeg 자동 준비 중"))

    def _video_progress(self, job: DesktopJob, value: int) -> None:
        self._check_cancel()
        job.progress = value
        self._post(lambda progress=value: self.progress_value.set(progress))
        self._post(self._refresh_queue)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled

    def _post(self, callback: object) -> None:
        self.events.put(callback)

    def _drain_events(self) -> None:
        try:
            while True:
                callback = self.events.get_nowait()
                if callable(callback):
                    callback()
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)

    def _worker_finished(self) -> None:
        self.worker = None
        self._refresh_actions()
        self._show_preview(self.selected_job())

    def cancel(self) -> None:
        self.cancel_event.set()
        self.status_text.set("현재 단계가 끝나는 즉시 작업을 취소합니다.")

    def close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Background Studio", "처리 중입니다. 취소하고 종료할까요?"):
                return
            self.cancel_event.set()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    multiprocessing.freeze_support()
    try:
        DesktopApp().run()
    except Exception as exc:
        root = Tk()
        root.withdraw()
        messagebox.showerror("Background Studio Python", str(exc))
        root.destroy()


if __name__ == "__main__":
    main()
