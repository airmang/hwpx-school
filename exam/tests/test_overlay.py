"""그림 위 얹기(글자·점) — 원고 문법·검사·조판·역변환·왕복·렌더. 합성 킷·합성 그림만(학교 킷 없이 돈다).

10-26 수학 교사 답: 그림에서 글자를 지우고, 문제와 같은 글꼴·크기의 한/글 수식(점 이름·길이)과 점(●)을 그림 위에
따로 얹는다. 원고는 `:::그림` 펜스 안 그림 줄 아래 `$…$ {x=…cm y=…cm}`·`● {x=…cm y=…cm}`(그림 왼쪽 위에서 잰 중심)."""

from pathlib import Path

import lxml.etree as ET
import pytest
from exam_kit import HP, q
from exam_kit.compose import CM, 점_지름
from exam_kit.kit import load_kit
from exam_kit.lint import lint
from exam_kit.reverse import (
    Geometry,
    _attach,
    _Fig,
    _fig_box,
    _float_item,
    floats_in,
    para_geometry,
    para_tops,
    paragraph_text,
    picture_place,
)
from exam_kit.roundtrip import rebuild, roundtrip
from exam_kit.scan import Overlay, figure_parts, overlay_line, scan_markdown

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
# 그림.png 600×360 → 폭 6cm면 높이 3.6cm. A는 그림 위끝보다 0.2cm 위(꼭짓점 이름이 그림 밖으로 나가는 흔한 경우)
얹기 = ["$\\mathrm{A}$ {x=0cm y=-0.2cm}", "$\\mathrm{B}$ {x=6cm y=3.6cm}", "$5$ {x=3cm y=1.8cm}", "● {x=1.5cm y=1cm}"]


def _md(lines=얹기, *, extra: str = "", pic: str = "![](그림.png){width=6cm}") -> str:
    body = "\n".join(lines)
    return 머리 + f"""
## 1. [5.0점]
그림과 같은 사각형에서 선분의 길이는?

:::그림
{pic}
{body}
:::
{extra}
① $1$
② $2$
*③ $3$
④ $4$
⑤ $5$
"""


def _codes(md: str) -> list[str]:
    return [v.code for v in lint(md)]


# --- 원고 문법·검사 -------------------------------------------------------------


def test_원고_문법():
    s = scan_markdown(_md())
    assert s.errors == ()
    [b] = s.questions[0].blocks
    pics, overlays, bad = figure_parts(b)
    assert (pics, bad) == (["![](그림.png){width=6cm}"], [])
    assert overlays == [Overlay("글자", "\\mathrm{A}", 0.0, -0.2), Overlay("글자", "\\mathrm{B}", 6.0, 3.6),
                        Overlay("글자", "5", 3.0, 1.8), Overlay("점", None, 1.5, 1.0)]
    assert overlay_line(Overlay("글자", "\\mathrm{A}", 1.3, -0.09)) == "$\\mathrm{A}$ {x=1.3cm y=-0.09cm}"
    assert overlay_line(Overlay("점", None, -0.001, 2.0)) == "● {x=0cm y=2cm}"
    assert not {"E025", "E027"} & set(_codes(_md()))


@pytest.mark.parametrize("lines, pic, extra", [
    (얹기 + ["A {x=1cm y=1cm}"], None, ""),                            # 수식 아닌 글자
    (얹기 + ["![](그림.png){width=6cm}"], None, ""),                   # 그림 줄 둘
    (얹기, None, "● {x=1cm y=1cm}\n"),                                 # 펜스 밖 얹기 줄(발문 이음 줄이 되어 버린다)
    (["$a$와 $b$ {x=1cm y=1cm}"], None, ""),                           # 수식 둘
])
def test_E027(lines, pic, extra):
    md = _md(lines, extra=extra, **({"pic": pic} if pic else {}))
    assert "E027" in _codes(md)


def test_E027_자료_박스_안():
    md = 머리 + """
## 1. [5.0점]
다음 자료를 보고 답한 것은?

:::자료
![](그림.png){width=6cm}
$\\mathrm{A}$ {x=0cm y=0cm}
:::

① $1$
② $2$
*③ $3$
④ $4$
⑤ $5$
"""
    assert "E027" in _codes(md)


