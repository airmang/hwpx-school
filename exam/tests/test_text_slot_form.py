"""글자 자리 양식 킷(범용화 두 번째 학교, 누름틀 없는 서식) — 양식 준비. 서식 파일이 없으면 건너뛴다(저장소에 넣지 않는다)."""

from pathlib import Path

from _kits import kit_dir, 글자자리_킷
from exam_kit import q
from exam_kit.compose import _body_region, harvest_samples
from exam_kit.kit import load_kit, verify_kit
from exam_kit.prepare import _text, _top_tables, prepare_document

킷_B = kit_dir(글자자리_킷)


def test_학교B_킷은_양식과_맞는다(학교B_양식):
    assert verify_kit(load_kit(킷_B), form_path=학교B_양식) == []


def test_학교B_양식_준비(학교B_양식):
    kit = load_kit(킷_B)
    doc, prep = prepare_document(학교B_양식, kit)
    sec = doc.sections[0].element
    ps = list(doc.sections[0].paragraphs)
    assert not [f for f in sec.iter(q("hp", "fieldBegin")) if f.get("type") == "MEMO"]  # 메모 14개(결정표 21)
    assert not [e for e in sec.iter() if e.tag in (q("hp", "line"), q("hp", "ellipse"))]  # 화살표·동그라미(23)
    assert not any(_text(p.element).strip().startswith("【논술형") for p in ps)  # 논술형·오른쪽 단 견본(25~27)
    [tail] = _top_tables(ps[-1].element)
    assert kit.tailbox["match_text"] in _text(tail)  # 꼬리 박스가 마지막(31)
    pos = tail.find(q("hp", "pos"))
    assert (pos.get("treatAsChar"), pos.get("vertRelTo")) == ("0", "PAPER")
    notice = next(t for t in _top_tables(ps[0].element) if "저작권" in _text(t))
    assert "논술형 :" not in _text(notice) and "선택형" in _text(notice)  # 17
    assert "논술형 답안" in _text(notice)  # 같은 낱말이 든 다른 안내 문장은 남는다
    assert _body_region(doc, kit) == (1, len(ps) - 2)  # 관리박스 뒤 ~ 꼬리 앞 전부


def test_학교B_견본_채집(학교B_양식):
    kit = load_kit(킷_B)
    doc, _ = prepare_document(학교B_양식, kit)
    s = harvest_samples(doc, kit)
    assert (s.보기_tbl.get("rowCnt"), s.보기_tbl.get("colCnt")) == ("5", "5") and "보 기" in _text(s.보기_tbl)
    assert (s.자료_tbl.get("rowCnt"), s.자료_tbl.get("colCnt")) == ("1", "1")


_머리 = ("---\n양식: 글자자리-예시\n학년도: 2026\n학년: 2\n학기: 2\n차: 2\n과목: 인공지능 기초\n"
        "시행: {시행}\n출제교사: 김편집, 이출제\n---\n")


def _셀글(doc, kit):
    from exam_kit.slots import _ts

    p0 = doc.sections[0].paragraphs[0].element
    tbl = next(t for t in _top_tables(p0) if "교장" in _text(t))
    return {(int(a.get("rowAddr")), int(a.get("colAddr"))): ["".join(x.text or "" for x in _ts(p))
                                                            for p in tc.find(q("hp", "subList")).findall(q("hp", "p"))]
            for tc in tbl.iter(q("hp", "tc")) for a in [tc.find(q("hp", "cellAddr"))]}


