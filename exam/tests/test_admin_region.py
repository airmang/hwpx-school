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
from exam_kit.prepare import _replace_range, sample_role
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
