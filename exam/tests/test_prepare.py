from pathlib import Path

import lxml.etree as ET
import pytest
from hwpx.document import HwpxDocument
from hwpx_automation.office.exam import lower_exam, parse_exam_markdown, profile_form, replace_body_region

from _helpers import 텍스트, 최상위_문단
from _kits import kit_dir
from exam_kit import q
from exam_kit._png import png
from exam_kit.frontmatter import parse_front_matter
from exam_kit.kit import load_kit, style_ids
from exam_kit.prepare import Prepared, finalize_form, prepare_document, prepare_form, prepared_for
from exam_kit.slots import fill_slots
from test_frontmatter import 머리

킷_디렉터리 = kit_dir()
합성_md = "# 합성\n" + "".join(
    f"## {k}. (4점)\n합성 발문 {k}?\n" + "".join(f"{m} 답지 {i}\n" for i, m in enumerate("①②③④⑤")) for k in range(1, 4)
)


def _표(p_el):
    return [t for run in p_el.findall(q("hp", "run")) for t in run.findall(q("hp", "tbl"))]


@pytest.fixture
def 준비(양식_hwpx):
    kit = load_kit(킷_디렉터리)
    doc, prepared = prepare_document(양식_hwpx, kit)
    return kit, doc, prepared


def test_관리박스_정리(준비, 양식_hwpx):
    kit, doc, prepared = 준비
    p0 = 최상위_문단(doc)[0].element
    t = 텍스트(p0)
    assert "출제교사" in t and "교  장" in t and "인쇄된 문항지" in t
    assert not any(w in t for w in kit.guidance_text) and "논술형" not in t
    유의 = next(x for x in _표(p0) if "인쇄된 문항지" in 텍스트(x))
    assert 유의.find(q("hp", "sz")).get("height") == str(kit.notice_box_height)
    assert all(tc.find(q("hp", "cellSz")).get("height") == str(kit.notice_box_height)
               for tr in 유의.findall(q("hp", "tr")) for tc in tr.findall(q("hp", "tc")))
    assert len(doc.list_form_fields()) == 18
    assert p0.find(q("hp", "linesegarray")) is None  # 규격표 높이를 기억하던 줄 캐시 제거(Task 22 렌더 실측)
    form = HwpxDocument.open(str(양식_hwpx))
    for tag in ("header", "footer"):
        a = doc.sections[0].element.find(f".//{q('hp', tag)}")
        b = form.sections[0].element.find(f".//{q('hp', tag)}")
        assert ET.tostring(a) == ET.tostring(b)


def test_본문은_샘플_구역만_남는다(준비):
    kit, doc, prepared = 준비
    ps = 최상위_문단(doc)
    texts = [텍스트(p.element) for p in ps]
    assert "저작권" in texts[-1]
    본문 = ps[1:-1]
    assert any("각 지도에 대한" in 텍스트(p.element) for p in 본문)          # 샘플 문항(교체 대상)은 남아 있다
    ids = style_ids(doc)
    보기 = [t for p in 본문 for t in _표(p.element) if t.get("rowCnt") == "4" and t.get("colCnt") == "5"]
    assert 보기 and ids["(보기)박스안내용"][0] in {x.get("styleIDRef") for x in 보기[0].iter(q("hp", "p"))}
    자료 = [t for p in 본문 for t in _표(p.element) if t.get("rowCnt") == "3" and t.get("colCnt") == "3"
           and ids["박스안내용"][0] in {x.get("styleIDRef") for x in t.iter(q("hp", "p"))}]
    assert len(자료) == 1
    assert not any(p.element.get("pageBreak") == "1" for p in ps)
    assert not any(w in "".join(texts) for w in ("Ctrl+2", "원안지 마지막 장", "논술형 1."))
    pos = _표(ps[-1].element)[0].find(q("hp", "pos"))
    assert (pos.get("treatAsChar"), pos.get("vertRelTo"), pos.get("horzOffset"), pos.get("vertOffset")) == \
        ("0", "PAPER", str(kit.tailbox["horzOffset"]), str(kit.tailbox["vertOffset"]))
    assert ps[-1].element.find(q("hp", "linesegarray")) is None  # 닻 문단의 낡은 줄 캐시(높이 9542) 제거(Task 26)
    tbl_sz = _표(ps[-1].element)[0].find(q("hp", "sz"))
    assert (int(tbl_sz.get("width")), int(tbl_sz.get("height"))) == (kit.tailbox["width"], kit.tailbox["height"])
    assert prepared.removed > 30 and len(prepared.form_bindata) == 3