def test_E025_얹는_글자의_수식():
    assert "E025" in _codes(_md(["$\\frac{1$ {x=1cm y=1cm}"]))


# --- 조판 ----------------------------------------------------------------------


@pytest.fixture
def 조판(tmp_path):
    kit = load_kit(킷)
    src = rebuild(_md(), kit, 서식, 픽스처, tmp_path / "원안지.hwpx")
    from hwpx.document import HwpxDocument

    doc = HwpxDocument.open(str(src))
    host = next(p.element for p in doc.sections[0].paragraphs if p.element.find(f".//{q('hp', 'pic')}") is not None)
    return kit, src, doc, host


def test_조판_얹기는_그림_문단의_떠_있는_개체(조판):
    kit, _, doc, host = 조판
    floats = floats_in(host)
    assert [f.tag.split("}")[1] for f in floats] == ["equation"] * 3 + ["ellipse"]
    for f in floats:
        pos = f.find(q("hp", "pos"))
        assert (f.get("textWrap"), pos.get("treatAsChar"), pos.get("vertRelTo"), pos.get("horzRelTo")) == \
            ("IN_FRONT_OF_TEXT", "0", "PARA", "COLUMN")
    pic = host.find(f".//{q('hp', 'pic')}")
    assert all(int(f.get("zOrder")) > int(pic.get("zOrder")) for f in floats)  # 그림 위에
    # 글자 크기 = 발문 수식 크기(문항 번호 스타일 글자 크기)
    from exam_kit.kit import style_ids

    cp = style_ids(doc)[kit.styles["number"]][2]
    size = next(c for c in doc.oxml.headers[0].element.iter(q("hh", "charPr")) if c.get("id") == cp).get("height")
    assert {f.get("baseUnit") for f in floats[:3]} == {size}
    # 점: 지름 점_지름, 중심이 그림 왼쪽 위 + (1.5cm, 1cm)
    geo = para_geometry(doc)[host.get("paraPrIDRef")]
    w = int(pic.find(q("hp", "sz")).get("width"))
    x0 = geo["left"] + geo["intent"] + (kit.columns["width"] - geo["left"] - geo["right"] - geo["intent"] - w) // 2
    dot = floats[3].find(q("hp", "pos"))
    assert int(dot.get("horzOffset")) + 점_지름 // 2 == x0 + round(1.5 * CM)
    assert int(dot.get("vertOffset")) + 점_지름 // 2 == geo["prev"] + round(1.0 * CM)


def test_조판_그림_밖으로_나간_글자만큼_문단_간격(조판):
    """한/글은 문단 기준 음수 세로 오프셋을 0으로 자른다 — 그림 위로 나간 A만큼 문단 앞 간격을 둔다(아래로 나간 B는 뒤 간격)."""
    _, _, doc, host = 조판
    geo = para_geometry(doc)[host.get("paraPrIDRef")]
    a = floats_in(host)[0]
    assert int(a.find(q("hp", "pos")).get("vertOffset")) == 0  # 맨 위 글자가 문단 원점에 닿는다
    assert geo["prev"] == int(a.find(q("hp", "sz")).get("height")) // 2 + round(0.2 * CM)


def test_조판_단_밖으로_나가면_멈춘다(tmp_path):
    with pytest.raises(ValueError, match="단 밖"):
        rebuild(_md(["$\\mathrm{A}$ {x=-4cm y=0cm}"]), load_kit(킷), 서식, 픽스처, tmp_path / "x.hwpx")


# --- 역변환·왕복 ----------------------------------------------------------------


def test_왕복_불변(조판, tmp_path):
    kit, src, _, _ = 조판
    r = roundtrip(src, kit, 서식, tmp_path / "rt")
    assert r.same, r.diffs
    back = (tmp_path / "rt" / "원고" / "원고.md").read_text(encoding="utf-8")
    fence = back.split(":::그림\n", 1)[1].split("\n:::", 1)[0].splitlines()
    assert fence[0] == "![](그림_01_1.png){width=6cm}"
    # 좌표·차례는 그대로다. 수식 글은 상류 되돌림 표기가 다를 수 있다(`\\mathrm{B}` → `\\text{B}`) — 왕복 불변(r.same)이 조판 결과로 본다
    assert [ln.split(" {", 1)[1] for ln in fence[1:]] == [ln.split(" {", 1)[1] for ln in 얹기]


