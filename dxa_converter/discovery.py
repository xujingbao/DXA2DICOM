"""在目录或 ZIP 中查找成对的 .pXX / .rXX 文件。"""

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

_SUFFIX_RE = re.compile(r"^\.([rp])([0-9A-Za-z]{2})$")


@dataclass(frozen=True)
class ScanPair:
    """同一次扫描的 .rXX(原始数据)与 .pXX(元数据)。

    Attributes:
        stem: 文件主名,例如 ``PA26629A``。
        code: 两位后缀码,例如 ``0C``。
        raw_path: .rXX 路径。
        exam_path: .pXX 路径。
    """

    stem: str
    code: str
    raw_path: Path
    exam_path: Path


def _is_noise(path: Path) -> bool:
    """macOS 压缩包里的 AppleDouble / __MACOSX 垃圾文件。"""
    return path.name.startswith(".") or "__MACOSX" in path.parts


def find_scan_pairs(root: Path) -> Tuple[List[ScanPair], List[Path]]:
    """递归查找成对文件。

    Args:
        root: 目录路径。

    Returns:
        (完整的扫描对列表, 缺少配对 .pXX 的 .rXX 列表)。
    """
    raws: Dict[Tuple[Path, str, str], Path] = {}
    exams: Dict[Tuple[Path, str, str], Path] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or _is_noise(path):
            continue
        match = _SUFFIX_RE.match(path.suffix)
        if not match:
            continue
        key = (path.parent, path.stem.upper(), match.group(2).upper())
        (raws if match.group(1) == "r" else exams)[key] = path
    pairs: List[ScanPair] = []
    orphans: List[Path] = []
    for key, raw_path in raws.items():
        exam_path = exams.get(key)
        if exam_path is None:
            orphans.append(raw_path)
        else:
            pairs.append(ScanPair(raw_path.stem, key[2], raw_path, exam_path))
    return pairs, orphans


def extract_zip(zip_path: Path, dest: Path) -> Path:
    """解压 ZIP 到目标目录(zipfile 会拒绝越界路径)。

    Args:
        zip_path: ZIP 文件路径。
        dest: 解压目录。

    Returns:
        解压目录。

    Raises:
        zipfile.BadZipFile: 不是合法 ZIP。
    """
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    return dest
