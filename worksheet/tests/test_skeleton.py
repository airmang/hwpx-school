import copy
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from hwpx.document import HwpxDocument

from worksheet.ns import HH, HP
from worksheet.skeleton import _사후조건_확인, extract_skeleton

from _helpers import _charpr_글꼴이름_전부, _금칙장식체_심기, _png, _제목_charpr

_표준_스켈레톤 = Path(__file__).resolve().parents[1] / "kits" / "standard" / "skeleton.hwpx"
_OPF_NS = {"opf": "http://www.idpf.org/2007/opf/"}


def _q(tag: str) -> str:
    return f"{{{HP}}}{tag}"


def test_스켈레톤은_문단1개와_스타일을_남긴다(원본_hwpx, tmp_path):
    dest = tmp_path / "skeleton.hwpx"
    보고 = extract_skeleton(원본_hwpx, dest)

    # 스타일표는 원본(= 씨앗 스켈레톤에 본문만 채운 것)의 것을 그대로 남긴다 — 개수는 씨앗에서 읽는다.
    씨앗 = HwpxDocument.open(_표준_스켈레톤).styles
    개수 = (len(씨앗.border_fills), len(씨앗.char_properties), len(씨앗.paragraph_properties))
    assert 보고 == {
        "paragraphs": 1,
        "border_fills": 개수[0],
        "char_prs": 개수[1],
        "para_prs": 개수[2],
        "bin_data": 0,
        "parts": 11,
        "first_run_stripped": 0,
        "fonts_remapped": 0,
    }
    doc = HwpxDocument.open(dest)
    assert doc.validate().ok
    assert (
        len(doc.styles.border_fills), len(doc.styles.char_properties), len(doc.styles.paragraph_properties),
    ) == 개수


def test_스켈레톤은_secPr을_보존한다(원본_hwpx, tmp_path):
    dest = tmp_path / "skeleton.hwpx"
    extract_skeleton(원본_hwpx, dest)

    section0 = zipfile.ZipFile(dest).read("Contents/section0.xml").decode()
    assert "<hp:secPr" in section0
    assert 'width="59528"' in section0 and 'height="84186"' in section0
    assert 'left="4251"' in section0 and 'top="2834"' in section0


def test_스켈레톤은_작성자_흔적과_그림을_남기지_않는다(원본_hwpx, tmp_path):
    dest = tmp_path / "skeleton.hwpx"
    extract_skeleton(원본_hwpx, dest)

    hpf = zipfile.ZipFile(dest).read("Contents/content.hpf").decode()
    assert "BinData/" not in hpf
    assert "금칙작성자" not in hpf
    assert "금칙제목" not in hpf
    assert dest.stat().st_size < 100_000

    # Preview/PrvText.txt는 OPF 매니페스트 밖에 있어 본문 스트리핑에 딸려 오지
    # 않는다 — 원본 저장 시점의 본문 미리보기가 그대로 남으면 학교·교사 실명이 샌다
    # (check_hygiene은 section0.xml·content.hpf만 보므로 이 잔존은 잡지 못한다).
    preview = zipfile.ZipFile(dest).read("Preview/PrvText.txt").decode()
    assert "금칙학교" not in preview


def test_스켈레톤은_미리보기_그림도_비운다(원본_hwpx, tmp_path):
    """미리보기는 원본 1쪽 스냅샷이라 텍스트 검사로는 못 잡는 유출 통로다."""
    dest = tmp_path / "skeleton.hwpx"
    extract_skeleton(원본_hwpx, dest)

    z = zipfile.ZipFile(dest)
    원본_미리보기 = zipfile.ZipFile(원본_hwpx).read("Preview/PrvImage.png")
    새_미리보기 = z.read("Preview/PrvImage.png")
    assert len(새_미리보기) < 1_000
    assert 새_미리보기 != 원본_미리보기
    assert z.read("Preview/PrvText.txt") == b""


# --- 섹션이 둘 이상인 원본은 지원하지 않는다(fail closed) ----------------------------


@pytest.fixture
def 두_섹션_원본(tmp_path) -> Path:
    """섹션이 둘인 합성 원본 — 지금 코드는 sections[0]만 비워 뒤 섹션 본문이 통째로 남는다."""
    dest = tmp_path / "두섹션.hwpx"
    doc = HwpxDocument.open(_표준_스켈레톤)
    doc.add_section()
    doc.save_to_path(dest)
    return dest


