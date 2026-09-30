import lxml.etree as ET
import pymupdf
import pytest
from hwpx_automation.office.exam import (
    lower_exam,
    parse_exam_markdown,
    profile_form,
    replace_body_region,
)

from exam_kit import q
from exam_kit.geometry import tail_box_top
from exam_kit.kit import load_kit, style_ids
from exam_kit.prepare import finalize_form, prepare_document
from exam_kit.verify import (
    _left_column_x,
    _right_column_x,
    _tail_box_findings,
    _tail_index,
    errors,
    extract_answers,
    question_heads,
    verify_document,
    verify_render,
)


def _md(n: int) -> str:
    """합성 문항 n개(발문 + 답지 5) — python-hwpx-automation의 md 파서용."""
    return "# 합성\n" + "".join(
        f"## {k}. (4점)\n합성 발문 {k}?\n" + "".join(f"{m} 답지 {i}\n" for i, m in enumerate("①②③④⑤"))
        for k in range(1, n + 1)
    )


def _정답_표시(doc, k: int, mark: str) -> None:
    """문항 k(1-based)의 mark 답지에 형광펜(정답 표시)을 얹는다 — v1 조판 뒤 후처리."""
    ps = list(doc.sections[0].paragraphs)
    heads = question_heads(doc)
    start, end = heads[k - 1], heads[k] if k < len(heads) else _tail_index(doc)
    for p in ps[start:end]:
        if mark in p.text:
            p.add_highlight(color="#FFFF00", match=mark)
            return
    raise AssertionError(f"문항 {k}에서 {mark} 답지 문단을 찾지 못함")


def _compose(doc, kit, prepared, n: int, *, 정답: dict[int, str] | None = None):
    """실제 조판 파이프라인(v1)으로 합성 문항 n개를 앉히고 마무리한다(스켈레톤 없이)."""
    prof = profile_form(doc)
    replace_body_region(doc, prof, lower_exam(parse_exam_markdown(_md(n)), prof))
    if 정답:
        for k, mark in 정답.items():
            _정답_표시(doc, k, mark)
    finalize_form(doc, kit, prepared)


@pytest.fixture
def 준비(킷_루트, 양식_hwpx):
    kit = load_kit(킷_루트)
    doc, prepared = prepare_document(양식_hwpx, kit)
    return kit, doc, prepared


def test_heads와_정답(준비):
    kit, doc, prepared = 준비
    _compose(doc, kit, prepared, 3, 정답={1: "②", 2: "②", 3: "②"})
    assert len(question_heads(doc)) == 3
    assert extract_answers(doc) == {"1": "②", "2": "②", "3": "②"}


def test_문항지_판_깨끗(준비):
    kit, doc, prepared = 준비
    _compose(doc, kit, prepared, 3, 정답=None)
    fs = verify_document(doc, kit, expect_answers=None, answer_key=False, draft=True)
    assert [f.code for f in errors(fs)] == []


def test_M7a_빈문단(준비):
    kit, doc, prepared = 준비
    _compose(doc, kit, prepared, 2, 정답={1: "①", 2: "①"})
    # 꼬리 검사(M7a)는 조판·마무리가 끝난 뒤 상태만 본다 — 빈 문단은 finalize_form 뒤에 끼워 넣는다.
    sec = doc.sections[0]
    normal = style_ids(doc)[kit.styles["normal"]]
    blank = sec.add_paragraph("", para_pr_id_ref=normal[1], style_id_ref=normal[0], char_pr_id_ref=normal[2], inherit_style=False)
    idx = question_heads(doc)[1]  # 2번 문항 머리 앞
    sec.insert_paragraphs(idx, [blank.element])
    sec.remove_paragraph(blank)  # add_paragraph가 끝에 붙인 원본을 걷어낸다(insert_paragraphs는 복제본을 넣는다)
    sec.mark_dirty()
    fs = verify_document(doc, kit, expect_answers={"1": "①", "2": "①"}, answer_key=True, draft=True)
    assert "M7a" in {f.code for f in errors(fs)}


