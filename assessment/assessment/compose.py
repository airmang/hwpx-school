"""마크다운 + 킷 → 학생용·정답용 hwpx. 검사 문제가 하나라도 있으면 아무것도 쓰지 않는다."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from assessment.backends.hwpx import HwpxWriter
from assessment.blocks import plan_sheet
from assessment.checks import check_answers, check_sheet, check_student
from assessment.kit import load_kit
from assessment.md import parse_sheet


@dataclass(frozen=True)
class ComposeReport:
    student: Path
    answers: Path
    items: int
    memos: int


def output_paths(out: Path) -> tuple[Path, Path]:
    out = Path(out)
    if out.suffix.lower() != ".hwpx":
        raise ValueError(f"출력은 .hwpx 여야 한다: {out.name}")
    return out.with_name(f"{out.stem}_학생용.hwpx"), out.with_name(f"{out.stem}_정답용.hwpx")


def _임시_경로(대상: Path) -> Path:
    fd, 이름 = tempfile.mkstemp(prefix=대상.name + ".", suffix=".tmp", dir=str(대상.parent))
    os.close(fd)
    return Path(이름)


def compose(md_path: Path, kit_root: Path, out: Path) -> ComposeReport:
    """검사까지 통과한 뒤에만 기존 산출물을 교체한다(원자적).

    두 파일을 대상 폴더의 임시 이름으로 먼저 쓰고, 그 임시 파일에 check_student·
    check_answers 를 돌린 뒤, 전부 통과했을 때만 os.replace 로 실제 이름에 올린다.
    도중에 무엇이 실패하든(그림 폭 초과·검사 문제·그 밖의 예외) 임시 파일만 지우고
    기존에 있던 쌍은 그대로 둔다 — extract_skeleton 의 fail-closed 패턴과 같다.
    """
    md_path = Path(md_path)
    sheet = parse_sheet(md_path.read_text(encoding="utf-8"))
    kit = load_kit(kit_root)
    if sheet.kit != kit.name:
        raise ValueError(f"킷 이름이 다르다: md={sheet.kit} 킷={kit.name}")
    문제 = check_sheet(sheet, base_dir=md_path.parent)
    if 문제:
        raise ValueError("\n".join(문제))
    학생, 정답 = output_paths(out)
    학생.parent.mkdir(parents=True, exist_ok=True)
    임시_학생 = _임시_경로(학생)
    임시_정답 = _임시_경로(정답)
    try:
        for 임시경로, answers in ((임시_학생, False), (임시_정답, True)):
            w = HwpxWriter(kit)
            for plan in plan_sheet(sheet, kit, base_dir=md_path.parent, answers=answers):
                w.draw(plan)
            w.save(임시경로)
        문제 = check_student(임시_학생, sheet) + check_answers(임시_정답, sheet)
        if 문제:
            raise ValueError("\n".join(문제))
    except BaseException:
        임시_학생.unlink(missing_ok=True)
        임시_정답.unlink(missing_ok=True)
        raise
    # 마지막 교체(학생 → 정답 순서로 os.replace 두 번)도 POSIX 가 허락하는 한
    # 전부-아니면-전무로 만든다: 기존 학생용이 있으면 먼저 백업으로 치워 두고,
    # 정답 교체가 실패하면 그 백업으로 되돌리고(없었으면 새 학생용을 지우고)
    # 남은 임시 파일을 모두 지운 뒤 다시 던진다. 성공하면 백업만 지운다.
    학생_백업 = _임시_경로(학생) if 학생.exists() else None
    if 학생_백업 is not None:
        os.replace(학생, 학생_백업)
    try:
        os.replace(임시_학생, 학생)
        os.replace(임시_정답, 정답)
    except OSError:
        if 학생_백업 is not None:
            os.replace(학생_백업, 학생)
        else:
            학생.unlink(missing_ok=True)
        임시_학생.unlink(missing_ok=True)
        임시_정답.unlink(missing_ok=True)
        raise
    if 학생_백업 is not None:
        학생_백업.unlink(missing_ok=True)
    return ComposeReport(학생, 정답, len(sheet.items), len(sheet.items))
