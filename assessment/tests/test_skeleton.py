import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from hwpx.document import HwpxDocument
from lxml import etree

from assessment.kit import load_kit
from assessment.memo import append_memo_run
from assessment.ns import HH, HP
from assessment.skeleton import extract_skeleton
from test_hwpx import _png

# 합성 원본에 심는 지어낸 장식 글꼴 — 배포 환경에 없는 글꼴을 font_map 으로 옮기는 경우를 흉내 낸다.
_원본_글꼴 = "가상장식체"
_대상_글꼴 = "함초롬돋움"
# 장식 글꼴을 가리키게 바꿔 둘 킷 역할(글자 모양).
_장식_역할 = ("title", "note", "body")
_언어_속성 = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")


def _q(tag: str) -> str:
    return f"{{{HP}}}{tag}"


def _장식_charPr_id(킷_루트: Path) -> tuple[str, ...]:
    킷 = json.loads((킷_루트 / "kit.json").read_text(encoding="utf-8"))
    return tuple(str(킷["styles"]["charPr"][역할]) for 역할 in _장식_역할)


@pytest.fixture(scope="module")
def 합성_원본(킷_루트, tmp_path_factory) -> Path:
    """실제 양식 대신 테스트가 직접 짓는 '채워진 원본' — 공개 테스트는 비공개 자산 없이 돈다.

    커밋된 씨앗 스켈레톤(1단 머리 + 2단 전환)을 열어, 추출이 기대하는 원본 모양
    (머리 문단 → 학번 줄 → 2단 전환 문단 → 본문)으로 되돌리고 본문 글·표·그림·정답 메모·
    형광펜·메타데이터·미리보기를 채운다. 지어낸 장식 글꼴(`_원본_글꼴`)을 모든 언어 목록에
    더하고 킷의 몇 역할이 그것을 가리키게 해 font_map 검사의 재료로 쓴다.
    """
    dest = tmp_path_factory.mktemp("원본") / "합성원본.hwpx"
    doc = HwpxDocument.open(킷_루트 / "skeleton.hwpx")
    section = doc.sections[0]
    element = section.element

    # 머리 문단에 형광펜 제목 run 을 더한다(추출은 첫 run 만 남긴다).
    머리 = element.findall(_q("p"))[0]
    t = etree.SubElement(etree.SubElement(머리, _q("run"), {"charPrIDRef": "7"}), _q("t"))
    etree.SubElement(t, _q("markpenBegin"), {"color": "#FFFF00"}).tail = "합성 수행평가 제목"
    etree.SubElement(t, _q("markpenEnd"))

    # 학번 줄을 머리와 2단 전환 문단 사이로 옮긴다 — 전환 문단이 세 번째가 된다.
    학번 = doc.add_paragraph("학번 :    이름 : 합성학생")
    element.remove(학번.element)
    element.insert(1, 학번.element)

    doc.add_paragraph("1. 합성 문제 본문")
    메모_문단 = doc.add_paragraph("[2점]")
    append_memo_run(메모_문단.runs[0].element, "", ("합성 정답",), number=1, kit=load_kit(킷_루트))
    표 = doc.add_table(2, 2, width=25229)
    표.set_cell_text(0, 0, "표 안 내용")
    doc.add_picture(_png(20, 20), "png", width_mm=10, height_mm=10)
    section.mark_dirty()

    header_part = doc.parts.headers[0]
    header = header_part.element
    for fontface in header.findall(f".//{{{HH}}}fontface"):
        새_id = str(len(fontface.findall(f"{{{HH}}}font")))
        fontface.append(fontface.makeelement(
            f"{{{HH}}}font", {"id": 새_id, "face": _원본_글꼴, "type": "TTF", "isEmbedded": "0"},
        ))
        fontface.set("fontCnt", str(int(새_id) + 1))
    장식_id = _장식_charPr_id(킷_루트)
    for charpr in header.findall(f".//{{{HH}}}charPr"):
        if charpr.get("id") in 장식_id:
            fontref = charpr.find(f"{{{HH}}}fontRef")
            for 속성 in _언어_속성:
                fontref.set(속성, "2")  # 템플릿 글꼴 둘(0·1) 뒤에 더한 장식 글꼴
    header_part.mark_dirty()

    doc.package.set_document_metadata(creator="합성작성자", title="합성제목")
    doc.package.write("Preview/PrvText.txt", "합성학교 합성교사")
    doc.save_to_path(dest)

    # 픽스처가 실제로 채워졌는지 먼저 확인한다 — 안 그러면 세척 검사가 공허해진다.
    z = zipfile.ZipFile(dest)
    assert any(n.startswith("BinData/") for n in z.namelist())
    본문 = z.read("Contents/section0.xml").decode()
    assert "MEMO" in 본문 and "markpen" in 본문 and "<hp:t>" in 본문
    assert _원본_글꼴 in z.read("Contents/header.xml").decode()
    assert "합성학교" in z.read("Preview/PrvText.txt").decode("utf-8", "ignore")
    return dest