def test_학교B_글자_자리_슬롯(학교B_양식):
    from exam_kit.frontmatter import parse_front_matter
    from exam_kit.slots import fill_slots, fill_total_pages, read_total_pages

    kit = load_kit(킷_B)
    doc, _ = prepare_document(학교B_양식, kit)
    fm, _ = parse_front_matter(_머리.format(시행="12월 15일 (화) 3교시"), kit.front_matter)  # 과목코드·대상·인쇄 없이
    fill_slots(doc, kit, fm, question_count=20, total_points=100.0, page_count=None)
    셀 = _셀글(doc, kit)
    assert 셀[(0, 0)] == ["2026학년도 2학기 2차 정기시험"] and 셀[(0, 2)][0] == "2학년" and 셀[(0, 2)][1].strip() == "인공지능 기초"
    assert 셀[(2, 1)] == ["12월 15일 (화) 3교시"]
    assert 셀[(2, 3)] == ["출제교사 : 김편집 \U000f012b, 이출제 \U000f012b"]  # 편집자 맨 앞(원고 차례), 이름 뒤 도장 기호
    notice = next(t for t in _top_tables(doc.sections[0].paragraphs[0].element) if "저작권" in _text(t))
    assert "총점 : 100점" in _text(notice) and "선택형 : 100점(20문항)" in _text(notice)
    footer = [f for f in doc.sections[0].element.iter(q("hp", "footer")) if "쪽 중" in _text(f)][0]
    assert _text(footer).startswith("인공지능 기초 2학년 (")
    fill_total_pages(doc, kit, 4)
    assert read_total_pages(doc, kit) == "4"


def test_학교B_초안_시행은_자리표시로(학교B_양식):
    from exam_kit.frontmatter import parse_front_matter
    from exam_kit.slots import fill_slots

    kit = load_kit(킷_B)
    doc, _ = prepare_document(학교B_양식, kit)
    fm, _ = parse_front_matter(_머리.format(시행="__월 __일 (_) _교시"), kit.front_matter)
    assert fm.is_draft
    fill_slots(doc, kit, fm, question_count=20, total_points=100.0)
    assert _셀글(doc, kit)[(2, 1)] == ["__월 __일 (_) _교시"]  # 양식 예시 값(6월 29일)이 남지 않는다


def test_글자자리_합성_원고_두_판_조판(학교B_양식, tmp_path):
    """합성 원고(〈보기〉·〈조건〉·◦ 자료·자료, 글자 번호) → 문항지·답 표시본 — 기계 잔존 0, 정답은 형광펜으로 뽑힌다."""
    from hwpx.document import HwpxDocument

    from exam_kit.compose import compose
    from exam_kit.prepare import finalize_form
    from exam_kit.scan import scan_markdown
    from exam_kit.slots import fill_slots
    from exam_kit.verify import extract_answers, question_heads, verify_document

    kit = load_kit(킷_B)
    md = (Path(__file__).parent / "fixtures" / "글자자리_합성_4문항.md").read_text(encoding="utf-8")
    s = scan_markdown(md, kit.front_matter)
    정답 = {"1": "②", "2": "③", "3": "①", "4": "②"}
    for key in (False, True):
        doc, prep = prepare_document(학교B_양식, kit)
        fill_slots(doc, kit, s.front, question_count=len(s.questions), total_points=20.0)
        prep = prep.refresh(doc)
        compose(doc, s, kit, answer_key=key, image_root=tmp_path)
        finalize_form(doc, kit, prep)
        out = tmp_path / f"b_{key}.hwpx"
        doc.save_to_path(str(out))
        d2 = HwpxDocument.open(str(out))
        assert len(question_heads(d2)) == 4  # 글자 번호 문항 머리
        assert extract_answers(d2) == (정답 if key else {})
        assert verify_document(d2, kit, expect_answers=정답 if key else None, answer_key=key, draft=False) == []
        heads = [d2.sections[0].paragraphs[i].element for i in question_heads(d2)]
        첫_run = ["".join(t.text or "" for t in h.find(q("hp", "run")).findall(q("hp", "t"))) for h in heads]
        assert 첫_run == ["1. ", "2. ", "3. ", "4. "]  # 견본 번호 글자 모양으로 쓴 번호(결정표 3)


def test_학교B_학교_규칙은_메모_규칙만():
    from exam_kit.lint import lint

    kit = load_kit(킷_B)
    assert set(kit.rules["rules"]) == {"E014", "E007"}  # 그 학교 결정 — 메모 규칙만 켠다
    md = (Path(__file__).parent / "fixtures" / "글자자리_합성_4문항.md").read_text(encoding="utf-8")
    나쁜 = md.replace("옳은 것은?", "옳은 것을 고른 것은?", 1)
    codes = {v.code for v in lint(나쁜, rules=kit.rules)}
    assert "E014" in codes and "W020" not in codes and "E017" not in codes
