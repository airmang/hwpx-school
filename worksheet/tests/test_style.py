import json
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from worksheet.kit import load_kit
from worksheet.kit_style import resolve_kit

_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
# 스타일 번호는 씨앗 스크립트가 kit.json 에 쓴 값을 그대로 읽는다 — 다시 박아 두지 않는다.
_번호 = json.loads((Path(__file__).resolve().parents[1] / "kits" / "standard" / "kit.json").read_text(encoding="utf-8"))["styles"]


def test_표준_킷의_역할을_실제_값으로_푼다(킷_루트):
    r = resolve_kit(load_kit(킷_루트))
    assert r.char["label"].size_pt == 12 and r.char["label"].bold
    assert r.char["label"].face == "함초롬돋움"
    assert r.char["label"].color == "#000000"
    assert r.para["label"].align == "CENTER" and r.para["label"].line_percent == 160
    assert r.para["cell"].align == "LEFT"
    assert r.box["shade"].fill == "#DEE7F1"
    assert r.box["plain"].fill is None
    assert r.box["plain"].left.kind == "SOLID" and r.box["plain"].left.width_mm == 0.12
    assert (r.page.width, r.page.height) == (59528, 84186)
    assert (r.page.left, r.page.right, r.page.top, r.page.bottom) == (4251, 4251, 2834, 2834)


def test_스켈레톤에_없는_스타일_번호는_조판_전에_거부한다(킷_루트, tmp_path):
    root = tmp_path / "망가진킷"
    shutil.copytree(킷_루트, root)
    데이터 = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    데이터["styles"]["charPr"]["label"] = 9999
    (root / "kit.json").write_text(json.dumps(데이터, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="스켈레톤에 없는 스타일: charPr.label=9999"):
        resolve_kit(load_kit(root))


def test_charPr이_가리키는_글꼴_id가_HANGUL_목록에_없으면_조판_전에_거부한다(킷_루트, tmp_path):
    """charPr 번호 자체는 스켈레톤에 있어도(fail-closed 1단계 통과), 그 charPr의
    fontRef.hangul이 가리키는 글꼴 id가 HANGUL fontface 목록에 없으면 `_글자()`가
    빈 글꼴명으로 조용히 넘어가지 않고 똑같이 거부해야 한다. `prompt`의 charPr 번호는
    kit.json에서 그 역할 하나만 가리켜(다른 역할과 안 겹쳐) 오류 메시지의 역할 이름을 못박을 수 있다."""
    prompt_번호 = _번호["charPr"]["prompt"]
    assert list(_번호["charPr"].values()).count(prompt_번호) == 1
    root = tmp_path / "글꼴깨진킷"
    shutil.copytree(킷_루트, root)
    스켈레톤 = root / "skeleton.hwpx"

    with zipfile.ZipFile(스켈레톤) as z:
        조각들 = [(정보, z.read(정보.filename)) for 정보 in z.infolist()]
    헤더_위치 = next(i for i, (정보, _) in enumerate(조각들) if 정보.filename == "Contents/header.xml")
    헤더 = ET.fromstring(조각들[헤더_위치][1])
    prompt_charpr = 헤더.find(f".//{_HH}charPr[@id='{prompt_번호}']")  # prompt 하나만 이 번호를 쓴다
    prompt_charpr.find(f"{_HH}fontRef").set("hangul", "999")  # HANGUL 목록에 없는 id
    새_헤더 = ET.tostring(헤더, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(스켈레톤, "w") as zout:
        for i, (정보, 데이터) in enumerate(조각들):
            zout.writestr(정보, 새_헤더 if i == 헤더_위치 else 데이터)

    with pytest.raises(ValueError, match="스켈레톤에 없는 글꼴: charPr.prompt의 fontRef hangul='999'"):
        resolve_kit(load_kit(root))


def test_docx_글꼴은_킷에서_오고_기본은_맑은_고딕(킷_루트, tmp_path):
    assert load_kit(킷_루트).docx_font == "맑은 고딕"
    root = tmp_path / "글꼴킷"
    shutil.copytree(킷_루트, root)
    데이터 = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    데이터["docx"] = {"font": "나눔고딕"}
    (root / "kit.json").write_text(json.dumps(데이터, ensure_ascii=False), encoding="utf-8")
    assert load_kit(root).docx_font == "나눔고딕"


@pytest.mark.parametrize("값", [["맑은 고딕"], {"font": ""}, {"font": 3}, "맑은 고딕"])
def test_docx_키의_꼴이_틀리면_거부한다(킷_루트, tmp_path, 값):
    root = tmp_path / "틀린킷"
    shutil.copytree(킷_루트, root)
    데이터 = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    데이터["docx"] = 값
    (root / "kit.json").write_text(json.dumps(데이터, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match='kit.json 의 docx 는 {"font": "<글꼴 이름>"} 꼴이어야 한다'):
        load_kit(root)


_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _스켈레톤_고치기(킷_루트, tmp_path, 부품: str, 고치기) -> "Path":
    root = tmp_path / "고친킷"
    shutil.copytree(킷_루트, root)
    스켈레톤 = root / "skeleton.hwpx"
    with zipfile.ZipFile(스켈레톤) as z:
        조각들 = [(정보, z.read(정보.filename)) for 정보 in z.infolist()]
    for i, (정보, 데이터) in enumerate(조각들):
        if 정보.filename == 부품:
            뿌리 = ET.fromstring(데이터)
            고치기(뿌리)
            조각들[i] = (정보, ET.tostring(뿌리, encoding="utf-8", xml_declaration=True))
    with zipfile.ZipFile(스켈레톤, "w") as zout:
        for 정보, 데이터 in 조각들:
            zout.writestr(정보, 데이터)
    return root


def _margin_빼기(뿌리):
    for 부모 in 뿌리.iter():
        for c in list(부모):
            if c.tag == f"{_HP}margin":
                부모.remove(c)


@pytest.mark.parametrize("부품, 고치기, 문구", [
    ("Contents/section0.xml", lambda r: next(r.iter(f"{_HP}pagePr")).set("width", "넓게"),
     "스켈레톤 Contents/section0.xml 의 hp:pagePr width='넓게' 를 정수로 읽을 수 없다"),
    ("Contents/section0.xml", _margin_빼기, "스켈레톤 Contents/section0.xml 에 hp:margin 이 없다"),
    ("Contents/header.xml", lambda r: r.find(f".//{_HH}charPr[@id='{_번호['charPr']['prompt']}']").set("height", "크게"),
     "스켈레톤 Contents/header.xml 의 charPr.prompt height='크게' 를 정수로 읽을 수 없다"),
    # grid 의 borderFill 번호는 grid 역할 하나만 가리킨다
    ("Contents/header.xml", lambda r: r.find(f".//{_HH}borderFill[@id='{_번호['borderFill']['grid']}']/{_HH}leftBorder").set("width", "굵게 mm"),
     "스켈레톤 Contents/header.xml 의 borderFill.grid leftBorder width='굵게 mm' 를 수로 읽을 수 없다"),
])
def test_스켈레톤_값을_못_읽으면_부품을_밝힌_한국어_오류로_거부한다(킷_루트, tmp_path, 부품, 고치기, 문구):
    root = _스켈레톤_고치기(킷_루트, tmp_path, 부품, 고치기)
    with pytest.raises(ValueError) as 잡힘:
        resolve_kit(load_kit(root))
    assert str(잡힘.value) == 문구
