"""hwpx 그리기 — 계획(`worksheet.plan`)을 python-hwpx 로 그린다. 킷의 스타일 번호를 그대로 쓴다."""

from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument

from worksheet.blocks import plan_node
from worksheet.furniture import plan_band, plan_heading, plan_keyword_page
from worksheet.kit import Kit
from worksheet.md import Node
from worksheet.ns import HP
from worksheet.plan import (
    CELL_ROLES,
    BandPlan,
    BlockPlan,
    FigurePlan,
    HeadingPlan,
    KeywordPagePlan,
    ParagraphPlan,
    PicturePlan,
    Plan,
    TablePlan,
)


class _칸그림:
    """이미 등록된 이진 항목 id 와 배치 크기 — `_셀` 의 `그림=` 인자."""

    def __init__(self, item_id: str, width: int, height: int) -> None:
        self.item_id, self.width, self.height = item_id, width, height


# --- 셀 하나에 글·테두리/음영·문단/글자 서식·행 높이를 함께 입히는 유일한 자리 -------------
# 원인: python-hwpx 의 add_table 은 셀 문단을 paraPr 0 / charPr 0(10pt 보통 바탕체·양쪽
# 정렬)으로 만든다. `add_band`(머리띠)의 칸 서식 루프와 달리, 블록 10종의 셀은 이 헬퍼가
# 없으면 그 기본값에 그대로 남는다 — 이 헬퍼 하나로 셀 서식 로직을 한 곳에 모은다.


def _셀(
    표, 행: int, 열: int, 글: str, *, kit: Kit, 역할: str,
    폭: int | None = None, 높이: int | None = None, 그림: _칸그림 | None = None,
) -> None:
    """셀 하나에 글(또는 그림)·테두리/음영·문단/글자 서식·행 높이를 함께 입힌다.

    역할: "label"(음영 머리·라벨 칸) | "cell"(본문 칸) | "answer"(학생이 쓰는 답 칸).
    **빈 칸에도 서식을 입힌다** — 학생이 쓰거나 교사가 나중에 채울 칸의 줄 높이·글꼴도
    양식을 따라야 한다.

    내용(글 또는 그림)을 먼저 쓰고 서식을 나중에 입힌다(`add_band`와 같은 순서) — 거꾸로
    하면 python-hwpx 가 문단을 다시 만들며 서식을 지울 수 있다(실측: `HwpxOxmlTableCell.
    set_text`의 `split_paragraphs` 경로). `그림`을 주면 `글` 대신 그 그림을 칸의 첫 문단에
    앉힌다(칸 안 그림 — `_표_그리기`가 그리기 전에 `_그림_등록`으로 이미 등록해 둔
    값이다) — 이 갈래도 "내용 먼저" 순서를 지킨다. 이어지는 para/charPr 루프는 문단 안의
    모든 run에 적용되므로(python-hwpx의 charPr 세터가 그렇게 동작한다 — 실측) 그림 run도
    같이 킷 값을 받는다 — 그림에 따로 charPr를 넘기지 않는 이유다.

    높이: 역할의 기본 rowHeight 대신 쓸 값 — 라벨설명·비교표의 머리열처럼 한 행의 여러
        칸이 같은 높이여야 하는 자리에 쓴다("한 행 = 한 높이"가 일반 규칙이다 — §2.1 참고).

    그림 칸의 문단은 역할이 무엇이든(label/cell/answer) `center`로 정렬한다 — 학습지
    양식에서 그림을 담은 칸은 대개 가운데 정렬이다. 글자 칸(그림이 없는 칸)은 역할
    그대로(`파라_키`)를 쓴다 — 정렬이 바뀌는 것은 그림 칸뿐이다.
    """
    if 역할 not in CELL_ROLES:
        raise ValueError(f"모르는 셀 역할: {역할!r}")
    보더_키, 파라_키, 캐릭_키, 높이_키 = CELL_ROLES[역할]

    if 그림 is not None:
        표.cell(행, 열).paragraphs[0].add_picture(그림.item_id, width=그림.width, height=그림.height)
    else:
        표.set_cell_text(행, 열, 글)
    if 보더_키 is not None:
        표.set_cell_border_fill(행, 열, kit.border_fill[보더_키])
    표.cell(행, 열).set_size(
        width=폭, height=높이 if 높이 is not None else kit.furniture["rowHeight"][높이_키]
    )
    문단_파라_키 = "center" if 그림 is not None else 파라_키
    for 문단 in 표.cell(행, 열).paragraphs:
        문단.para_pr_id_ref = kit.para_pr[문단_파라_키]
        문단.char_pr_id_ref = kit.char_pr[캐릭_키]


