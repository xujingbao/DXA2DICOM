"""后台转换线程。"""

from pathlib import Path
from typing import List

from PySide6.QtCore import QThread, Signal

from dxa_converter.converter import ConversionResult, convert_input


class ConvertWorker(QThread):
    """后台转换线程,避免阻塞界面。"""

    message = Signal(str)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, inputs: List[Path], out_dir: Path, anonymize: bool) -> None:
        super().__init__()
        self._inputs = inputs
        self._out_dir = out_dir
        self._anonymize = anonymize

    def run(self) -> None:
        """依次转换所有输入。"""
        results: List[ConversionResult] = []
        try:
            for path in self._inputs:
                self.message.emit(f"处理 {path.name}")
                results += convert_input(
                    path, self._out_dir, self._anonymize, self.message.emit
                )
        except (FileNotFoundError, ValueError, OSError) as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(results)
