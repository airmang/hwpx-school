import dataclasses
import re
import zipfile

import pytest

from _helpers import _png
from worksheet.backends.docx import DocxWriter, 원문자
from worksheet.blocks import plan_node
from worksheet.furniture import plan_band, plan_heading, plan_keyword_page
from worksheet.kit import load_kit
from worksheet.md import parse_sheet
from worksheet.kit_style import resolve_kit

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_블록들 = """---
kit: 시험킷
title: t
---

> 발문이다.

■ 정의 줄

![](본문.png){width=5cm}

:::라벨설명 labelWidth=3cm
[1] 라벨
: ![](칸.png)
:::

:::비교표 cols="가|나" rows="하나|둘"
값|![](칸.png){width=15cm}
:::

:::답칸 label="답" lines=2
:::

:::강조박스 title="규칙"
한 줄
두 줄
:::

:::나란히 cols="예제 1|예제 2"
![](칸.png)|![](칸.png)
:::
"""


@pytest.fixture
def 블록_docx(킷_루트, tmp_path):
    (tmp_path / "본문.png").write_bytes(_png(400, 200))
    (tmp_path / "칸.png").write_bytes(_png(300, 120))
    kit = load_kit(킷_루트)
    w = DocxWriter(kit, resolve_kit(kit))
    for node in parse_sheet(_블록들).nodes:
        w.draw(plan_node(kit, node, base_dir=tmp_path))
    out = tmp_path / "블록.docx"
    w.save(out)
    return out, kit


def _본문(path):
    import xml.etree.ElementTree as ET
    return ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))


def test_모든_run_의_한글_글꼴이_킷의_docx_글꼴이다(블록_docx):
    out, kit = 블록_docx
    for r in _본문(out).iter(f"{W}r"):
        fonts = r.find(f"{W}rPr/{W}rFonts")
        assert fonts is not None and fonts.get(f"{W}eastAsia") == kit.docx_font


def test_표가_연달아_붙지_않는다(블록_docx):
    out, _ = 블록_docx
    몸 = _본문(out).find(f"{W}body")
    태그들 = [c.tag for c in 몸]
    assert all(not (a == b == f"{W}tbl") for a, b in zip(태그들, 태그들[1:]))