def test_섹션이_둘_이상이면_거부한다(두_섹션_원본, tmp_path):
    with pytest.raises(ValueError, match="섹션이 둘 이상인 원본은 지원하지 않는다: 2개"):
        extract_skeleton(두_섹션_원본, tmp_path / "skeleton.hwpx")


# --- 첫 문단의 첫 run에 글자가 같이 있으면 그 글자만 지운다(secPr·ctrl만 남긴다) --------


@pytest.fixture
def 첫_run에_글자가_든_원본(tmp_path) -> Path:
    """첫 문단의 첫 run이 secPr·ctrl 말고 글자(hp:t)도 담은 합성 원본.

    지금 코드는 이 run을 통째로 보존해 글자가 스켈레톤에 새는데, 이 픽스처가 그 상황을
    재현한다(한글이 저장한 문서의 첫 run은 보통 secPr·ctrl 뿐이지만, 어떤 학교 원본이
    이런 구조일 가능성에 대비한 견고화다).
    """
    dest = tmp_path / "첫run글자.hwpx"
    doc = HwpxDocument.open(_표준_스켈레톤)
    section = doc.sections[0]
    첫_run = section.element.findall(_q("p"))[0].findall(_q("run"))[0]
    글자 = 첫_run.makeelement(_q("t"), {})
    글자.text = "유출될_글자"
    첫_run.append(글자)
    section.mark_dirty()
    doc.save_to_path(dest)
    return dest


def test_첫_run의_글자는_지우고_secPr_ctrl만_남긴다(첫_run에_글자가_든_원본, tmp_path):
    dest = tmp_path / "skeleton.hwpx"
    보고 = extract_skeleton(첫_run에_글자가_든_원본, dest)

    assert 보고["first_run_stripped"] == 1
    section0 = zipfile.ZipFile(dest).read("Contents/section0.xml").decode()
    assert "유출될_글자" not in section0
    assert "<hp:secPr" in section0
    assert "<hp:ctrl>" in section0
    assert HwpxDocument.open(dest).validate().ok


# --- lastsaveby·CreatedDate·ModifiedDate·date·description을 전부 세척한다 --------------


def _메타_심기(package, 이름: str, 값: str) -> None:
    """set_document_metadata가 못 받는 opf:meta(lastsaveby·date 등)에 값을 직접 심는다."""
    tree = package.manifest_tree()
    metadata = tree.find("opf:metadata", _OPF_NS)
    for meta in metadata.findall("opf:meta", _OPF_NS):
        if meta.get("name") == 이름:
            meta.text = 값
            break
    package.set_xml("Contents/content.hpf", tree)


@pytest.fixture
def 메타데이터_심은_원본(tmp_path) -> Path:
    """lastsaveby·date에 더러운 값을 심은 합성 원본 — 이 둘은 set_document_metadata가 못 받는
    키라 extract_skeleton이 content.hpf를 직접 고쳐야 지워진다."""
    dest = tmp_path / "메타더러움.hwpx"
    doc = HwpxDocument.open(_표준_스켈레톤)
    doc.package.set_document_metadata(
        created_date="2020-01-01T00:00:00Z", modified_date="2020-06-01T00:00:00Z",
    )
    _메타_심기(doc.package, "lastsaveby", "김금칙")
    _메타_심기(doc.package, "date", "2020년 1월 1일 수요일 오전 12:00:00")
    doc.save_to_path(dest)
    return dest


def test_메타데이터를_전부_세척한다(메타데이터_심은_원본, tmp_path):
    dest = tmp_path / "skeleton.hwpx"
    extract_skeleton(메타데이터_심은_원본, dest)

    메타 = HwpxDocument.open(dest).package.document_metadata()
    assert 메타.creator is None
    assert 메타.subject is None
    assert 메타.description is None
    assert 메타.keyword is None
    assert 메타.lastsaveby is None
    assert 메타.date is None
    assert 메타.created_date == "1970-01-01T00:00:00Z"
    assert 메타.modified_date == "1970-01-01T00:00:00Z"


# --- 열거하지 않은 이름의 opf:meta도 세척한다(블랙리스트 → 화이트리스트) -------


def _새_메타_심기(package, 이름: str, 값: str) -> None:
    """content.hpf metadata에 **원래 없던** 이름의 opf:meta를 새로 만들어 심는다."""
    tree = package.manifest_tree()
    metadata = tree.find("opf:metadata", _OPF_NS)
    새_메타 = metadata.makeelement(
        f"{{{_OPF_NS['opf']}}}meta", {"name": 이름, "content": "text"},
    )
    새_메타.text = 값
    metadata.append(새_메타)
    package.set_xml("Contents/content.hpf", tree)