def _xml(inner: str):
    return ET.fromstring(f'<hp:p xmlns:hp="{HP}" paraPrIDRef="0">{inner}</hp:p>')


def _seg(vertpos: int) -> str:
    return f'<hp:linesegarray><hp:lineseg vertpos="{vertpos}"/></hp:linesegarray>'


def _pos(v: int, h: int, rel: str = "PARA") -> str:
    return (f'<hp:pos treatAsChar="0" vertRelTo="PARA" horzRelTo="{rel}" vertAlign="TOP" horzAlign="LEFT" '
            f'vertOffset="{v}" horzOffset="{h}"/>')


def _eq(script: str, v: int, h: int, w: int = 800, hh: int = 1100) -> str:
    return (f'<hp:equation><hp:sz width="{w}" height="{hh}"/>{_pos(v, h)}<hp:outMargin left="56" top="0"/>'
            f'<hp:script>{script}</hp:script></hp:equation>')


def test_교사식_배치_그림과_다른_문단의_글자():
    """교사 한/글 원안지: 그림은 떠 있는 개체(단 기준), 글자는 그 아래 빈 문단들에 문단 기준으로 앵커돼 있다 — 두 문단의
    세로 거리는 한/글이 저장한 줄 배치(vertpos − prev)로 잰다."""
    pic = (f'<hp:pic><hp:sz width="12000" height="10000"/>{_pos(1500, 10000, "COLUMN")}'
           f'<hp:img binaryItemIDRef="i1"/></hp:pic>')
    p0 = _xml(f'<hp:run>{pic}{_eq("rm P", 700, 13000)}</hp:run>{_seg(40000)}')
    p1 = _xml(f'<hp:run>{_eq("rm Q", 1500, 16000)}<hp:ellipse><hp:sz width="300" height="300"/>{_pos(200, 12000)}'
              f'</hp:ellipse></hp:run>{_seg(41800)}')
    paras = [p0, p1]
    gp = {"0": {"align": "JUSTIFY", "left": 0, "right": 0, "intent": 0, "prev": 0}}
    geo = Geometry(30000, gp, para_tops(paras, gp))
    box, mixed = _fig_box(p0.find(f".//{q('hp', 'pic')}"), p0, geo)
    assert (box, mixed) == ((10000, 1500, 12000, 10000), False)
    fig = _Fig("![](a.png){width=4.23cm}", 0, box, mixed)
    floats = [_float_item(x, i, p, geo) for i, p in enumerate(paras) for x in floats_in(p)]
    _attach([fig], floats, geo)
    cm = lambda v: round(v / CM, 2)  # noqa: E731
    assert fig.overlays == [
        Overlay("글자", "rmP", cm(13000 + 56 + 400 - 10000), cm(700 + 550 - 1500)),
        Overlay("글자", "rmQ", cm(16000 + 56 + 400 - 10000), cm(1800 + 1500 + 550 - 1500)),
        Overlay("점", None, cm(12000 + 150 - 10000), cm(1800 + 200 + 150 - 1500)),
    ]
    assert fig.md()[0] == ":::그림" and fig.md()[-1] == ":::"
    assert paragraph_text(p0, set(), floating_ok=True) == ""  # 얹은 글자는 발문 글이 아니다


def test_교사식_배치_줄_배치가_없으면_멈춘다():
    pic = f'<hp:pic><hp:sz width="12000" height="10000"/>{_pos(0, 0, "COLUMN")}</hp:pic>'
    p0, p1 = _xml(f"<hp:run>{pic}</hp:run>"), _xml(f'<hp:run>{_eq("rm P", 0, 100)}</hp:run>')
    gp = {"0": {"align": "JUSTIFY", "left": 0, "right": 0, "intent": 0, "prev": 0}}
    geo = Geometry(30000, gp, para_tops([p0, p1], gp))
    fig = _Fig("x", 0, *_fig_box(p0.find(f".//{q('hp', 'pic')}"), p0, geo))
    with pytest.raises(ValueError, match="줄 배치"):
        _attach([fig], [_float_item(x, 1, p1, geo) for x in floats_in(p1)], geo)


