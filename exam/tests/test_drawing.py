"""좌표로 그리는 도형(`:::도형`, exam_kit.drawing) — 원고 문법·검사·조판·역변환 멈춤·작은 수정·렌더. 합성 킷만.

10-29 owner: 그림 한 장으로 넣으면 선분·글자를 한/글에서 따로 고칠 수 없다 — 개체마다 따로 넣어 손으로 마무리할 수 있게."""

from pathlib import Path

import pytest
from exam_kit import drawing, q
from exam_kit.kit import load_kit
from exam_kit.lint import lint, rule_E008
from exam_kit.roundtrip import rebuild
from exam_kit.scan import Block, scan_markdown

루트 = Path(__file__).resolve().parents[1]
킷 = 루트 / "kits" / "synthetic"
서식 = 킷 / "synthetic_form.hwpx"
픽스처 = Path(__file__).parent / "fixtures"

머리 = """---
양식: synthetic
학년도: 2026
학년: 1
학기: 1
차: 1
과목: 수학
시행: 4월 21일 (화) 1교시
출제교사: 김출제
만점: 5
---
"""
도형 = """점 A 2.5 0.35 위
점 B 0.4 2.6 왼쪽
점 C 2.2 3.7 아래
점 D 4.6 2.4 오른쪽
점 H 3.2 2.95 -
면 ABC 옅게
선 AB AC AD BC CD
점선 BD AH
길이 BC 8 오른쪽
직각 H AD
● H
곡선 0.5 3.5 1.0 3.0 1.6 2.9"""


def _md(body: str = 도형, attrs: str = "width=5cm height=4cm") -> str:
    return 머리 + f"""
## 1. [5.0점]
그림의 사면체에서 값은?

:::도형 {attrs}
{body}
:::

*① $1$
② $2$
③ $3$
④ $4$
⑤ $5$
"""


def _block(md: str) -> Block:
    [b] = [b for b in scan_markdown(md).questions[0].blocks if b.kind == "도형"]
    return b


def _codes(md: str) -> list[str]:
    return [v.code for v in lint(md)]


# --- 원고 문법·검사 -------------------------------------------------------------


def test_원고_문법():
    d = drawing.parse(_block(_md()))
    assert d.bad == [] and (d.width_cm, d.height_cm) == (5.0, 4.0)
    assert d.points["A"] == (2.5, 0.35) and d.label_dir["A"] == "위" and d.label_dir["H"] is None
    assert ("B", "D", True) in d.lines and ("A", "B", False) in d.lines and len(d.lines) == 7
    assert d.faces == [(["A", "B", "C"], drawing.채움["옅게"])]
    assert d.lengths == [("B", "C", "8", "오른쪽")] and d.rights == [("H", "A", "D")]
    assert d.dots == [(3.2, 2.95)] and d.curves == [([(0.5, 3.5), (1.0, 3.0), (1.6, 2.9)], False)]
    assert not {"E025", "E029"} & set(_codes(_md()))


@pytest.mark.parametrize("body, why", [
    ("점 A 1 1 위\n선 AZ", "정의하지 않은 점 Z"),
    ("점 A 9 1 위", "틀"),
    ("점 A 1 1 북쪽", "이름 놓을 쪽"),
    ("점 A 1 1 위\n삼각형 ABC", "모르는 줄"),
    ("곡선 1 1 2", "좌표 셋"),
])
def test_E029_도형_문법(body, why):
    md = _md(body)
    assert any(v.code == "E029" and why in v.msg for v in lint(md)), [v.msg for v in lint(md)]


def test_E029_틀_크기가_없으면():
    assert "E029" in _codes(_md("점 A 1 1 위", attrs=""))


def test_E025_도형_글자도_수식():
    assert "E025" in _codes(_md("점 B 0.4 2.6 왼쪽\n점 C 2.2 3.7 아래\n길이 BC $\\frac{1$ 오른쪽"))


def test_학교_규칙_E008은_도형을_그림_자리로():
    cfg = {"order": {"자료": 0, "표": 0, "그림": 0, "코드": 0, "보기": 1, "주": 1, "답항표": 2}, "message": "순서"}
    assert rule_E008(scan_markdown(_md()), cfg) == []


# --- 기하 -----------------------------------------------------------------------


def test_길이_호는_진행_방향의_왼쪽_오른쪽으로_휜다():
    (_, top, _), n = drawing.length_arc((0, 0), (2, 0), "왼쪽")  # 오른쪽으로 갈 때 왼쪽 = 화면 위(y −)
    assert top[1] < 0 and n == (0.0, -1.0)
    (_, top, _), _ = drawing.length_arc((0, 0), (2, 0), "오른쪽")
    assert top[1] > 0


def test_겹침_판정():
    assert drawing.hits_box(((0, 0), (2, 2)), (0.9, 0.9, 1.1, 1.1))
    assert not drawing.hits_box(((0, 0), (2, 0)), (0.9, 0.1, 1.1, 0.3))


# --- 조판 ----------------------------------------------------------------------