@pytest.fixture
def 모르는_메타_심은_원본(tmp_path) -> Path:
    """content.hpf에 **처음 보는 이름**의 opf:meta를 심은 합성 원본.

    지금(수정 전) 세척은 lastsaveby·description·date 셋만 열거해 지우는 블랙리스트라
    이 이름은 존재 자체를 모른다 — 다른 학교 원본에만 있는 한컴 자체 필드가 이 자리다.
    """
    dest = tmp_path / "모르는메타.hwpx"
    doc = HwpxDocument.open(_표준_스켈레톤)
    _새_메타_심기(doc.package, "금칙필드", "금칙작성자")
    doc.save_to_path(dest)
    return dest


def test_모르는_이름의_메타도_세척한다(모르는_메타_심은_원본, tmp_path):
    dest = tmp_path / "skeleton.hwpx"
    extract_skeleton(모르는_메타_심은_원본, dest)

    hpf = zipfile.ZipFile(dest).read("Contents/content.hpf").decode()
    assert "금칙작성자" not in hpf


def test_모르는_메타가_있어도_결정성은_그대로다(모르는_메타_심은_원본, tmp_path):
    dest1 = tmp_path / "a.hwpx"
    dest2 = tmp_path / "b.hwpx"
    extract_skeleton(모르는_메타_심은_원본, dest1)
    extract_skeleton(모르는_메타_심은_원본, dest2)
    assert dest1.read_bytes() == dest2.read_bytes()


# --- 결정성 — 같은 원본은 몇 번을 뽑아도 같은 바이트다 -------------------------------


def test_같은_원본은_두_번_뽑아도_바이트가_같다(원본_hwpx, tmp_path):
    dest1 = tmp_path / "a.hwpx"
    dest2 = tmp_path / "b.hwpx"
    extract_skeleton(원본_hwpx, dest1)
    extract_skeleton(원본_hwpx, dest2)
    assert dest1.read_bytes() == dest2.read_bytes()


# --- 사후 조건(fail closed) — BinData 제거가 실제로 먹혔는지 저장 후 다시 확인한다 ------


def test_사후조건은_물리_BinData_부품이_남아있으면_거부한다(tmp_path):
    doc = HwpxDocument.open(_표준_스켈레톤)
    doc.add_picture(_png(5, 5), "png", width_mm=5, height_mm=5)
    dirty = tmp_path / "dirty.hwpx"
    doc.save_to_path(dirty)

    with pytest.raises(ValueError, match="BinData"):
        _사후조건_확인(HwpxDocument.open(dirty))


def test_사후조건은_끊어진_BinData_참조가_남아있으면_거부한다(tmp_path):
    """물리 부품은 지워졌지만 content.hpf 매니페스트에 참조만 남은 경우(정규식이 항목을
    못 찾았을 때의 재현) — validate()도 물리 부품 수도 이 경우를 못 잡는다. 문자열 검사만
    잡는다(실측: 아래 두 assert가 이 사실 자체를 고정한다)."""
    doc = HwpxDocument.open(_표준_스켈레톤)
    doc.add_picture(_png(5, 5), "png", width_mm=5, height_mm=5)
    src = tmp_path / "src.hwpx"
    doc.save_to_path(src)

    broken = tmp_path / "broken.hwpx"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(broken, "w") as zout:
        for info in zin.infolist():
            if info.filename.startswith("BinData/"):
                continue
            zout.writestr(info, zin.read(info.filename))

    broken_doc = HwpxDocument.open(broken)
    assert broken_doc.validate().ok  # ①만으로는 이 붕괴를 못 잡는다는 실측 고정
    assert not [n for n in broken_doc.package.part_names() if n.startswith("BinData/")]

    with pytest.raises(ValueError, match="BinData"):
        _사후조건_확인(HwpxDocument.open(broken))


# --- 사후조건이 실패해도 dest에 "중립처럼 보이지만 아닌" 파일이 안 남는다 -------
# save_to_path(dest)가 먼저고 사후조건 확인이 나중이면, 실패해도 dest에는 이미 완전한 zip이
# 쓰여 있다 — 임시 경로에 저장 → 사후조건 통과 시에만 os.replace로 원자적 교체해야 한다.


