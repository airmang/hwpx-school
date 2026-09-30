"""합성 서식·합성 킷(kits/synthetic) — 학교 킷 없이 도는 엔진 끝까지 테스트.

서식은 tools/make_synthetic_form.py가 python-hwpx 기본 템플릿에서 만든 학교 무관 서식이다. 이 파일의 테스트는
환경변수 없이 누구 PC에서든 돈다(실렌더 하나만 한컴이 있을 때).
"""

from pathlib import Path

import pytest
from hwpx.document import HwpxDocument

from exam_kit import q
from exam_kit.compose import _body_region, compose, harvest_samples
from exam_kit.kit import load_kit, verify_kit
from exam_kit.lint import errors, lint
from exam_kit.onboard import scan
from exam_kit.prepare import _text, _top_tables, finalize_form, prepare_document
from exam_kit.scan import scan_markdown
from exam_kit.slots import fill_slots, read_total_pages
from exam_kit.verify import extract_answers, question_heads, verify_document

킷 = Path(__file__).resolve().parents[1] / "kits" / "synthetic"
서식 = 킷 / "synthetic_form.hwpx"
원고 = Path(__file__).parent / "fixtures" / "합성서식_6문항.md"
정답 = {"1": "②", "2": "②", "3": "③", "4": "①", "5": "④", "6": "⑤"}


def test_합성_킷은_합성_서식과_맞는다():
    assert verify_kit(load_kit(킷), form_path=서식) == []


def test_합성_서식_해부():
    r = scan(서식)
    assert "## 누름틀 0개" in r and "## 메모 0개" in r
    assert "number.mode 후보 literal" in r and "논술형/서술형으로 시작하는 문단 #" in r


def test_합성_서식_준비():
    kit = load_kit(킷)
    doc, _ = prepare_document(서식, kit)
    ps = list(doc.sections[0].paragraphs)
    assert not any(_text(p.element).strip().startswith("【논술형") for p in ps)
    [tail] = _top_tables(ps[-1].element)
    assert "확인 사항" in _text(tail)
    assert tail.find(q("hp", "pos")).get("vertRelTo") == "PAPER"
    notice = next(t for t in _top_tables(ps[0].element) if "유의" in _text(t))
    assert "논술형 :" not in _text(notice)
    assert _body_region(doc, kit) == (1, len(ps) - 2)
    s = harvest_samples(doc, kit)
    assert s.번호_charpr is not None and "보 기" in _text(s.보기_tbl)


def _조판(answer_key: bool, tmp_path: Path) -> HwpxDocument:
    kit = load_kit(킷)
    s = scan_markdown(원고.read_text(encoding="utf-8"), kit.front_matter)
    doc, prep = prepare_document(서식, kit)
    fill_slots(doc, kit, s.front, question_count=len(s.questions), total_points=30.0)
    prep = prep.refresh(doc)
    compose(doc, s, kit, answer_key=answer_key, image_root=원고.parent)
    finalize_form(doc, kit, prep)
    out = tmp_path / f"합성_{answer_key}.hwpx"
    doc.save_to_path(str(out))
    return HwpxDocument.open(str(out))


def test_합성_원고_규칙_검사():
    assert errors(lint(원고.read_text(encoding="utf-8"))) == []


@pytest.mark.parametrize("answer_key", [False, True])
def test_합성_원고_두_판_조판(answer_key, tmp_path):
    kit = load_kit(킷)
    doc = _조판(answer_key, tmp_path)
    assert len(question_heads(doc)) == 6
    assert extract_answers(doc) == (정답 if answer_key else {})
    assert verify_document(doc, kit, expect_answers=정답 if answer_key else None, answer_key=answer_key, draft=False) == []
    결재 = _text(next(t for t in _top_tables(doc.sections[0].paragraphs[0].element) if "결  재" in _text(t)))
    assert "2026학년도 1학기 1차" in 결재 and "2학년" in 결재 and "4월 20일 (월) 2교시" in 결재 and "김출제, 이검토" in 결재
    assert read_total_pages(doc, kit) == "1"  # 총쪽수는 렌더 뒤에 채운다 — 서식 값 그대로


def test_합성_원고_전체_조판_실렌더(오라클, tmp_path):
    from exam_kit.build import build

    r = build(원고, 킷, tmp_path / "out", form_path=서식)
    assert not r.blocked
    assert r.findings and all(fs == [] for fs in r.findings.values()), r.findings  # 두 판 기계 잔존 0
