"""관리 구역이 문단 여럿인 서식·결재 쪽·형광펜 고칠 자리 — 학교 무관 합성 입력으로 고정한다.

새 학교 등록에서 처음 나온 서식 모양을 킷 값으로 받게 넓힌 엔진 동작:
- 관리 구역 = 문단 0 ~ admin.paragraph(결재표·제목표·유의 상자가 문단 여럿에 나뉜 서식)
- front_pages: 쪽 번호에 들지 않는 앞쪽(결재란만 있는 쪽) — 총쪽수 = 렌더 쪽수 − front_pages
- admin.unmark: 서식이 고칠 자리를 노란 형광펜으로 표시 — 채우면서 형광펜을 걷는다
- 쪽 수에 기대는 글자 자리({총쪽수}·{양면장수})는 총쪽수와 함께 채운다
"""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hwpx.document import HwpxDocument

from exam_kit.kit import admin_paragraphs, admin_tables, load_kit
from exam_kit.onboard import _body_columns
from exam_kit.prepare import _replace_range, drop_form_parts, fix_form_text, sample_role
from exam_kit.slots import fill_total_pages, pages_filled, read_total_pages, replace_across

_합성 = Path(__file__).resolve().parents[1] / "kits" / "synthetic"
_고정 = {"seed": 7, "now": datetime(2026, 1, 1, tzinfo=timezone.utc)}


