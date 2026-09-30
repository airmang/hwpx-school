"""조판 계획 — 무엇을 그릴지(칸 역할·글·그림·폭·높이). 문서 객체를 모른다(형식 무관).

단위는 HWPUNIT(1/7200 인치). 블록 계획자(`worksheet.blocks`)와 가구 계획자(`worksheet.furniture`)가
만들고, 형식별 백엔드(`worksheet.backends.*`)가 그린다 — 파생값(행 높이·열 폭·그림 크기)을 계획에서
한 번만 계산하므로 두 형식이 같은 숫자를 쓴다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worksheet.kit import Kit

# 셀 역할 → (borderFill 킷 키 또는 None, paraPr 킷 키, charPr 킷 키, rowHeight 킷 키).
# borderFill 이 None 이면 표의 기본 테두리(plain/grid)를 그대로 둔다.
CELL_ROLES: dict[str, tuple[str | None, str, str, str]] = {
    "label": ("shade", "label", "label", "label"),
    "cell": (None, "cell", "cell", "cell"),
    "answer": ("answer", "cell", "cell", "answer"),
}


@dataclass(frozen=True)
class PicturePlan:
    path: Path        # 절대경로
    width: int        # 배치 폭
    height: int       # 배치 높이
    px_width: int
    px_height: int


@dataclass(frozen=True)
class CellPlan:
    role: str                          # CELL_ROLES 의 키
    text: str = ""
    picture: PicturePlan | None = None
    width: int | None = None           # None = 표의 열 폭
    height: int | None = None          # None = 역할의 기본 rowHeight
    nested: TablePlan | None = None    # 이 칸 안에 들어가는 표(강조박스)


@dataclass(frozen=True)
class TablePlan:
    block: str
    rows: tuple[tuple[CellPlan, ...], ...]
    height: int | None                 # 표 높이 합
    border: str = "plain"              # 표 기본 borderFill 역할
    equal_columns: bool = False
    width: int | None = None           # None = 본문 폭(중첩표는 담는 칸 안쪽)


@dataclass(frozen=True)
class ParagraphPlan:
    text: str
    para: str
    char: str


@dataclass(frozen=True)
class FigurePlan:
    path: Path
    width_mm: float
    height_mm: float


BlockPlan = TablePlan | ParagraphPlan | FigurePlan


@dataclass(frozen=True)
class BandPlan:
    title: str
    teacher_lines: tuple[str, ...]   # 슬롯을 채운 교사칸 문단들
    name_lines: tuple[str, ...]      # 슬롯을 채운 이름칸 문단들
    stamp: bool                      # 이 회차에 확인도장이 있는가(섹션 제목이 하나라도 있으면 참)


@dataclass(frozen=True)
class HeadingPlan:
    number: int
    text: str
    textbook_ref: str | None         # textbookFormat 을 채운 문구
    stamp: bool                      # hwpx 는 첫 제목 문단에 도장을 띄운다


@dataclass(frozen=True)
class KeywordPagePlan:
    head: str
    rows: int


Plan = BlockPlan | BandPlan | HeadingPlan | KeywordPagePlan


def column_widths(plan: TablePlan, kit: Kit, *, 폭: int | None = None) -> list[int]:
    """열 폭 — python-hwpx `equalize_column_widths()` 와 같은 분배(앞 열 round(W/n), 마지막 열이
    나머지)를 쓴다. 균등이 아니면 첫 행 칸들의 `width` 를 쓴다(라벨설명). 한 열 표는 표 폭 하나.

    중첩표(강조박스)는 호출자가 `폭=`(담는 칸의 안쪽 폭)을 넘겨야 한다 — 중첩표의 `width` 는
    보통 None 이라, 안 넘기면 본문 폭으로 떨어진다."""
    전체 = 폭 if 폭 is not None else (plan.width if plan.width is not None else kit.body_width)
    열수 = len(plan.rows[0])
    if 열수 == 1:
        return [전체]
    if plan.equal_columns:
        앞 = round(전체 / 열수)
        return [앞] * (열수 - 1) + [전체 - 앞 * (열수 - 1)]
    폭들 = [칸.width for 칸 in plan.rows[0]]
    if any(w is None for w in 폭들):
        raise ValueError(f"{plan.block}: 균등이 아닌 표는 첫 행 칸 폭이 모두 있어야 한다")
    return [int(w) for w in 폭들]