def _그림_등록(doc: HwpxDocument, 그림: PicturePlan, 캐시: dict[Path, str]) -> _칸그림:
    """칸 그림 하나를 이진 항목으로 등록하고 배치 크기와 묶는다.

    같은 파일을 조판 1회 안에서 여러 칸에 쓰면(캐시 적중) 다시 읽거나 `doc.media.add_image`로
    다시 등록하지 않는다 — BinData에 같은 그림이 여러 번 들어가는 것을 막는다. 캐시 키는
    계획이 정한 절대경로다.
    """
    item_id = 캐시.get(그림.path)
    if item_id is None:
        item_id = doc.media.add_image(그림.path.read_bytes(), "png").item_id
        캐시[그림.path] = item_id
    return _칸그림(item_id, 그림.width, 그림.height)


def _강조박스_빈_선행_문단_제거(칸) -> None:
    """`add_table()`이 중첩표를 새 문단에 넣어, `_셀`이 이미 만든 빈 문단이 그 앞에 그대로
    남는다(문단 2개: `('', 표 없음)` 다음 `('', 표 있음)`) — 실한컴에서 제목 행과 상자 사이에
    빈 줄로 보인다.

    `HwpxOxmlParagraph.remove()`는 `self.section.element`(섹션 직속)에서 형제를 찾는다 —
    표 셀 안 문단(부모가 `hp:subList`)엔 못 쓴다: 대상이 그 부모의 직계 자식이 아니라서
    `ET.remove()`가 `ValueError`를 던지고, 라이브러리는 그 예외를 조용히 삼켜(`except
    ValueError: return`) 아무 일도 안 하고 끝난다(실측 — 조용한 no-op이라 트레이스백으로도
    못 잡는다). 그래서 셀의 `hp:subList`를 직접 찾아 ET로 뗀다.

    제거 대상이 예상과 다르면(문단이 2개가 아니거나, 첫 문단에 글자·중첩표가 있으면)
    건드리지 않는다 — 방어적으로.
    """
    문단들 = 칸.paragraphs
    if len(문단들) != 2:
        return
    첫_문단 = 문단들[0]
    if 첫_문단.text.strip() or 첫_문단.tables:
        return
    서브리스트 = 칸.element.find(f"{{{HP}}}subList")
    서브리스트.remove(첫_문단.element)


def _표_그리기(doc: HwpxDocument, kit: Kit, plan: TablePlan, 캐시: dict[Path, str]) -> None:
    # 그림은 표를 만들기 **전에** 행 순서대로 등록한다 — BinData 번호가 등록 순서로 정해지므로
    # 표보다 먼저, 위 행부터 왼쪽 칸부터 등록해야 번호가 늘 같다.
    for 행 in plan.rows:
        for 칸 in 행:
            if 칸.picture is not None:
                _그림_등록(doc, 칸.picture, 캐시)
    표 = doc.add_table(
        len(plan.rows), len(plan.rows[0]),
        width=plan.width if plan.width is not None else kit.body_width,
        height=plan.height,
        border_fill_id_ref=kit.border_fill[plan.border],
        para_pr_id_ref=kit.para_pr["body"],
    )
    if plan.equal_columns:
        표.equalize_column_widths()
    for r, 행 in enumerate(plan.rows):
        for c, 칸 in enumerate(행):
            그림 = _그림_등록(doc, 칸.picture, 캐시) if 칸.picture is not None else None
            _셀(표, r, c, 칸.text, kit=kit, 역할=칸.role, 폭=칸.width, 높이=칸.height, 그림=그림)
            if 칸.nested is not None:
                담는칸 = 표.cell(r, c)
                안쪽 = 담는칸.add_table(
                    1, 1, height=칸.nested.height, border_fill_id_ref=kit.border_fill[칸.nested.border]
                )
                assert len(칸.nested.rows) == 1 and len(칸.nested.rows[0]) == 1, "중첩표는 1×1(강조박스)만 그린다"
                안쪽칸 = 칸.nested.rows[0][0]
                _셀(안쪽, 0, 0, 안쪽칸.text, kit=kit, 역할=안쪽칸.role)
                # add_table()이 중첩표를 담을 새 문단을 만든다(글자 없음) — 그 문단도 "표 안"이므로
                # 기본값(paraPr 0)으로 남기지 않는다. 글자가 없으니 charPr는 건드리지 않는다.
                담는칸.paragraphs[-1].para_pr_id_ref = kit.para_pr["cell"]
                _강조박스_빈_선행_문단_제거(담는칸)


