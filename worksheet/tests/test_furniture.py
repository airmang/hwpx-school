import dataclasses
import re
import zipfile
import xml.etree.ElementTree as ET

import pytest
from hwpx.document import HwpxDocument

from worksheet.backends.hwpx import add_band, add_heading, add_keyword_page
from worksheet.kit import load_kit


@pytest.fixture
def 문서(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    doc = HwpxDocument.open(kit.skeleton_path)
    return doc, kit, tmp_path


def test_머리띠는_1행4열이고_칸폭이_킷에서_온다(문서):
    doc, kit, _ = 문서
    band = add_band(doc, kit, title="탐색을 활용한 문제해결")

    assert band.row_count == 1 and band.column_count == 4
    assert [band.cell(0, c).width for c in range(4)] == kit.furniture["band"]["cols"]


def test_머리띠_텍스트가_슬롯에서_나온다(문서):
    doc, kit, _ = 문서
    band = add_band(doc, kit, title="인공지능")

    # 교사칸은 두 문단이고 조합식은 킷에서 온다
    교사칸 = [줄.strip() for 줄 in band.cell(0, 1).text.splitlines() if 줄.strip()]
    assert 교사칸 == ["시험고등학교", "정보 김교사T"]
    assert band.cell(0, 2).text.strip() == "인공지능"
    # 이름칸은 두 줄이고 문구는 킷에서 온다(코드에 박지 않는다)
    이름칸 = band.cell(0, 3).text
    assert "2학년" in 이름칸 and "반" in 이름칸 and "번" in 이름칸 and "이름" in 이름칸
    assert len([줄 for 줄 in 이름칸.splitlines() if 줄.strip()]) == 2


def test_slots_인자를_주면_킷_슬롯_대신_그것을_쓴다(문서):
    """`compose()`가 `effective_slots(kit, grade=sheet.grade)`를 넘기는 자리."""
    doc, kit, _ = 문서
    band = add_band(doc, kit, title="인공지능", slots={**kit.slots, "grade": "3학년"})

    이름칸 = band.cell(0, 3).text
    assert "3학년" in 이름칸 and "2학년" not in 이름칸


def test_slots_인자를_안_주면_킷_슬롯_그대로다(문서):
    doc, kit, _ = 문서
    band = add_band(doc, kit, title="인공지능", slots=None)

    이름칸 = band.cell(0, 3).text
    assert "2학년" in 이름칸


def test_머리띠_칸마다_킷_서식이_입혀진다(문서):
    """킷의 band_* 스타일 ID가 실제로 쓰여야 한다 — 선언만 되고 안 쓰이면 머리띠 글꼴이 킷과 다르다."""
    doc, kit, tmp_path = 문서
    add_band(doc, kit, title="인공지능")
    out = tmp_path / "bandstyle.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    첫표 = xml[xml.index("<hp:tbl") : xml.index("</hp:tbl>")]
    칸들 = 첫표.split("<hp:tc ")[1:]
    기대 = [
        (kit.para_pr["center"], kit.char_pr["band_left"]),
        (kit.para_pr["center"], kit.char_pr["band_teacher"]),
        (kit.para_pr["band_title"], kit.char_pr["band_title"]),
        (kit.para_pr["band_name"], kit.char_pr["band_name"]),
    ]
    assert len(칸들) == 4
    for 칸, (문단_서식, 글자_서식) in zip(칸들, 기대):
        문단refs = re.findall(r'<hp:p [^>]*paraPrIDRef="(\d+)"', 칸)
        글자refs = re.findall(r'<hp:run charPrIDRef="(\d+)"', 칸)
        assert 문단refs and set(문단refs) == {str(문단_서식)}
        assert 글자refs and set(글자refs) == {str(글자_서식)}


def test_머리띠_제목칸만_음영이다(문서):
    doc, kit, tmp_path = 문서
    add_band(doc, kit, title="인공지능")
    out = tmp_path / "band.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    첫표 = xml[xml.index("<hp:tbl") : xml.index("</hp:tbl>")]
    assert 첫표.count(f'borderFillIDRef="{kit.border_fill["shade"]}"') == 1
    assert HwpxDocument.open(out).validate().ok


def test_키워드면은_36행_1열이다(문서):
    doc, kit, _ = 문서
    표 = add_keyword_page(doc, kit)
    assert 표.row_count == 36 and 표.column_count == 1
    assert 표.cell(0, 0).text.strip().startswith("오늘의 키워드")


def test_키워드면_줄_테두리가_머리_본문_끝으로_나뉜다(문서):
    doc, kit, tmp_path = 문서
    add_keyword_page(doc, kit)
    out = tmp_path / "kw.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    표 = xml.rsplit("<hp:tbl", 1)[1]
    # 표 요소 자체도 borderFillIDRef 를 달고 있어 단순 count 는 셀 수와 어긋난다
    # (rule_line 번호를 세면 34가 아니라 35가 된다). 셀만 뽑아 순서대로 본다.
    셀 = re.findall(r'<hp:tc[^>]*borderFillIDRef="(\d+)"', 표)
    assert len(셀) == 36
    assert 셀[0] == str(kit.border_fill["rule_head"])
    assert 셀[1:-1] == [str(kit.border_fill["rule_line"])] * 34
    assert 셀[-1] == str(kit.border_fill["rule_last"])
    assert HwpxDocument.open(out).validate().ok


def test_키워드면_문단_서식이_머리칸과_줄칸으로_갈린다(문서):
    """머리 칸은 paraPr cell + charPr keyword_head, 나머지 줄 칸은 paraPr cell +
    charPr body(킷이 명시한 값 — 지금 값은 0이지만 "0이 아니다"로 단언하지 않는다:
    킷이 0을 고를 자유를 막지 않기 위해 "킷이 정한 값과 같다"로 본다)."""
    doc, kit, tmp_path = 문서
    add_keyword_page(doc, kit)
    out = tmp_path / "kwstyle.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    표 = xml.rsplit("<hp:tbl", 1)[1]
    칸들 = 표.split("<hp:tc ")[1:]
    assert len(칸들) == 36

    머리_문단파라 = re.findall(r'<hp:p [^>]*paraPrIDRef="(\d+)"', 칸들[0])
    머리_글자 = re.findall(r'<hp:run charPrIDRef="(\d+)"><hp:t>[^<]*</hp:t>', 칸들[0])
    assert 머리_문단파라 and set(머리_문단파라) == {str(kit.para_pr["cell"])}
    assert str(kit.char_pr["keyword_head"]) in 머리_글자

    for 칸 in 칸들[1:]:
        줄_문단파라 = re.findall(r'<hp:p [^>]*paraPrIDRef="(\d+)"', 칸)
        줄_글자 = re.findall(r'<hp:run charPrIDRef="(\d+)"', 칸)
        assert 줄_문단파라 and set(줄_문단파라) == {str(kit.para_pr["cell"])}
        assert 줄_글자 and set(줄_글자) == {str(kit.char_pr["body"])}


HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _마지막_문단_자식(path):
    xml = zipfile.ZipFile(path).read("Contents/section0.xml").decode()
    root = ET.fromstring(xml)
    문단 = root.findall(f"{{{HP}}}p")[-1]
    return [
        c.tag.split("}")[-1]
        for run in 문단.findall(f"{{{HP}}}run")
        for c in run
    ]


def test_제목은_타원_텍스트_순서로_놓인다(문서):
    """타원 run 하나 + 텍스트 run **둘**(제목 run, 출처 run) — 출처 표기는 제목과 별도
    run이라 t가 둘이다(테스트: test_교과서_쪽은_제목과_별도_run으로_붙는다 가 각 run의
    charPr까지 본다)."""
    doc, kit, tmp_path = 문서
    add_heading(doc, kit, number=1, text="탐색 알고리즘 종류", textbook="33-35P")
    out = tmp_path / "head.hwpx"
    doc.save_to_path(out)

    assert _마지막_문단_자식(out) == ["ellipse", "t", "t"]
    assert HwpxDocument.open(out).validate().ok


def test_첫_제목에는_확인도장이_붙는다(문서):
    doc, kit, tmp_path = 문서
    add_heading(doc, kit, number=1, text="인간의 지능", with_stamp=True)
    out = tmp_path / "stamp.hwpx"
    doc.save_to_path(out)

    assert _마지막_문단_자식(out) == ["ellipse", "t", "rect"]
    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    assert 'textWrap="IN_FRONT_OF_TEXT"' in xml
    assert "확인도장" in xml


def test_타원_속성이_킷_규격을_따른다(문서):
    doc, kit, tmp_path = 문서
    add_heading(doc, kit, number=3, text="맹목적 탐색")
    out = tmp_path / "circle.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    타원 = xml[xml.index("<hp:ellipse") : xml.index("</hp:ellipse>")]
    assert 'numberingType="PICTURE"' in 타원
    assert 'textWrap="TOP_AND_BOTTOM"' in 타원
    assert f'faceColor="{kit.furniture["circle"]["fill"]}"' in 타원
    assert ">3<" in 타원


def test_교과서_쪽은_제목과_별도_run으로_붙는다(문서):
    """제목 run(charPr headline) 뒤에 출처가 **별도 run**(charPr heading_ref)으로
    온다 — 출처 표기는 제목보다 작은 글자다."""
    doc, kit, tmp_path = 문서
    add_heading(doc, kit, number=2, text="A* 알고리즘", textbook="40P")
    out = tmp_path / "tb.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    문단 = xml[xml.rindex("<hp:p ") :]
    글자_run들 = [
        (cp, t) for cp, t in re.findall(r'<hp:run charPrIDRef="(\d+)"><hp:t>([^<]*)</hp:t>', 문단)
        if t
    ]
    assert (str(kit.char_pr["headline"]), " A* 알고리즘 ") in 글자_run들
    assert (str(kit.char_pr["heading_ref"]), ": 교과서 40P") in 글자_run들
    제목_순서 = 글자_run들.index((str(kit.char_pr["headline"]), " A* 알고리즘 "))
    출처_순서 = 글자_run들.index((str(kit.char_pr["heading_ref"]), ": 교과서 40P"))
    assert 출처_순서 > 제목_순서, "출처 run이 제목 run보다 뒤에 와야 한다"


def test_교과서_쪽이_없으면_제목_run_하나뿐이다(문서):
    doc, kit, tmp_path = 문서
    add_heading(doc, kit, number=1, text="제목")
    out = tmp_path / "notb.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    문단 = xml[xml.rindex("<hp:p ") :]
    # 타원 drawText 속 번호 run(charPr circle_num)도 같은 정규식에 걸리므로 headline 만 본다.
    제목_run들 = [
        (cp, t) for cp, t in re.findall(r'<hp:run charPrIDRef="(\d+)"><hp:t>([^<]*)</hp:t>', 문단)
        if cp == str(kit.char_pr["headline"])
    ]
    assert 제목_run들 == [(str(kit.char_pr["headline"]), " 제목")]


def test_킷의_textbookFormat을_바꾸면_교과서_문구가_안_나온다(문서):
    """문구는 코드가 아니라 킷(furniture.heading.textbookFormat)에서 온다 — 킷을 바꾸면
    문구도 따라간다는 증거다."""
    doc, kit, tmp_path = 문서
    바뀐_킷 = dataclasses.replace(
        kit, furniture={**kit.furniture, "heading": {"textbookFormat": "(교재 {textbook})"}}
    )
    add_heading(doc, 바뀐_킷, number=1, text="제목", textbook="40P")
    out = tmp_path / "customfmt.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    assert xml.count("교과서") == 0
    assert "(교재 40P)" in xml


def _pos(xml: str, 도형: str) -> dict[str, str]:
    import re

    i = xml.index(f"<hp:{도형}")
    조각 = xml[i : xml.index(f"</hp:{도형}>", i)]
    raw = re.search(r"<hp:pos ([^/>]*)/>", 조각).group(1)
    return dict(re.findall(r'(\w+)="([^"]*)"', raw))


def test_타원은_글자처럼_놓여_제목과_같은_줄에_온다(문서):
    """treatAsChar=0이면 실한컴에서 제목 위로 떠오른다."""
    doc, kit, tmp_path = 문서
    add_heading(doc, kit, number=1, text="제목")
    out = tmp_path / "inline.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    assert _pos(xml, "ellipse")["treatAsChar"] == "1"


def test_확인도장은_용지_기준_오른쪽_위에_고정된다(문서):
    """relTo가 PARA/COLUMN이면 실한컴에서 제목에 겹친다."""
    doc, kit, tmp_path = 문서
    add_heading(doc, kit, number=1, text="제목", with_stamp=True)
    out = tmp_path / "stamppos.hwpx"
    doc.save_to_path(out)

    pos = _pos(zipfile.ZipFile(out).read("Contents/section0.xml").decode(), "rect")
    assert pos["treatAsChar"] == "0"
    assert pos["vertRelTo"] == "PAPER" and pos["horzRelTo"] == "PAPER"
    assert pos["vertOffset"] == "5961" and pos["horzOffset"] == "46774"


def test_두_도형의_선과_채움이_킷에서_온다(문서):
    """라이브러리 기본값에 기대면 그 기본값이 바뀔 때 조용히 어긋난다."""
    doc, kit, tmp_path = 문서
    add_heading(doc, kit, number=1, text="제목", with_stamp=True)
    out = tmp_path / "shapestyle.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    타원 = xml[xml.index("<hp:ellipse") : xml.index("</hp:ellipse>")]
    사각형 = xml[xml.index("<hp:rect") : xml.index("</hp:rect>")]
    assert f'color="{kit.furniture["circle"]["line"]}"' in 타원
    assert f'faceColor="{kit.furniture["circle"]["fill"]}"' in 타원
    assert f'color="{kit.furniture["stamp"]["line"]}"' in 사각형
    assert 'faceColor=' not in 사각형          # stamp.fill 이 None 이면 채움이 없다
