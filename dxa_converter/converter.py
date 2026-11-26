"""转换流程编排:输入(目录/ZIP) -> DICOM 文件。"""

import logging
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from dxa_converter.dicom_writer import make_study_uid, write_raw_dicom
from dxa_converter.discovery import ScanPair, extract_zip, find_scan_pairs
from dxa_converter.exam_reader import read_exam_info
from dxa_converter.raw_reader import read_raw_blocks
from dxa_converter.records import HologicFormatError

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


@dataclass
class ConversionResult:
    """单个扫描对的转换结果。

    Attributes:
        label: 扫描标识,例如 ``PA26629A.0C``。
        outputs: 成功写出的 DICOM 文件。
        error: 失败原因,成功时为 None。
    """

    label: str
    outputs: List[Path] = field(default_factory=list)
    error: Optional[str] = None


def convert_pair(pair: ScanPair, out_dir: Path, anonymize: bool) -> List[Path]:
    """转换一个扫描对。

    Args:
        pair: 扫描对。
        out_dir: 输出根目录,文件写入其下的 ``<stem>_<code>/`` 子目录。
        anonymize: 是否匿名化。

    Returns:
        写出的 DICOM 文件列表。

    Raises:
        HologicFormatError: 文件结构异常。
        OSError: 读写失败。
    """
    exam = read_exam_info(pair.exam_path)
    blocks = read_raw_blocks(pair.raw_path)
    study_uid = make_study_uid(exam)
    source_name = pair.raw_path.name
    target = out_dir / f"{pair.stem}_{pair.code}"
    return [
        write_raw_dicom(
            block,
            exam,
            target / f"{pair.stem}_{pair.code}_{block.name}.dcm",
            source_name,
            study_uid,
            anonymize,
        )
        for block in blocks
    ]


def _convert_directory(
    root: Path, out_dir: Path, anonymize: bool, progress: ProgressCallback
) -> List[ConversionResult]:
    pairs, orphans = find_scan_pairs(root)
    results: List[ConversionResult] = []
    for orphan in orphans:
        progress(f"跳过 {orphan.name}: 缺少对应的 .p 文件")
        results.append(ConversionResult(orphan.name, error="缺少对应的 .p 文件"))
    if not pairs and not orphans:
        progress("未找到任何 .pXX/.rXX 文件")
    for pair in pairs:
        label = f"{pair.stem}.{pair.code}"
        try:
            outputs = convert_pair(pair, out_dir, anonymize)
            results.append(ConversionResult(label, outputs))
            progress(f"完成 {label}: 输出 {len(outputs)} 个 DICOM")
        except (HologicFormatError, OSError) as exc:
            logger.error("convert_failed", extra={"scan": label, "error": str(exc)})
            results.append(ConversionResult(label, error=str(exc)))
            progress(f"失败 {label}: {exc}")
    return results


def convert_input(
    input_path: Path,
    out_dir: Path,
    anonymize: bool = True,
    progress: Optional[ProgressCallback] = None,
) -> List[ConversionResult]:
    """转换目录或 ZIP 中的全部扫描。

    Args:
        input_path: 包含 .pXX/.rXX 的目录,或其 ZIP 压缩包。
        out_dir: 输出目录(不存在会创建)。
        anonymize: 是否匿名化,默认开启。
        progress: 进度消息回调。

    Returns:
        每个扫描对的结果。

    Raises:
        FileNotFoundError: 输入路径不存在。
        ValueError: 输入既不是目录也不是 ZIP。
    """
    notify: ProgressCallback = progress or (lambda _msg: None)
    if not input_path.exists():
        raise FileNotFoundError(f"输入路径不存在: {input_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    if input_path.is_dir():
        return _convert_directory(input_path, out_dir, anonymize, notify)
    if not zipfile.is_zipfile(input_path):
        raise ValueError("输入必须是文件夹或 ZIP 压缩包")
    with tempfile.TemporaryDirectory(prefix="dxa_") as tmp:
        notify(f"解压 {input_path.name}")
        root = extract_zip(input_path, Path(tmp))
        return _convert_directory(root, out_dir, anonymize, notify)