def test_사후조건_실패시_새_dest는_생기지_않는다(원본_hwpx, tmp_path, monkeypatch):
    dest = tmp_path / "skeleton.hwpx"

    def _항상_실패(saved, **_kwargs):
        raise ValueError("스켈레톤을 안전하게 만들지 못했다: 주입된 실패(테스트용)")

    monkeypatch.setattr("worksheet.skeleton._사후조건_확인", _항상_실패)

    with pytest.raises(ValueError, match="주입된 실패"):
        extract_skeleton(원본_hwpx, dest)

    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []  # 임시 파일도 안 남았다


def test_사후조건_실패시_기존_dest는_그대로_남는다(원본_hwpx, tmp_path, monkeypatch):
    dest = tmp_path / "skeleton.hwpx"
    기존_내용 = "기존 스켈레톤 바이트".encode("utf-8")
    dest.write_bytes(기존_내용)

    def _항상_실패(saved, **_kwargs):
        raise ValueError("스켈레톤을 안전하게 만들지 못했다: 주입된 실패(테스트용)")

    monkeypatch.setattr("worksheet.skeleton._사후조건_확인", _항상_실패)

    with pytest.raises(ValueError, match="주입된 실패"):
        extract_skeleton(원본_hwpx, dest)

    assert dest.read_bytes() == 기존_내용  # 덮어쓰기 전이므로 그대로다
    assert list(tmp_path.iterdir()) == [dest]  # 임시 파일이 곁에 남지 않았다


# --- 보존하는 ctrl 안(머리말·꼬리말 자리)에 내용이 있으면 거부한다 -------------


@pytest.fixture
def 컨트롤_안에_글자가_든_원본(tmp_path) -> Path:
    """ctrl **안**(머리말·꼬리말이 실제로 위치하는 자리)에 글자가 든 합성 원본.

    ctrl 자체는 보존 대상이라 지금 코드(수정 전)는 그 안쪽을 안 보고 그냥 통과시킨다 —
    다른 학교 원본이 머리말에 학교명을 넣어 뒀다면 그대로 "중립" 스켈레톤에 남는다.
    """
    dest = tmp_path / "컨트롤글자.hwpx"
    doc = HwpxDocument.open(_표준_스켈레톤)
    section = doc.sections[0]
    첫_run = section.element.findall(_q("p"))[0].findall(_q("run"))[0]
    ctrl = 첫_run.find(_q("ctrl"))
    글자 = ctrl.makeelement(_q("t"), {})
    글자.text = "유출될_머리말"
    ctrl.append(글자)
    section.mark_dirty()
    doc.save_to_path(dest)
    return dest


def test_컨트롤_안에_내용이_있으면_거부한다(컨트롤_안에_글자가_든_원본, tmp_path):
    dest = tmp_path / "skeleton.hwpx"
    with pytest.raises(
        ValueError, match="첫 문단의 컨트롤 안에 내용이 있다.*hp:t",
    ):
        extract_skeleton(컨트롤_안에_글자가_든_원본, dest)
    assert not dest.exists()


def test_컨트롤_안의_표도_거부한다(tmp_path):
    """글자뿐 아니라 표·그림·도형 자손도 같은 문구로 거부해야 한다 — 표로 대표 확인.

    hp:tbl은 hp:sz·hp:pos·hp:outMargin·hp:inMargin 같은 필수 자식이 없으면 라이브러리
    자신의 저장 시 안전성 검사(open-safety)가 막는다 — 맨손으로 만들지 않고 add_table로
    진짜 유효한 표를 하나 만든 뒤 그 XML을 통째로 복사해 ctrl 안에 심는다.
    """
    dest_src = tmp_path / "컨트롤표.hwpx"
    doc = HwpxDocument.open(_표준_스켈레톤)
    표 = doc.add_table(1, 1, width=1000, height=1000)
    표_사본 = copy.deepcopy(표.element)

    section = doc.sections[0]
    첫_run = section.element.findall(_q("p"))[0].findall(_q("run"))[0]
    ctrl = 첫_run.find(_q("ctrl"))
    ctrl.append(표_사본)
    section.mark_dirty()
    doc.save_to_path(dest_src)

    dest = tmp_path / "skeleton.hwpx"
    with pytest.raises(
        ValueError, match="첫 문단의 컨트롤 안에 내용이 있다.*hp:tbl",
    ):
        extract_skeleton(dest_src, dest)
    assert not dest.exists()


