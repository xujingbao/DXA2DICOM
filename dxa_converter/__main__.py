"""入口:带参数走命令行,不带参数打开图形界面。"""

import sys


def run() -> int:
    """根据命令行参数选择 CLI 或 GUI。"""
    if len(sys.argv) > 1:
        from dxa_converter.cli import main

        return main()
    from dxa_converter.gui import run_gui

    return run_gui()


if __name__ == "__main__":
    sys.exit(run())