def test_조판_뒤_마무리(준비, tmp_hwpx):
    kit, doc, prepared = 준비
    prof = profile_form(doc)                                   # v1이 샘플 구역을 앵커로 잡는다
    replace_body_region(doc, prof, lower_exam(parse_exam_markdown(합성_md), prof))
    finalize_form(doc, kit, prepared)
    sec_text = "".join(doc.sections[0].element.itertext())
    assert not any(w in sec_text for w in kit.forbidden_text)
    assert [n for n in doc.package.part_names() if n.startswith("BinData/")] == []
    assert doc.sections[0].element.find(f".//{q('hp', 'pic')}") is None
    assert doc.package.get_text("Preview/PrvText.txt") == ""
    assert doc.validate().ok
    ps = 최상위_문단(doc)
    assert "저작권" in 텍스트(ps[-1].element)
    heads = [p for p in ps if "합성 발문" in 텍스트(p.element)]
    assert len(heads) == 3
    assert 텍스트(ps[-2].element).strip() != "" or ps[-2].element.find(f".//{q('hp', 'tbl')}") is not None  # 꼬리 앞 빈 문단 0
    out = tmp_hwpx("final.hwpx")
    doc.save_to_path(str(out))
    assert HwpxDocument.open(str(out)).validate().ok


def test_슬롯_채움_뒤_마무리(준비, 양식_hwpx):
    kit, doc, prepared = 준비
    fm, _ = parse_front_matter(머리)

    # 머리말 슬롯(머리_학년/학기/차/과목)을 채운 뒤 refresh 없이 마무리하면 — 그 정당한
    # 변화를 "머리말이 양식과 다르다"로 오판해 실패해야 한다.
    fill_slots(doc, kit, fm, question_count=3, total_points=12.0, page_count=1)
    prof = profile_form(doc)
    replace_body_region(doc, prof, lower_exam(parse_exam_markdown(합성_md), prof))
    with pytest.raises(ValueError, match="머리말"):
        finalize_form(doc, kit, prepared)

    # 독립된 둘째 사본: 같은 순서라도 refresh를 끼우면 통과한다.
    doc2, prepared2 = prepare_document(양식_hwpx, kit)
    fill_slots(doc2, kit, fm, question_count=3, total_points=12.0, page_count=1)
    prepared2 = prepared2.refresh(doc2)
    prof2 = profile_form(doc2)
    replace_body_region(doc2, prof2, lower_exam(parse_exam_markdown(합성_md), prof2))
    finalize_form(doc2, kit, prepared2)  # 예외 없이 통과


def test_머리말_변조_검출(준비):
    kit, doc, prepared = 준비
    fm, _ = parse_front_matter(머리)
    fill_slots(doc, kit, fm, question_count=3, total_points=12.0, page_count=1)
    prepared = prepared.refresh(doc)
    prof = profile_form(doc)
    replace_body_region(doc, prof, lower_exam(parse_exam_markdown(합성_md), prof))
    sec = doc.sections[0].element
    header = sec.find(f".//{q('hp', 'header')}")
    header.find(f".//{q('hp', 'cellSz')}").set("height", "10668")  # refresh 이후의 진짜 변조
    with pytest.raises(ValueError, match="머리말"):
        finalize_form(doc, kit, prepared)


def test_삽입_그림_생존(준비):
    kit, doc, prepared = 준비
    prof = profile_form(doc)
    replace_body_region(doc, prof, lower_exam(parse_exam_markdown(합성_md), prof))
    bid = doc.media.add_image(png(60, 40, (120, 120, 120)), "png")
    doc.sections[0].paragraphs[1].add_picture(bid, width=6000, height=4000, treat_as_char=True)
    finalize_form(doc, kit, prepared)
    bindata = [n for n in doc.package.part_names() if n.startswith("BinData/")]
    assert bindata and not any(href in bindata for _, href in prepared.form_bindata)  # 문항 그림은 남고 양식 그림은 없다
    assert len(doc.sections[0].element.findall(f".//{q('hp', 'pic')}")) == 1
    assert doc.validate().ok


def test_사이드카(준비, tmp_hwpx):
    kit, doc, prepared = 준비
    p = tmp_hwpx("prep.hwpx")
    doc.save_to_path(str(p))
    prepared.save(p)
    assert prepared_for(p) == prepared


def test_양식_변조_감지(양식_hwpx):
    kit = load_kit(킷_디렉터리)
    doc = HwpxDocument.open(str(양식_hwpx))
    sec = doc.sections[0]
    보기_p = next(p for p in sec.paragraphs if any("< 보 기 >" in 텍스트(t) for t in _표(p.element)))
    sec.remove_paragraph(보기_p)
    with pytest.raises(ValueError, match="양식"):
        prepare_form(doc, kit)


def test_sha_검사(양식_hwpx, tmp_path):
    kit = load_kit(킷_디렉터리)
    bad = tmp_path / "bad.hwpx"
    bad.write_bytes(양식_hwpx.read_bytes() + b"\0")
    with pytest.raises(ValueError, match="sha256"):
        prepare_document(bad, kit)
