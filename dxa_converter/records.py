"""Hologic QDR 归档文件的通用记录解析。

文件由连续记录组成,每条记录布局为::

    tag  : uint16 (小端)
    len  : uint32 (小端, 含 6 字节记录头在内的整条记录长度)
    body : len - 6 字节
"""

import struct
from dataclasses import dataclass
from typing import List

RECORD_HEADER = struct.Struct("<HI")
RECORD_HEADER_SIZE = RECORD_HEADER.size


class HologicFormatError(ValueError):
    """文件不符合已知的 Hologic 记录结构。"""


@dataclass(frozen=True)
class Record:
    """单条记录。

    Attributes:
        tag: 记录标识。
        offset: 记录在文件中的起始偏移。
        body: 记录体(不含记录头)。
    """

    tag: int
    offset: int
    body: bytes


def parse_records(data: bytes) -> List[Record]:
    """把整个文件解析为记录列表。

    Args:
        data: 文件完整字节。

    Returns:
        按文件顺序排列的记录。

    Raises:
        HologicFormatError: 记录长度非法或文件末尾存在无法解析的残余字节。
    """
    records: List[Record] = []
    pos = 0
    size = len(data)
    while pos < size:
        if pos + RECORD_HEADER_SIZE > size:
            raise HologicFormatError(f"偏移 {pos} 处记录头被截断")
        tag, length = RECORD_HEADER.unpack_from(data, pos)
        if length < RECORD_HEADER_SIZE or pos + length > size:
            raise HologicFormatError(
                f"偏移 {pos} 处记录 tag=0x{tag:X} 长度 {length} 非法"
            )
        records.append(Record(tag, pos, data[pos + RECORD_HEADER_SIZE : pos + length]))
        pos += length
    return records