# --- font_map — kit.json이 준 글꼴 매핑을 header.xml에 적용한다 ------------------------
# kits/standard/skeleton.hwpx는 기본 템플릿 글꼴만 써서 장식 글꼴이 없으므로, 여기서는
# 합성으로 심는다(`_금칙장식체_심기`) — 목록 **중간**에 끼워 id 재부여가
# 실제로 일어나게 한다.


@pytest.fixture
def 장식_글꼴_심은_원본(tmp_path) -> Path:
    dest = tmp_path / "장식글꼴.hwpx"
    _금칙장식체_심기(_표준_스켈레톤, dest)
    return dest


_언어_속성 = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")


def test_font_map이_지정한_글꼴만_바뀌고_나머지_charPr은_그대로다(장식_글꼴_심은_원본, tmp_path):
    dest = tmp_path / "skeleton.hwpx"
    font_map = {"금칙장식체": "함초롬돋움"}
    이전 = _charpr_글꼴이름_전부(장식_글꼴_심은_원본)

    보고 = extract_skeleton(장식_글꼴_심은_원본, dest, font_map=font_map)

    header = zipfile.ZipFile(dest).read("Contents/header.xml").decode()
    assert "금칙장식체" not in header

    이후 = _charpr_글꼴이름_전부(dest)
    assert set(이전) == set(이후)  # 같은 (charPr id, 언어) 전수를 본다 — 재부여로 안 사라졌다
    # 핵심 단언 — 테스트가 직접(엔진 헬퍼를 안 부르고) XML에서 계산한다: 바꾸기 전 이름을
    # font_map으로 옮긴 값 == 바뀐 뒤 이름, 모든 charPr × 언어에 대해.
    for 키, 이전_이름 in 이전.items():
        assert font_map.get(이전_이름, 이전_이름) == 이후[키], f"{키}: {이전_이름} -> {이후[키]}"

    for 속성 in _언어_속성:
        assert 이후[("0", 속성)] == "함초롬돋움"
        assert 이후[(_제목_charpr, 속성)] == "함초롬돋움"

    assert 보고["fonts_remapped"] == 2 * len(_언어_속성)  # charPr 2개 × 언어 7개
    assert HwpxDocument.open(dest).validate().ok


def test_font_map의_대상_글꼴이_없으면_새로_더한다(장식_글꼴_심은_원본, tmp_path):
    dest = tmp_path / "skeleton.hwpx"
    extract_skeleton(장식_글꼴_심은_원본, dest, font_map={"금칙장식체": "새글꼴"})

    root = ET.fromstring(zipfile.ZipFile(dest).read("Contents/header.xml"))
    for fontface in root.findall(f".//{{{HH}}}fontface"):
        fonts = fontface.findall(f"{{{HH}}}font")
        얼굴들 = [f.get("face") for f in fonts]
        assert "새글꼴" in 얼굴들
        assert "금칙장식체" not in 얼굴들
        assert fontface.get("fontCnt") == str(len(fonts))
        ids = sorted(int(f.get("id")) for f in fonts)
        assert ids == list(range(len(fonts)))  # 0..N-1 연속

    assert HwpxDocument.open(dest).validate().ok


def test_font_map의_원래_글꼴이_없으면_아무_일도_안_한다(원본_hwpx, tmp_path):
    """다른 학교 양식에 표준 씨앗의 fontMap이 딸려 와도 무해해야 한다 — 원본_hwpx에는 애초에
    `금칙장식체`가 없다."""
    map_없음 = tmp_path / "a.hwpx"
    map_있음 = tmp_path / "b.hwpx"
    extract_skeleton(원본_hwpx, map_없음)
    extract_skeleton(원본_hwpx, map_있음, font_map={"금칙장식체": "함초롬돋움"})
    assert map_없음.read_bytes() == map_있음.read_bytes()


def test_font_map을_적용해도_같은_원본은_두_번_뽑으면_바이트가_같다(장식_글꼴_심은_원본, tmp_path):
    dest1 = tmp_path / "a.hwpx"
    dest2 = tmp_path / "b.hwpx"
    font_map = {"금칙장식체": "함초롬돋움"}
    extract_skeleton(장식_글꼴_심은_원본, dest1, font_map=font_map)
    extract_skeleton(장식_글꼴_심은_원본, dest2, font_map=font_map)
    assert dest1.read_bytes() == dest2.read_bytes()


