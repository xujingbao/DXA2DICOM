# DXA2DICOM

把 Hologic 双能 X 线骨密度仪(DXA)导出的私有归档文件(`.pXX` / `.rXX`)还原为标准 DICOM。

- `.rXX`:原始探测器计数(uint16),按数据块解析后写成多帧 DICOM,每帧一个通道,像素值不做缩放。
- `.pXX`:患者与检查元数据(性别、年龄、身高体重、扫描时间、设备信息等),写入 DICOM 头。

## 使用

输入可以是文件夹或 ZIP,程序按文件名自动配对 `PAxxxxxA.pNN` 与 `PAxxxxxA.rNN`。

```bash
pip install -r requirements.txt

python -m dxa_converter                              # 图形界面(支持拖拽、预览)
python -m dxa_converter 某目录或.zip -o 输出目录        # 命令行
python -m dxa_converter 某目录 -o 输出目录 --keep-identity   # 保留姓名与出生日期
```

默认匿名化:不写入姓名与出生日期,患者 ID 改为哈希值。

输出为每个扫描一个子目录,内含 `*_CA.dcm` 与 `*_DE.dcm` 两个多帧文件(6 帧)。

## 限制

- 导出的是设备原始计数,不是设备显示的重建图,也不含 BMD / 软组织分解结果。
- DICOM 类型为多帧 Secondary Capture(`Modality=OT`),不是 Hologic 原生 DXA DICOM。
- 6 个通道的物理含义(推测为 3 组低能/高能)与 `PixelSpacing` 未确认,因此没有写 `PixelSpacing`。
- 体重(`0x403`)、身高(`0x404`)字段是按数值范围推断的,请与设备界面核对。

## 构建

```bash
# macOS(在 mac 上执行)
pip install pyinstaller
pyinstaller --noconfirm --windowed --name DXA2DICOM --paths . dxa_converter/__main__.py
```

Windows 包由 GitHub Actions 构建:推送 `v*` 标签(如 `git tag v0.2.0 && git push origin v0.2.0`),
构建完成后自动发布到 Release。也可在 Actions 页面手动运行 Build Windows。

## 许可与隐私

- 界面使用 `PySide6-Fluent-Widgets`,协议为 GPLv3;对外分发时需遵守,或购买其商业授权。
- 样本数据含真实患者信息,不要提交到仓库。`.gitignore` 为白名单,只放行应用源码。

## 目录

```
dxa_converter/
  records.py       记录解析(tag u16 + len u32)
  raw_reader.py    读取 .rXX 数据块
  exam_reader.py   读取 .pXX 元数据
  dicom_writer.py  写 DICOM
  discovery.py     查找 .p/.r 配对、解压 ZIP
  converter.py     转换流程
  cli.py           命令行
  gui.py / gui_style.py / gui_worker.py / preview.py   图形界面
```