@pytest.mark.parametrize("inner, match", [
    (f'<hp:ellipse><hp:sz width="3000" height="3000"/>{_pos(0, 0)}</hp:ellipse>', "큰 원"),
    (_eq("rm P", 0, 28000), "붙일 그림이 0개"),  # 그림에서 1cm 넘게 떨어진 글자
])
def test_역변환_얹기_오류(inner, match):
    pic = f'<hp:pic><hp:sz width="5000" height="5000"/>{_pos(0, 0, "COLUMN")}</hp:pic>'
    p = _xml(f"<hp:run>{pic}{inner}</hp:run>")
    gp = {"0": {"align": "JUSTIFY", "left": 0, "right": 0, "intent": 0, "prev": 0}}
    geo = Geometry(30000, gp, [None])
    fig = _Fig("x", 0, *_fig_box(p.find(f".//{q('hp', 'pic')}"), p, geo))
    with pytest.raises(ValueError, match=match):
        _attach([fig], [_float_item(x, 0, p, geo) for x in floats_in(p)], geo)


def test_역변환_박스_안의_얹기는_멈춘다():
    with pytest.raises(ValueError, match="박스·표 안"):
        paragraph_text(_xml(f'<hp:run>{_eq("rm P", 0, 0)}</hp:run>'), set())


def test_역변환_글자처럼_취급한_원은_멈춘다():
    el = _xml('<hp:run><hp:ellipse><hp:sz width="300" height="300"/><hp:pos treatAsChar="1"/></hp:ellipse></hp:run>')
    with pytest.raises(ValueError, match="글자처럼 취급한 원"):
        floats_in(el)


def test_떠_있는_그림이_단_가운데_근처면_가운데():
    """기하 원안지: 손으로 끌어 놓은 떠 있는 그림(왼쪽 + 띄움)의 중심이 단 가운데 ±1cm 안이면 가운데(10-26 교사 답)."""
    def pic(off: int, w: int = 11000):
        return ET.fromstring(f'<hp:pic xmlns:hp="{HP}"><hp:pos treatAsChar="0" horzRelTo="COLUMN" horzAlign="LEFT" '
                             f'horzOffset="{off}"/><hp:sz width="{w}"/></hp:pic>')

    para = ET.fromstring(f'<hp:p xmlns:hp="{HP}" paraPrIDRef="7"/>')
    col = 30900
    assert picture_place(pic(9950), para, {}, col) == ("center", 0)       # 중심 = 단 가운데
    assert picture_place(pic(9950 + 2700), para, {}, col) == ("center", 0)  # 0.95cm 오른쪽
    assert picture_place(pic(2000), para, {}, col) == ("left", 2000)      # 2.7cm 왼쪽 — 왼쪽 + 띄움
    assert picture_place(pic(9950), para, {}) == ("left", 9950)           # 단 폭을 모르면 지금까지처럼


# --- 렌더 ----------------------------------------------------------------------


