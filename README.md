# DXA2DICOM

把 Hologic 双能 X 线骨密度仪(DXA)导出的私有归档文件(`.pXX` / `.rXX`)还原为标准 DICOM。

- `.rXX`:原始探测器计数(uint16),按数据块解析后写成多帧 DICOM,每帧一个通道,像素值不做缩放。
- `.pXX`:患者与检查元数据(性别、年龄、身高体重、扫描时间、设备信息等),写入 DICOM 头。
- 成像参数:从 `.pXX` 中提取设备配置、校准与分析参数,界面可查看,并写入 DICOM 私有标签。

## 下载

https://dxa2dicom.com/download/ ,提供 Windows(zip,免安装)与 macOS(Apple 芯片 / Intel 芯片 dmg)。
也可在本仓库 Releases 页面下载。

> 安装包暂无代码签名:macOS 首次打开需在“系统设置 → 隐私与安全性”手动放行,Windows 会出现 SmartScreen “未知发布者”提示。

## 使用

输入可以是文件夹或 ZIP,程序按文件名自动配对 `PAxxxxxA.pNN` 与 `PAxxxxxA.rNN`。

```bash
pip install -r requirements.txt

python -m dxa_converter                              # 图形界面(支持拖拽、预览)
python -m dxa_converter 某目录或.zip -o 输出目录        # 命令行
python -m dxa_converter 某目录 -o 输出目录 --keep-identity   # 保留姓名与出生日期
```

默认匿名化:不写入姓名与出生日期,患者 ID 改为哈希值。

输出为每个扫描一个子目录(`<文件名>_<编号>/`),内含 `*_CA.dcm` 与 `*_DE.dcm` 两个多帧文件(6 帧)。同一次扫描的文件共用 Study UID。

### 图形界面

- 选择数据:文件夹或 ZIP,支持拖拽;输出目录默认 `<输入>/DICOM_output`,并记住上次选择。
- 预览:按扫描、数据块分页查看各通道,点击缩略图放大。右上开关切换显示方式:
  - 逐通道拉伸(1%–99%):每个通道各自拉伸,便于看结构;
  - 统一窗宽:各通道使用同一窗宽,亮度可横向比较。
  - 该开关只影响显示,不改变导出的像素值。
- 成像参数:预览中的“成像参数”页签,含检查信息(不含姓名、出生日期)与各参数块,支持搜索过滤。

### DICOM 私有标签

成像参数以 `key = value` 文本写入私有块 `(0029,0010)`,creator 为 `DXA2DICOM`:

| 标签 | 内容 |
|---|---|
| `(0029,1001)` | 设备配置 |
| `(0029,1002)` | 校准与分析参数 |
| `(0029,1003)` | 分析设置 |

设备配置中的 `patient_id`、`customer` 始终不写入。参数含义以 Hologic 为准,本工具只原样提取。

## 限制

- 导出的是设备原始计数,不是设备显示的重建图,也不含 BMD / T 值 / Z 值 / 软组织分解结果。
- DICOM 类型为多帧 Secondary Capture(`Modality=OT`),不是 Hologic 原生 DXA DICOM。
- 6 个通道的物理含义(推测为 3 组低能/高能)与 `PixelSpacing` 未确认,因此没有写 `PixelSpacing`。
- 体重(`0x403`)、身高(`0x404`)字段是按数值范围推断的,请与设备界面核对。
- 目前只在同一台设备(序列号 310376M)的脊柱类扫描样本上验证过,其他部位与机型未验证。
- `.pXX` 内的两张 8 位处理图尚未导出。

## 构建

```bash
# macOS(在 mac 上执行)
pip install pyinstaller
pyinstaller --noconfirm --windowed --name DXA2DICOM --paths . dxa_converter/__main__.py
```

发布由 GitHub Actions 完成:改 `dxa_converter/__init__.py` 中的版本号并推送后,推送 `v*` 标签(如 `git tag v0.2.1 && git push origin v0.2.1`),
Windows 与 macOS(arm64 / x64)两个工作流会把安装包发布到同一个 Release:

- `.github/workflows/build-windows.yml` → `DXA2DICOM-windows.zip`
- `.github/workflows/build-macos.yml` → `DXA2DICOM-macos-arm64.dmg`、`DXA2DICOM-macos-x64.dmg`

也可在 Actions 页面手动运行。官网页面源码在 `web/`,安装包不入库。

## 许可与隐私

- 界面使用 `PySide6-Fluent-Widgets`,协议为 GPLv3;对外分发时需遵守,或购买其商业授权。
- 样本数据含真实患者信息,不要提交到仓库。`.gitignore` 为白名单,只放行应用源码。

## 目录

```
dxa_converter/
  records.py       记录解析(tag u16 + len u32)
  raw_reader.py    读取 .rXX 数据块
  exam_reader.py   读取 .pXX 元数据
  params_reader.py 读取成像参数文本块
  dicom_writer.py  写 DICOM(含私有参数标签)
  discovery.py     查找 .p/.r 配对、解压 ZIP
  converter.py     转换流程
  cli.py           命令行
  gui.py / gui_style.py / gui_worker.py   图形界面
  preview.py / params_panel.py            预览与成像参数面板
web/               官网源码(dxa2dicom.com)
.github/workflows/ 构建与发布
```
