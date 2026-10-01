"""보존 블록(서술형·논술형 등 아직 조판하지 않는 구간) — 역변환이 떼어 두고, 조판이 원본 모양 그대로 다시 심는다.

합성 킷·합성 문서만: 합성 원고를 조판한 문서의 꼬리 박스 앞에 서술형 구간(글 두 문단 + 표)을 손으로 넣어 '원안지'로 삼는다."""

from pathlib import Path

import pytest
from exam_kit import preserve
from exam_kit.kit import load_kit
from exam_kit.lint import lint
from exam_kit.reverse import reverse
from exam_kit.roundtrip import rebuild, roundtrip
from exam_kit.scan import scan_markdown
from exam_kit.verify import _tail_index, question_heads
from hwpx.document import HwpxDocument

킷 = Path(__file__).resolve().parents[1] / "kits" / "synthetic"
서식 = 킷 / "synthetic_form.hwpx"
픽스처 = Path(__file__).parent / "fixtures"
서술형 = "【서술형 1】 합성 서술형 물음이다. 까닭을 쓰시오. (5점)"


def _원안지(tmp_path: Path) -> Path:
    kit = load_kit(킷)
    md = 픽스처 / "합성서식_6문항.md"
    base = rebuild(md.read_text(encoding="utf-8"), kit, 서식, 픽스처, tmp_path / "base.hwpx")
    doc = HwpxDocument.open(str(base))
    sec = doc.sections[0]
    tail = _tail_index(doc, kit.tailbox["match_text"])
    added = [doc.add_paragraph(서술형), doc.add_paragraph("(1) 합성 첫째 물음")]
    t = doc.add_table(2, 2)
    t.cell(0, 0).text, t.cell(1, 1).text = "가", "나"
    added.append(list(sec.paragraphs)[-1])
    sec.insert_paragraphs(tail, added)
    for p in added:
        sec.remove_paragraph(p)
    sec.mark_dirty()
    out = tmp_path / "원안지.hwpx"
    doc.save_to_path(str(out))
    return out


def test_역변환은_서술형_구간을_보존_블록으로_뗀다(tmp_path):
    md = reverse(_원안지(tmp_path), load_kit(킷), image_dir=tmp_path / "원고")
    s = scan_markdown(md, load_kit(킷).front_matter)
    assert s.errors == () and len(s.questions) == 6  # 서술형은 문항으로 읽지 않는다
    (b,) = s.preserved
    assert b.attrs["src"] == "보존_01.hwpx" and b.lines[0] == 서술형 and b.lines[-1] == "가나"
    part = HwpxDocument.open(str(tmp_path / "원고" / "보존_01.hwpx"))
    # 문단 0은 구역 설정만(꼬리말 글은 secPr 안 — 넣을 때 insert_document가 secPr째 뗀다), 구간 문단은 그대로
    assert preserve.preview([p.element for p in part.sections[0].paragraphs[1:]]) == list(b.lines)
    assert all(v.code != "E026" for v in lint(md, md_dir=tmp_path / "원고"))


def test_왕복하면_같은_자리에_원본_모양으로_다시_심긴다(tmp_path):
    r = roundtrip(_원안지(tmp_path), load_kit(킷), 서식, tmp_path / "rt")
    assert r.same, r.diffs
    doc = HwpxDocument.open(str(tmp_path / "rt" / "다시_조판.hwpx"))
    (a, b), = preserve.ranges(doc)
    ps = [p.element for p in doc.sections[0].paragraphs]
    assert preserve.preview(ps[a:b + 1]) == [서술형, "(1) 합성 첫째 물음", "가나"]
    assert b == _tail_index(doc, load_kit(킷).tailbox["match_text"]) - 1  # 문항 뒤·꼬리 박스 바로 앞
    assert all(h < a for h in question_heads(doc))  # 보존 구간의 머리는 문항이 아니다
    assert ps[a].find(".//{*}tbl") is None and ps[b].find(".//{*}tbl") is not None  # 표도 그대로


def test_보존_블록_문법():
    head = ("---\n양식: x\n학년도: 2026\n학년: 1\n학기: 1\n차: 1\n과목: x\n시행: 4.20.(월) 2교시\n출제교사: x\n---\n"
            "## 1. [1.0점]\n가?\n\n*① a\n② b\n③ c\n④ d\n⑤ e\n")
    ok = scan_markdown(head + '\n## 보존\n:::보존 src="보존_01.hwpx"\n미리보기\n:::\n')
    assert ok.errors == () and ok.preserved[0].attrs["src"] == "보존_01.hwpx"
    reasons = lambda md: [e.reason for e in scan_markdown(md).errors]
    assert any("`## 보존` 아래에만" in r for r in reasons(head + ':::보존 src="x.hwpx"\n:::\n'))
    assert any("문항은 그 앞에" in r for r in reasons(head + '\n## 보존\n:::보존 src="x.hwpx"\n:::\n## 2. [1.0점]\n'))
    assert any("src" in r for r in reasons(head + "\n## 보존\n:::보존\n:::\n"))


def test_보존_파일이_없으면_E026(tmp_path):
    md = ("---\n양식: x\n학년도: 2026\n학년: 1\n학기: 1\n차: 1\n과목: x\n시행: 4.20.(월) 2교시\n출제교사: x\n---\n"
          '## 1. [1.0점]\n가?\n\n*① a\n② b\n③ c\n④ d\n⑤ e\n\n## 보존\n:::보존 src="없는.hwpx"\n:::\n')
    assert [v.code for v in lint(md, md_dir=tmp_path) if v.code == "E026"] == ["E026"]


@pytest.mark.parametrize("text, hit", [("【서술형 1】 쓰시오", True), ("[논술형 2] 논하시오", True), ("서답형 1. 답하시오", True),
                                       ("■ 서·논술형", True), ("서술형 문항의 특징으로 옳은 것은?", True),
                                       ("다음은 서술의 한 방법이다.", False), ("① 서술형", False)])
def test_보존_구간_시작_글(text, hit):
    assert bool(preserve.START_RE.match(text)) is hit


def test_보존_블록이_든_원고_전체_조판_실렌더(오라클, tmp_path):
    """역변환 원고(보존 블록 포함)를 실한컴 렌더 루프까지 — 두 판 기계 잔존 0, 보존 구간은 문항 뒤·꼬리 박스 앞."""
    from exam_kit.build import build

    reverse_dir = tmp_path / "원고"
    md = reverse(_원안지(tmp_path), load_kit(킷), image_dir=reverse_dir)
    (reverse_dir / "원고.md").write_text(md, encoding="utf-8")
    r = build(reverse_dir / "원고.md", 킷, tmp_path / "out", form_path=서식)
    assert not r.blocked and r.residue("문항지") == 0 and r.residue("답표시본") == 0, r.findings
    doc = HwpxDocument.open(str(r.문항지))
    (_, b), = preserve.ranges(doc)
    assert b == _tail_index(doc, load_kit(킷).tailbox["match_text"]) - 1