def test_font_map을_적용해도_자기_자신을_원본으로_써도_멱등이다(장식_글꼴_심은_원본, tmp_path):
    """공개 사용자는 원본 hwpx가 없고 스켈레톤만 있다 — source와 dest가 같은 파일이어도
    안전해야 하고, 이미 한 번 옮긴 뒤 같은 font_map으로 또 돌리면(원래 글꼴이 더는 없으므로)
    바이트가 그대로여야 한다."""
    working = tmp_path / "working.hwpx"
    working.write_bytes(장식_글꼴_심은_원본.read_bytes())
    font_map = {"금칙장식체": "함초롬돋움"}

    extract_skeleton(working, working, font_map=font_map)
    한_번_옮긴_뒤 = working.read_bytes()

    extract_skeleton(working, working, font_map=font_map)
    assert working.read_bytes() == 한_번_옮긴_뒤


def test_연쇄가_아닌_두_항목은_각각_독립적으로_재지정된다(tmp_path):
    """{"금칙장식체가":"함초롬바탕", "금칙장식체나":"함초롬돋움"}처럼 대상이 서로 다른
    원래 글꼴의 목록에 없는(=연쇄가 아닌) 두 항목은, 순서대로 적용돼도 서로 안 얽히고
    각자 지정한 대로 재지정돼야 한다."""
    중간 = tmp_path / "중간.hwpx"
    dirty = tmp_path / "dirty.hwpx"
    _금칙장식체_심기(_표준_스켈레톤, 중간, face="금칙장식체가", 대상_charpr_ids=("0",))
    _금칙장식체_심기(중간, dirty, face="금칙장식체나", 대상_charpr_ids=(_제목_charpr,))

    dest = tmp_path / "skeleton.hwpx"
    font_map = {"금칙장식체가": "함초롬바탕", "금칙장식체나": "함초롬돋움"}
    이전 = _charpr_글꼴이름_전부(dirty)

    보고 = extract_skeleton(dirty, dest, font_map=font_map)

    header = zipfile.ZipFile(dest).read("Contents/header.xml").decode()
    assert "금칙장식체가" not in header
    assert "금칙장식체나" not in header

    이후 = _charpr_글꼴이름_전부(dest)
    assert set(이전) == set(이후)
    for 키, 이전_이름 in 이전.items():
        assert font_map.get(이전_이름, 이전_이름) == 이후[키], f"{키}: {이전_이름} -> {이후[키]}"

    for 속성 in _언어_속성:
        assert 이후[("0", 속성)] == "함초롬바탕"
        assert 이후[(_제목_charpr, 속성)] == "함초롬돋움"

    assert 보고["fonts_remapped"] == 2 * len(_언어_속성)  # charPr 2개 × 언어 7개, 각각 독립
    assert HwpxDocument.open(dest).validate().ok


def test_font_map은_아무_charPr도_안_가리키는_글꼴도_목록에서_지운다(tmp_path):
    """목록에는 있지만 그 언어에서 아무 charPr도 안 쓰는 글꼴도 재지정 건수(0건)와 별개로
    목록 자체는 바뀌어야 한다 — id·fontCnt가 계속 일관돼야 한다."""
    dirty = tmp_path / "dirty.hwpx"
    _금칙장식체_심기(_표준_스켈레톤, dirty, 대상_charpr_ids=())  # 아무 charPr도 안 가리킨다

    dest = tmp_path / "skeleton.hwpx"
    이전 = _charpr_글꼴이름_전부(dirty)

    보고 = extract_skeleton(dirty, dest, font_map={"금칙장식체": "함초롬돋움"})
    assert 보고["fonts_remapped"] == 0  # 가리키던 charPr이 없었으니 재지정 건수는 0

    root = ET.fromstring(zipfile.ZipFile(dest).read("Contents/header.xml"))
    for fontface in root.findall(f".//{{{HH}}}fontface"):
        fonts = fontface.findall(f"{{{HH}}}font")
        얼굴들 = [f.get("face") for f in fonts]
        assert "금칙장식체" not in 얼굴들
        assert fontface.get("fontCnt") == str(len(fonts))
        ids = sorted(int(f.get("id")) for f in fonts)
        assert ids == list(range(len(fonts)))  # 0..N-1 연속

    # 재지정 건수가 0이어도 다른 모든 charPr의 글꼴 이름은 그대로다(목록 구조만 바뀌었다).
    이후 = _charpr_글꼴이름_전부(dest)
    assert set(이전) == set(이후)
    for 키, 이전_이름 in 이전.items():
        assert 이전_이름 == 이후[키], f"{키}: {이전_이름} -> {이후[키]}"

    assert HwpxDocument.open(dest).validate().ok
