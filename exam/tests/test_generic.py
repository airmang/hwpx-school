"""킷 없는 양식의 역변환(exam_kit.generic, 이슈 #8 일반 규칙) — 합성 문서만.

합성 킷으로 조판한 원안지를 '킷을 모르는 양식'으로 보고 일반 규칙으로 읽는다: 문항 머리·박스·꼬리·머리 값을 킷 없이 찾고,
합성 킷 위에 다시 조판해 왕복 불변을 본다."""

from pathlib import Path
from xml.sax.saxutils import escape

import lxml.etree as ET
import pytest
from exam_kit import HP
from exam_kit.generic import front, generic_profile, heads, tail
from exam_kit.kit import load_kit
from exam_kit.reverse import GENERIC_BOXES, classify_table, reverse
from exam_kit.roundtrip import rebuild, roundtrip
from exam_kit.scan import scan_markdown
from hwpx.document import HwpxDocument

킷 = Path(__file__).resolve().parents[1] / "kits" / "synthetic"
서식 = 킷 / "synthetic_form.hwpx"
픽스처 = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name", ["합성서식_6문항.md", "견본_전유형.md", "수식_합성.md", "글자자리_합성_4문항.md"])
def test_킷_없이_읽어도_왕복_불변(name, tmp_path):
    kit = load_kit(킷)
    src = rebuild((픽스처 / name).read_text(encoding="utf-8"), kit, 서식, 픽스처, tmp_path / "원안지.hwpx")
    r = roundtrip(src, kit, 서식, tmp_path / "rt", source=generic_profile(), front={"과목": "합성"})
    assert r.same, r.diffs


def test_킷으로_읽은_것과_같은_원고(tmp_path):
    """합성 서식에서 일반 규칙의 본문 = 합성 킷 프로필의 본문(머리 값 줄만 다를 수 있다)."""
    kit = load_kit(킷)
    src = rebuild((픽스처 / "견본_전유형.md").read_text(encoding="utf-8"), kit, 서식, 픽스처, tmp_path / "원안지.hwpx")
    a = reverse(src, kit, image_dir=tmp_path / "a").split("---", 2)[2]
    b = reverse(src, generic_profile(), image_dir=tmp_path / "b", front={"과목": "합성"}).split("---", 2)[2]
    assert a == b


def _doc(texts: list[str]) -> HwpxDocument:
    doc = HwpxDocument.new()
    for t in texts:
        doc.add_paragraph(t)
    return doc


def test_문항_머리는_차례대로_이어지는_번호만():
    doc = _doc(["안내: 3. 답안지에 쓰시오.", "1. 첫 물음? [3점]", "① 가", "2) 둘째 물음? (4점)", "5. 엉뚱한 번호", "3. 셋째 물음?"])
    texts = [p.text for p in doc.sections[0].paragraphs]
    assert [texts[i] for i in heads(doc)] == ["1. 첫 물음? [3점]", "2) 둘째 물음? (4점)", "3. 셋째 물음?"]


def test_머리_값은_괄호_안_값도_찾는다():
    doc = _doc(["2026학년도 (1)학년 (2)학기 (1)차 정기시험 (합성과학)과 문항지", "시행: 11월 20일 (목) 3교시  출제교사: 김합성",
                "1. 물음?"])
    f = front(doc)
    assert (f["학년도"], f["학년"], f["학기"], f["차"], f["과목"]) == ("2026", "1", "2", "1", "합성과학")
    assert f["시행"] == "11.20.(목) 3교시" and f["출제교사"] == "김합성" and f["양식"] == "미등록"


def test_꼬리는_마지막_문항_뒤_안내_상자():
    doc = _doc(["1. 물음?", "① 가"])
    t = doc.add_table(1, 1)
    t.cell(0, 0).text = "※ 확인 사항 — 답안지를 확인하시오."
    assert tail(doc) == len(doc.sections[0].paragraphs) - 1
    assert tail(_doc(["1. 물음?", "① 가"])) == 3  # 안내 상자가 없으면 문서 끝


def _tbl(rows: list[list[str]], spans: dict | None = None):
    spans = spans or {}
    trs = ""
    for r, row in enumerate(rows):
        tcs = ""
        for c, text in enumerate(row):
            if text is None:
                continue
            rs, cs = spans.get((r, c), (1, 1))
            run = f'<hp:run charPrIDRef="0"><hp:t>{escape(text)}</hp:t></hp:run>' if text else ""
            tcs += (f'<hp:tc><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0">{run}</hp:p></hp:subList>'
                    f'<hp:cellAddr colAddr="{c}" rowAddr="{r}"/><hp:cellSpan colSpan="{cs}" rowSpan="{rs}"/></hp:tc>')
        trs += f"<hp:tr>{tcs}</hp:tr>"
    return ET.fromstring(f'<hp:tbl xmlns:hp="{HP}" rowCnt="{len(rows)}" colCnt="{len(rows[0])}">{trs}</hp:tbl>')


@pytest.mark.parametrize("title", ["< 보 기 >", "〈보기〉", "[보기]", "보 기"])
def test_제목_글로_보기_박스를_찾는다(title):
    kind, lines = classify_table(_tbl([[title], ["ㄱ. 합성 하나."], ["ㄴ. 합성 둘."]]), set(), boxes=GENERIC_BOXES)
    assert (kind, lines) == ("보기", ["ㄱ. 합성 하나.", "ㄴ. 합성 둘."])


def test_조건_박스와_자료_틀():
    assert classify_table(_tbl([["〈조건〉"], ["(가) 합성 조건."]]), set(), boxes=GENERIC_BOXES) == ("조건", ["(가) 합성 조건."])
    assert classify_table(_tbl([["합성 자료 글."]]), set(), boxes=GENERIC_BOXES) == ("자료", ["합성 자료 글."])
    frame = _tbl([["", None, None], ["", "틀 안 자료.", ""], ["", None, None]], {(0, 0): (1, 3), (2, 0): (1, 3)})
    assert classify_table(frame, set(), boxes=GENERIC_BOXES) == ("자료", ["틀 안 자료."])
    kind, lines = classify_table(_tbl([["열", "값"], ["가", "1"]]), set(), boxes=GENERIC_BOXES)
    assert kind == "표" and lines[0] == "| 열 | 값 |"


def test_역변환_명령은_킷_없이도_돈다(tmp_path, capsys):
    from exam_kit.reverse import main

    kit = load_kit(킷)
    src = rebuild((픽스처 / "합성서식_6문항.md").read_text(encoding="utf-8"), kit, 서식, 픽스처, tmp_path / "원안지.hwpx")
    assert main([str(src), "--out", str(tmp_path / "md" / "원고.md"), "--front", "과목=합성"]) == 0
    assert "일반 규칙으로 읽었다" in capsys.readouterr().out
    s = scan_markdown((tmp_path / "md" / "원고.md").read_text(encoding="utf-8"))
    assert len(s.questions) == 6 and s.front.양식 == "미등록"
