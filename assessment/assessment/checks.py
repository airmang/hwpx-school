"""[기계] 검사 — 통과는 형태 일치가 아니다(형태는 실한컴 렌더 육안으로만)."""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from assessment.md import Figure, Group, Item, Sheet, SideBySide
from assessment.ns import HP

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def png_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(_PNG_SIG) or data[12:16] != b"IHDR":
        raise ValueError("PNG 가 아니다")
    return struct.unpack(">II", data[16:24])


def _펼친_그림(blocks):
    for b in blocks:
        if isinstance(b, Figure):
            yield b
        elif isinstance(b, SideBySide):
            yield from b.figures


def _그림들(sheet: Sheet):
    for e in sheet.entries:
        if isinstance(e, Group):
            for b in _펼친_그림(e.blocks):
                yield f"[{e.first}-{e.last}] 묶음", b
        elif not isinstance(e, Item):
            for b in _펼친_그림((e,)):
                yield "문항 밖", b
    for it in sheet.items:
        for b in _펼친_그림(it.blocks):
            yield f"{it.number}번 문항", b


def check_sheet(sheet: Sheet, *, base_dir: Path) -> list[str]:
    문제: list[str] = []
    합 = sum(it.points for it in sheet.items)
    if 합 != sheet.total:
        문제.append(f"배점 합계가 total 과 다르다: 문항 합 {합}점 ≠ total {sheet.total}점")
    for it in sheet.items:
        if it.answer is None:
            문제.append(f"{it.number}번 문항에 :::정답 이 없다({it.line}번째 줄)")
    for e in sheet.entries:
        if isinstance(e, Group):
            if not e.items:
                문제.append(f"[{e.first}-{e.last}] 묶음에 문항이 없다({e.line}번째 줄)")
            elif (e.items[0].number, e.items[-1].number) != (e.first, e.last):
                문제.append(
                    f"묶음 번호 [{e.first}-{e.last}] 가 실제 문항 번호 "
                    f"[{e.items[0].number}-{e.items[-1].number}] 와 다르다({e.line}번째 줄)"
                )
    for 자리, fig in _그림들(sheet):
        경로 = base_dir / fig.path
        if not 경로.exists():
            문제.append(f"{자리}의 그림 파일이 없다: {fig.path}")
            continue
        try:
            png_size(경로.read_bytes())
        except ValueError:
            문제.append(f"{자리}의 그림이 PNG 가 아니다: {fig.path}")
    return 문제


# --- 산출물 검사 ---------------------------------------------------------------
def _섹션_뿌리들(path: Path) -> list[ET.Element]:
    with zipfile.ZipFile(path) as z:
        return [ET.fromstring(z.read(n)) for n in sorted(z.namelist()) if n.startswith("Contents/section")]


def _메모_수(뿌리들) -> int:
    return sum(1 for r in 뿌리들 for e in r.iter(f"{{{HP}}}fieldBegin") if e.get("type") == "MEMO")


def _본문_줄들(뿌리들) -> set[str]:
    """메모 속을 뺀 모든 문단의 글 — 문단 하나 = 한 줄.

    (주의: iter 는 메모 subList 안 문단까지 줍는다 — 정답용을 학생용 자리에 넣으면 정답 줄이
    걸리는 것은 의도다. 학생용에는 메모가 없다.)"""
    줄들: set[str] = set()
    for r in 뿌리들:
        for p in r.iter(f"{{{HP}}}p"):
            줄들.add("".join("".join(t.itertext()) for t in p.iter(f"{{{HP}}}t")).strip())
    return 줄들


def check_student(path: Path, sheet: Sheet) -> list[str]:
    뿌리들 = _섹션_뿌리들(path)
    문제: list[str] = []
    n = _메모_수(뿌리들)
    if n:
        문제.append(f"학생용에 메모가 {n}개 있다 — 0개여야 한다")
    줄들 = _본문_줄들(뿌리들)
    for it in sheet.items:
        for 답 in it.answer or ():
            if len(답.strip()) >= 4 and 답.strip() in 줄들:
                문제.append(f"학생용에 {it.number}번 정답 줄과 같은 글이 있다: {답.strip()!r}")
    return 문제


def check_answers(path: Path, sheet: Sheet) -> list[str]:
    n = _메모_수(_섹션_뿌리들(path))
    return [] if n == len(sheet.items) else [f"정답용 메모 수가 문항 수와 다르다: 메모 {n} ≠ 문항 {len(sheet.items)}"]