def _킷(tmp_path: Path, **바꿀) -> Path:
    """합성 킷을 tmp에 복사하고 kit.json 최상위 키를 바꾼다."""
    root = tmp_path / "kit"
    shutil.copytree(_합성, root)
    d = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    for k, v in 바꿀.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    (root / "kit.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return root


# ---- front_pages -------------------------------------------------------------

def test_front_pages_없으면_0(tmp_path):
    assert load_kit(_킷(tmp_path)).front_pages == 0


def test_front_pages_값(tmp_path):
    assert load_kit(_킷(tmp_path, front_pages=1)).front_pages == 1


@pytest.mark.parametrize("나쁜", [-1, 1.5, True, "1"])
def test_front_pages_정수_아니면_멈춘다(tmp_path, 나쁜):
    with pytest.raises(ValueError, match="front_pages"):
        load_kit(_킷(tmp_path, front_pages=나쁜))


# ---- 관리 구역 -----------------------------------------------------------------

def test_관리_구역은_문단_0부터_admin_paragraph까지(tmp_path):
    doc = HwpxDocument.new(**_고정)
    for i in range(4):
        p = doc.add_paragraph(f"문단{i}")
        if i in (0, 2):
            p.add_table(1, 1)
    d = json.loads((_합성 / "kit.json").read_text(encoding="utf-8"))
    d["admin"]["paragraph"] = 2
    kit = load_kit(_킷(tmp_path, admin=d["admin"]))
    ps = list(doc.sections[0].paragraphs)
    assert [p.text for p in admin_paragraphs(doc, kit)] == [p.text for p in ps[:3]]
    assert len(admin_tables(doc, kit)) == len(ps[0].tables) + len(ps[2].tables)


def test_관리_구역_기본은_문단_0_하나():
    kit = load_kit(_합성)
    assert kit.admin["paragraph"] == 0
    doc = HwpxDocument.open(str(_합성 / "synthetic_form.hwpx"))
    assert len(admin_paragraphs(doc, kit)) == 1


def test_견본을_알아볼_스타일은_sample_style_없으면_style():
    assert sample_role({"style": "box"}) == "box"
    assert sample_role({"style": "box", "sample_style": "normal"}) == "normal"


# ---- 형광펜 고칠 자리 ------------------------------------------------------------

def _형광펜_문단(글: str, 칠할: str):
    doc = HwpxDocument.new(**_고정)
    p = doc.add_paragraph(글)
    p.add_highlight(color="#FFFF00", match=칠할)
    return doc, p


def _형광펜(doc) -> list[str]:
    return [h.text for h in doc.text.highlights]


def test_unmark면_찾은_글만_덮던_형광펜이_사라진다():
    doc, p = _형광펜_문단("인쇄 35*12 매", "35*12")
    assert replace_across(p, re.compile(r"\d+\*\d+"), "40*3", unmark=True) is True
    assert p.text == "인쇄 40*3 매"
    assert _형광펜(doc) == []


def test_unmark_아니면_형광펜이_새_글을_덮는다():
    doc, p = _형광펜_문단("인쇄 35*12 매", "35*12")
    assert replace_across(p, re.compile(r"\d+\*\d+"), "40*3") is True
    assert p.text == "인쇄 40*3 매"
    assert _형광펜(doc) == ["40*3"]  # 기존 동작 그대로


def test_글_바꾸기로_걷은_자리에_빈_형광펜이_남지_않는다():
    doc, p = _형광펜_문단("문항수 20문항 (선택형 20문항+논술형 0문항)", "+논술형 0문항")
    assert _replace_range(p, "+논술형 0문항", "") == 1
    assert p.text == "문항수 20문항 (선택형 20문항)"
    assert _형광펜(doc) == []


# ---- 쪽 수에 기대는 글자 자리 ----------------------------------------------------------

def _쪽_킷(tmp_path: Path) -> Path:
    """합성 킷 + 유의 상자의 '총점 : N점'을 양면 장 수 자리로 쓰는 슬롯(쪽 수에만 기대는 슬롯의 틀)."""
    d = json.loads((_합성 / "kit.json").read_text(encoding="utf-8"))
    slots = d["text_slots"] + [{"name": "장수", "where": {"notice": True},
                                "find": "총점 : \\S+점", "fill": "총점 : {양면장수}점"}]
    return _킷(tmp_path, text_slots=slots)


def test_총쪽수와_함께_쪽_수_자리를_채운다(tmp_path):
    kit = load_kit(_쪽_킷(tmp_path))
    doc = HwpxDocument.open(str(_합성 / "synthetic_form.hwpx"))
    assert not pages_filled(doc, kit, 5)
    fill_total_pages(doc, kit, 5)
    assert read_total_pages(doc, kit) == "5"
    assert pages_filled(doc, kit, 5)
    글 = "".join(p.text for t in admin_tables(doc, kit) for row in t.rows for c in row.cells for p in c.paragraphs)
    assert "총점 : 3점" in 글  # ⌈5 ÷ 2⌉


def test_쪽_수_자리가_없으면_총쪽수만_본다(tmp_path):
    kit = load_kit(_킷(tmp_path))
    doc = HwpxDocument.open(str(_합성 / "synthetic_form.hwpx"))
    fill_total_pages(doc, kit, 4)
    assert pages_filled(doc, kit, 4) and not pages_filled(doc, kit, 3)


# ---- 해부: 본문 단 ---------------------------------------------------------------

def test_본문_단은_단_수가_가장_많은_정의():
    class C:
        def __init__(self, n):
            self.count = n
    one, two = C(1), C(2)
    assert _body_columns([one, two]) is two
    assert _body_columns([two]) is two
    assert _body_columns([]) is None

# ---- 고르라고 준 관리 구역 부품 걷기(admin.drop) -----------------------------------------

def _두_벌_서식():
    """결재표 + 논술형 유의 상자(문단 0) · 안내 줄(1) · 선택형 유의 상자(2) · 빈 줄(3) · 규격표(4) · 본문(5)."""
    doc = HwpxDocument.new(**_고정)
    ps = [doc.add_paragraph(""), doc.add_paragraph("(선택형 문항만 출제할 경우에는 아래 표 사용)"),
          doc.add_paragraph(""), doc.add_paragraph(""), doc.add_paragraph(""), doc.add_paragraph("본문")]
    for p, 글 in ((ps[0], "결재"), (ps[0], "유의 논술형 문제는"), (ps[2], "유의 선택형"), (ps[4], "글자체")):
        p.add_table(1, 1).cell(0, 0).text = 글
    return doc


_규칙 = [{"table_with": "논술형 문제는"}, {"paragraph": 1, "with": "선택형 문항만"},
        {"paragraph": 3, "with": ""}, {"paragraph": 4, "with": "글자체"}]


def _drop_킷(tmp_path, 규칙):
    d = json.loads((_합성 / "kit.json").read_text(encoding="utf-8"))
    d["admin"].update(paragraph=1, drop=규칙)
    return load_kit(_킷(tmp_path, admin=d["admin"]))


def test_admin_drop은_고른_표와_문단만_걷는다(tmp_path):
    doc = _두_벌_서식()
    drop_form_parts(doc, _drop_킷(tmp_path, _규칙))
    ps = list(doc.sections[0].paragraphs)
    글 = lambda t: t.cell(0, 0).text
    assert [[글(t) for t in p.tables] for p in ps[:2]] == [["결재"], ["유의 선택형"]]
    assert ps[2].text == "본문" and len(ps) == 3  # 지운 것은 1·3·4번 문단


def test_admin_drop_없으면_그대로(tmp_path):
    doc = _두_벌_서식()
    n = len(list(doc.sections[0].paragraphs))
    drop_form_parts(doc, load_kit(_합성))
    assert len(list(doc.sections[0].paragraphs)) == n


@pytest.mark.parametrize("나쁜, 말", [
    ([{"table_with": "유의"}], "2개"),                       # 표가 하나로 정해지지 않는다
    ([{"paragraph": 1, "with": "논술형"}], "없다"),            # 문단 글이 다르다(양식이 바뀌었다)
    ([{"paragraph": 2, "with": ""}], "빈 문단이 아니다"),        # 표가 있는 문단을 빈 줄로 적었다
    ([{"cell": 1}], "table_with 또는 paragraph"),
])
def test_admin_drop_양식과_안_맞으면_멈춘다(tmp_path, 나쁜, 말):
    with pytest.raises(ValueError, match=말):
        drop_form_parts(_두_벌_서식(), _drop_킷(tmp_path, 나쁜))


# ---- 양식 머리말·꼬리말의 잘못 든 글 고치기(admin.form_fix) ---------------------------------

def _머리말_서식(머리="2학년 문항지`", 꼬리="- 1 -"):
    doc = HwpxDocument.new(**_고정)
    doc.add_paragraph("본문")
    doc.page.set_header(text=머리)
    doc.page.set_footer(text=꼬리)
    return doc


def _fix_킷(tmp_path, 규칙):
    d = json.loads((_합성 / "kit.json").read_text(encoding="utf-8"))
    d["admin"].update(form_fix=규칙)
    return load_kit(_킷(tmp_path, admin=d["admin"]))


def test_admin_form_fix는_머리말의_군더더기_글자를_지운다(tmp_path):
    doc = _머리말_서식()
    fix_form_text(doc, _fix_킷(tmp_path, [{"where": {"header_with": "문항지"}, "find": "`$", "fill": ""}]))
    assert [p.text for h in doc.page.headers() for p in h.paragraphs] == ["2학년 문항지"]
    assert [p.text for f in doc.page.footers() for p in f.paragraphs] == ["- 1 -"]  # 꼬리말은 그대로


def test_admin_form_fix는_꼬리말도_고친다(tmp_path):
    doc = _머리말_서식(꼬리="- 1 -  ")
    fix_form_text(doc, _fix_킷(tmp_path, [{"where": {"footer_with": "- 1"}, "find": r"\s+$", "fill": ""}]))
    assert [p.text for f in doc.page.footers() for p in f.paragraphs] == ["- 1 -"]


def test_admin_form_fix_없으면_그대로(tmp_path):
    doc = _머리말_서식()
    fix_form_text(doc, load_kit(_합성))
    assert [p.text for h in doc.page.headers() for p in h.paragraphs] == ["2학년 문항지`"]


@pytest.mark.parametrize("나쁜, 말", [
    ([{"where": {"header_with": "문항지"}, "find": "~$", "fill": ""}], "양식이 바뀌었다"),  # 학교가 이미 고쳤다
    ([{"where": {"header_with": "답안지"}, "find": "`$", "fill": ""}], "양식이 바뀌었다"),  # 그런 머리말이 없다
    ([{"where": {"notice": True}, "find": "`$"}], "header_with·footer_with"),              # 머리말·꼬리말 밖은 받지 않는다
    ([{"where": {"header_with": "문항지"}}], "header_with·footer_with"),                    # find가 없다
])
def test_admin_form_fix_양식과_안_맞으면_멈춘다(tmp_path, 나쁜, 말):
    with pytest.raises(ValueError, match=말):
        fix_form_text(_머리말_서식(), _fix_킷(tmp_path, 나쁜))
