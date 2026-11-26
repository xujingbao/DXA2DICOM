"""命令行入口:批量转换目录或 ZIP。"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from dxa_converter.converter import convert_input


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="dxa_converter", description="Hologic DXA 归档文件转 DICOM"
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="目录或 ZIP,可多个")
    parser.add_argument("-o", "--output", required=True, type=Path, help="输出目录")
    parser.add_argument(
        "--keep-identity",
        action="store_true",
        help="保留姓名与出生日期(默认匿名化)",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """命令行主函数。

    Args:
        argv: 参数列表,默认取 sys.argv。

    Returns:
        进程退出码: 0 全部成功, 1 存在失败。
    """
    args = build_parser().parse_args(argv)
    failed = False
    for path in args.inputs:
        try:
            results = convert_input(
                path, args.output, not args.keep_identity, progress=print
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"错误 {path}: {exc}", file=sys.stderr)
            failed = True
            continue
        failed = failed or any(r.error for r in results) or not results
    return 1 if failed else 0