@pytest.fixture(params=["합성", "양식"])
def 원본(request) -> Path:
    """추출 불변식은 합성 원본에서 늘 돌고, `ASSESSMENT_FORM_PATH` 가 있으면 실제 양식에서도 돈다."""
    return request.getfixturevalue("합성_원본" if request.param == "합성" else "원본_경로")


def _문단들(path):
    with zipfile.ZipFile(path) as z:
        뿌리 = ET.fromstring(z.read("Contents/section0.xml"))
    return 뿌리.findall(f"{{{HP}}}p")


def _전환_문단에_금지_요소를_주입한_변형본(원본_경로, 저장할_곳):
    """P2(2단 전환 문단)의 ctrl 안에 hp:pic을 몰래 넣은 변형 원본을 만든다.

    실제로 이런 원본이 있을지는 모르지만, extract_skeleton이 P2의 ctrl **안쪽**까지
    보고 있는지(화이트리스트만 보고 안쪽 내용을 놓치지 않는지)를 증명하는 데는 이걸로
    충분하다 — P0의 같은 검사(`_보존_run_안의_금지_태그`)와 대칭이어야 한다.
    """
    doc = HwpxDocument.open(원본_경로)
    section = doc.sections[0]
    element = section.element
    paragraphs = element.findall(_q("p"))
    전환_run = next(
        r for r in paragraphs[2].findall(_q("run"))
        if r.findall(f".//{_q('colPr')}[@colCount='2']")
    )
    ctrl = 전환_run.find(_q("ctrl"))
    etree.SubElement(ctrl, _q("pic"))
    section.mark_dirty()
    doc.save_to_path(저장할_곳)
    return 저장할_곳


def test_스켈레톤은_문단_둘_1단과_2단(원본, tmp_path):
    dest = tmp_path / "s.hwpx"
    extract_skeleton(원본, dest)
    p = _문단들(dest)
    assert len(p) == 2
    col0 = p[0].findall(f".//{{{HP}}}colPr")
    col1 = p[1].findall(f".//{{{HP}}}colPr")
    assert [c.get("colCount") for c in col0] == ["1"]
    assert [c.get("colCount") for c in col1] == ["2"]
    assert p[0].findall(f".//{{{HP}}}secPr")


def test_스켈레톤에는_글자_그림_메모가_없다(원본, tmp_path):
    dest = tmp_path / "s.hwpx"
    extract_skeleton(원본, dest)
    with zipfile.ZipFile(dest) as z:
        이름들 = z.namelist()
        본문 = z.read("Contents/section0.xml").decode()
        미리보기 = z.read("Preview/PrvText.txt").decode() if "Preview/PrvText.txt" in 이름들 else ""
        메타 = z.read("Contents/content.hpf").decode()
    assert not [n for n in 이름들 if n.startswith("BinData/")]
    assert "<hp:t>" not in 본문 and "MEMO" not in 본문 and "markpen" not in 본문
    assert 미리보기 == ""
    assert "합성" not in 메타


def test_커밋된_킷_스켈레톤도_같은_불변식(킷_루트):
    p = _문단들(킷_루트 / "skeleton.hwpx")
    assert len(p) == 2


def test_2단_전환_문단의_컨트롤_안에_금지된_내용이_있으면_거부한다(원본, tmp_path):
    변형본 = _전환_문단에_금지_요소를_주입한_변형본(원본, tmp_path / "변형본.hwpx")
    dest = tmp_path / "s.hwpx"
    with pytest.raises(ValueError, match="2단 전환 문단"):
        extract_skeleton(변형본, dest)
    assert not dest.exists()


# --- font_map — 배포 환경에 없는 원본 글꼴을 있는 글꼴로 옮긴다 ----------------------------
# 합성 원본에 심은 지어낸 장식 글꼴(`_원본_글꼴`)을 옮겨 검증한다.


def _charPr_글꼴(header_bytes: bytes, cid: str, 속성: str) -> str | None:
    root = ET.fromstring(header_bytes)
    id_to_face: dict[str, str] = {}
    for fontface in root.findall(f".//{{{HH}}}fontface"):
        lang_to_attr = {
            "HANGUL": "hangul", "LATIN": "latin", "HANJA": "hanja", "JAPANESE": "japanese",
            "OTHER": "other", "SYMBOL": "symbol", "USER": "user",
        }
        if lang_to_attr.get(fontface.get("lang")) != 속성:
            continue
        id_to_face = {f.get("id"): f.get("face") for f in fontface.findall(f"{{{HH}}}font")}
    charpr = root.find(f".//{{{HH}}}charPr[@id='{cid}']")
    fontref = charpr.find(f"{{{HH}}}fontRef")
    return id_to_face.get(fontref.get(속성))


