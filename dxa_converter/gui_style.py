"""界面主题与少量自定义样式(组件本身的外观由 qfluentwidgets 负责)。"""

from qfluentwidgets import Theme, isDarkTheme, setTheme, setThemeColor

ACCENT = "#2f6fed"


def apply_theme() -> None:
    """跟随系统明暗主题,并设置强调色。"""
    setTheme(Theme.AUTO)
    setThemeColor(ACCENT)


def window_style() -> str:
    """窗口背景与缩略图底色(随当前明暗主题)。"""
    background = "#202020" if isDarkTheme() else "#f3f3f3"
    return f"""
#root {{ background-color: {background}; }}
QLabel#thumb {{
    background-color: #1c1c1e;
    border-radius: 6px;
    padding: 4px;
}}
"""