def test_M7b_스타일_밖(준비):
    kit, doc, prepared = 준비
    _compose(doc, kit, prepared, 2, 정답={1: "①", 2: "①"})
    # 이 문서에 실재하는 스타일은 정확히 킷의 8종뿐이라(style_ids로 실측 확인) '8종 밖'을
    # 재현하려면 header의 styles 표에 9번째 스타일을 하나 복제해 심어야 한다 — 바탕글(id 0)의
    # paraPr·charPr을 그대로 물려받는 새 style id를 등록한다.
    styles_el = doc.headers[0].element.find(f".//{q('hh', 'styles')}")
    새_id = str(len(styles_el))
    복제 = ET.SubElement(styles_el, q("hh", "style"))
    복제.set("id", 새_id)
    복제.set("type", "PARA")
    복제.set("name", "복제")
    복제.set("paraPrIDRef", "0")
    복제.set("charPrIDRef", "8")
    복제.set("nextStyleIDRef", 새_id)
    복제.set("langID", "1042")
    복제.set("lockForm", "0")
    styles_el.set("itemCnt", str(int(styles_el.get("itemCnt")) + 1))

    sec = doc.sections[0]
    outlier = sec.add_paragraph("범위 밖 스타일 문단", para_pr_id_ref=0, style_id_ref=새_id, char_pr_id_ref=8, inherit_style=False)
    idx = question_heads(doc)[1]  # 2번 문항 머리 앞
    sec.insert_paragraphs(idx, [outlier.element])
    sec.remove_paragraph(outlier)
    sec.mark_dirty()
    fs = verify_document(doc, kit, expect_answers={"1": "①", "2": "①"}, answer_key=True, draft=True)
    assert "M7b" in {f.code for f in errors(fs)}


def test_M8_M11(준비):
    kit, doc, prepared = 준비
    _compose(doc, kit, prepared, 2, 정답={1: "③", 2: "③"})
    fs = verify_document(doc, kit, expect_answers={"1": "③", "2": "④"}, answer_key=True, draft=True)
    codes = {f.code for f in errors(fs)}
    assert "M11" in codes and "M8" not in codes
    fs = verify_document(doc, kit, expect_answers=None, answer_key=False, draft=True)
    assert "M8" in {f.code for f in errors(fs)}


def test_M7c_자리표시(준비):
    kit, doc, prepared = 준비
    _compose(doc, kit, prepared, 1, 정답={1: "①"})
    fs = verify_document(doc, kit, expect_answers=None, answer_key=False, draft=False)
    assert "M7c" in {f.code for f in errors(fs)}
    fs = verify_document(doc, kit, expect_answers=None, answer_key=False, draft=True)
    assert "M7c" not in {f.code for f in errors(fs)}


def test_M7d_견본_잔존(준비):
    kit, doc, prepared = 준비  # 견본이 그대로 남아 있는, 아직 조판 전인 문서
    fs = verify_document(doc, kit, expect_answers=None, answer_key=False, draft=True)
    assert "M7d" in {f.code for f in errors(fs)}


# ---- M10 기하 판정(_tail_box_findings)은 순수 함수라 한컴 렌더 없이 합성 PDF로 검증한다 ----
# hwpx 실렌더가 표 테두리를 변(가로선·세로선) 단위로 쪼개 내보내는 모양을 그대로 흉내 낸다(task-13-report.md).
# 실렌더 M10(빈 쪽·총쪽수·꼬리 박스 자리)은 tests/test_layout.py.

@pytest.fixture
def 킷(킷_루트):
    return load_kit(킷_루트)


def _테두리(page, x0, y0, x1, y1):
    for a, b in (((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))):
        page.draw_line(a, b, color=(0, 0, 0), width=0.36)


def _꼬리박스_합성쪽(kit, *, x0: float, dy: float = 0.0, 겹침: bool = False, 보기: bool = False):
    """꼬리 박스(폭 kit.tailbox.width)를 제자리(tail_box_top)에서 dy만큼 옮겨 그린 쪽."""
    W, H = kit.page["width"] / 100.0, kit.page["height"] / 100.0
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    y0 = tail_box_top(kit) + dy
    x1 = x0 + kit.tailbox["width"] / 100.0
    _테두리(page, x0, y0, x1, y0 + kit.tailbox["height"] / 100.0)
    if 보기:  # 같은 단 위쪽의 〈보기〉 박스(본문 표 폭) — 꼬리 박스로 섞이면 안 된다
        _테두리(page, x0, 500, x0 + kit.columns["body_table_width"] / 100.0, 600)
        page.draw_rect(pymupdf.Rect(x0 + 10, 520, x0 + 19, 529), color=None, fill=(0, 0, 0))
    if 겹침:
        page.draw_rect(pymupdf.Rect(x0 + 5, y0 + 5, x0 + 12, y0 + 18), color=None, fill=(0, 0, 0))
    return doc, page


