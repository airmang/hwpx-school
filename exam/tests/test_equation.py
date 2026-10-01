"""인라인 수식 `$…$`(LaTeX → 한/글 수식) — 원고 표기·원고 규칙 E025·조판·줄 캐시 글·역변환. 합성 킷만 쓴다(학교 킷 없이 돈다)."""

import re
from pathlib import Path

import pytest
from hwpx.document import HwpxDocument

from exam_kit import equation as eq
from exam_kit import q
from exam_kit.compose import (
    _Composer,
    _글폭,
    choice_paragraphs,
    compose,
    estimate_extra,
    estimate_lines,
    relayout_choices,
    wrap_words,
    물결,
)
from exam_kit.fit import Lines, _폭, para_text, tail_ratio
from exam_kit.kit import load_kit
from exam_kit.lint import errors, lint
from exam_kit.prepare import finalize_form, prepare_document
from exam_kit.reverse import paragraph_text
from exam_kit.scan import scan_markdown
from exam_kit.slots import fill_slots
from exam_kit.verify import extract_answers, question_heads, verify_document

킷 = Path(__file__).resolve().parents[1] / "kits" / "synthetic"
서식 = 킷 / "synthetic_form.hwpx"
원고 = Path(__file__).parent / "fixtures" / "수식_합성.md"
정답 = {"1": "⑤", "2": "③", "3": "②", "4": "②", "5": "④", "6": "①", "7": "②", "8": "③", "9": "④"}


# ---- 원고 표기 -----------------------------------------------------------------

def test_수식_조각과_가린_글():
    masked, maths = eq.mask(r"함수 $f(x)=x^2$의 값과 $ \frac{1}{2} $")
    assert [m.latex for m in maths] == ["f(x)=x^2", r"\frac{1}{2}"]
    assert maths[1].script == "{1} over {2}" and maths[1].source == r"$\frac{1}{2}$"
    assert masked == "함수 " + eq.자리(0) + "의 값과 " + eq.자리(1)
    assert eq.unmask(masked, maths) == r"함수 $f(x)=x^2$의 값과 $\frac{1}{2}$"
    assert eq.pieces(masked, maths) == ["함수 ", maths[0], "의 값과 ", maths[1]]
    assert eq.mask("수식 없는 글") == ("수식 없는 글", ())


def test_달러_글자는_역슬래시로_쓴다():
    masked, maths = eq.mask(r"값이 \$5인 것과 $x$개")
    assert masked == "값이 $5인 것과 " + eq.자리(0) + "개" and maths[0].latex == "x"
    assert eq.unmask(masked, maths) == r"값이 \$5인 것과 $x$개"


@pytest.mark.parametrize("text, why", [
    ("값은 $x 이다", "닫히지 않은"),
    ("$$x$$", "블록 수식"),
    ("빈 $ $ 수식", "빈 수식"),
    (r"$\notacommand{x}$", "바꿀 수 없다"),
    ("$a~b$", "바꿀 수 없다"),  # LaTeX `~`(띄움)은 변환표에 없다 — 물결(∼)로 바꾸지 않고 오류로 알린다
])
def test_수식_표기_오류(text, why):
    with pytest.raises(eq.MathError, match=why):
        eq.mask(text)


def test_물결은_수식_밖에만():
    pairs = [("~", "∼")]
    assert 물결("$-1$~$3$ 범위, $a~b$", pairs) == "$-1$∼$3$ 범위, $a~b$"
    assert 물결("닫히지 않은 $a~b", pairs) == "닫히지 않은 $a∼b"  # 표기 오류는 조판·검사(E025)가 알린다


def test_표_칸은_수식_안의_세로선으로_나누지_않는다():
    assert eq.split_cells("| $|x|$ | 2 |") == ["$|x|$", "2"]
    assert eq.split_pipes("가|$|x-1|$|나") == ["가", "$|x-1|$", "나"]
    assert eq.split_pipes("ㄱ | ㄴ") == ["ㄱ ", " ㄴ"]  # 수식이 없으면 str.split("|")과 같다


