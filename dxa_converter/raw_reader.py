"""读取 .rXX 文件中的原始探测器计数数据块。

.rXX 中有两类数据块,每块前面紧跟一条描述记录:

=========  =========  ==========================================
描述 tag   数据 tag   说明
=========  =========  ==========================================
0xDD       0xCA       通道交错排列 (行内按 位置×通道 存放)
0xFC       0xDE       通道分块排列 (行内按 通道×位置 存放,
                      每块末尾带 2 个扫描位置计数字,已裁掉)
=========  =========  ==========================================

描述记录按 uint16 解读时:
    w[8]  数据 tag      w[10] 每通道有效采样数
    w[11] 0=交错 1=分块  w[12] 通道数
    w[13] 每通道块字节数  w[14] 每行字节数
"""

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from dxa_converter.records import HologicFormatError, Record, parse_records

DATA_TO_DESCRIPTOR_TAG: Dict[int, int] = {0xCA: 0xDD, 0xDE: 0xFC}

_W_DATA_TAG = 8
_W_VALID = 10
_W_LAYOUT = 11
_W_CHANNELS = 12
_W_BLOCK_BYTES = 13
_W_ROW_BYTES = 14
_MIN_DESCRIPTOR_WORDS = 15


@dataclass(frozen=True)
class RawBlock:
    """一块原始计数数据。

    Attributes:
        name: 数据块名称,例如 ``CA`` / ``DE``。
        data_tag: 源记录 tag。
        frames: 形状 (通道, 行, 列) 的 uint16 数组。
        layout: ``interleaved`` 或 ``blocked``。
    """

    name: str
    data_tag: int
    frames: np.ndarray
    layout: str


def _find_descriptor(records: Sequence[Record], index: int, tag: int) -> Record:
    """向前查找离数据记录最近的描述记录。"""
    for rec in reversed(records[:index]):
        if rec.tag == tag:
            return rec
    raise HologicFormatError(f"数据记录前缺少描述记录 0x{tag:X}")


def _decode_block(data_rec: Record, desc_rec: Record) -> RawBlock:
    """按描述记录把数据记录体还原为 (通道, 行, 列) 数组。"""
    n_words = len(desc_rec.body) // 2
    if n_words < _MIN_DESCRIPTOR_WORDS:
        raise HologicFormatError(f"描述记录 0x{desc_rec.tag:X} 过短")
    w = struct.unpack(f"<{n_words}H", desc_rec.body[: n_words * 2])
    if w[_W_DATA_TAG] != data_rec.tag:
        raise HologicFormatError(
            f"描述记录指向 0x{w[_W_DATA_TAG]:X},与数据记录 0x{data_rec.tag:X} 不符"
        )
    channels, valid = w[_W_CHANNELS], w[_W_VALID]
    block, row_bytes = w[_W_BLOCK_BYTES] // 2, w[_W_ROW_BYTES]
    if channels < 1 or valid < 1 or valid > block or row_bytes != channels * block * 2:
        raise HologicFormatError(f"描述记录 0x{desc_rec.tag:X} 参数不自洽: {w[8:15]}")
    body = data_rec.body
    if len(body) == 0 or len(body) % row_bytes:
        raise HologicFormatError(
            f"数据记录 0x{data_rec.tag:X} 长度 {len(body)} 不是行字节数 {row_bytes} 的整数倍"
        )
    rows = len(body) // row_bytes
    arr = np.frombuffer(body, dtype="<u2")
    if w[_W_LAYOUT] == 0:
        layout = "interleaved"
        frames = arr.reshape(rows, block, channels).transpose(2, 0, 1)
    else:
        layout = "blocked"
        frames = arr.reshape(rows, channels, block).transpose(1, 0, 2)
    frames = np.ascontiguousarray(frames[:, :, :valid]).astype(np.uint16, copy=False)
    return RawBlock(f"{data_rec.tag:02X}", data_rec.tag, frames, layout)


def read_raw_blocks(path: Path) -> List[RawBlock]:
    """读取 .rXX 文件中的所有原始数据块。

    Args:
        path: .rXX 文件路径。

    Returns:
        数据块列表(文件中没有的块不会出现)。

    Raises:
        HologicFormatError: 文件结构异常,或没有找到任何数据块。
    """
    records = parse_records(path.read_bytes())
    blocks: List[RawBlock] = []
    for idx, rec in enumerate(records):
        desc_tag: Optional[int] = DATA_TO_DESCRIPTOR_TAG.get(rec.tag)
        if desc_tag is None:
            continue
        blocks.append(_decode_block(rec, _find_descriptor(records, idx, desc_tag)))
    if not blocks:
        raise HologicFormatError(f"{path.name} 中没有找到原始数据块")
    return blocks