def test_칸_안_그림은_칸_안쪽보다_넓지_않다(블록_docx):
    out, _ = 블록_docx
    몸 = _본문(out)
    WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
    for tc in 몸.iter(f"{W}tc"):
        폭 = int(tc.find(f"{W}tcPr/{W}tcW").get(f"{W}w"))  # twip
        for ext in tc.iter(f"{WP}extent"):
            # 여유 2 twip: 그림 크기는 hwpx 와 같은 근사 열 폭(본문 폭 ÷ 열 수)으로 계산하고, 균등 분배의
            # 마지막 열은 그보다 몇 HWPUNIT 작을 수 있다(twip 반올림 포함) — 인쇄에 안 보이는 크기다.
            assert int(ext.get("cx")) <= (폭 - (510 * 2) // 5 + 2) * 635


def test_칸_안_그림은_twip_로_반올림한_칸_안쪽을_넘지_않는다(블록_docx):
    """칸 폭은 twip 으로 반올림되고 그림은 HWPUNIT×127 EMU 로 정확하다 — 그림 크기를 온 twip 으로
    내려 잡아야 반올림한 칸 안쪽(칸 폭 − 좌우 여백)을 1 twip 도 넘지 않는다."""
    out, _ = 블록_docx
    WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
    본_수 = 0
    for tc in _본문(out).iter(f"{W}tc"):
        안쪽 = int(tc.find(f"{W}tcPr/{W}tcW").get(f"{W}w")) - 2 * round(510 / 5)
        for ext in tc.iter(f"{WP}extent"):
            cx, cy = int(ext.get("cx")), int(ext.get("cy"))
            assert cx % 635 == 0 and cy % 635 == 0, (cx, cy)
            assert cx <= 안쪽 * 635, (cx / 635, 안쪽)
            본_수 += 1
    assert 본_수 > 0


_TCPR_순서 = ("cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
              "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark")


_TBLPR_순서 = ("tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize",
               "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook")
_변_순서 = ("top", "left", "start", "bottom", "right", "end", "insideH", "insideV", "tl2br", "tr2bl")
_PPR_순서 = ("pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
             "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
             "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
             "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
             "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
             "sectPr", "pPrChange")
_RPR_순서 = ("rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline",
             "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing",
             "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText",
             "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath")


def _순서_지킴(뿌리, 태그: str, 순서: tuple[str, ...]) -> None:
    본 = 0
    for 요소 in 뿌리.iter(f"{W}{태그}"):
        이름들 = [c.tag.split("}")[1] for c in 요소]
        자리 = [순서.index(n) for n in 이름들]  # 순서에 없는 요소도 실패로 잡는다(ValueError)
        assert 자리 == sorted(자리), (태그, 이름들)
        본 += 1
    assert 본 > 0, f"{태그} 가 하나도 없다 — 검사가 공허하다"


@pytest.mark.parametrize("태그, 순서", [
    ("tcPr", _TCPR_순서), ("tblPr", _TBLPR_순서), ("tcBorders", _변_순서), ("tblCellMar", _변_순서),
    ("pPr", _PPR_순서), ("rPr", _RPR_순서),
])
def test_속성_요소가_스키마_순서를_따른다(블록_docx, 태그, 순서):
    """Word 는 순서를 어긴 요소가 있으면 파일을 '복구'하겠다고 묻는다."""
    out, _ = 블록_docx
    _순서_지킴(_본문(out), 태그, 순서)


def test_스타일의_문단_글자_속성도_스키마_순서를_따른다(블록_docx):
    import xml.etree.ElementTree as ET

    out, _ = 블록_docx
    스타일 = ET.fromstring(zipfile.ZipFile(out).read("word/styles.xml"))
    _순서_지킴(스타일, "rPr", _RPR_순서)
    _순서_지킴(스타일, "pPr", _PPR_순서)


def test_인라인_그림은_둘레_여백이_0이다(블록_docx):
    out, _ = 블록_docx
    WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
    그림들 = list(_본문(out).iter(f"{WP}inline"))
    assert 그림들
    for g in 그림들:
        assert all(g.get(k) == "0" for k in ("distT", "distB", "distL", "distR")), g.attrib


def test_호환_모드는_15다(블록_docx):
    import xml.etree.ElementTree as ET

    out, _ = 블록_docx
    설정 = ET.fromstring(zipfile.ZipFile(out).read("word/settings.xml"))
    모드들 = [c.get(f"{W}val") for c in 설정.iter(f"{W}compatSetting") if c.get(f"{W}name") == "compatibilityMode"]
    assert 모드들 == ["15"]


def test_쪽_여백은_머리말_꼬리말_띠를_포함한다(블록_docx):
    """한글의 본문은 위 여백 + 머리말 띠 아래에서 시작한다(띠는 여백에 더해진다). Word 의 pgMar top 은
    용지 끝에서 본문까지라 둘을 더해야 같은 본문 자리가 되고, header 는 머리말 글이 놓일 자리다."""
    out, kit = 블록_docx
    p = resolve_kit(kit).page
    여백 = _본문(out).find(f"{W}body/{W}sectPr/{W}pgMar")
    값 = {k: int(여백.get(f"{W}{k}")) for k in ("top", "bottom", "header", "footer", "left", "right")}
    assert 값 == {
        "top": round((p.top + p.header) / 5), "bottom": round((p.bottom + p.footer) / 5),
        "header": round(p.top / 5), "footer": round(p.bottom / 5),
        "left": round(p.left / 5), "right": round(p.right / 5),
    }


def test_쪽_테두리는_그리지_않는다(블록_docx):
    """구글 문서가 쪽 테두리를 버려 넣으면 Word 와 구글 문서의 모양이 갈린다."""
    out, _ = 블록_docx
    assert _본문(out).find(f"{W}body/{W}sectPr/{W}pgBorders") is None


def test_기본_문단_스타일은_본문_글자_크기_한_줄_한국어다(블록_docx):
    import xml.etree.ElementTree as ET

    out, kit = 블록_docx
    r = resolve_kit(kit)
    스타일 = ET.fromstring(zipfile.ZipFile(out).read("word/styles.xml"))
    normal = next(s for s in 스타일.iter(f"{W}style") if s.get(f"{W}styleId") == "Normal")
    assert normal.find(f"{W}rPr/{W}sz").get(f"{W}val") == str(int(r.char["body"].size_pt * 2))
    간격 = normal.find(f"{W}pPr/{W}spacing")
    assert 간격.get(f"{W}line") == "240" and 간격.get(f"{W}lineRule") == "auto"
    assert normal.find(f"{W}rPr/{W}lang").get(f"{W}eastAsia") == "ko-KR"


def test_표_폭은_칸_폭의_합과_같다(킷_루트, tmp_path):
    """열마다 twip 으로 반올림하므로 표 폭도 반올림한 열 폭의 합이어야 tblW·gridCol·tcW 가 맞는다."""
    import xml.etree.ElementTree as ET

    from worksheet.plan import CellPlan, TablePlan

    kit = load_kit(킷_루트)
    w = DocxWriter(kit, resolve_kit(kit))
    w.draw(TablePlan("비교표", (tuple(CellPlan("cell", str(i)) for i in range(7)),), None, equal_columns=True))
    w.save(tmp_path / "칠.docx")
    표 = next(_본문(tmp_path / "칠.docx").iter(f"{W}tbl"))
    tblW = int(표.find(f"{W}tblPr/{W}tblW").get(f"{W}w"))
    열 = [int(g.get(f"{W}w")) for g in 표.iter(f"{W}gridCol")]
    칸 = [int(t.get(f"{W}w")) for t in 표.iter(f"{W}tcW")]
    assert 열 == 칸 and tblW == sum(열) == 10093


def test_순서_목록에_없는_태그는_거부한다():
    from docx.oxml import OxmlElement

    from worksheet.backends.docx import _TCPR, _두기

    with pytest.raises(AssertionError):
        _두기(OxmlElement("w:tcPr"), "w:tblW", {}, _TCPR)


def test_라벨_칸은_음영과_가운데_12pt_굵게(블록_docx):
    out, kit = 블록_docx
    r = resolve_kit(kit)
    칸 = next(tc for tc in _본문(out).iter(f"{W}tc") if "".join(t.text or "" for t in tc.iter(f"{W}t")) == "[1] 라벨")
    assert 칸.find(f"{W}tcPr/{W}shd").get(f"{W}fill") == r.box["shade"].fill.lstrip("#")
    assert 칸.find(f".//{W}jc").get(f"{W}val") == "center"
    run = 칸.find(f".//{W}r/{W}rPr")
    assert run.find(f"{W}sz").get(f"{W}val") == str(int(r.char["label"].size_pt * 2))
    assert run.find(f"{W}b") is not None


def test_모든_행에_최소_높이가_있다(블록_docx):
    out, _ = 블록_docx
    for tr in _본문(out).iter(f"{W}tr"):
        h = tr.find(f"{W}trPr/{W}trHeight")
        assert h is not None and h.get(f"{W}hRule") == "atLeast" and int(h.get(f"{W}val")) > 0


def test_칸_안_그림_문단은_가운데(블록_docx):
    out, _ = 블록_docx
    for tc in _본문(out).iter(f"{W}tc"):
        for p in tc.findall(f"{W}p"):
            if p.find(f".//{W}drawing") is not None:
                assert p.find(f"{W}pPr/{W}jc").get(f"{W}val") == "center"


def test_떠_있는_도형이_없다(블록_docx):
    out, _ = 블록_docx
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert "wp:anchor" not in xml and "<v:shape" not in xml and "w:pict" not in xml


def test_칸_문단은_역할의_문단_서식을_쓴다(블록_docx):
    """글자 칸은 역할의 문단 서식(label·cell)을 그대로 쓴다 — 가운데 정렬로 바뀌는 것은 그림 칸뿐이다."""
    out, kit = 블록_docx
    r = resolve_kit(kit)
    _jc = {"LEFT": "left", "CENTER": "center", "RIGHT": "right", "JUSTIFY": "both", "DISTRIBUTE": "distribute"}
    칸 = next(tc for tc in _본문(out).iter(f"{W}tc") if "".join(t.text or "" for t in tc.iter(f"{W}t")) == "값")
    p = 칸.find(f"{W}p")
    jc = p.find(f"{W}pPr/{W}jc")
    assert (jc.get(f"{W}val") if jc is not None else "left") == _jc[r.para["cell"].align]
    assert p.find(f"{W}r/{W}rPr/{W}sz").get(f"{W}val") == str(int(r.char["cell"].size_pt * 2))


def test_본문_그림_문단은_본문_서식이다(블록_docx):
    out, kit = 블록_docx
    r = resolve_kit(kit)
    몸 = _본문(out).find(f"{W}body")
    p = next(p for p in 몸.findall(f"{W}p") if p.find(f".//{W}drawing") is not None)
    jc = p.find(f"{W}pPr/{W}jc")
    기대 = {"LEFT": "left", "CENTER": "center", "RIGHT": "right", "JUSTIFY": "both", "DISTRIBUTE": "distribute"}[r.para["body"].align]
    assert (jc.get(f"{W}val") if jc is not None else "left") == 기대


def test_중첩표는_1x1_만_그린다(킷_루트, tmp_path):
    from worksheet.plan import CellPlan, TablePlan

    kit = load_kit(킷_루트)
    안쪽 = TablePlan("강조박스", ((CellPlan("cell", "가"), CellPlan("cell", "나")),), None)
    겉 = TablePlan("강조박스", ((CellPlan("cell", "", nested=안쪽),),), None)
    with pytest.raises(AssertionError):
        DocxWriter(kit, resolve_kit(kit)).draw(겉)


def test_twip_emu_환산():
    from worksheet.backends.docx import emu, twip

    assert twip(7200) == 1440 and twip(510) == 102
    assert emu(7200) == 914400


def test_중첩표_칸은_1pt_문단_표_1pt_문단_순이다(블록_docx):
    """구글 문서는 칸이 표로 시작하는 것을 못 받아 전체 줄 높이의 빈 줄을 끼워 넣는다(실측
    3쪽 → 2쪽) — 앞 문단을 지우는 대신 1pt 로 눌러 남긴다(뒤 문단은 원래도 1pt)."""
    out, _ = 블록_docx
    tc = next(tc for tc in _본문(out).iter(f"{W}tc") if tc.find(f"{W}tbl") is not None)
    자식들 = [c.tag.split("}")[1] for c in tc if c.tag != f"{W}tcPr"]
    assert 자식들 == ["p", "tbl", "p"]
    앞, _, 뒤 = (c for c in tc if c.tag != f"{W}tcPr")
    앞_spacing = 앞.find(f"{W}pPr/{W}spacing")
    assert 앞_spacing.get(f"{W}before") == "0" and 앞_spacing.get(f"{W}after") == "0"
    assert 앞_spacing.get(f"{W}line") == "20" and 앞_spacing.get(f"{W}lineRule") == "exact"
    assert 앞.find(f"{W}pPr/{W}rPr/{W}sz").get(f"{W}val") == "2"
    뒤_spacing = 뒤.find(f"{W}pPr/{W}spacing")
    assert 뒤_spacing.get(f"{W}line") == "20" and 뒤_spacing.get(f"{W}lineRule") == "exact"


# --- 가구: 머리띠(+확인도장 칸)·원문자 제목·키워드면 ------------------------------------


def _가구_docx(kit, tmp_path, *, 제목수=2, 도장=True):
    w = DocxWriter(kit, resolve_kit(kit))
    w.draw(plan_band(kit, title="회차 제목", stamp=도장))
    w.draw(plan_keyword_page(kit))
    for n in range(1, 제목수 + 1):
        w.draw(plan_heading(kit, number=n, text=f"제목 {n}", textbook="33P" if n == 1 else None, with_stamp=(n == 1)))
    out = tmp_path / "가구.docx"
    w.save(out)
    return _본문(out)


def _칸_글(tc):
    return "".join(t.text or "" for t in tc.iter(f"{W}t"))


def test_머리띠는_한_줄_표이고_도장_칸이_오른쪽에_있다(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    몸 = _가구_docx(kit, tmp_path)
    머리띠 = 몸.find(f"{W}body/{W}tbl")
    칸들 = 머리띠.findall(f"{W}tr/{W}tc")
    글들 = [_칸_글(tc) for tc in 칸들]
    assert 글들[2] == "회차 제목"
    assert 글들[-1] == kit.furniture["stamp"]["text"]
    폭합 = sum(int(tc.find(f"{W}tcPr/{W}tcW").get(f"{W}w")) for tc in 칸들)
    assert abs(폭합 - kit.body_width / 5) <= len(칸들)


def test_도장이_없는_머리띠에는_빈_칸이_남지_않는다(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    몸 = _가구_docx(kit, tmp_path, 도장=False)
    칸들 = 몸.find(f"{W}body/{W}tbl").findall(f"{W}tr/{W}tc")
    assert len(칸들) == len(kit.furniture["band"]["cols"])
    assert kit.furniture["stamp"]["text"] not in [_칸_글(tc) for tc in 칸들]
    폭합 = sum(int(tc.find(f"{W}tcPr/{W}tcW").get(f"{W}w")) for tc in 칸들)
    assert abs(폭합 - int(kit.furniture["band"]["width"]) / 5) <= len(칸들)


def test_머리띠_간격_칸의_tcMar은_좌우가_0이고_스키마_순서를_따른다(킷_루트, tmp_path):
    """구글 문서는 칸 여백(tcMar, 표 기본 좌우 102twip씩)보다 좁은 열을 만나면 열을 넓혀 머리띠가
    오른쪽 여백을 넘는다(실측 847→836px) — 간격 칸(테두리 없는 칸)의 좌우 여백을 0으로 막는다."""
    kit = load_kit(킷_루트)
    몸 = _가구_docx(kit, tmp_path)
    _순서_지킴(몸, "tcPr", _TCPR_순서)
    칸들 = 몸.find(f"{W}body/{W}tbl").findall(f"{W}tr/{W}tc")
    assert len(칸들) == 6  # 표준 킷은 간격 칸이 있다(간격 > 0)
    마진 = 칸들[4].find(f"{W}tcPr/{W}tcMar")
    assert 마진 is not None
    assert 마진.find(f"{W}left").get(f"{W}w") == "0" and 마진.find(f"{W}left").get(f"{W}type") == "dxa"
    assert 마진.find(f"{W}right").get(f"{W}w") == "0" and 마진.find(f"{W}right").get(f"{W}type") == "dxa"


def test_원문자_제목은_킷_색_반전_원문자_글자이고_출처는_별도_run(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    몸 = _가구_docx(kit, tmp_path)
    제목들 = [p for p in 몸.iter(f"{W}p") if "제목 1" in "".join(t.text or "" for t in p.iter(f"{W}t"))]
    runs = 제목들[0].findall(f"{W}r")
    assert runs[0].find(f"{W}t").text == 원문자(1)
    assert runs[0].find(f"{W}rPr/{W}color").get(f"{W}val") == kit.furniture["circle"]["fill"].lstrip("#").upper()
    assert runs[-1].find(f"{W}t").text == kit.furniture["heading"]["textbookFormat"].format(textbook="33P")


def test_21번째_제목부터는_괄호_숫자다():
    assert 원문자(20) == "⓴"
    assert 원문자(21) == "(21)"


def test_제목이_21개_넘어도_그린다(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    몸 = _가구_docx(kit, tmp_path, 제목수=22)
    번호들 = [p.find(f"{W}r/{W}t").text for p in 몸.iter(f"{W}p")
             if "제목 " in "".join(t.text or "" for t in p.iter(f"{W}t"))]
    assert 번호들[19:] == ["⓴", "(21)", "(22)"]


def test_키워드면은_행_수만큼이고_머리_칸에_문구가_있다(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    몸 = _가구_docx(kit, tmp_path)
    표들 = 몸.findall(f"{W}body/{W}tbl")
    키워드 = 표들[1]
    assert len(키워드.findall(f"{W}tr")) == int(kit.furniture["keywordPage"]["rows"])
    assert kit.furniture["keywordPage"]["head"].strip() in "".join(t.text or "" for t in 키워드.iter(f"{W}t"))


def test_키워드면_줄은_정확한_높이이고_빈_문단이_그_안에_들어간다(킷_루트, tmp_path):
    """키워드면은 한 쪽을 통째로 차지한다 — 줄(머리 칸 뺀 행)이 최소 높이면 빈 문단의 줄 높이만큼
    자라 표가 다음 쪽으로 넘친다. 줄은 계획한 높이 그대로(exact), 문단 줄 + 칸 위아래 여백 ≤ 행 높이."""
    kit = load_kit(킷_루트)
    키워드 = _가구_docx(kit, tmp_path).findall(f"{W}body/{W}tbl")[1]
    마진 = 키워드.find(f"{W}tblPr/{W}tblCellMar")
    위아래 = int(마진.find(f"{W}top").get(f"{W}w")) + int(마진.find(f"{W}bottom").get(f"{W}w"))
    설정 = kit.furniture["keywordPage"]
    계획_높이 = round(int(설정["height"]) // int(설정["rows"]) / 5)
    행들 = 키워드.findall(f"{W}tr")
    assert 행들[0].find(f"{W}trPr/{W}trHeight").get(f"{W}hRule") == "atLeast"
    for i, tr in enumerate(행들[1:], start=1):
        h = tr.find(f"{W}trPr/{W}trHeight")
        assert h.get(f"{W}hRule") == "exact" and int(h.get(f"{W}val")) == 계획_높이, i
        간격 = tr.find(f"{W}tc/{W}p/{W}pPr/{W}spacing")
        assert 간격.get(f"{W}lineRule") == "exact", i
        assert int(간격.get(f"{W}line")) + 위아래 <= 계획_높이, i
        # LibreOffice 는 exact 행에 칸 아래 여백을 더 얹는다 — 줄 칸은 위아래 여백이 0 이다
        tcPr = tr.find(f"{W}tc/{W}tcPr")
        assert {c.get(f"{W}w") for c in tcPr.find(f"{W}tcMar")} == {"0"}, i
        _순서_지킴(tr, "tcPr", _TCPR_순서)
        _순서_지킴(tr, "tcMar", _변_순서)
        # 구글 문서는 exact 줄간격이 없어 빈 문단을 문단부호 글자 크기로 잰다 — 부호를 1pt 로 누른다
        pPr = tr.find(f"{W}tc/{W}p/{W}pPr")
        부호 = pPr.find(f"{W}rPr")
        assert 부호 is not None and 부호.find(f"{W}sz").get(f"{W}val") == "2", i
        assert 부호.find(f"{W}szCs").get(f"{W}val") == "2", i
        _순서_지킴(tr, "pPr", _PPR_순서)
        _순서_지킴(tr, "rPr", _RPR_순서)


def test_키워드면_칸은_rule_상자의_채움색을_칠한다(킷_루트, tmp_path):
    """hwpx 는 rule_* borderFill 을 통째로 입혀 채움색까지 칠한다 — docx 도 같은 뜻이어야 한다.
    실제 킷의 rule_* 는 채움색이 없어, 스켈레톤에서 채움색이 있는 번호(shade·answer)로 바꾼 킷으로 본다."""
    kit = load_kit(킷_루트)
    채움 = {"rule_head": kit.border_fill["shade"], "rule_line": kit.border_fill["answer"], "rule_last": kit.border_fill["shade"]}
    kit = dataclasses.replace(kit, border_fill={**kit.border_fill, **채움})
    해석 = resolve_kit(kit)
    assert all(해석.box[k].fill for k in ("rule_head", "rule_line", "rule_last"))
    키워드 = _가구_docx(kit, tmp_path).findall(f"{W}body/{W}tbl")[1]
    행들 = 키워드.findall(f"{W}tr")
    for i, tr in enumerate(행들):
        상자 = "rule_head" if i == 0 else ("rule_last" if i == len(행들) - 1 else "rule_line")
        shd = tr.find(f"{W}tc/{W}tcPr/{W}shd")
        assert shd is not None, f"키워드면 {i}번째 줄에 음영이 없다"
        assert shd.get(f"{W}fill") == 해석.box[상자].fill.lstrip("#").upper()
