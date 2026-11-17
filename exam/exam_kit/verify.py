"""조판된 hwpx의 [기계] 검사. 통과는 '기계 잔존 0'일 뿐 — 판정은 사용자 검수."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf
from hwpx.document import HwpxDocument

from .geometry import equation_glyphs, measure, tail_box_rect, tail_box_top, text_lines
from .kit import Kit, style_ids
from .read import is_blank, nested_raw, script, tree
from .render import RenderResult


@dataclass(frozen=True)
class Finding:
    code: str
    level: str
    msg: str


def _f(code: str, msg: str, level: str = "E") -> Finding:
    return Finding(code, level, msg)


def errors(fs: list[Finding]) -> list[Finding]:
    return [f for f in fs if f.level == "E"]


def _numbered_para_prs(doc: HwpxDocument) -> set[str]:
    return {pid for pid, pp in doc.styles.paragraph_properties.items()
            if pp.heading is not None and pp.heading.type == "NUMBER"}


_글자_번호 = re.compile(r"^\d{1,3}\.\s?$")
def _section_text(doc: HwpxDocument) -> str:
    """구역 0의 글 — 문단 글(안쪽 표 칸·글상자·캡션·머리말·각주까지), 메모 글, 개체 설명·수식 스크립트, 누름틀 안내문·메모.
    금지 문구(서식 안내·샘플 글)가 남았는지 찾을 때 쓴다."""
    first = doc.sections[0]
    parts = [nested_raw(first.paragraphs)]
    parts += [nested_raw(memo.paragraphs) for memo in first.memos]
    for place in doc.text.iter_objects():
        if place.section is first or place.section == first:
            o = place.object
            parts.append(o.description if hasattr(o, "description") else "")
            parts.append(script(o) if place.kind == "equation" else "")
    parts += [f"{f.prompt}{f.memo}" for f in doc.fields.all]
    return "".join(parts)


def _t_lead_text(run) -> str:
    """run의 글 요소(t)마다 첫 글(``t.text`` — 형광펜·탭 같은 표시 뒤의 글은 빼고)을 이은 것.

    ``run.content``에서 글 요소 안의 글 조각 가운데, 바로 앞 조각이 같은 글 요소의 표시·글리프가 아닌 것이 그 글 요소의 첫 글이다
    (조각 둘이 잇따라 글이면 둘째는 다음 글 요소의 첫 글이다).
    """
    out, previous = [], None
    for item in run.content:
        if item.container == "t" and item.kind == "text":
            if previous is None or previous.container != "t" or previous.kind == "text":
                out.append(item.text)
        previous = item
    return "".join(out)


def _literal_head(p) -> bool:
    """글자 번호 문항 머리: 첫 글 run이 `N.`(뒤 공백 하나까지)만이다 — 킷 number.mode literal(학교 B) 조판."""
    for run in p.runs:
        text = _t_lead_text(run)
        if text:
            return bool(_글자_번호.match(text))
    return False


def question_heads(doc: HwpxDocument) -> list[int]:
    """문항 머리 문단 — 자동번호 paraPr 또는 글자 번호 run으로 시작하는 문단. 보존 구간(책갈피 보존_NN — 원본 그대로 심은
    서술형·논술형 등)의 머리는 엔진이 조판한 문항이 아니라 뺀다."""
    from .preserve import inside, ranges

    nums = _numbered_para_prs(doc)
    spans = ranges(doc)
    return [i for i, p in enumerate(doc.sections[0].paragraphs)
            if (str(p.para_pr_id_ref) in nums or (i > 0 and _literal_head(p))) and not inside(i, spans)]


def _tail_index(doc: HwpxDocument, marker: str | None = None) -> int:
    """꼬리 박스 문단의 번호. marker(킷 tailbox.match_text)가 있으면 그 글을 품은 마지막 문단, 없으면 구조로 —
    용지 기준으로 고정한 표(prepare.pin_tailbox)를 가진 마지막 문단(관리박스 문단 0은 빼고). 못 찾으면 마지막 문단."""
    ps = list(doc.sections[0].paragraphs)
    for i in range(len(ps) - 1, 0 if marker is None else -1, -1):
        if marker is not None:
            if marker in nested_raw([ps[i]]):
                return i
        elif any(not (pos := place.object.position).treat_as_char and pos.vertical_relative_to == "PAPER"
                 for place in ps[i].iter_objects(kinds="table")):
            return i
    return len(ps) - 1


def extract_answers(doc: HwpxDocument) -> dict[str, str]:
    heads = question_heads(doc)
    ps = list(doc.sections[0].paragraphs)
    out: dict[str, str] = {}
    for k, start in enumerate(heads, 1):
        end = heads[k] if k < len(heads) else _tail_index(doc)
        for top in ps[start:end]:
            for p in tree(top):
                for run in p.runs:
                    items = run.content
                    for i, item in enumerate(items):
                        if item.container != "t" or item.name != "markpenBegin" \
                                or (item.attribute("color") or "").upper() != "#FFFF00":
                            continue
                        after = items[i + 1] if i + 1 < len(items) else None  # 형광펜 바로 뒤 글(같은 글 조각)
                        mark = (after.text if after is not None and after.container == "t" and after.kind == "text"
                                else "").strip()[:1]
                        if mark and mark in "①②③④⑤":  # "" in str은 참 — 빈 형광펜을 답으로 세지 않는다
                            out[str(k)] = mark
    return out


def _markpens(doc: HwpxDocument) -> list[str]:
    first = doc.sections[0]
    return [h.color or "" for h in doc.text.highlights if h.paragraph is not None and h.paragraph.section is first]


def verify_document(doc: HwpxDocument, kit: Kit, *, expect_answers: dict[str, str] | None,
                    answer_key: bool, draft: bool) -> list[Finding]:
    fs: list[Finding] = []
    if not doc.validate().ok:
        fs.append(_f("M6", "validate().ok == False"))
    ps = list(doc.sections[0].paragraphs)
    heads = question_heads(doc)
    tail = _tail_index(doc, kit.tailbox["match_text"])
    from .preserve import inside, ranges

    kept = ranges(doc)  # 보존 구간(원본 모양 그대로 심은 서술형 등)은 양식 모양 검사(M7a·M7b)에서 뺀다 — 원본 그대로가 목적이다
    if heads:
        for i in range(heads[0], tail):
            if is_blank(ps[i]) and not inside(i, kept):
                fs.append(_f("M7a", f"빈 최상위 문단 (index {i})"))
    ids = style_ids(doc)
    allowed = {ids[n][0] for n in kit.styles.values() if n in ids}  # 킷 스타일 8종의 id
    for i in range(1, tail):
        if inside(i, kept):
            continue
        sid = str(ps[i].style_id_ref or "0")
        if sid not in allowed:
            fs.append(_f("M7b", f"양식 스타일 밖의 문단 (index {i}, style {sid})"))
    values = {f.field_id: f.value for f in doc.fields.all}
    for slot, fid in kit.slot_ids().items():
        v = values.get(fid, "")
        ph = kit.placeholders.get(slot)
        unfilled = (ph is not None and v == ph) or v == "" or set(v) <= {"_"}
        if unfilled:
            fs.append(_f("M7c", f"슬롯 {slot} 미확정: {v!r}", "W" if draft else "E"))
    text = _section_text(doc)
    for w in kit.forbidden_text:
        if w in text:
            fs.append(_f("M7d", f"금지 문구 잔존: {w!r}"))
    pens = _markpens(doc)
    if answer_key:
        want = len(heads) if expect_answers is None else len(expect_answers)  # 원고에 정답이 있는 문항 수
        if len(pens) != want:
            fs.append(_f("M8", f"형광펜 {len(pens)}개 ≠ 정답 표시 문항 {want}개"))
        if want < len(heads):  # 정답 표시 없는 문항 — 초안은 경고, 최종판은 오류
            fs.append(_f("M8", f"정답 표시 없는 문항 {len(heads) - want}개", "W" if draft else "E"))
        if any(c.upper() != "#FFFF00" for c in pens):
            fs.append(_f("M8", f"형광펜 색 이상: {sorted({c.upper() for c in pens})}"))
    elif pens:
        fs.append(_f("M8", f"문항지 판에 형광펜 {len(pens)}개"))
    if expect_answers is not None:
        got = extract_answers(doc)
        if got != expect_answers:
            diff = {k: (expect_answers.get(k), got.get(k)) for k in set(expect_answers) | set(got) if expect_answers.get(k) != got.get(k)}
            fs.append(_f("M11", f"정답 불일치 {diff}"))
    return fs


def _glyph_boxes(page) -> list:
    """곡선(글리프) 채움 도형 — 텍스트 층 없는 렌더에서 '글자가 여기 있다'의 대용(spike_synthetic.py)."""
    return [d["rect"] for d in page.get_drawings()
            if d.get("fill") is not None and 0.3 < d["rect"].width < 40 and d["rect"].height < 40]


def _right_column_x(kit: Kit) -> tuple[float, float]:
    left = kit.page["margin"]["left"] / 100.0
    col_w = kit.columns["width"] / 100.0
    gap = kit.columns["gap"] / 100.0
    x0 = left + col_w + gap
    return x0, x0 + col_w


def _left_column_x(kit: Kit) -> tuple[float, float]:
    x0 = kit.page["margin"]["left"] / 100.0
    col_w = kit.columns["width"] / 100.0
    return x0, x0 + col_w


def _tail_box_findings(page, kit: Kit) -> list[Finding]:
    """꼬리 박스가 오른쪽 단 맨 아래 제자리에 있고 글자와 안 겹치는지 — 순수 함수(pymupdf 쪽 하나).

    박스는 geometry.tail_box_rect(폭 = kit.tailbox.width인 가로 테두리선 무리)로 찾는다 — 오른쪽 단에 〈보기〉·격자표가
    있어도 섞이지 않는다(폭, 또는 box_fit = column으로 같은 폭이면 표지 글·높이 — G5-1). 자리 = 윗선이 tail_box_top(kit) ±3pt(설계 R-5, Task 26). 실렌더 없이도
    (합성 PDF) 검증할 수 있도록 쪽 하나만 받는다.
    """
    box = tail_box_rect(page, kit)
    if box is None:
        return [_f("M10", f"꼬리 박스를 찾지 못했다 — 폭 {kit.tailbox['width'] / 100:.0f}pt 테두리선이 없다")]
    right_x0, _ = _right_column_x(kit)
    if abs(box.x0 - right_x0) > 2.0:
        return [_f("M10", f"꼬리 박스가 왼쪽 단에 있다(오른쪽 단이 아니다) — {[round(v) for v in box]}")]
    fs = []
    top = tail_box_top(kit)
    if abs(box.y0 - top) > 3.0:
        fs.append(_f("M10", f"꼬리 박스 윗선 {box.y0:.1f}pt ≠ 제자리 {top:.1f}pt(오른쪽 단 맨 아래)"))
    glyphs = _glyph_boxes(page)
    inside = pymupdf.Rect(box.x0 - 1, box.y0 - 1, box.x1 + 1, box.y1 + 1)
    overlapping = [g for g in glyphs if box.intersects(g)]
    # 텍스트 층 글자(ㄱ·ㄴ·ㄷ·굴림 등): 박스 자신의 글(굴림)은 박스 안에 통째로 든다 — 경계에 걸친 줄만 겹침
    overlapping += [t for t in text_lines(page) if box.intersects(t) and not inside.contains(t)]
    overlapping += [e for e in equation_glyphs(page) if box.intersects(e)]  # 수식 글자(텍스트 층 HyhwpEQ)
    if overlapping:
        fs.append(_f("M10", f"꼬리 박스({[round(v) for v in box]})가 글자와 겹친다 — {len(overlapping)}개, 예 {[[round(v) for v in g] for g in overlapping[:4]]}"))
    return fs


def verify_render(rr: RenderResult, doc: HwpxDocument, kit: Kit, *, expected_pages: int | None) -> list[Finding]:
    """M10 — 쪽수(기대·총쪽수 누름틀) · 빈 쪽 없음 · 꼬리 박스가 마지막 쪽 오른쪽 단 맨 아래, 글자와 안 겹침."""
    fs: list[Finding] = []
    if expected_pages is not None and rr.page_count != expected_pages:
        fs.append(_f("M10", f"렌더 쪽수 {rr.page_count} ≠ 기대 {expected_pages}"))
    from .slots import read_total_pages

    total = read_total_pages(doc, kit)
    if not total.isdigit():
        fs.append(_f("M10", f"총쪽수 누름틀이 채워지지 않았다: {total!r}"))
    elif int(total) != rr.page_count:
        fs.append(_f("M10", f"총쪽수 누름틀 {total} ≠ 렌더 쪽수 {rr.page_count}"))
    layout = measure(rr.pdf, kit)
    blank = [p.page for p in layout if p.blank]
    if blank:
        fs.append(_f("M10", f"본문이 없는 쪽: {blank}"))
    with pymupdf.open(str(rr.pdf)) as pdf:
        last = pdf[pdf.page_count - 1]
        fs.extend(_tail_box_findings(last, kit))
    return fs