def test_꼬리박스_기하_정상(킷):
    x0, _ = _right_column_x(킷)
    _pdf, page = _꼬리박스_합성쪽(킷, x0=x0)
    assert _tail_box_findings(page, 킷) == []
    _pdf, page = _꼬리박스_합성쪽(킷, x0=x0, 보기=True)
    assert _tail_box_findings(page, 킷) == []  # 오른쪽 단의 〈보기〉 박스가 꼬리 박스 외곽에 섞이지 않는다


def test_꼬리박스_기하_글자와_겹침(킷):
    x0, _ = _right_column_x(킷)
    _pdf, page = _꼬리박스_합성쪽(킷, x0=x0, 겹침=True)
    fs = _tail_box_findings(page, 킷)
    assert {f.code for f in fs} == {"M10"}
    assert "겹친다" in fs[0].msg


def test_꼬리박스_기하_텍스트_층_글자와_겹침(킷):
    x0, _ = _right_column_x(킷)
    _pdf, page = _꼬리박스_합성쪽(킷, x0=x0)
    page.insert_text((x0 + 20, tail_box_top(킷) + 50), "안쪽 글은 박스 자신의 글", fontsize=9)  # 통째로 안 — 겹침 아님
    assert _tail_box_findings(page, 킷) == []
    page.insert_text((x0 + 20, tail_box_top(킷) + 3), "ㄱ ㄴ", fontsize=11)  # 윗선에 걸친 텍스트 층 줄
    fs = _tail_box_findings(page, 킷)
    assert [f.code for f in fs] == ["M10"] and "겹친다" in fs[0].msg


def test_꼬리박스_기하_왼쪽단(킷):
    x0, _ = _left_column_x(킷)
    _pdf, page = _꼬리박스_합성쪽(킷, x0=x0)
    fs = _tail_box_findings(page, 킷)
    assert {f.code for f in fs} == {"M10"}
    assert "왼쪽" in fs[0].msg


def test_꼬리박스_기하_제자리_아님(킷):
    x0, _ = _right_column_x(킷)
    _pdf, page = _꼬리박스_합성쪽(킷, x0=x0, dy=-200)  # 오른쪽 단 중간에 뜬 박스
    fs = _tail_box_findings(page, 킷)
    assert [f.code for f in fs] == ["M10"] and "제자리" in fs[0].msg


def test_verify_render_빈_쪽과_총쪽수(킷, tmp_path, 준비):
    """합성 2쪽 PDF: 1쪽 본문, 2쪽 꼬리 박스만 → 빈 쪽. 총쪽수 누름틀 3 ≠ 2."""
    from exam_kit.render import RenderResult
    from exam_kit.slots import fill_total_pages

    kit, doc, _ = 준비
    x0, _ = _right_column_x(kit)
    pdf, _page = _꼬리박스_합성쪽(kit, x0=x0)
    first = pdf.new_page(0, width=_page.rect.width, height=_page.rect.height)
    first.draw_rect(pymupdf.Rect(60, 300, 69, 309), color=None, fill=(0, 0, 0))
    out = tmp_path / "blank.pdf"
    pdf.save(str(out))
    rr = RenderResult(pdf=out, pages=[], page_count=2, seconds=0.0, hwpx_sha256="")
    msgs = [f.msg for f in verify_render(rr, doc, kit, expected_pages=None)]
    assert any("총쪽수 누름틀이 채워지지 않았다: '몇'" in m for m in msgs)  # 자리표시 그대로
    fill_total_pages(doc, kit, 3)
    msgs = [f.msg for f in verify_render(rr, doc, kit, expected_pages=None)]
    assert any("본문이 없는 쪽: [2]" in m for m in msgs)
    assert any("총쪽수 누름틀 3 ≠ 렌더 쪽수 2" in m for m in msgs)
