"""PySide6 + Fluent 组件的图形界面:选择数据、预览、一键转换。"""

import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    HeaderCardWidget,
    IndeterminateProgressBar,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SwitchButton,
    TitleLabel,
)

from dxa_converter import __version__
from dxa_converter.converter import ConversionResult
from dxa_converter.discovery import ScanPair, extract_zip, find_scan_pairs
from dxa_converter.gui_style import apply_theme, window_style
from dxa_converter.gui_worker import ConvertWorker
from dxa_converter.preview import PreviewPanel

SETTINGS_ORG = "DXA"
SETTINGS_APP = "DICOMConverter"
SETTING_OUTPUT = "output_dir"
DEFAULT_OUTPUT_NAME = "DICOM_output"
INFO_DURATION_MS = 4000


def _card(title: str) -> Tuple[HeaderCardWidget, QVBoxLayout]:
    """创建卡片,返回卡片与其纵向内容布局(HeaderCardWidget 自带布局是横向的)。"""
    card = HeaderCardWidget()
    card.setTitle(title)
    body = QVBoxLayout()
    card.viewLayout.addLayout(body)
    return card, body


class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Hologic DXA 转 DICOM  v{__version__}")
        self.resize(1200, 760)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._inputs: List[Path] = []
        self._worker: Optional[ConvertWorker] = None
        self._tmp_dirs: List["tempfile.TemporaryDirectory[str]"] = []
        self._auto_output = True
        self._build_ui()
        saved = str(self._settings.value(SETTING_OUTPUT, ""))
        if saved:
            self._output_edit.setText(saved)
            self._auto_output = False

    # ---------- 界面构建 ----------

    def _build_ui(self) -> None:
        left = QWidget()
        layout = QVBoxLayout(left)
        layout.addWidget(TitleLabel("Hologic DXA 转 DICOM"))
        layout.addWidget(CaptionLabel("把设备导出的 .p/.r 归档文件还原为标准 DICOM"))
        layout.addWidget(self._build_input_card())
        layout.addWidget(self._build_output_card())
        layout.addWidget(self._build_option_card())
        layout.addLayout(self._build_action_area(), 1)

        self._preview = PreviewPanel()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self._preview)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setChildrenCollapsible(False)
        splitter.setObjectName("root")
        self.setCentralWidget(splitter)
        self.setStyleSheet(window_style())

    def _build_input_card(self) -> HeaderCardWidget:
        card, body = _card("① 选择数据")
        btn_dir = PushButton(FluentIcon.FOLDER, "选择文件夹")
        btn_zip = PushButton(FluentIcon.ZIP_FOLDER, "选择 ZIP")
        btn_dir.clicked.connect(self._pick_dir)
        btn_zip.clicked.connect(self._pick_zip)
        row = QHBoxLayout()
        row.addWidget(btn_dir)
        row.addWidget(btn_zip)
        self._input_summary = BodyLabel("尚未选择,也可以直接把文件夹或 ZIP 拖进窗口")
        self._input_summary.setWordWrap(True)
        body.addLayout(row)
        body.addWidget(self._input_summary)
        return card

    def _build_output_card(self) -> HeaderCardWidget:
        card, body = _card("② 输出位置")
        self._output_edit = LineEdit()
        self._output_edit.setPlaceholderText("DICOM 输出目录")
        self._output_edit.setClearButtonEnabled(True)
        self._output_edit.textEdited.connect(self._on_output_edited)
        btn = PushButton(FluentIcon.FOLDER_ADD, "选择")
        btn.clicked.connect(self._pick_output)
        row = QHBoxLayout()
        row.addWidget(self._output_edit, 1)
        row.addWidget(btn)
        body.addLayout(row)
        return card

    def _build_option_card(self) -> HeaderCardWidget:
        card, body = _card("③ 选项")
        self._anon_switch = SwitchButton()
        self._anon_switch.setOnText("匿名化:开(推荐)")
        self._anon_switch.setOffText("匿名化:关")
        self._anon_switch.setChecked(True)
        hint = CaptionLabel("开启后不写入姓名与出生日期,患者 ID 改为哈希值;性别、年龄、身高体重保留。")
        hint.setWordWrap(True)
        body.addWidget(self._anon_switch)
        body.addWidget(hint)
        return card

    def _build_action_area(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        self._start_btn = PrimaryPushButton(FluentIcon.PLAY, "开始转换")
        self._start_btn.setFixedHeight(40)
        self._start_btn.clicked.connect(self._start)
        self._progress = IndeterminateProgressBar(start=False)
        self._log = PlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("转换日志")
        self._open_btn = PushButton(FluentIcon.FOLDER, "打开输出目录")
        self._open_btn.clicked.connect(self._open_output)
        self._open_btn.hide()
        layout.addWidget(self._start_btn)
        layout.addWidget(self._progress)
        layout.addWidget(self._log, 1)
        layout.addWidget(self._open_btn)
        return layout

    # ---------- 提示 ----------

    def _notify(self, level: str, title: str, content: str = "") -> None:
        """用 Fluent InfoBar 在窗口右上角提示。level: success/warning/error。"""
        factory = getattr(InfoBar, level)
        factory(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=INFO_DURATION_MS,
            parent=self,
        )

    # ---------- 输入处理 ----------

    def _set_inputs(self, paths: List[Path]) -> None:
        self._inputs = paths
        pairs = self._collect_pairs(paths)
        self._preview.set_pairs(pairs)
        names = "、".join(p.name for p in paths)
        if pairs:
            self._input_summary.setText(f"{names}\n找到 {len(pairs)} 组扫描")
        else:
            self._input_summary.setText(f"{names}\n未找到成对的 .p/.r 文件")
            self._notify("warning", "未找到数据", "所选内容里没有成对的 .p/.r 文件")
        self._maybe_set_auto_output(paths[0])
        self._open_btn.hide()

    def _maybe_set_auto_output(self, first_input: Path) -> None:
        if not self._auto_output:
            return
        base = first_input if first_input.is_dir() else first_input.parent
        self._output_edit.setText(str(base / DEFAULT_OUTPUT_NAME))

    def _cleanup_tmp(self) -> None:
        for tmp in self._tmp_dirs:
            tmp.cleanup()
        self._tmp_dirs = []

    def _collect_pairs(self, paths: List[Path]) -> List[ScanPair]:
        """为预览收集扫描对;ZIP 解压到临时目录,换输入或退出时清理。"""
        self._cleanup_tmp()
        pairs: List[ScanPair] = []
        for path in paths:
            root = path
            if not path.is_dir():
                try:
                    tmp = tempfile.TemporaryDirectory(prefix="dxa_preview_")
                    self._tmp_dirs.append(tmp)
                    root = extract_zip(path, Path(tmp.name))
                except (zipfile.BadZipFile, OSError) as exc:
                    self._notify("error", f"无法读取 {path.name}", str(exc))
                    continue
            pairs += find_scan_pairs(root)[0]
        return pairs

    def _pick_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self._set_inputs([Path(folder)])

    def _pick_zip(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择 ZIP", "", "ZIP (*.zip)")
        if files:
            self._set_inputs([Path(f) for f in files])

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """接受拖入文件夹或 ZIP。"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """处理拖入:只保留文件夹和 .zip。"""
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        valid = [p for p in paths if p.is_dir() or p.suffix.lower() == ".zip"]
        if valid:
            self._set_inputs(valid)
        else:
            self._notify("warning", "不支持的内容", "请拖入文件夹或 ZIP 压缩包")

    # ---------- 输出与转换 ----------

    def _on_output_edited(self, _text: str) -> None:
        self._auto_output = False

    def _pick_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self._output_edit.setText(folder)
            self._auto_output = False

    def _open_output(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._output_edit.text().strip()))

    def _confirm_identity(self) -> bool:
        box = MessageBox(
            "确认关闭匿名化",
            "未匿名化的 DICOM 会包含患者姓名与出生日期,确认继续?",
            self,
        )
        box.yesButton.setText("继续")
        box.cancelButton.setText("取消")
        return bool(box.exec())

    def _start(self) -> None:
        out_text = self._output_edit.text().strip()
        if not self._inputs or not out_text:
            self._notify("warning", "信息不完整", "请先选择输入数据和输出目录")
            return
        anonymize = self._anon_switch.isChecked()
        if not anonymize and not self._confirm_identity():
            return
        if not self._auto_output:
            self._settings.setValue(SETTING_OUTPUT, out_text)
        self._log.clear()
        self._open_btn.hide()
        self._start_btn.setEnabled(False)
        self._start_btn.setText("转换中…")
        self._progress.start()
        self._worker = ConvertWorker(self._inputs, Path(out_text), anonymize)
        self._worker.message.connect(self._log.appendPlainText)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _finish_ui(self) -> None:
        self._progress.stop()
        self._start_btn.setEnabled(True)
        self._start_btn.setText("开始转换")

    def _on_done(self, results: List[ConversionResult]) -> None:
        self._finish_ui()
        ok = sum(1 for r in results if not r.error)
        failed = len(results) - ok
        files = sum(len(r.outputs) for r in results)
        self._log.appendPlainText(f"\n全部结束: 成功 {ok} 组, 失败 {failed} 组, 共 {files} 个 DICOM")
        if files:
            self._open_btn.show()
        if failed:
            self._notify("warning", "部分转换失败", f"成功 {ok} 组,失败 {failed} 组,详见日志")
        elif files:
            self._notify("success", "转换完成", f"共生成 {files} 个 DICOM")
        else:
            self._notify("warning", "没有可转换的数据")

    def _on_failed(self, reason: str) -> None:
        self._finish_ui()
        self._notify("error", "转换失败", reason)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """退出时清理预览用的临时目录。"""
        self._cleanup_tmp()
        super().closeEvent(event)


def run_gui() -> int:
    """启动图形界面。"""
    app = QApplication(sys.argv)
    apply_theme()
    window = MainWindow()
    window.show()
    return app.exec()