@pytest.fixture
def 조판(tmp_path):
    from hwpx.document import HwpxDocument

    src = rebuild(_md(), load_kit(킷), 서식, 픽스처, tmp_path / "원안지.hwpx")
    doc = HwpxDocument.open(str(src))
    host = next(p.element for p in doc.sections[0].paragraphs if p.element.find(f".//{q('hp', 'rect')}") is not None)
    return src, doc, host


def test_조판_개체마다_따로(조판):
    _, _, host = 조판
    objs = [e for r in host.findall(q("hp", "run")) for e in r if e.tag.split("}")[1] in
            ("rect", "polygon", "line", "curve", "equation", "ellipse")]
    kinds = [e.tag.split("}")[1] for e in objs]
    # 틀 → 면 → 선 7 → 곡선(자유) → 길이 호 → 직각 2변 → 점 이름 4·길이 숫자 1 → 점 — 위에 그려지는 차례
    assert kinds == ["rect", "polygon"] + ["line"] * 7 + ["curve", "curve"] + ["line"] * 2 + ["equation"] * 5 + ["ellipse"]
    frame, *floats = objs
    assert frame.find(q("hp", "pos")).get("treatAsChar") == "1"
    assert frame.find(q("hp", "lineShape")).get("style") == "NONE"  # 보이지 않는 틀
    assert all(f.get("textWrap") == "IN_FRONT_OF_TEXT" and f.find(q("hp", "pos")).get("treatAsChar") == "0" for f in floats)
    dashed = [e for e in objs if e.tag == q("hp", "line") and e.find(q("hp", "lineShape")).get("style") == "DASH"]
    assert len(dashed) == 2  # 점선 BD·AH
    assert [int(f.get("zOrder")) for f in floats] == sorted(int(f.get("zOrder")) for f in floats)


def test_점_이름이_선과_겹치면_알린다(tmp_path):
    from exam_kit.compose import compose
    from exam_kit.prepare import prepare_document
    from exam_kit.slots import fill_slots

    kit = load_kit(킷)
    s = scan_markdown(_md("점 A 0.5 2 오른쪽\n점 B 3 2 -\n선 AB"), kit.front_matter)  # A 이름을 선분 AB 위에
    doc, _ = prepare_document(서식, kit)
    fill_slots(doc, kit, s.front, question_count=1, total_points=5.0)
    notes = compose(doc, s, kit, answer_key=False, image_root=tmp_path).notes
    assert any("[글자·선 겹침]" in n and "mathrm{A}" in n for n in notes)


def test_역변환은_도형에서_까닭을_대고_멈춘다(조판):
    from exam_kit.reverse import ReverseStop, reverse

    src, _, _ = 조판
    with pytest.raises(ReverseStop, match=":::도형"):
        reverse(src, load_kit(킷), image_dir=src.parent / "그림")


def test_작은_수정은_도형이_바뀌면_다시_조판(tmp_path):
    from exam_kit.patch import NeedsRebuild, apply_patch
    from hwpx.document import HwpxDocument

    kit = load_kit(킷)
    old = HwpxDocument.open(str(rebuild(_md(), kit, 서식, 픽스처, tmp_path / "old.hwpx")))
    new = HwpxDocument.open(str(rebuild(_md(도형.replace("점 D 4.6 2.4", "점 D 4.5 2.4")), kit, 서식, 픽스처, tmp_path / "new.hwpx")))
    with pytest.raises(NeedsRebuild, match="도형"):
        apply_patch(old, new, kit)


# --- 렌더 ----------------------------------------------------------------------


def test_렌더_선분이_좌표대로(조판, 오라클, tmp_path):
    """실한컴: 실선 AD의 PDF 길이·기울기가 원고 좌표와 같고(0.05cm), 점 이름 A가 꼭짓점 A 위에 떨어져 앉는다."""
    import math

    import pymupdf
    from exam_kit.render import render

    src, _, _ = 조판
    page = pymupdf.open(str(render(src, tmp_path / "r", oracle=오라클).pdf))[0]
    pt = 72 / 2.54
    want = (4.6 - 2.5, 2.4 - 0.35)  # A → D
    segs = [(it[1], it[2]) for d in page.get_drawings() for it in d["items"] if it[0] == "l"]
    ad = [s for s in segs if abs(math.dist(s[0], s[1]) / pt - math.hypot(*want)) < 0.05]
    assert ad, "선분 AD가 없다"
    (x1, y1), (x2, y2) = sorted(ad[0], key=lambda p: p.y)  # 위가 A
    assert abs((x2 - x1) / pt - want[0]) < 0.05 and abs((y2 - y1) / pt - want[1]) < 0.05
    a = [((c["bbox"][0] + c["bbox"][2]) / 2, (c["bbox"][1] + c["bbox"][3]) / 2) for b in page.get_text("rawdict")["blocks"]
         for ln in b.get("lines", []) for sp in ln["spans"] if "EQ" in sp["font"] for c in sp["chars"] if c["c"] == "A"]
    assert any(abs(cx - x1) < 0.1 * pt and 0.1 * pt < y1 - cy < 0.6 * pt for cx, cy in a), (a, (x1, y1))
