"""문항 트리 → 조판 계획. 킷의 키 이름만 알고 스타일 번호는 모른다."""

from __future__ import annotations

import re
from pathlib import Path

from assessment.checks import png_size
from assessment.kit import Kit
from assessment.md import (
    AnswerGrid, AnswerLine, Block, ColumnBreak, DataTable, Figure, Group, Hint, Item,
    LabeledLines, Lines, Passage, Sheet, SideBySide, Text,
)
from assessment.plan import (
    HWPUNIT_PER_MM, CellPlan, ColumnBreakPlan, ParaPlan, PicturePlan, Plan, RunPlan,
    TablePlan, TitlePlan,
)

_제목_꼬리 = re.compile(r"^(?P<main>.*?)(?P<suffix>\([^()]*\))$")
_첫_숫자 = re.compile(r"\d+")


class InputError(ValueError):
    """구조는 맞지만 값이 조판 불가능한 입력 오류 — cli 는 이걸 종료코드 2(한 줄)로 다룬다.

    (check_sheet 가 담는 "검사 문제" 목록과 달리, 이건 문항 트리만으로는 못 잡고
    실제로 계획을 세워봐야 드러난다 — 예: 그림 폭이 칸 안쪽보다 넓다.)"""


def _para(text: str, char: str = "body", para: str = "body") -> ParaPlan:
    return ParaPlan((RunPlan(text, char),), para)


def _균등(합: int, n: int) -> tuple[int, ...]:
    몫, 나머지 = divmod(합, n)
    return tuple(몫 + (1 if i < 나머지 else 0) for i in range(n))


def plan_title(sheet: Sheet) -> TitlePlan:
    m = _제목_꼬리.match(sheet.title)
    main, suffix = (m["main"], m["suffix"]) if m and m["main"] else (sheet.title, None)
    return TitlePlan(main, suffix, f"({sheet.score})" if sheet.score else None)


