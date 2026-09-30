"""킷 스타일의 실제 값 — 한글 스타일 번호를 모르는 형식(docx)이 쓰는, 형식에 매이지 않는 값 타입.

스켈레톤에서 값을 푸는 일은 `worksheet.kit_style.resolve_kit` 이 한다."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CharStyle:
    face: str
    size_pt: float
    bold: bool
    underline: bool
    color: str


@dataclass(frozen=True)
class ParaStyle:
    align: str
    line_percent: int | None


@dataclass(frozen=True)
class Side:
    kind: str
    width_mm: float
    color: str


@dataclass(frozen=True)
class BoxStyle:
    left: Side
    right: Side
    top: Side
    bottom: Side
    fill: str | None


@dataclass(frozen=True)
class PageStyle:
    width: int
    height: int
    left: int
    right: int
    top: int
    bottom: int
    header: int
    footer: int


@dataclass(frozen=True)
class ResolvedKit:
    char: dict[str, CharStyle]
    para: dict[str, ParaStyle]
    box: dict[str, BoxStyle]
    page: PageStyle
