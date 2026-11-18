"""글자 자리 슬롯 바꾸기(replace_across) — 문단의 실제 글에서 찾고 공개 API로 바꾼다."""

import re
from datetime import datetime, timezone

from hwpx.document import HwpxDocument

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
