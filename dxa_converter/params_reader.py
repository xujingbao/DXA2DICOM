"""读取 .pXX 中可读的成像/校准/分析参数文本块。

参数块是 ``key=value`` 文本(块 0x145 以 NUL 分隔,其余按行分隔),
部分块含 ``{ ... }`` 嵌套。这些参数的物理含义以 Hologic 为准,本模块只做原样提取。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dxa_converter.exam_reader import ExamInfoSchema
from dxa_converter.records import parse_records

SECTION_TITLES = {
    0x145: "设备配置",
    0x15D: "校准与分析参数",
    0x44C: "分析设置",
}
# 含患者或机构身份的键,任何情况下都不提取
EXCLUDED_KEYS = frozenset({"patient_id", "customer"})

Item = Tuple[str, str]


@dataclass
class ParamSection:
    """一组参数。

    Attributes:
        title: 分组名称。
        items: (参数名, 参数值) 列表,保持文件中的顺序。
    """

    title: str
    items: List[Item] = field(default_factory=list)


def parse_param_text(text: str) -> List[Item]:
    """解析 ``key=value`` 文本,支持 ``{ ... }`` 嵌套(键名用 ``.`` 连接)。"""
    items: List[Item] = []
    prefix: List[str] = []
    groups: List[str] = []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            if value.endswith("{"):
                prefix.append(key)
                groups.append(".".join(prefix))
                items.append((".".join(prefix), ""))  # 占位,承接后续无键的矩阵行
                continue
            closes = value.endswith("}")
            value = value.rstrip("}").strip()
            items.append((".".join(prefix + [key]), value))
            if closes and prefix:
                prefix.pop()
        else:
            closes = line.endswith("}")
            line = line.rstrip("}").strip()
            if line and items:
                name, value = items[-1]
                items[-1] = (name, f"{value} {line}".strip())
            if closes and prefix:
                prefix.pop()
    return [(k, v) for k, v in items if v or k not in groups]


def _block_items(body: bytes) -> List[Item]:
    items: List[Item] = []
    for chunk in body.split(b"\x00"):
        if chunk.strip():
            items += parse_param_text(chunk.decode("latin-1"))
    return [(k, v) for k, v in items if k.split(".")[-1].lower() not in EXCLUDED_KEYS]


def read_param_sections(path: Path) -> List[ParamSection]:
    """读取 .pXX 中的参数分组(没有的分组不返回)。

    Args:
        path: .pXX 文件路径。

    Returns:
        按 ``SECTION_TITLES`` 顺序排列的参数分组。

    Raises:
        HologicFormatError: 文件记录结构异常。
    """
    bodies: Dict[int, bytes] = {}
    for rec in parse_records(path.read_bytes()):
        if rec.tag in SECTION_TITLES:
            bodies.setdefault(rec.tag, rec.body)
    sections: List[ParamSection] = []
    for tag, title in SECTION_TITLES.items():
        body: Optional[bytes] = bodies.get(tag)
        items = _block_items(body) if body else []
        if items:
            sections.append(ParamSection(title, items))
    return sections


def exam_rows(exam: ExamInfoSchema) -> List[Item]:
    """检查信息摘要(不含姓名、出生日期、患者键)。"""
    rows: List[Item] = []
    if exam.scan_time:
        rows.append(("扫描时间", f"{exam.scan_time:%Y-%m-%d %H:%M:%S}"))
    if exam.protocol_path:
        rows.append(("扫描协议", exam.protocol_path.replace("\\", "/").split("/")[-1]))
    if exam.device_serial:
        rows.append(("设备序列号", exam.device_serial))
    if exam.software_version:
        rows.append(("软件版本", exam.software_version))
    if exam.sex:
        rows.append(("性别", exam.sex))
    if exam.height_cm:
        rows.append(("身高 (cm)", f"{exam.height_cm:g}"))
    if exam.weight_kg:
        rows.append(("体重 (kg)", f"{exam.weight_kg:g}"))
    if exam.param_38 or exam.param_39:
        rows.append(("头参数 0x38 / 0x39(含义未确认)", f"{exam.param_38} / {exam.param_39}"))
    return rows
