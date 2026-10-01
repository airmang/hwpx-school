"""역변환 입력 — 원안지 `.hwp`·`.hwpx`를 python-hwpx로 연다(한/글로 다시 저장하지 않는다).

`.hwp`는 `HwpxDocument.open`이 HWPX 문서 모형으로 바꾼다. 바꾸지 못한 내용(conversion_report.unconverted)이 하나라도
있으면 원고가 원본과 달라지므로 멈춘다 — 그때의 예비 경로는 한/글에서 hwpx로 저장해 다시 넣는 것이다. HWPX에 담을
자리가 없는 데이터(dropped)는 한/글의 hwpx 저장도 버리는 것이라 멈추지 않고 알림으로 남긴다.
그림(BinData)은 hwpx 패키지에서 읽으므로 `.hwp`는 변환 사본을 work 폴더에 저장해 두고 그 파일을 쓴다.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

from hwpx.document import HwpxDocument

HWP_SUFFIXES = (".hwp", ".hwpx")


class SourceError(ValueError):
    """원안지를 원고로 되돌릴 입력으로 쓸 수 없다(형식·변환 손실)."""


@dataclass
class Source:
    doc: HwpxDocument
    path: Path    # 받은 파일
    hwpx: Path    # 그림을 읽을 hwpx 패키지(.hwp면 변환 사본)
    notes: list[str] = field(default_factory=list)  # 보고서에 남길 알림(변환이 버린 데이터 등)


def _counts(m) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(m.items()))


def open_source(path: Path, work: Path) -> Source:
    """`.hwp`·`.hwpx` → Source. `.hwp`는 work/<이름>_변환.hwpx로 저장한 사본을 다시 연다(그림·부품을 hwpx로 읽게)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".hwpx":
        return Source(HwpxDocument.open(str(path)), path, path)
    if suffix != ".hwp":
        raise SourceError(f"원안지는 {' 또는 '.join(HWP_SUFFIXES)}여야 한다: {path.name}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # 바꾸지 못한 내용은 아래에서 conversion_report로 따로 멈춘다
        doc = HwpxDocument.open(str(path))
    report = doc.conversion_report
    notes = []
    if report is not None:
        if report.unconverted:
            raise SourceError(f"{path.name}: python-hwpx가 hwp에서 바꾸지 못한 내용이 있다({_counts(report.unconverted)}) — "
                              "원고가 원본과 달라진다. 한/글에서 hwpx로 저장해 그 파일을 넣는다")
        if report.dropped:
            notes.append(f"hwp 변환이 HWPX에 자리가 없는 데이터를 뺐다({_counts(report.dropped)}) — 한/글의 hwpx 저장도 버리는 것")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    copy = work / f"{path.stem}_변환.hwpx"
    doc.save_to_path(str(copy))
    return Source(HwpxDocument.open(str(copy)), path, copy, notes)
