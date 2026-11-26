"""读取 .pXX 文件中的患者与检查元数据。"""

import struct
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional, TypeVar

from pydantic import BaseModel

from dxa_converter.records import Record, parse_records

T = TypeVar("T")

TAG_PATIENT_KEY = 0x3E9
TAG_PATIENT_NAME = 0x3EA
TAG_BIRTH_DATE = 0x3F0
TAG_SEX = 0x3F1
TAG_ETHNICITY = 0x3F2
TAG_WEIGHT_KG = 0x403
TAG_HEIGHT_CM = 0x404
TAG_SCAN_TIME = 0x408
TAG_DEVICE_SERIAL = 0x41C
TAG_SOFTWARE_VERSION = 0x428
TAG_SOURCE_NAME = 0x43C
TAG_PROTOCOL_PATH = 0x150
TAG_PARAM_38 = 0x38
TAG_PARAM_39 = 0x39

_DATETIME_FORMAT = "%m/%d/%Y %H:%M:%S"


class ExamInfoSchema(BaseModel):
    """从 .pXX 中提取的检查信息,缺失字段为 None。"""

    patient_key: Optional[str] = None
    patient_name: Optional[str] = None
    birth_date: Optional[datetime] = None
    sex: Optional[str] = None
    ethnicity: Optional[str] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    scan_time: Optional[datetime] = None
    device_serial: Optional[str] = None
    software_version: Optional[str] = None
    protocol_path: Optional[str] = None
    source_name: Optional[str] = None
    param_38: Optional[str] = None
    param_39: Optional[str] = None


def _utf16(body: bytes) -> Optional[str]:
    text = body.decode("utf-16le", errors="ignore").split("\x00")[0].strip()
    return text or None


def _ascii(body: bytes) -> Optional[str]:
    text = body.split(b"\x00")[0].decode("ascii", errors="ignore").strip()
    return text or None


def _float64(body: bytes) -> Optional[float]:
    if len(body) < 8:
        return None
    value = struct.unpack("<d", body[:8])[0]
    return value if value == value and value > 0 else None


def _datetime(body: bytes) -> Optional[datetime]:
    text = _ascii(body)
    if text is None:
        return None
    try:
        return datetime.strptime(text, _DATETIME_FORMAT)
    except ValueError:
        return None


def read_exam_info(path: Path) -> ExamInfoSchema:
    """读取 .pXX 文件。

    Args:
        path: .pXX 文件路径。

    Returns:
        检查信息。文件里没有的字段保持为 None。

    Raises:
        HologicFormatError: 文件记录结构异常。
    """
    first: Dict[int, Record] = {}
    for rec in parse_records(path.read_bytes()):
        first.setdefault(rec.tag, rec)

    def pick(tag: int, parser: Callable[[bytes], Optional[T]]) -> Optional[T]:
        rec = first.get(tag)
        return parser(rec.body) if rec else None

    sex = pick(TAG_SEX, _utf16)
    return ExamInfoSchema(
        patient_key=pick(TAG_PATIENT_KEY, _utf16),
        patient_name=pick(TAG_PATIENT_NAME, _utf16),
        birth_date=pick(TAG_BIRTH_DATE, _datetime),
        sex=sex if sex in ("M", "F") else None,
        ethnicity=pick(TAG_ETHNICITY, _utf16),
        weight_kg=pick(TAG_WEIGHT_KG, _float64),
        height_cm=pick(TAG_HEIGHT_CM, _float64),
        scan_time=pick(TAG_SCAN_TIME, _datetime),
        device_serial=pick(TAG_DEVICE_SERIAL, _utf16),
        software_version=pick(TAG_SOFTWARE_VERSION, _utf16),
        protocol_path=pick(TAG_PROTOCOL_PATH, _ascii),
        source_name=pick(TAG_SOURCE_NAME, _utf16),
        param_38=pick(TAG_PARAM_38, _ascii),
        param_39=pick(TAG_PARAM_39, _ascii),
    )