def draw_block(doc: HwpxDocument, kit: Kit, plan: BlockPlan, *, 그림_캐시: dict[Path, str]) -> None:
    if isinstance(plan, TablePlan):
        _표_그리기(doc, kit, plan, 그림_캐시)
    elif isinstance(plan, ParagraphPlan):
        doc.add_paragraph(plan.text, para_pr_id_ref=kit.para_pr[plan.para], char_pr_id_ref=kit.char_pr[plan.char])
    elif isinstance(plan, FigurePlan):
        doc.add_picture(
            plan.path.read_bytes(), "png", width_mm=plan.width_mm, height_mm=plan.height_mm,
            para_pr_id_ref=kit.para_pr["body"], char_pr_id_ref=kit.char_pr["body"],
        )
    else:
        raise TypeError(f"그릴 수 없는 계획: {type(plan).__name__}")


def render_node(doc: HwpxDocument, kit: Kit, node: Node, *, base_dir: Path, 그림_캐시: dict[Path, str] | None = None) -> None:
    """노드 하나를 계획해서 그린다 — 테스트·직접 호출용. 캐시를 안 넘기면 이 호출만의 빈 캐시.

    `compose()`는 이 함수를 여러 번 부르는 동안 캐시 하나를 계속 넘겨 같은 그림 파일이 여러
    칸·여러 블록에 걸쳐 나와도 BinData에 한 번만 등록되게 한다."""
    draw_block(doc, kit, plan_node(kit, node, base_dir=base_dir), 그림_캐시={} if 그림_캐시 is None else 그림_캐시)


# --- 가구 — 머리띠·섹션 제목·확인도장·키워드면 ------------------------------------------------


def draw_band(doc: HwpxDocument, kit: Kit, plan: BandPlan):
    """회차 머리띠를 그린다. `plan.stamp` 은 쓰지 않는다 — hwpx 는 도장을 첫 제목 문단에 띄운다."""
    설정 = kit.furniture["band"]
    band = doc.add_table(
        1,
        4,
        width=설정["width"],
        height=설정["height"],
        border_fill_id_ref=kit.border_fill["plain"],
        para_pr_id_ref=kit.para_pr["body"],
    )
    for 열, 폭 in enumerate(설정["cols"]):
        band.cell(0, 열).set_size(width=폭, height=설정["height"])

    band.set_cell_border_fill(0, 2, kit.border_fill["shade"])
    교사칸 = "\n".join(plan.teacher_lines)
    band.set_cell_text(0, 1, 교사칸, split_paragraphs=True)
    band.set_cell_text(0, 2, plan.title)
    이름칸 = "\n".join(plan.name_lines)
    band.set_cell_text(0, 3, 이름칸, split_paragraphs=True)

    # 칸마다 킷의 문단·글자 서식을 입힌다. 표 셀 문단은 paraPr 0 / charPr 0 으로 생기므로
    # 입히지 않으면 머리띠 글꼴이 킷이 정한 굵은 글꼴과 달라진다 — 실한컴 렌더에서 확인된 결함이다.
    칸_서식 = (
        (kit.para_pr["center"], kit.char_pr["band_left"]),
        (kit.para_pr["center"], kit.char_pr["band_teacher"]),
        (kit.para_pr["band_title"], kit.char_pr["band_title"]),
        (kit.para_pr["band_name"], kit.char_pr["band_name"]),
    )
    for 열, (문단_서식, 글자_서식) in enumerate(칸_서식):
        for 문단 in band.cell(0, 열).paragraphs:
            문단.para_pr_id_ref = 문단_서식
            문단.char_pr_id_ref = 글자_서식
    return band