def test_렌더_얹은_자리(조판, 오라클, tmp_path):
    """실한컴: 얹은 글자·점의 중심이 원고 좌표(그림 왼쪽 위 기준)에서 0.05cm 안 — 그림 위로 나간 A 포함."""
    import pymupdf
    from exam_kit.render import render

    _, src, _, _ = 조판
    r = render(src, tmp_path / "r", oracle=오라클)
    page = pymupdf.open(str(r.pdf))[0]
    x0, y0, x1, y1 = max((i["bbox"] for i in page.get_image_info()), key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    pt = 72 / 2.54
    # 수식 글자(텍스트 층 HyhwpEQ — 숫자는 사용자 영역 글자로 찍힌다) 중심, 그림 왼쪽 위 기준 cm
    glyphs = [(((c["bbox"][0] + c["bbox"][2]) / 2 - x0) / pt, ((c["bbox"][1] + c["bbox"][3]) / 2 - y0) / pt)
              for bl in page.get_text("rawdict")["blocks"] for ln in bl.get("lines", []) for sp in ln["spans"]
              if "EQ" in sp["font"] for c in sp["chars"] if c["c"].strip()]
    dots = [(((d["rect"].x0 + d["rect"].x1) / 2 - x0) / pt, ((d["rect"].y0 + d["rect"].y1) / 2 - y0) / pt)
            for d in page.get_drawings() if d.get("fill") is not None and 2 < d["rect"].width < 5]
    for (wx, wy), found in [((0, -0.2), glyphs), ((6, 3.6), glyphs), ((3, 1.8), glyphs), ((1.5, 1.0), dots)]:
        assert any(abs(gx - wx) < 0.05 and abs(gy - wy) < 0.05 for gx, gy in found), ((wx, wy), found)


# --- 붙은 글꼴 명령(rmA)·겹침 --------------------------------------------------------


def test_붙은_rm은_문서에_띄워_쓰고_원고에_붙여_쓴다():
    """교사 원안지의 점 이름 `rmA`: python-hwpx 폭 어림은 r·m·A 세 글자로 읽어 세 배 넓게 잡는다 — 그 상자 가운데에 놓은 글자가
    0.30cm 밀렸다(10-26 렌더). 문서에는 `rm A`(폭이 맞는다), 원고 LaTeX에는 `rmA`(띄운 `rm A`는 되돌리면 글자 rm이 찍힌다)."""
    from exam_kit import equation
    from hwpx.equation import eqedit_to_latex

    assert equation.to_script("rmA") == "rm A"
    assert equation.box("rm A", 1100)[0] < equation.box("rmA", 1100)[0] / 2
    for doc in ("rm A", "rmA", "rm PQR", "rm K ( 7 , - 2 )"):
        latex = eqedit_to_latex(equation.glued(doc))
        assert equation.to_script(latex) == equation.spaced(doc)  # 고정점
    assert equation.spaced("5 rm cm") == "5 rm cm"  # 소문자 단위는 그대로


def test_역변환_얹은_rmA는_원고에_붙은_꼴로():
    p = _xml(f'<hp:run>{_eq("rm C", 0, 100)}</hp:run>')
    gp = {"0": {"align": "JUSTIFY", "left": 0, "right": 0, "intent": 0, "prev": 0}}
    ov = _float_item(floats_in(p)[0], 0, p, Geometry(30000, gp, [None]))[0]
    assert ov.latex == "rmC"


@pytest.mark.parametrize("x, clash", [(3.0, True), (1.0, False)])
def test_얹은_글자가_그림_선과_겹치면_알린다(tmp_path, x, clash):
    from PIL import Image, ImageDraw

    im = Image.new("L", (600, 360), 255)
    ImageDraw.Draw(im).line([(300, 0), (300, 359)], fill=0, width=4)  # 가운데(3cm) 세로선
    im.save(tmp_path / "그림.png")
    kit = load_kit(킷)
    s = scan_markdown(_md([f"$\\mathrm{{E}}$ {{x={x}cm y=1.8cm}}"]), kit.front_matter)
    from exam_kit.compose import compose
    from exam_kit.prepare import prepare_document
    from exam_kit.slots import fill_slots

    doc, _ = prepare_document(서식, kit)
    fill_slots(doc, kit, s.front, question_count=1, total_points=5.0)
    notes = compose(doc, s, kit, answer_key=False, image_root=tmp_path).notes
    assert any("[글자·선 겹침]" in n for n in notes) == clash


def test_수식_글꼴은_킷_값_없으면_HancomEQN(조판, tmp_path):
    """교사 원안지 수식은 HancomEQN(실측 250개) — python-hwpx 기본 HYhwpEQ는 더 가늘어 달라 보였다(10-26 owner)."""
    import dataclasses

    _, _, doc, _ = 조판
    fonts = {e.get("font") for e in doc.sections[0].element.iter(q("hp", "equation"))}
    assert fonts == {"HancomEQN"}
    kit = load_kit(킷)
    kit = dataclasses.replace(kit, typeset={**kit.typeset, "equation_font": "HYhwpEQ"})
    src = rebuild(_md(), kit, 서식, 픽스처, tmp_path / "y.hwpx")
    from hwpx.document import HwpxDocument

    assert {e.get("font") for e in HwpxDocument.open(str(src)).sections[0].element.iter(q("hp", "equation"))} == {"HYhwpEQ"}