def _그림_칸(kit: Kit, fig: Figure, base_dir: Path, 칸폭: int) -> CellPlan:
    """그림 칸 하나 — 그림 폭은 width 가 없으면 칸 안쪽 폭, 있으면 그 값(안쪽 초과는 InputError)."""
    안쪽 = 칸폭 - kit.furniture["cellInnerMargin"]
    경로 = (base_dir / fig.path).resolve()
    px_w, px_h = png_size(경로.read_bytes())
    폭 = 안쪽 if fig.width_mm is None else round(fig.width_mm * HWPUNIT_PER_MM)
    if 폭 > 안쪽:
        raise InputError(f"그림 폭이 칸 안쪽보다 넓다: {fig.path} {폭} > {안쪽} HWPUNIT — width 를 줄인다")
    그림 = PicturePlan(경로, 폭, 폭 * px_h // px_w)
    캡션_문단 = "caption_left" if fig.caption_align == "left" else None
    return CellPlan("figure", fig.caption, 그림, 캡션_문단)


def plan_block(kit: Kit, b: Block, base_dir: Path) -> Plan:
    w = kit.furniture["widths"]
    match b:
        case Text(text):
            return _para(text)
        case Hint(text):
            return _para(text, char="hint")
        case Passage(kind, lines):
            # 안내(문항 밖 블록)는 조건과 같은 상자.
            역할, 폭 = ("passage", w["passage"]) if kind == "제시문" else ("condition", w["box"])
            return TablePlan(((CellPlan(역할, lines),),), (폭,))
        case DataTable(header, rows):
            n = len(header)
            cols = (w["box"],) if n == 1 else (w["dataLabel"], *_균등(w["box"] - w["dataLabel"], n - 1))
            # 머리 행(여러 줄일 수 있다)은 음영, 몸은 흰 칸. 가려진 칸("")은 백엔드가 건너뛴다.
            head = tuple(tuple(CellPlan("data_head", (h,)) for h in r) for r in b.head_rows)
            body = tuple(tuple(CellPlan("data", (c,)) for c in r) for r in rows)
            return TablePlan((*head, *body), cols, b.merges)
        case Figure():
            return TablePlan(((_그림_칸(kit, b, base_dir, w["box"]),),), (w["box"],))
        case SideBySide(figures):
            # 나란히: 한 행 N칸, 칸 폭은 박스 폭 균등.
            폭들 = _균등(w["box"], len(figures))
            return TablePlan((tuple(_그림_칸(kit, f, base_dir, 폭) for f, 폭 in zip(figures, 폭들)),), 폭들)
        case AnswerLine(labels):
            # 밑줄은 칸 아래 테두리라 답칸이 붙어 있으면 한 줄로 이어진다 — 사이에 테두리 없는 틈 칸.
            n, 틈 = len(labels), w["answerGap"]
            답폭 = _균등(w["answerLine"] - 틈 * (n - 1), n)
            칸들: list[CellPlan] = []
            폭들: list[int] = []
            for i, (l, 폭) in enumerate(zip(labels, 답폭)):
                if i:
                    칸들.append(CellPlan("answer_gap"))
                    폭들.append(틈)
                칸들.append(CellPlan("answer_line", (l,)))
                폭들.append(폭)
            return TablePlan((tuple(칸들),), tuple(폭들))
        case AnswerGrid(labels):
            return TablePlan(
                tuple((CellPlan("grid_label", (l,)), CellPlan("grid_blank")) for l in labels),
                (w["gridLabel"], w["box"] - w["gridLabel"]),
            )
        case Lines(count):
            역할 = "single" if count == 1 else "rule"
            return TablePlan(tuple((CellPlan(역할),) for _ in range(count)), (w["box"],))
        case LabeledLines(labels):
            return TablePlan(tuple((CellPlan("labeled", (f"{l} : ",)),) for l in labels), (w["box"],))
        case ColumnBreak():
            return ColumnBreakPlan()
    raise TypeError(f"계획할 수 없는 블록: {type(b).__name__}")


def plan_item(kit: Kit, it: Item, base_dir: Path, answers: bool) -> list[Plan]:
    발문 = ParaPlan(
        (RunPlan(f"{it.number}. {it.prompt} ", "body"),
         RunPlan(f"[{it.points_text}]", "body", it.answer if answers else None)),
        "body",
    )
    return [발문, *(plan_block(kit, b, base_dir) for b in it.blocks), _para("")]


def plan_footer(kit: Kit, sheet: Sheet) -> list[Plan]:
    f = kit.furniture["footer"]
    w = kit.furniture["widths"]["score"]
    out: list[Plan] = [_para("", "note", "center")]
    out += [_para(줄.format(n=len(sheet.items)), "note", "center") for 줄 in f["lines"]]
    out.append(_para("", "note", "footer_gap"))
    m = _첫_숫자.search(sheet.score or "")
    환산 = f"   /{m.group()}" if m else ""
    득점표 = TablePlan(
        (
            (CellPlan("score_head", (f["scoreHead"][0],)), CellPlan("score_head"), CellPlan("score_head", (f["scoreHead"][1],))),
            (CellPlan("score_value", (f"   /{sheet.total}",)), CellPlan("score_value"), CellPlan("score_value", (환산,) if 환산 else ())),
            (CellPlan("sign_label", (f["signLabel"],)), CellPlan("sign", tuple(f["signLines"])), CellPlan("sign")),
        ),
        tuple(w),
        ((0, 0, 0, 1), (1, 0, 1, 1), (2, 1, 2, 2)),
    )
    out.append(득점표)
    return out


def plan_sheet(sheet: Sheet, kit: Kit, *, base_dir: Path, answers: bool) -> list[Plan]:
    계획: list[Plan] = [plan_title(sheet)]
    for e in sheet.entries:
        if isinstance(e, ColumnBreak):
            계획.append(ColumnBreakPlan())
        elif isinstance(e, Group):
            계획.append(_para(f"[{e.first}-{e.last}] {e.prompt}"))
            계획 += [plan_block(kit, b, base_dir) for b in e.blocks]
            계획.append(_para(""))
            for it in e.items:
                계획 += plan_item(kit, it, base_dir, answers)
        elif isinstance(e, Item):
            계획 += plan_item(kit, e, base_dir, answers)
        else:  # 문항 밖 블록 — 그 자리에 블록 그대로, 뒤에 빈 줄 하나.
            계획 += [plan_block(kit, e, base_dir), _para("")]
    계획 += plan_footer(kit, sheet)
    return 계획