def test_수식_폭은_상자_폭과_바깥_여백():
    (m,) = eq.mask("$x^2$")[1]
    w, h = eq.box(m.script, 1100)
    assert eq.width(m, 1100) == w + 2 * eq.바깥_여백 and eq.height(m, 1100) == h > 1100


def test_줄_캐시_글은_수식_하나에_8자리():
    s = eq.line_chars(2345)
    assert len(s) == eq.TEXTPOS == 8
    assert eq.line_char_width(s[0]) == 2345 and all(eq.line_char_width(c) == 0 for c in s[1:])
    assert eq.line_char_width("가") is None
    assert eq.line_key("가" + eq.line_chars(10) + "나") == eq.line_key("가" + eq.line_chars(99) + "나")
    assert eq.readable("가" + eq.line_chars(10) + "나") == "가[수식]나"  # 보고서 알림에 찍는 글


# ---- 원고 규칙 E025 ------------------------------------------------------------

def _md(body: str) -> str:
    머리 = 원고.read_text(encoding="utf-8").split("\n## 1.")[0].replace("만점: 45", "만점: 5")
    return 머리 + "\n" + body


def test_합성_수학_원고는_오류_0():
    vs = lint(원고.read_text(encoding="utf-8"))
    assert errors(vs) == [], [f"{v.code} L{v.line_no} {v.msg}" for v in errors(vs)]


@pytest.mark.parametrize("where, body", [
    ("발문", "## 1. [5.0점]\n$x 의 값은?\n\n*① 1\n② 2\n③ 3\n④ 4\n⑤ 5\n"),
    ("답지", "## 1. [5.0점]\n값은?\n\n*① $\\notacommand$\n② 2\n③ 3\n④ 4\n⑤ 5\n"),
    ("보기", "## 1. [5.0점]\n옳은 것은?\n\n:::보기\nㄱ. $$x$$이다.\n:::\n\n*① ㄱ\n② ㄴ\n③ ㄷ\n④ ㄱ, ㄴ\n⑤ ㄴ, ㄷ\n"),
    ("자료 표", "## 1. [5.0점]\n값은?\n\n:::자료\n| $x | 1 |\n|---|---|\n| 2 | 3 |\n:::\n\n*① 1\n② 2\n③ 3\n④ 4\n⑤ 5\n"),
    ("답항표 머리", "## 1. [5.0점]\n값은?\n\n:::답항표 머리=\"$a|(나)\"\n*① 1 | 2\n② 1 | 3\n③ 2 | 3\n④ 2 | 4\n⑤ 3 | 4\n:::\n"),
])
def test_E025_수식_표기(where, body):
    vs = lint(_md(body))
    assert any(v.code == "E025" for v in vs), (where, [f"{v.code} {v.msg}" for v in vs])


def test_E025_코드_블록의_달러는_보지_않는다():
    body = "## 1. [5.0점]\n출력은?\n\n```\necho $HOME\n```\n\n*① 1\n② 2\n③ 3\n④ 4\n⑤ 5\n"
    assert not [v for v in lint(_md(body)) if v.code == "E025"]


# ---- 폭·줄 추정 -----------------------------------------------------------------

def test_폭과_줄_추정은_수식을_한_덩어리로():
    m = load_kit(킷).metrics
    (frac,) = eq.mask(r"$\frac{1}{2}$")[1]
    assert _글폭(r"① $\frac{1}{2}$", m) == m.text("① ") + eq.width(frac, m.char_height)
    long = "가" * 20 + r" $\frac{x^2-4}{x-2}$"
    w = _글폭("가" * 20 + " ", m)
    assert estimate_lines(long, w + 100, 30000, m) == 2  # 수식은 다음 줄로 통째로 넘어간다
    assert estimate_extra(long, w + 100, 30000, m) > 0  # 분수가 든 줄은 높아진다
    assert estimate_extra("가나다", 30000, 30000, m) == 0
    assert wrap_words(r"가나 $a + b$ 다라", m.text("가나 ") + 200, m) == "가나\n$a + b$\n다라"  # 수식 안 공백은 접지 않는다


# ---- 조판 ----------------------------------------------------------------------

