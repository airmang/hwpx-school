"""FrontMatter + 파생값 → 머리 값 채움. 두 방식이다(킷이 정한다).
- 누름틀: kit.slots(슬롯 이름 → 누름틀 id) + 출제교사 셀(kit.teacher_cell).
- 글자 자리: kit.text_slots — 결재 표 칸·유의 상자·꼬리말 문단의 글에서 정규식으로 찾아 바꾼다.
"""

from __future__ import annotations

import re

from hwpx.document import HwpxDocument

from . import q
from .frontmatter import FrontMatter
from .kit import Kit
from .read import cells_deep, t_text, table_paragraphs

_빨강 = "#FF0000"


def _set_para_text(p_el, text: str) -> None:
    """첫 run의 charPr를 지키고 본문을 text 하나로 바꾼다(탭·형광펜 등 자식 제거). prepare에서 옮겨 온 옛 길 — 공개
    ``run.text``는 빈 글 조각을 남기고 줄 캐시를 지워 바이트가 달라진다(기준 1 밖이라 그대로 둔다)."""
    runs = p_el.findall(q("hp", "run"))
    if not runs:
        run = p_el.makeelement(q("hp", "run"), {})
        p_el.append(run)
    else:
        run = runs[0]
        for extra in runs[1:]:
            p_el.remove(extra)
    for child in list(run):
        if child.tag == q("hp", "t"):
            run.remove(child)
    t = run.makeelement(q("hp", "t"), {})
    run.append(t)
    t.text = text


