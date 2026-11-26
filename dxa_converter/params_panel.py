"""成像参数面板:分组表格 + 搜索过滤。"""

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, SearchLineEdit, TableWidget

from dxa_converter.params_reader import Item, ParamSection

EXAM_SECTION_TITLE = "检查信息"
NOTE = "参数原样取自 .p 文件,物理含义以 Hologic 为准;姓名、出生日期、患者 ID 已排除"


class ParamsPanel(QWidget):
    """显示一次扫描的成像参数,可按关键字过滤。"""

    def __init__(self) -> None:
        super().__init__()
        self._sections: List[ParamSection] = []
        self._search = SearchLineEdit()
        self._search.setPlaceholderText("搜索参数名或值")
        self._search.textChanged.connect(self._render)
        self._table = TableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["参数", "值"])
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._search)
        layout.addWidget(self._table, 1)
        layout.addWidget(CaptionLabel(NOTE))

    def set_data(self, exam_items: List[Item], sections: List[ParamSection]) -> None:
        """设置要显示的数据:检查信息 + 各参数分组。"""
        self._sections = [ParamSection(EXAM_SECTION_TITLE, exam_items)] + sections
        self._search.clear()
        self._render()

    def _render(self) -> None:
        keyword = self._search.text().strip().lower()
        rows: List[tuple[str, str, bool]] = []
        for section in self._sections:
            matched = [
                (k, v) for k, v in section.items if keyword in k.lower() or keyword in v.lower()
            ]
            if not matched:
                continue
            rows.append((section.title, "", True))
            rows += [(k, v, False) for k, v in matched]
        self._table.setRowCount(len(rows))
        bold = QFont(self._table.font())
        bold.setBold(True)
        for row, (key, value, is_header) in enumerate(rows):
            key_item, value_item = QTableWidgetItem(key), QTableWidgetItem(value)
            value_item.setToolTip(value)
            if is_header:
                key_item.setFont(bold)
                key_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                value_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._table.setItem(row, 0, key_item)
            self._table.setItem(row, 1, value_item)