def draw_keyword_page(doc: HwpxDocument, kit: Kit, plan: KeywordPagePlan):
    """'오늘의 키워드' 줄 노트면 — 한 쪽을 통째로 차지한다."""
    설정 = kit.furniture["keywordPage"]
    행수 = plan.rows
    표 = doc.add_table(
        행수,
        1,
        width=설정["width"],
        height=설정["height"],
        border_fill_id_ref=kit.border_fill["rule_line"],
        para_pr_id_ref=kit.para_pr["body"],
    )
    표.set_cell_border_fill(0, 0, kit.border_fill["rule_head"])
    표.set_cell_border_fill(행수 - 1, 0, kit.border_fill["rule_last"])
    for 행 in range(1, 행수 - 1):
        표.set_cell_border_fill(행, 0, kit.border_fill["rule_line"])
    표.set_cell_text(0, 0, plan.head)

    # 여기도 표 셀 문단이라 add_table 기본값(paraPr 0/charPr 0)으로 남는다. 머리
    # 칸은 실제 글자가 있으니 charPr `keyword_head`, 나머지 줄 칸(학생이 쓰는 빈 줄)은
    # charPr `body`를 입힌다 — 지금 `body`는 0인데, 그건 킷이 고른 값이지 "서식을 안
    # 입혔다"는 뜻이 아니다(0을 고를 자유를 막지 않는다). 행 높이는 킷의 height/rows 그대로
    # 두고 건드리지 않는다.
    for 문단 in 표.cell(0, 0).paragraphs:
        문단.para_pr_id_ref = kit.para_pr["cell"]
        문단.char_pr_id_ref = kit.char_pr["keyword_head"]
    for 행 in range(1, 행수):
        for 문단 in 표.cell(행, 0).paragraphs:
            문단.para_pr_id_ref = kit.para_pr["cell"]
            문단.char_pr_id_ref = kit.char_pr["body"]
    return 표


def draw_heading(doc: HwpxDocument, kit: Kit, plan: HeadingPlan):
    """섹션 제목: 원문자 타원 + 제목 텍스트 (+ 회차 첫 제목이면 확인도장)."""
    원 = kit.furniture["circle"]
    도장 = kit.furniture["stamp"]

    문단 = doc.add_paragraph(
        "",
        para_pr_id_ref=kit.para_pr["body"],
        char_pr_id_ref=kit.char_pr["headline"],
        include_run=False,
    )

    # treat_as_char=True 라야 실한컴에서 제목과 같은 줄에 온다
    타원 = 문단.add_ellipse(
        원["curSz"][0],
        원["curSz"][1],
        line_color=원["line"],
        line_width=원["lineWidth"],
        fill_color=원["fill"],
        treat_as_char=True,
        char_pr_id_ref=kit.char_pr["headline"],
    )
    타원.set_attribute("numberingType", "PICTURE")
    타원.set_attribute("textWrap", "TOP_AND_BOTTOM")
    타원.set_draw_text(str(plan.number), char_pr_id_ref=kit.char_pr["circle_num"])

    # 출처 표기는 제목과 **별도 run**(charPr `heading_ref` — 제목보다 작은 글자)이다.
    # 문구는 킷(furniture.heading.textbookFormat)에서 온다 — 양식 문구의 실제 글자를
    # 여기 코드나 주석에 다시 옮겨 적지 않는다. 양식 문구가 엔진 코드에서 사라졌는지
    # 확인하려는 사람이 그 낱말로 worksheet/를 훑을 수 있어야 하는데, 주석에 낱말이
    # 남아 있으면 그 확인 자체가 걸린다.
    # 계획자는 None 이나 빈 문자열이 아닌 문구만 만든다(킷의 textbookFormat 은 비어 있지 않다)
    출처 = plan.textbook_ref is not None
    문단.add_run(f" {plan.text} " if 출처 else f" {plan.text}", char_pr_id_ref=kit.char_pr["headline"])
    if 출처:
        문단.add_run(plan.textbook_ref, char_pr_id_ref=kit.char_pr["heading_ref"])

    if plan.stamp:
        사각형 = 문단.add_rectangle(
            도장["curSz"][0],
            도장["curSz"][1],
            line_color=도장["line"],
            line_width=도장["lineWidth"],
            fill_color=도장["fill"],
            treat_as_char=False,
            char_pr_id_ref=kit.char_pr["headline"],
        )
        사각형.set_attribute("textWrap", "IN_FRONT_OF_TEXT")
        사각형.set_draw_text(도장["text"], char_pr_id_ref=kit.char_pr["stamp"])
        사각형.set_position(
            horizontal_offset=도장["pos"]["horzOffset"],
            vertical_offset=도장["pos"]["vertOffset"],
        )
        _anchor_to_paper(사각형, 문단)

    return 문단