def _fmt_points(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


def _needs_black_twin(style, *, upright: bool) -> bool:
    if style.attributes.get("textColor") == _빨강:
        return True
    return upright and "italic" in style.child_attributes


def _black_twin(doc: HwpxDocument, charpr_id: str, *, upright: bool = False) -> str:
    """charpr_id가 빨강이면(upright=True면 기울임까지 있으면) 검정(+정자체) 쌍둥이의 id를 돌려준다 — 공개
    ``styles.ensure_run(base_char_pr_id_ref=, color="#000000", italic=False)``(같은 모양이 있으면 그것, 없으면 새 id).

    fill_form_field는 채운 값 run의 charPr을 그 값을 감싸는 run에 맞춘다 — 대개는 검정이라 자연히 정리되지만, 원본
    양식에서 감싸는 run 자체가 빨강인 슬롯(선택형_문항수·선택형_만점·총쪽수)은 채워도 빨강으로 남는다. upright=True(출제교사
    이름 run 전용)는 기울임도 끈다(정자체). B11(소유자 결정 전) — 옛 판은 요소 술어로 쌍둥이를 찾고 textColor·hh:italic만
    고쳤다(next7/all)."""
    src = doc.styles.char_property(charpr_id)
    if src is None or not _needs_black_twin(src, upright=upright):
        return charpr_id
    return doc.styles.ensure_run(base_char_pr_id_ref=charpr_id, color="#000000", italic=False if upright else None)


def _unred(doc: HwpxDocument, run, *, upright: bool = False) -> None:
    """run(공개 run 또는 아직 요소로 다루는 run)의 글자 모양을 검정 쌍둥이로."""
    if hasattr(run, "char_pr_id_ref"):
        cpid = run.char_pr_id_ref
        black = _black_twin(doc, cpid, upright=upright)
        if black != cpid:
            run.char_pr_id_ref = black
        return
    cpid = run.get("charPrIDRef")
    black = _black_twin(doc, cpid, upright=upright)
    if black != cpid:
        run.set("charPrIDRef", black)


def _field_value_runs(p0, field_id: str) -> list:
    """p0(과 그 안 문단)에서 id가 field_id인 누름틀 시작(fieldBegin)을 찾아, 그 run 다음부터 다음 컨트롤(=fieldEnd) 전까지
    글자가 있는 run들 — 그 필드가 화면에 보여주는 값. 없으면 [].

    fieldBegin의 id는 옛 판처럼 id → fieldid → name 차례로 읽는다. fieldBegin 자신이 든 run(및 fieldEnd가 든 run)은
    화면에 보이지 않는 빈 칸(공백)뿐이라 글자 판정에서 자연히 빠진다. 글자 판정은 옛 판처럼 run의 hp:t마다 첫 글(조각
    앞)이 공백이 아닌가로 한다."""
    for para in [p0, *(place.paragraph for place in p0.iter_paragraphs())]:
        runs = para.runs
        for i, run in enumerate(runs):
            if not any(it.kind == "field_begin" and (it.attribute("id") or it.attribute("fieldid") or it.attribute("name"))
                       == field_id for it in run.content):
                continue
            값_run: list = []
            for nxt in runs[i + 1:]:
                if any(it.container == "ctrl" for it in nxt.content):
                    break  # 다음 컨트롤(=fieldEnd)에 도달
                if any(_t_첫_글(nxt, k).strip() for k in {it.child_index for it in nxt.content if it.container == "t"}):
                    값_run.append(nxt)
            return 값_run
    return []


def _t_첫_글(run, child_index: int) -> str:
    """run의 child_index번 hp:t의 첫 글 — 그 안 첫 조각이 글이면 그 글(옛 ``t.text``), 표시·글리프로 시작하면 ''."""
    first = next(it for it in run.content if it.container == "t" and it.child_index == child_index)
    return first.text if first.kind == "text" else ""


def slot_values(fm: FrontMatter, *, question_count: int, total_points: float, page_count: int | None) -> dict[str, str | None]:
    시행, 대상, 인쇄 = fm.시행_분해(), fm.대상_분해(), fm.인쇄_분해()
    return {
        "과목": fm.과목, "과목코드": fm.과목코드,
        "월": 시행["월"], "일": 시행["일"], "요일": 시행["요일"], "교시": 시행["교시"],
        "학년": 대상["학년"], "반_시작": 대상["반_시작"], "반_끝": 대상["반_끝"],
        "인쇄매수": 인쇄["인쇄매수"], "묶음": 인쇄["묶음"],
        "머리_학년": str(fm.학년), "머리_학기": str(fm.학기), "머리_차": str(fm.차), "머리_과목": fm.과목,
        "선택형_문항수": str(question_count), "선택형_만점": _fmt_points(total_points),
        "논술형_문항수": None, "논술형_만점": None,
        "총쪽수": None if page_count is None else str(page_count),
    }


def _fill_teacher(doc: HwpxDocument, kit: Kit, name: str) -> None:
    p0 = doc.sections[0].paragraphs[kit.admin["paragraph"]]
    결재란 = next(t for t in p0.tables if kit.teacher_cell["label"] in t_text(table_paragraphs(t)))
    cell = next(c for row in 결재란.rows for c in row.cells if kit.teacher_cell["label"] in t_text(c.paragraphs))
    ps = [p.element for p in cell.paragraphs]
    if len(ps) < 2:
        raise ValueError("출제교사 셀 문단이 2개 미만")
    _set_para_text(ps[1], kit.teacher_cell["template"].format(name=name))
    run = ps[1].find(q("hp", "run"))  # _set_para_text가 남긴 단 하나의 run — 자리표시 charPr(빨강·기울임)를 그대로 물려받는다
    if run is not None:
        _unred(doc, run, upright=True)  # 출제교사 이름은 정자체로(09-23 요청)
    for extra in ps[2:]:
        _set_para_text(extra, "")
    doc.sections[0].mark_dirty()


# ---- 글자 자리 슬롯 -------------------------------------------------------------

def _slot_paragraphs(doc: HwpxDocument, kit: Kit, where: dict) -> list:
    """슬롯 위치 → 문단 요소들. admin_table_with+cell(+para) · notice · footer_with."""
    sec = doc.sections[0].element
    p0 = doc.sections[0].paragraphs[kit.admin["paragraph"]]
    if "admin_table_with" in where:
        tbl = next(t for t in p0.tables if where["admin_table_with"] in t_text(table_paragraphs(t)))
        row, col = where["cell"]
        # 옛 판의 뜻을 그대로 둔 것이며 고침은 `-x`에 있다: 옛 판은 `tbl.iter(hp:tc)`에서 주소가 맞는 첫 칸을 골랐다(앞 칸
        # 안에 든 표의 같은 주소 칸이 먼저 나오면 그것 — cells_deep이 그 차례).
        tc = next(c for c in cells_deep(tbl) if c.address == (row, col))
        ps = [p.element for p in tc.paragraphs]
        return [ps[where["para"]]] if "para" in where else ps
    if where.get("notice"):
        tbl = next(t for t in p0.tables if kit.admin["notice_table_with"] in t_text(table_paragraphs(t)))
        return [p.element for tr in tbl.rows for tc in tr.cells for p in tc.paragraphs]
    if "footer_with" in where:
        # 꼬리말 요소를 직접 훑는다: 6.x가 꼬리말을 두 벌(구역 설정 안·컨트롤) 쓴 양식은 둘 다 채워야 한다. 공개 읽기
        # (doc.page.footers)는 한 벌만 내놓는다.
        return [p for f in sec.iter(q("hp", "footer")) if where["footer_with"] in "".join(f.itertext()) for p in f.iter(q("hp", "p"))]
    raise ValueError(f"글자 자리 슬롯 위치를 모른다: {where}")


def _ts(p_el) -> list:
    """문단 자신의 글 조각(hp:t) — 표·머리말 안 문단의 글은 빼고, 조각 안에 탭 등 자식이 있으면 글자 자리로 쓰지 않는다."""
    return [t for r in p_el.findall(q("hp", "run")) for t in r.findall(q("hp", "t")) if len(t) == 0]


def replace_across(p_el, rx: re.Pattern, new: str) -> bool:
    """문단의 글 조각을 이어 붙인 글에서 rx를 한 번 찾아 new로 바꾼다 — 바뀐 글은 찾은 자리가 시작하는 조각에,
    걸쳐 있던 뒤 조각에서는 찾은 부분만 지운다(조각별 글자 모양은 그대로). 못 찾으면 False."""
    ts = _ts(p_el)
    texts = [t.text or "" for t in ts]
    m = rx.search("".join(texts))
    if m is None:
        return False
    a, b, pos = m.start(), m.end(), 0
    for t, s in zip(ts, texts):
        lo, hi = pos, pos + len(s)
        pos = hi
        if hi <= a or lo >= b and not (lo == a == b):
            continue
        keep_head = s[:max(0, a - lo)] if lo <= a else ""
        keep_tail = s[b - lo:] if b < hi else ""
        t.text = keep_head + (new if lo <= a < hi or (a == hi and s == "") else "") + keep_tail
    return True


def slot_value(slot: dict, values: dict[str, str | None], fm: FrontMatter) -> str | None:
    """슬롯 fill 틀을 values로 채운다 — 쓰인 값 가운데 None(미확정)이 있으면 None(그 슬롯은 건드리지 않는다)."""
    vals = dict(values)
    if "each" in slot:  # 여러 명(출제교사): 이름마다 each 틀, join으로 잇는다
        vals[slot["name"]] = slot.get("join", ", ").join(slot["each"].format(name=n) for n in fm.teachers())
    keys = re.findall(r"{(\w+)}", slot["fill"])
    if any(vals.get(k) is None for k in keys):
        return None
    return slot["fill"].format(**{k: vals[k] for k in keys})


def fill_text_slots(doc: HwpxDocument, kit: Kit, fm: FrontMatter, values: dict[str, str | None]) -> dict[str, str | None]:
    """kit.text_slots를 차례로 채운다 — 슬롯 이름 → 채운 글(미확정이면 None). 찾을 글이 위치에 없으면 '양식이 바뀌었다'."""
    out: dict[str, str | None] = {}
    for slot in kit.text_slots:
        new = slot_value(slot, values, fm)
        out[slot["name"]] = new
        if new is None:
            continue
        rx = re.compile(slot["find"])
        # 위치 안에서 맞는 문단은 모두 바꾼다 — 같은 꼬리말이 두 벌(secPr 안·컨트롤 안) 적힌 서식도 있다
        hits = [replace_across(p, rx, new) for p in _slot_paragraphs(doc, kit, slot["where"])]
        if not any(hits):
            raise ValueError(f"양식이 바뀌었다: 글자 자리 슬롯 {slot['name']!r}의 {slot['find']!r}가 {slot['where']}에 없다")
    doc.sections[0].mark_dirty()
    return out


def _fill_regex(fill: str) -> re.Pattern:
    """슬롯 fill 틀 → 값을 되읽는 정규식 — `{이름}` 자리는 이름 붙은 묶음, 나머지 글은 그대로. 같은 이름이 두 번이면 둘째는 되참조."""
    seen: set[str] = set()
    out, pos = [], 0
    for m in re.finditer(r"{(\w+)}", fill):
        out.append(re.escape(fill[pos:m.start()]))
        name = m.group(1)
        out.append(f"(?P={name})" if name in seen else f"(?P<{name}>.+?)")
        seen.add(name)
        pos = m.end()
    out.append(re.escape(fill[pos:]))
    return re.compile("".join(out) + "$")


def read_text_slots(doc: HwpxDocument, kit: Kit) -> dict[str, str]:
    """fill_text_slots의 거꾸로 — 위치의 글에서 find로 찾은 글을 fill 틀로 되읽어 값 이름 → 값. 못 찾은 슬롯은 넘어간다
    (역변환이 그 머리 값을 '읽지 못함'으로 다룬다). 같은 값을 두 슬롯이 가지면 먼저 읽은 것."""
    out: dict[str, str] = {}
    for slot in kit.text_slots:
        rx = re.compile(slot["find"])
        try:
            paras = _slot_paragraphs(doc, kit, slot["where"])
        except (StopIteration, ValueError, IndexError):
            continue
        for p in paras:
            m = rx.search("".join(t.text or "" for t in _ts(p)))
            if not m:
                continue
            got = _fill_regex(slot["fill"]).match(m.group(0))
            if got:
                for k, v in got.groupdict().items():
                    out.setdefault(k, v.strip())
            break
    return out


def _text_values(fm: FrontMatter, *, question_count: int, total_points: float, page_count: int | None) -> dict:
    시행 = fm.시행_분해()
    return {"학년도": str(fm.학년도), "학년": str(fm.학년), "학기": str(fm.학기), "차": str(fm.차), "과목": fm.과목,
            # 미정(초안)은 자리표시를 그대로 찍는다 — 양식의 예시 값이 진짜 값처럼 남지 않게
            "월": 시행["월"] or "__", "일": 시행["일"] or "__", "요일": 시행["요일"] or "_", "교시": 시행["교시"] or "_",
            "만점": _fmt_points(fm.만점), "선택형_만점": _fmt_points(total_points), "문항수": str(question_count),
            "총쪽수": None if page_count is None else str(page_count)}


def read_total_pages(doc: HwpxDocument, kit: Kit) -> str:
    """문서에 적힌 총쪽수 — 누름틀(kit.slots) 또는 글자 자리 슬롯 '총쪽수'의 read 정규식."""
    if "총쪽수" in kit.slots:
        return {f.field_id: f.value for f in doc.fields.all}.get(kit.slots["총쪽수"], "")
    slot = next(s for s in kit.text_slots if s["name"] == "총쪽수")
    rx = re.compile(slot["read"])
    for p in _slot_paragraphs(doc, kit, slot["where"]):
        m = rx.search("".join(t.text or "" for t in _ts(p)))
        if m:
            return m.group(1)
    return ""


def fill_slots(doc: HwpxDocument, kit: Kit, fm: FrontMatter, *, question_count: int,
               total_points: float, page_count: int | None = None) -> dict[str, str]:
    if kit.text_slots:
        tv = _text_values(fm, question_count=question_count, total_points=total_points, page_count=page_count)
        return {k: v for k, v in fill_text_slots(doc, kit, fm, tv).items() if v is not None}
    values = slot_values(fm, question_count=question_count, total_points=total_points, page_count=page_count)
    p0 = doc.sections[0].paragraphs[0]
    채움: dict[str, str] = {}
    for slot, fid in kit.slot_ids().items():
        v = values.get(slot)
        if v is None:
            continue
        doc.fields.fill(v, field_id=fid)
        채움[slot] = v
        # fill_form_field는 값 run의 charPr을 감싸는 run에 맞추는데, 원본 양식에서 감싸는
        # run 자체가 빨강인 슬롯(선택형_문항수·선택형_만점·총쪽수)은 채워도 빨강으로 남는다.
        # 방금 채운 슬롯만 손보고, 아직 안 채운(초안) 자리표시는 건드리지 않는다 — 빨강은
        # verify.py의 초안 경고가 쓰는 신호다.
        for run in _field_value_runs(p0, fid):
            _unred(doc, run)
    if kit.teacher_cell is not None:
        _fill_teacher(doc, kit, fm.출제교사)
    doc.sections[0].mark_dirty()
    return 채움


def fill_total_pages(doc: HwpxDocument, kit: Kit, pages: int) -> None:
    """총쪽수만 다시 채운다 — 렌더로 쪽수가 확정된 뒤(layout.settle). 누름틀 또는 글자 자리 슬롯."""
    if "총쪽수" not in kit.slots:
        slot = next(s for s in kit.text_slots if s["name"] == "총쪽수")
        rx = re.compile(slot["find"])
        new = slot["fill"].format(총쪽수=str(pages))
        if not any([replace_across(p, rx, new) for p in _slot_paragraphs(doc, kit, slot["where"])]):
            raise ValueError(f"총쪽수 글자 자리 {slot['find']!r}가 {slot['where']}에 없다")
        doc.sections[0].mark_dirty()
        return
    fid = kit.slots["총쪽수"]
    doc.fields.fill(str(pages), field_id=fid)
    for run in _field_value_runs(doc.sections[0].paragraphs[0], fid):
        _unred(doc, run)
    doc.sections[0].mark_dirty()