def _조판(answer_key: bool, tmp_path: Path, md: str | None = None) -> tuple[HwpxDocument, Path]:
    kit = load_kit(킷)
    s = scan_markdown(md or 원고.read_text(encoding="utf-8"), kit.front_matter)
    doc, prep = prepare_document(서식, kit)
    fill_slots(doc, kit, s.front, question_count=len(s.questions), total_points=45.0)
    prep = prep.refresh(doc)
    compose(doc, s, kit, answer_key=answer_key, image_root=원고.parent)
    finalize_form(doc, kit, prep)
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = tmp_path / f"수식_{answer_key}.hwpx"
    doc.save_to_path(str(out))
    return HwpxDocument.open(str(out)), out


def _원고_수식() -> list[eq.Math]:
    """원고의 수식 차례(문서 차례와 같다 — 발문·박스·답지, 세트 지문은 첫 문항 앞)."""
    text = 원고.read_text(encoding="utf-8").split("---\n", 2)[2]
    return [x for ln in text.splitlines() for x in eq.mask(ln)[1]]


@pytest.mark.parametrize("answer_key", [False, True])
def test_합성_수학_두_판_조판(answer_key, tmp_path):
    kit = load_kit(킷)
    doc, _ = _조판(answer_key, tmp_path)
    assert len(question_heads(doc)) == 9
    assert extract_answers(doc) == (정답 if answer_key else {})
    assert verify_document(doc, kit, expect_answers=정답 if answer_key else None, answer_key=answer_key, draft=False) == []
    sec = doc.sections[0].element
    eqs = list(sec.iter(q("hp", "equation")))
    assert [e.find(q("hp", "script")).text for e in eqs] == [m.script for m in _원고_수식()]
    hdr = doc.headers[0].element
    for e in eqs:
        run = e.getparent()
        cp = hdr.find(f".//{q('hh', 'charPr')}[@id='{run.get('charPrIDRef')}']")
        assert e.get("baseUnit") == cp.get("height")  # 수식 기준 크기 = 그 자리 글자 크기
        assert e.find(q("hp", "pos")).get("treatAsChar") == "1"
        assert run.find(q("hp", "t")) is None  # 수식 run에는 글이 없다
    ids = [e.get("id") for e in sec.iter(*(q("hp", t) for t in ("tbl", "pic", "equation")))]
    assert len(ids) == len(set(ids))  # 개체 id가 겹치지 않는다(_renumber)
    # 표 칸(자료 표·답항표) 안에도 수식이 있다 — 절댓값 `|x-1|`은 칸을 나누지 않았다
    in_cells = [e for e in eqs if any(a.tag == q("hp", "tc") for a in e.iterancestors())]
    assert {e.find(q("hp", "script")).text for e in in_cells} >= {"| x - 1 |", "sqrt {3}", "1", "9"}


def test_두_판은_형광펜_말고_같다(tmp_path):
    a, _ = _조판(False, tmp_path / "a")
    b, _ = _조판(True, tmp_path / "b")

    def 글(doc) -> str:
        from lxml import etree as ET

        s = ET.tostring(doc.sections[0].element, encoding="unicode")
        s = re.sub(r"<hp:markpen(Begin|End)[^>]*/>", "", s)
        return re.sub(r'(<hp:p [^>]*?)id="\d+"', r"\1", s)

    assert 글(a) == 글(b)


def test_수식_문단의_줄_캐시_글은_수식마다_8자리(tmp_path):
    doc, _ = _조판(False, tmp_path)
    ps = list(doc.sections[0].paragraphs)
    head = ps[question_heads(doc)[0]].element
    text = para_text(head)
    widths = [eq.line_char_width(ch) for ch in text if eq.line_char_width(ch)]
    assert len(widths) == 4 and len(text) == len(re.sub(r"[\U00100000-\U0010FFFD​]", "", text)) + 4 * 8
    # 끝줄 추정 폭은 수식 폭을 쓴다
    ln = Lines(2, text[-12:], 30000, text, (0, len(text) - 12))
    assert tail_ratio(ln, load_kit(킷).metrics) == pytest.approx(_폭(text[-12:].strip(), load_kit(킷).metrics) / 30000)


