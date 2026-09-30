"""킷의 스타일 번호를 실제 값(`worksheet.style`)으로 푼다 — 스켈레톤을 읽는 hwpx 쪽 층.

글자·문단 모양은 `doc.styles` 로, 글꼴 이름·테두리·용지는 스켈레톤의 `Contents/header.xml`·
`Contents/section0.xml` 에서 읽는다. 킷이 가리키는 번호가 없으면 조판 전에 거부한다(fail closed)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable

from hwpx import HwpxDocument
from hwpx.oxml import ParagraphProperty, RunStyle

from worksheet.kit import Kit
from worksheet.style import BoxStyle, CharStyle, PageStyle, ParaStyle, ResolvedKit, Side

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_머리 = "Contents/header.xml"
_절 = "Contents/section0.xml"


def _정수(값: str | None, 속성: str, 부품: str, 자리: str) -> int:
    # 스켈레톤 값을 못 읽으면 영어 변환 오류 대신 어느 부품의 무엇인지 밝혀 거부한다(fail closed)
    try:
        return int(값)
    except (TypeError, ValueError):
        raise ValueError(f"스켈레톤 {부품} 의 {자리} {속성}={값!r} 를 정수로 읽을 수 없다") from None


def _하나(뿌리: ET.Element, 태그: str, 이름: str) -> ET.Element:
    e = next(뿌리.iter(f"{HP}{태그}"), None)
    if e is None:
        raise ValueError(f"스켈레톤 {_절} 에 {이름} 이 없다")
    return e


def _찾기[T](찾기: Callable[[int], T | None], 종류: str, 역할: str, 번호: int) -> T:
    try:
        요소 = 찾기(번호)
    except ValueError as e:  # 스타일 표를 풀다 못 읽는 값을 만나면 영어 오류로 나온다
        raise ValueError(f"스켈레톤 {_머리} 의 {종류} 를 읽을 수 없다 — {e}") from None
    if 요소 is None:
        raise ValueError(f"스켈레톤에 없는 스타일: {종류}.{역할}={번호}")
    return 요소


def _글자(cp: RunStyle, 글꼴: dict[str, str], 역할: str) -> CharStyle:
    글꼴_id = cp.child_attributes.get("fontRef", {}).get("hangul", "")
    if 글꼴_id not in 글꼴:
        raise ValueError(f"스켈레톤에 없는 글꼴: charPr.{역할}의 fontRef hangul={글꼴_id!r}")
    return CharStyle(
        face=글꼴[글꼴_id],
        size_pt=_정수(cp.attributes.get("height", "1000"), "height", _머리, f"charPr.{역할}") / 100,
        bold="bold" in cp.child_attributes,
        underline=cp.underline_type() not in (None, "NONE"),
        color=cp.attributes.get("textColor", "#000000"),
    )


def _문단(pp: ParagraphProperty, 역할: str) -> ParaStyle:
    al = pp.align.horizontal if pp.align is not None and pp.align.horizontal else "LEFT"
    # hp:switch 의 case 가 한글이 읽는 값이다
    vs = pp.version_switch
    ls = vs.case.line_spacing if vs is not None and vs.case is not None and vs.case.line_spacing else pp.line_spacing
    퍼센트 = (
        _정수(ls.attributes.get("value"), "value", _머리, f"paraPr.{역할} lineSpacing")
        if ls is not None and ls.attributes.get("type") == "PERCENT" else None
    )
    return ParaStyle(align=al, line_percent=퍼센트)


def _변(e: ET.Element | None, 자리: str) -> Side:
    if e is None:
        return Side("NONE", 0.0, "#000000")
    값 = e.get("width", "0 mm")
    try:
        굵기 = float(값.split()[0])
    except (IndexError, ValueError):
        이름 = e.tag.split("}")[-1]
        raise ValueError(f"스켈레톤 {_머리} 의 {자리} {이름} width={값!r} 를 수로 읽을 수 없다") from None
    return Side(e.get("type", "NONE"), 굵기, e.get("color", "#000000"))


def _상자(bf: ET.Element, 역할: str) -> BoxStyle:
    wb = bf.find(f".//{HC}winBrush")
    채움 = wb.get("faceColor") if wb is not None else None
    if 채움 is not None and 채움.lower() == "none":
        채움 = None
    자리 = f"borderFill.{역할}"
    return BoxStyle(
        left=_변(bf.find(f"{HH}leftBorder"), 자리), right=_변(bf.find(f"{HH}rightBorder"), 자리),
        top=_변(bf.find(f"{HH}topBorder"), 자리), bottom=_변(bf.find(f"{HH}bottomBorder"), 자리), fill=채움,
    )


def resolve_kit(kit: Kit) -> ResolvedKit:
    doc = HwpxDocument.open(kit.skeleton_path)
    머리 = doc.package.get_xml(_머리)
    절 = doc.package.get_xml(_절)
    # 글꼴 이름은 머리 XML 에서 읽는다 — 공개 API 는 글꼴 id 만 주고 id→이름 표가 없다
    글꼴 = {
        f.get("id"): f.get("face")
        for ff in 머리.iter(f"{HH}fontface") if ff.get("lang") == "HANGUL"
        for f in ff.findall(f"{HH}font")
    }
    # 테두리·채움은 머리 XML 에서 읽는다 — 공개 API 가 타입 있는 테두리·채움 값을 주지 않는다
    bfs = {e.get("id"): e for e in 머리.iter(f"{HH}borderFill")}
    # 용지는 구역 XML 에서 읽는다 — 공개 API(doc.page)는 없거나 못 읽는 값을 0 으로 채워 거부할 수 없다
    용지 = _하나(절, "pagePr", "hp:pagePr")
    여백 = _하나(절, "margin", "hp:margin")

    def 용지값(속성: str) -> int:
        return _정수(용지.get(속성), 속성, _절, "hp:pagePr")

    def 여백값(속성: str) -> int:
        return _정수(여백.get(속성), 속성, _절, "hp:margin")

    return ResolvedKit(
        char={
            역할: _글자(_찾기(doc.styles.char_property, "charPr", 역할, 번호), 글꼴, 역할)
            for 역할, 번호 in kit.char_pr.items()
        },
        para={
            역할: _문단(_찾기(doc.styles.paragraph_property, "paraPr", 역할, 번호), 역할)
            for 역할, 번호 in kit.para_pr.items()
        },
        box={역할: _상자(_찾기(bfs.get, "borderFill", 역할, str(번호)), 역할) for 역할, 번호 in kit.border_fill.items()},
        page=PageStyle(
            width=용지값("width"), height=용지값("height"),
            left=여백값("left"), right=여백값("right"), top=여백값("top"), bottom=여백값("bottom"),
            header=여백값("header"), footer=여백값("footer"),
        ),
    )
