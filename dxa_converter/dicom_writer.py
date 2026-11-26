"""把原始计数数据块写成标准多帧 DICOM。

输出为 Multi-frame Grayscale Word Secondary Capture(uint16, 每帧一个通道),
像素值即设备记录的原始计数,不做任何缩放。
"""

import hashlib
from pathlib import Path
from typing import List, Optional

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRLittleEndian,
    MultiFrameGrayscaleWordSecondaryCaptureImageStorage,
    PYDICOM_IMPLEMENTATION_UID,
    generate_uid,
)

from dxa_converter.exam_reader import ExamInfoSchema
from dxa_converter.raw_reader import RawBlock

SERIES_NUMBER_BY_BLOCK = {"CA": 1, "DE": 2}
UID_PREFIX = "2.25."
ANONYMOUS_NAME = "ANONYMOUS"


def _entropy_key(exam: ExamInfoSchema) -> str:
    """同一患者同一次扫描的稳定标识,用于生成确定性的 Study UID。"""
    scan = exam.scan_time.isoformat() if exam.scan_time else ""
    return f"{exam.patient_key or ''}|{scan}|{exam.device_serial or ''}"


def make_study_uid(exam: ExamInfoSchema) -> str:
    """生成确定性的 Study Instance UID(同一次检查的多个文件共用)。"""
    return generate_uid(prefix=UID_PREFIX, entropy_srcs=[_entropy_key(exam)])


def _patient_age(exam: ExamInfoSchema) -> Optional[str]:
    if not (exam.birth_date and exam.scan_time):
        return None
    born, seen = exam.birth_date, exam.scan_time
    years = seen.year - born.year - ((seen.month, seen.day) < (born.month, born.day))
    return f"{years:03d}Y" if 0 <= years <= 999 else None


def _fill_patient(ds: Dataset, exam: ExamInfoSchema, anonymize: bool) -> None:
    key = exam.patient_key or ""
    if anonymize:
        ds.PatientName = ANONYMOUS_NAME
        ds.PatientID = "DXA" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12].upper()
        ds.PatientBirthDate = ""
        ds.PatientIdentityRemoved = "YES"
    else:
        ds.PatientName = exam.patient_name or ""
        ds.PatientID = key
        ds.PatientBirthDate = exam.birth_date.strftime("%Y%m%d") if exam.birth_date else ""
    ds.PatientSex = exam.sex or ""
    age = _patient_age(exam)
    if age:
        ds.PatientAge = age
    if exam.weight_kg:
        ds.PatientWeight = f"{exam.weight_kg:.1f}"
    if exam.height_cm:
        ds.PatientSize = f"{exam.height_cm / 100:.3f}"


def _fill_study(ds: Dataset, exam: ExamInfoSchema, study_uid: str) -> None:
    ds.StudyInstanceUID = study_uid
    ds.StudyID = "1"
    ds.AccessionNumber = ""
    ds.ReferringPhysicianName = ""
    if exam.scan_time:
        date, time = exam.scan_time.strftime("%Y%m%d"), exam.scan_time.strftime("%H%M%S")
    else:
        date = time = ""
    for prefix in ("Study", "Content", "Acquisition"):
        setattr(ds, f"{prefix}Date", date)
        setattr(ds, f"{prefix}Time", time)


def _comments(block: RawBlock, exam: ExamInfoSchema, source_name: str) -> str:
    chan, rows, cols = block.frames.shape
    parts: List[str] = [
        f"Hologic raw detector counts (uint16, unscaled), block {block.name}",
        f"{chan} channels stored as frames in file order; each frame {rows} rows x {cols} cols",
        f"source={source_name}",
        f"source_layout={block.layout}",
    ]
    if exam.param_38 or exam.param_39:
        parts.append(
            f"source_header_0x38={exam.param_38} 0x39={exam.param_39} (physical meaning unverified)"
        )
    return "; ".join(parts)


def write_raw_dicom(
    block: RawBlock,
    exam: ExamInfoSchema,
    out_path: Path,
    source_name: str,
    study_uid: str,
    anonymize: bool,
) -> Path:
    """把一个原始数据块写成 DICOM 文件。

    Args:
        block: 原始数据块,``frames`` 形状为 (通道, 行, 列)。
        exam: 检查信息。
        out_path: 输出文件路径。
        source_name: 源文件名(写入 ImageComments 便于追溯)。
        study_uid: 同一次检查共用的 Study Instance UID。
        anonymize: True 时不写入姓名与出生日期,患者 ID 改为哈希值。

    Returns:
        实际写入的路径。
    """
    sop_uid = generate_uid(prefix=UID_PREFIX)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = MultiFrameGrayscaleWordSecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID

    ds = Dataset()
    ds.file_meta = meta
    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = sop_uid
    ds.ImageType = ["ORIGINAL", "PRIMARY"]
    ds.Modality = "OT"
    ds.ConversionType = "WSD"
    _fill_patient(ds, exam, anonymize)
    _fill_study(ds, exam, study_uid)

    ds.Manufacturer = "Hologic"
    ds.DeviceSerialNumber = exam.device_serial or ""
    ds.SoftwareVersions = exam.software_version or ""
    if exam.protocol_path:
        ds.ProtocolName = exam.protocol_path.replace("\\", "/").split("/")[-1]
    ds.SeriesInstanceUID = generate_uid(
        prefix=UID_PREFIX, entropy_srcs=[study_uid, source_name, block.name]
    )
    ds.SeriesNumber = SERIES_NUMBER_BY_BLOCK.get(block.name, 99)
    ds.InstanceNumber = 1
    ds.SeriesDescription = f"Hologic DXA raw counts {block.name}"
    ds.ImageComments = _comments(block, exam, source_name)

    chan, rows, cols = block.frames.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.NumberOfFrames = chan
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelData = block.frames.tobytes()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(out_path, enforce_file_format=True)
    return out_path