def test_수식_답지를_다른_배치형으로_다시_쓴다(tmp_path):
    kit = load_kit(킷)
    doc, _ = _조판(True, tmp_path)
    s = scan_markdown(원고.read_text(encoding="utf-8"), kit.front_matter)
    qn = s.questions[0]
    before = [m.script for m in _원고_수식()][4:9]  # 1번 답지의 수식 다섯(발문 수식 넷 다음)
    relayout_choices(doc, kit, qn, "5행", answer_key=True)
    ps = list(doc.sections[0].paragraphs)
    rows = choice_paragraphs(doc, kit, 1)
    assert len(rows) == 5
    got = [e.find(q("hp", "script")).text for i in rows for e in ps[i].element.iter(q("hp", "equation"))]
    assert got == before and extract_answers(doc)["1"] == "⑤"


def test_수식_조각과_밑줄(tmp_path):
    kit = load_kit(킷)
    doc, _ = prepare_document(서식, kit)
    from exam_kit.compose import harvest_samples

    c = _Composer(doc, kit, harvest_samples(doc, kit), answer_key=False)
    segs = c._segs(r"$f(x)=0$을 만족시키는 __양수 $x$__의 값은?", "number")
    assert [type(t).__name__ if isinstance(t, eq.Math) else t for t, _ in segs] == \
        ["Math", "을 만족시키는 ", "양수 ", "Math", "의 값은?"]
    ul = c.underline(c.style["number"][2])
    assert [cp for _, cp in segs] == [None, None, ul, ul, None]


def test_수식_글자는_가까운_글_줄에_붙는다():
    """분수·극한의 위아래 글자는 y0로 묶으면 따로 줄이 된다 — 가운데가 가까운 글 줄(그 세로 범위)에 붙인다."""
    import pymupdf

    from exam_kit.geometry import LINE_PT, _수식_붙이기, _y_묶음

    R = pymupdf.Rect
    글 = _y_묶음([(R(10, 100, 18, 109), ""), (R(20, 100, 28, 109), ""), (R(10, 130, 18, 139), "")])
    assert len(글) == 2
    위 = R(40, 91, 46, 97)    # 극한 위 글자 — 줄 윗끝보다 6pt 위(가운데 거리 6pt)
    아래 = R(40, 110, 46, 116)  # 분모 — 줄 아랫끝 바로 아래
    따로 = R(40, 160, 60, 168)  # 수식만 있는 줄(긴 수식이 줄을 따로 차지)
    줄 = _수식_붙이기(글, [위, 아래, 따로])
    assert [len(g) for g in 줄] == [4, 1, 1]
    assert 줄[0][-2][0] == 위 and 줄[0][-1][0] == 아래 and 줄[2] == [(따로, "")]
    assert 6.0 < LINE_PT * 0.45  # 위 글자 거리 6pt는 붙임 한도 안


def test_역변환은_수식을_LaTeX로_되돌린다(tmp_path):
    doc, _ = _조판(False, tmp_path)
    ps = list(doc.sections[0].paragraphs)
    heads = question_heads(doc)
    stem = paragraph_text(ps[heads[0]].element, set())
    assert stem.startswith("1.") and "이차방정식 $x^{2} - 5 x + 6 = 0$의 두 근을 $\\alpha$, $\\beta$라 할 때" in stem
    for m in eq.mask(stem)[1]:  # 되돌린 원고는 다시 같은 한/글 수식이 된다
        assert m.script in {x.script for x in _원고_수식()}


def test_합성_수학_원고_전체_조판_실렌더(오라클, tmp_path):
    """실한컴 렌더로 끝까지(렌더 루프·자간·두 판 대조) — 수식 글자(텍스트 층 HyhwpEQ)가 든 쪽에서도 기계 잔존 0."""
    from exam_kit.build import build

    r = build(원고, 킷, tmp_path / "out", form_path=서식)
    assert not r.blocked
    assert r.findings and all(fs == [] for fs in r.findings.values()), r.findings  # 두 판 기계 잔존 0
