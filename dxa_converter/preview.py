"""预览面板:列出扫描,并把原始计数的各通道渲染成灰度图。"""

from typing import List

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    ListWidget,
    SegmentedWidget,
    SmoothScrollArea,
    StrongBodyLabel,
)

from dxa_converter.discovery import ScanPair
from dxa_converter.exam_reader import read_exam_info
from dxa_converter.raw_reader import RawBlock, read_raw_blocks
from dxa_converter.records import HologicFormatError

GRID_COLUMNS = 3
THUMB_SIZE = (210, 300)
ENLARGED_SIZE = (760, 760)
WINDOW_PERCENTILES = (1.0, 99.0)


def frame_to_qimage(frame: np.ndarray) -> QImage:
    """把单个通道按 1%-99% 分位拉伸为 8 位灰度图(仅用于显示,不影响导出)。

    Args:
        frame: 形状 (行, 列) 的 uint16 数组。

    Returns:
        灰度 QImage。
    """
    lo, hi = np.percentile(frame, WINDOW_PERCENTILES)
    scaled = (frame.astype(np.float32) - lo) / max(float(hi - lo), 1.0)
    gray = np.ascontiguousarray((np.clip(scaled, 0.0, 1.0) * 255).astype(np.uint8))
    rows, cols = gray.shape
    return QImage(gray.data, cols, rows, cols, QImage.Format.Format_Grayscale8).copy()


def _scaled_pixmap(image: QImage, size: tuple[int, int]) -> QPixmap:
    return QPixmap.fromImage(image).scaled(
        size[0],
        size[1],
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class ClickableLabel(QLabel):
    """可点击的图像标签。"""

    clicked = Signal()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """左键释放时发出 clicked。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ImageDialog(QDialog):
    """放大查看单个通道。"""

    def __init__(self, title: str, image: QImage, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(_scaled_pixmap(image, ENLARGED_SIZE))
        layout = QVBoxLayout(self)
        layout.addWidget(label)


def _thumbnail(title: str, image: QImage, panel: QWidget) -> QWidget:
    thumb = ClickableLabel()
    thumb.setObjectName("thumb")
    thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    thumb.setPixmap(_scaled_pixmap(image, THUMB_SIZE))
    thumb.setCursor(Qt.CursorShape.PointingHandCursor)
    thumb.setToolTip("点击放大")
    thumb.clicked.connect(lambda: ImageDialog(title, image, panel).exec())
    caption = CaptionLabel(title)
    caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cell = QWidget()
    layout = QVBoxLayout(cell)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.addWidget(thumb)
    layout.addWidget(caption)
    return cell


def _block_page(block: RawBlock, panel: QWidget) -> QWidget:
    content = QWidget()
    content.setStyleSheet("background: transparent;")
    grid = QGridLayout(content)
    for index in range(block.frames.shape[0]):
        frame = block.frames[index]
        title = f"{block.name} 通道 {index} · {frame.shape[0]}×{frame.shape[1]}"
        cell = _thumbnail(title, frame_to_qimage(frame), panel)
        grid.addWidget(cell, index // GRID_COLUMNS, index % GRID_COLUMNS)
    scroll = SmoothScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    scroll.enableTransparentBackground()
    return scroll


class PreviewPanel(QWidget):
    """扫描列表 + 各数据块通道图。"""

    def __init__(self) -> None:
        super().__init__()
        self._pairs: List[ScanPair] = []
        self._list = ListWidget()
        self._list.setMaximumHeight(130)
        self._list.currentRowChanged.connect(self._show)
        self._segments = SegmentedWidget()
        self._pages = QStackedWidget()
        self._segments.currentItemChanged.connect(self._on_segment)
        self._status = CaptionLabel("选择输入后在此预览")
        hint = CaptionLabel("预览仅用于目测,已按 1%–99% 拉伸;点击缩略图可放大")
        layout = QVBoxLayout(self)
        layout.addWidget(StrongBodyLabel("预览"))
        layout.addWidget(self._list)
        layout.addWidget(hint)
        layout.addWidget(self._segments, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._pages, 1)
        layout.addWidget(self._status)

    def set_pairs(self, pairs: List[ScanPair]) -> None:
        """刷新扫描列表,并默认预览第一项。"""
        self._pairs = pairs
        self._list.blockSignals(True)
        self._list.clear()
        for pair in pairs:
            self._list.addItem(self._label(pair))
        self._list.blockSignals(False)
        self._clear_pages()
        if not pairs:
            self._status.setText("未找到可预览的 .p/.r 文件对")
            return
        self._list.setCurrentRow(0)

    @staticmethod
    def _label(pair: ScanPair) -> str:
        text = f"{pair.stem}.{pair.code}"
        try:
            scan_time = read_exam_info(pair.exam_path).scan_time
        except (HologicFormatError, OSError):
            return text
        return f"{text}    {scan_time:%Y-%m-%d %H:%M}" if scan_time else text

    def _clear_pages(self) -> None:
        self._segments.clear()
        while self._pages.count():
            page = self._pages.widget(0)
            if page is None:
                break
            self._pages.removeWidget(page)
            page.deleteLater()

    def _on_segment(self, route_key: str) -> None:
        self._pages.setCurrentIndex(int(route_key))

    def _show(self, row: int) -> None:
        self._clear_pages()
        if not 0 <= row < len(self._pairs):
            return
        pair = self._pairs[row]
        try:
            blocks = read_raw_blocks(pair.raw_path)
        except (HologicFormatError, OSError) as exc:
            self._status.setText(f"读取失败: {exc}")
            return
        for index, block in enumerate(blocks):
            chan, rows, cols = block.frames.shape
            self._pages.addWidget(_block_page(block, self))
            self._segments.addItem(str(index), f"{block.name}  {chan}×{rows}×{cols}")
        self._segments.setCurrentItem("0")
        self._status.setText(f"{pair.raw_path.name}: {len(blocks)} 个数据块")
