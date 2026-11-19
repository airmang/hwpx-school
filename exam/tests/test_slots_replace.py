"""글자 자리 슬롯 바꾸기(replace_across) — 문단의 실제 글에서 찾고 공개 API로 바꾼다."""

import re
from datetime import datetime, timezone

import pytest
from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError

from exam_kit.slots import replace_across

_고정 = {"seed": 7, "now": datetime(2026, 1, 1, tzinfo=timezone.utc)}


def _문단(*조각: str):
    doc = HwpxDocument.new(**_고정)
    p = doc.add_paragraph(조각[0])
    for 글 in 조각[1:]:
        p.add_run(글)
    return doc, p


def test_탭으로_떨어진_글자는_이어진_글로_찾지_않는다():
    # 'A' · 'M<탭>N' · 'B' — 문단 글은 'AM\tNB'라 'AB'는 없다. 탭 든 조각을 빼고 이어 붙이면 'AB'가 생겨 잘못 바꿨다.
    _, p = _문단("A", "M\tN", "B")
    assert re.search("AB", p.text) is None
    assert replace_across(p, re.compile("AB"), "X") is False
    assert p.text == "AM\tNB"


def test_런을_넘는_자리는_찾은_곳이_시작하는_런의_모양으로_바뀐다():
    doc, p = _문단("가나", "다라")
    첫 = p.runs[0].char_pr_id_ref
    assert replace_across(p, re.compile("나다"), "XY") is True
    assert p.text == "가XY라"
    런 = next(r for r in p.runs if "XY" in r.text)
    assert 런.char_pr_id_ref == 첫


def test_탭_든_글에서도_찾는다():
    _, p = _문단("학년\t__반")
    assert replace_across(p, re.compile("__"), "3") is True
    assert p.text == "학년\t3반"


def test_못_찾으면_그대로():
    _, p = _문단("가나다")
    assert replace_across(p, re.compile("라"), "X") is False
    assert p.text == "가나다"


def _누름틀_문단():
    # 'A' · 'BC' · 'D' — 가운데 두 글자를 누름틀로 감싼다(누름틀 시작은 1, 끝은 3 자리)
    doc, p = _문단("A", "BC", "D")
    p.add_form_field("slot", start=1, end=3, prompt="P")
    return doc, p


@pytest.mark.parametrize(("찾을", "코드"), [
    ("AB", "paragraph-range-splits-field"),     # 누름틀 시작만 안쪽
    ("CD", "paragraph-range-splits-field"),     # 누름틀 끝만 안쪽
    ("ABCD", "paragraph-range-holds-objects"),  # 누름틀 통째로 안쪽
])
@pytest.mark.parametrize("새", ["X", "XYZ", ""])
def test_누름틀과_겹친_자리는_쓰기_전에_거부하고_문단을_그대로_둔다(찾을, 코드, 새):
    doc, p = _누름틀_문단()
    전 = doc.to_bytes()
    with pytest.raises(HwpxValueError) as e:
        replace_across(p, re.compile(찾을), 새)
    assert e.value.code == 코드
    assert p.text == "ABCD"
    assert doc.to_bytes() == 전  # 넣은 글도, 누름틀 값도 그대로 — 저장해도 바이트가 같다
    assert [f.value for f in HwpxDocument.open(doc.to_bytes()).fields.all] == ["BC"]


def test_형광펜_시작을_탭으로_옮겨야_하면_쓰기_전에_거부한다():
    # 'AB<탭>CD'의 'B<탭>C'에 형광펜 — 'AB'를 지우면 형광펜 시작이 탭 자리로 가야 해서 본체가 거부한다
    doc, p = _문단("AB\tCD")
    doc.text.highlight(p, start=1, end=4)
    전 = doc.to_bytes()
    with pytest.raises(HwpxValueError) as e:
        replace_across(p, re.compile("AB"), "X")
    assert e.value.code == "paragraph-range-splits-mark"
    assert doc.to_bytes() == 전


@pytest.mark.parametrize(("찾을", "글", "값"), [("BC", "AXD", "X"), ("B", "AXCD", "XC")])
def test_누름틀_양끝_사이의_글은_바꾼다(찾을, 글, 값):
    doc, p = _누름틀_문단()
    assert replace_across(p, re.compile(찾을), "X") is True
    다시 = HwpxDocument.open(doc.to_bytes())
    assert 다시.paragraphs[0].text == 글
    assert [f.value for f in 다시.fields.all] == [값]