def test_font_map이_원본_글꼴을_대상_글꼴로_옮긴다(합성_원본, 킷_루트, tmp_path):
    dest = tmp_path / "s.hwpx"
    보고 = extract_skeleton(합성_원본, dest, font_map={_원본_글꼴: _대상_글꼴})

    header = zipfile.ZipFile(dest).read("Contents/header.xml")
    for cid in _장식_charPr_id(킷_루트):
        for 속성 in _언어_속성:
            assert _charPr_글꼴(header, cid, 속성) == _대상_글꼴, f"charPr {cid} {속성}"

    assert _원본_글꼴 not in header.decode()
    assert 보고["fonts_remapped"] == len(_장식_역할) * len(_언어_속성)
    assert HwpxDocument.open(dest).validate().ok


def test_font_map을_안_주면_보고서의_fonts_remapped는_0(합성_원본, tmp_path):
    dest = tmp_path / "s.hwpx"
    보고 = extract_skeleton(합성_원본, dest)
    assert 보고["fonts_remapped"] == 0
    header = zipfile.ZipFile(dest).read("Contents/header.xml").decode()
    assert _원본_글꼴 in header  # font_map을 안 줬으니 원본 글꼴 이름은 그대로 남는다


def test_커밋된_킷_스켈레톤은_기본_템플릿_글꼴만_쓴다(킷_루트):
    """씨앗은 기본 템플릿 글꼴(함초롬돋움·함초롬바탕)뿐이다 — 킷 역할 글자는 전부 함초롬돋움."""
    header = zipfile.ZipFile(킷_루트 / "skeleton.hwpx").read("Contents/header.xml")
    얼굴들 = {f.get("face") for f in ET.fromstring(header).iter(f"{{{HH}}}font")}
    assert 얼굴들 == {"함초롬돋움", "함초롬바탕"}
    킷 = json.loads((킷_루트 / "kit.json").read_text(encoding="utf-8"))
    assert 킷["fontMap"] == {}
    for 역할, cid in 킷["styles"]["charPr"].items():
        if 역할 == "blank":
            continue
        for 속성 in _언어_속성:
            assert _charPr_글꼴(header, str(cid), 속성) == _대상_글꼴, f"{역할} {속성}"


# --- 밑줄 답칸용 borderFill — 밑줄을 칸 아래 테두리로 그린다 ------------------------------
# 양식 header 에 "아래 테두리만 있는" borderFill 이 없으면 스켈레톤 추출이 결정적으로 더한다.


def _테두리(header: bytes, bid: str) -> dict:
    root = ET.fromstring(header)
    bf = root.find(f".//{{{HH}}}borderFill[@id='{bid}']")
    assert bf is not None, f"borderFill {bid} 가 없다"
    return {
        변: (e.get("type"), e.get("width"), e.get("color"))
        for 변 in ("left", "right", "top", "bottom")
        for e in [bf.find(f"{{{HH}}}{변}Border")]
    }


def test_스켈레톤에_아래_테두리만_있는_borderFill을_더한다(원본, tmp_path):
    dest = tmp_path / "s.hwpx"
    보고 = extract_skeleton(원본, dest)
    header = zipfile.ZipFile(dest).read("Contents/header.xml")
    선 = _테두리(header, str(보고["underline_border_fill"]))
    assert 선["bottom"] == ("SOLID", "0.12 mm", "#000000")
    assert all(선[변][0] == "NONE" for 변 in ("left", "right", "top"))


def test_밑줄_borderFill은_결정적이다(원본, tmp_path):
    """두 번 뽑아도 같은 id·같은 header — 킷 id 가 스켈레톤을 다시 뽑아도 어긋나지 않는다."""
    a, b = tmp_path / "a.hwpx", tmp_path / "b.hwpx"
    보고_a = extract_skeleton(원본, a)
    보고_b = extract_skeleton(원본, b)
    assert 보고_a["underline_border_fill"] == 보고_b["underline_border_fill"]
    assert zipfile.ZipFile(a).read("Contents/header.xml") == zipfile.ZipFile(b).read("Contents/header.xml")


def test_커밋된_킷의_밑줄_borderFill은_아래_테두리만(킷_루트):
    킷 = json.loads((킷_루트 / "kit.json").read_text(encoding="utf-8"))
    header = zipfile.ZipFile(킷_루트 / "skeleton.hwpx").read("Contents/header.xml")
    선 = _테두리(header, str(킷["styles"]["borderFill"]["underline"]))
    assert 선["bottom"] == ("SOLID", "0.12 mm", "#000000")
    assert all(선[변][0] == "NONE" for 변 in ("left", "right", "top"))
