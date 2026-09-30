from pathlib import Path

import pytest
from hwpx.document import HwpxDocument

from _helpers import 텍스트, 최상위_문단
from exam_kit import q
from exam_kit.frontmatter import parse_front_matter
from exam_kit.kit import load_kit
from exam_kit.prepare import prepare_document
from exam_kit.slots import fill_slots, fill_total_pages, slot_values
from test_frontmatter import 머리


def _color(doc, char_pr_id: str) -> str:
    h = doc.headers[0].element
    return next(c.get("textColor") for c in h.iter(q("hh", "charPr")) if c.get("id") == char_pr_id)


def _charpr(doc, char_pr_id: str):
    h = doc.headers[0].element
    return next(c for c in h.iter(q("hh", "charPr")) if c.get("id") == char_pr_id)


def test_slot_values():
    fm, _ = parse_front_matter(머리)
    v = slot_values(fm, question_count=20, total_points=100.0, page_count=None)
    assert v["과목"] == "인공지능 기초" and v["과목코드"] == "16"
    assert v["머리_학년"] == "2" and v["머리_과목"] == "인공지능 기초"
    assert v["선택형_문항수"] == "20" and v["선택형_만점"] == "100"
    assert v["총쪽수"] is None and v["논술형_문항수"] is None


def test_fill_slots_양식(킷_루트, tmp_hwpx, 양식_hwpx):
    kit = load_kit(킷_루트)
    fm, _ = parse_front_matter(머리)
    doc, _ = prepare_document(양식_hwpx, kit)
    채움 = fill_slots(doc, kit, fm, question_count=20, total_points=100.0, page_count=4)
    assert 채움["총쪽수"] == "4" and "논술형_문항수" not in 채움
    values = {f.field_id: f.value for f in doc.list_form_fields()}
    assert values[kit.slots["과목"]] == "인공지능 기초"
    assert values[kit.slots["일"]] == "14" and values[kit.slots["요일"]] == "월"
    assert values[kit.slots["선택형_문항수"]] == "20"
    for slot, fid in kit.slot_ids().items():
        ph = kit.placeholders[slot]
        assert ph is None or values[fid] != ph, (slot, values[fid])
    p0 = 최상위_문단(doc)[0].element
    assert "출제교사" in 텍스트(p0) and "김출제 (인)" in 텍스트(p0) and "편집교사" not in 텍스트(p0)
    for run in p0.iter(q("hp", "run")):
        if any((t.text or "").strip() for t in run.findall(q("hp", "t"))):
            assert _color(doc, run.get("charPrIDRef")) != "#FF0000"
    이름_run = next(r for r in p0.iter(q("hp", "run")) if any((t.text or "") == "김출제 (인)" for t in r.findall(q("hp", "t"))))
    이름_charpr = _charpr(doc, 이름_run.get("charPrIDRef"))
    assert 이름_charpr.get("textColor") == "#000000"
    assert 이름_charpr.find(q("hh", "italic")) is None  # 기울임 없는 정자체
    out = tmp_hwpx("filled.hwpx")
    doc.save_to_path(str(out))
    assert HwpxDocument.open(str(out)).validate().ok


def test_초안은_미확정_슬롯을_남긴다(킷_루트, 양식_hwpx):
    kit = load_kit(킷_루트)
    fm, _ = parse_front_matter(머리.replace("12.14.(월) 3교시", "12.__.(_) _교시"))
    doc, _ = prepare_document(양식_hwpx, kit)
    채움 = fill_slots(doc, kit, fm, question_count=20, total_points=100.0)
    assert "일" not in 채움 and 채움["월"] == "12"
    values = {f.field_id: f.value for f in doc.list_form_fields()}
    assert values[kit.slots["일"]] == "일"  # 자리표시 그대로 — verify.py M-7c가 초안 경고로 잡는다


def test_총쪽수만_다시_채운다(킷_루트, tmp_hwpx, 양식_hwpx):
    kit = load_kit(킷_루트)
    fm, _ = parse_front_matter(머리)
    doc, _ = prepare_document(양식_hwpx, kit)
    fill_slots(doc, kit, fm, question_count=20, total_points=100.0)  # 쪽수는 아직 모른다
    fid = kit.slots["총쪽수"]
    assert {f.field_id: f.value for f in doc.list_form_fields()}[fid] == "몇"
    for n in (3, 4):  # 두 번 채워도 마지막 값 하나
        fill_total_pages(doc, kit, n)
        values = {f.field_id: f.value for f in doc.list_form_fields()}
        assert values[fid] == str(n) and values[kit.slots["선택형_문항수"]] == "20"
    p0 = 최상위_문단(doc)[0].element
    for run in p0.iter(q("hp", "run")):
        if any((t.text or "") == "4" for t in run.findall(q("hp", "t"))):
            assert _color(doc, run.get("charPrIDRef")) != "#FF0000"
    out = tmp_hwpx("pages.hwpx")
    doc.save_to_path(str(out))
    assert HwpxDocument.open(str(out)).validate().ok