def _anchor_to_paper(shape, paragraph) -> None:
    """pos 의 relTo 를 PAPER 로 바꾼다.

    python-hwpx 6.4.0의 set_position()은 오프셋만 설정하고 vertRelTo/horzRelTo를
    바꾸는 경로가 없다(공개 이슈로 등록돼 있다:
    <https://github.com/airmang/python-hwpx/issues/100>). 그 셋은 ET로 직접 건드린다.
    """
    inst_id = shape.inst_id
    for 요소 in paragraph.element.iter(f"{{{HP}}}rect"):
        if 요소.get("instid") != inst_id:
            continue
        pos = 요소.find(f"{{{HP}}}pos")
        pos.set("vertRelTo", "PAPER")
        pos.set("horzRelTo", "PAPER")
        return
    raise RuntimeError(f"도형을 문단에서 찾지 못했다: instid={inst_id}")


def add_band(doc: HwpxDocument, kit: Kit, *, title: str, slots: dict[str, str] | None = None):
    """머리띠를 계획해서 그린다 — 테스트·직접 호출용."""
    return draw_band(doc, kit, plan_band(kit, title=title, slots=slots))


def add_keyword_page(doc: HwpxDocument, kit: Kit):
    """키워드면을 계획해서 그린다 — 테스트·직접 호출용."""
    return draw_keyword_page(doc, kit, plan_keyword_page(kit))


def add_heading(
    doc: HwpxDocument,
    kit: Kit,
    *,
    number: int,
    text: str,
    textbook: str | None = None,
    with_stamp: bool = False,
):
    """섹션 제목을 계획해서 그린다 — 테스트·직접 호출용."""
    return draw_heading(
        doc, kit, plan_heading(kit, number=number, text=text, textbook=textbook, with_stamp=with_stamp)
    )


class HwpxWriter:
    """계획 목록을 hwpx 로 — 킷 스켈레톤을 열고, 그리고, 저장한다."""

    def __init__(self, kit: Kit) -> None:
        self.kit = kit
        self.doc = HwpxDocument.open(kit.skeleton_path)
        # 칸 안 그림 등록 결과(절대경로 → 이진 항목 id) — 이 문서 전체가 공유한다. 같은 그림
        # 파일이 여러 칸·여러 블록에 나와도 BinData에 한 번만 들어간다.
        self._그림_캐시: dict[Path, str] = {}

    def draw(self, plan: Plan) -> None:
        if isinstance(plan, BandPlan):
            draw_band(self.doc, self.kit, plan)
        elif isinstance(plan, KeywordPagePlan):
            draw_keyword_page(self.doc, self.kit, plan)
        elif isinstance(plan, HeadingPlan):
            draw_heading(self.doc, self.kit, plan)
        else:
            draw_block(self.doc, self.kit, plan, 그림_캐시=self._그림_캐시)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save_to_path(path)
