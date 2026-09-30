"""조판 계획 — 무엇을 그릴지(칸 역할·글·그림·폭). 문서 객체를 모른다(형식 무관).
단위는 HWPUNIT(1/7200 인치). 파생값은 여기서 한 번만 계산해 백엔드가 그대로 쓴다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

HWPUNIT_PER_MM = 7200 / 25.4

# 셀 역할 → (borderFill 킷 키, paraPr 킷 키, charPr 킷 키, rowHeight 킷 키). 숫자는 kit.json 에만.
CELL_ROLES: dict[str, tuple[str, str, str, str]] = {
    "passage": ("box", "passage", "body", "auto"),
    "condition": ("box", "body", "body", "auto"),
    "answer_line": ("underline", "body", "answer_label", "auto"),
    "answer_gap": ("none", "body", "blank", "auto"),
    "grid_label": ("shade", "center", "body", "grid"),
    "grid_blank": ("box", "body", "blank", "grid"),
    "rule": ("rule", "body", "blank", "rule"),
    "single": ("box", "body", "blank", "single"),
    "labeled": ("box", "body", "body", "labeled"),
    "data_head": ("shade", "center", "body", "auto"),
    "data": ("box", "center", "body", "auto"),
    "figure": ("box", "center", "body", "auto"),
    "score_head": ("shade", "center", "score", "auto"),
    "score_value": ("box", "score_value", "title", "score"),
    "sign_label": ("shade", "center", "score", "score"),
    "sign": ("box", "center", "score", "score"),
}


@dataclass(frozen=True)
class RunPlan:
    text: str
    char: str
    memo: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ParaPlan:
    runs: tuple[RunPlan, ...]
    para: str


@dataclass(frozen=True)
class PicturePlan:
    path: Path
    width: int
    height: int


@dataclass(frozen=True)
class CellPlan:
    role: str
    lines: tuple[str, ...] = ()
    picture: PicturePlan | None = None
    # 그림 칸의 캡션 문단 모양(킷 paraPr 키 이름). None 이면 role 의 paraPr 을 그대로 쓴다(가운데).
    caption_para: str | None = None


@dataclass(frozen=True)
class TablePlan:
    rows: tuple[tuple[CellPlan, ...], ...]
    col_widths: tuple[int, ...]
    merges: tuple[tuple[int, int, int, int], ...] = ()

    @property
    def width(self) -> int:
        return sum(self.col_widths)


@dataclass(frozen=True)
class TitlePlan:
    main: str
    suffix: str | None
    score: str | None


@dataclass(frozen=True)
class ColumnBreakPlan:
    pass


Plan = TitlePlan | ParaPlan | TablePlan | ColumnBreakPlan
