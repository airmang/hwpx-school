import dataclasses
import re
import xml.etree.ElementTree as ET
import zipfile

import pytest
from hwpx.document import HwpxDocument

from _helpers import _png
from worksheet.backends.docx import DocxWriter
from worksheet.backends.hwpx import _셀, render_node
from worksheet.blocks import (
    PLANNERS, SPECS, STRUCTURAL, _MM_HWPUNIT, _int_attr, _length_attr, _모르는_속성_문구,
    _칸_여백_상하, _칸_여백_좌우, fence_problems, parse_pairs, plan_node, png_size,
)
from worksheet.kit import load_kit
from worksheet.md import Body, Fence, Figure, Prompt
from worksheet.kit_style import resolve_kit
from worksheet.vocab import FENCE_BLOCKS, STRUCTURAL_BLOCKS

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


@pytest.fixture
def 문서(킷_루트, tmp_path):
    kit = load_kit(킷_루트)
    return HwpxDocument.open(kit.skeleton_path), kit, tmp_path


def _hwpx로_그린다(doc, kit, fence, base_dir) -> bool:
    """hwpx 렌더러가 예외 없이 그리는가 — 그렸다면 표가 실제로 하나 더 생겨야 한다."""
    표_전 = len(doc.tables)
    try:
        render_node(doc, kit, fence, base_dir=base_dir)
    except ValueError:
        assert len(doc.tables) == 표_전, "거부했다면 표를 반쯤 그리지도 않아야 한다"
        return False
    assert len(doc.tables) > 표_전, "문제가 없다면 렌더러가 실제로 뭔가 그려야 한다"
    return True


def _docx로_그린다(kit, fence, base_dir) -> bool:
    """docx 렌더러가 같은 계획을 예외 없이 그리는가 — 양방향 성질의 두 번째 형식."""
    writer = DocxWriter(kit, resolve_kit(kit))
    try:
        writer.draw(plan_node(kit, fence, base_dir=base_dir))
    except ValueError:
        return False
    assert len(writer.doc.tables) == 1, "문제가 없다면 docx 렌더러도 표를 실제로 그려야 한다"
    return True


def test_png_크기를_읽는다():
    assert png_size(_png(640, 480)) == (640, 480)
    with pytest.raises(ValueError, match="PNG"):
        png_size(b"\xff\xd8\xff\xe0not-a-png")


def test_정의빈칸은_본문폭_1열표다(문서):
    doc, kit, tmp_path = 문서
    render_node(doc, kit, Body("■ 정렬: 자료를 정해진 ________에 따라"), base_dir=tmp_path)
    out = tmp_path / "def.hwpx"
    doc.save_to_path(out)

    표 = doc.tables.all[-1]
    assert 표.row_count == 1 and 표.column_count == 1
    assert "■ 정렬" in 표.cell(0, 0).text
    assert HwpxDocument.open(out).validate().ok


def test_발문은_표가_아니라_문단이다(문서):
    doc, kit, tmp_path = 문서
    표_전 = len(doc.tables)
    render_node(doc, kit, Prompt("아래 그림의 트리 구조에서 …"), base_dir=tmp_path)

    assert len(doc.tables) == 표_전
    assert doc.paragraphs[-1].para_pr_id_ref == str(kit.para_pr["prompt"])
    assert "아래 그림" in doc.paragraphs[-1].text


def test_발문_run은_킷의_prompt_charPr를_쓴다(문서):
    """charPr.body(=0)는 킷이 고른 서식이 아니라 "아무것도 안 입힌" 라이브러리 기본값과
    우연히 같은 값이다 — 저장 XML만 봐서는 구별이 안 되고 실한컴 렌더에서만 드러난다
    (발문이 10pt 바탕체로 보인 적이 있다). 별도 키 charPr.prompt(=17, 10pt 굵은 제목
    글꼴)를 쓰면 이 우연이 사라진다."""
    doc, kit, tmp_path = 문서
    render_node(doc, kit, Prompt("본문"), base_dir=tmp_path)
    assert doc.paragraphs[-1].char_pr_id_ref == str(kit.char_pr["prompt"])


def test_발문_charPr는_킷이_바뀌면_따라간다(문서):
    """킷 스왑 원칙 — 값이 코드에 박혀 있지 않다는 증거(test_kit.py의 textbookFormat
    스왑 테스트와 같은 방식)."""
    doc, kit, tmp_path = 문서
    바뀐_킷 = dataclasses.replace(kit, char_pr={**kit.char_pr, "prompt": 99})
    render_node(doc, 바뀐_킷, Prompt("본문"), base_dir=tmp_path)
    assert doc.paragraphs[-1].char_pr_id_ref == "99"


def test_그림칸은_비율을_지키고_그림을_넣는다(문서, tmp_path):
    doc, kit, _ = 문서
    (tmp_path / "그림").mkdir()
    (tmp_path / "그림" / "트리.png").write_bytes(_png(400, 200))

    render_node(doc, kit, Figure("그림/트리.png", width_mm=80.0), base_dir=tmp_path)
    out = tmp_path / "fig.hwpx"
    doc.save_to_path(out)

    saved = HwpxDocument.open(out)
    assert saved.validate().ok
    assert len(saved.media.images) == 1
    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    assert "<hp:pic" in xml


def test_라벨_설명_쌍을_읽는다():
    assert parse_pairs("[1] 인간의 지능\n: 설명 A\n[2] 컴퓨터의 지능\n: 설명 B") == [
        ("[1] 인간의 지능", "설명 A"),
        ("[2] 컴퓨터의 지능", "설명 B"),
    ]


def test_설명_없이_라벨만_끝나면_빈_설명으로_남는다():
    """마지막 라벨 뒤에 ': 설명' 줄이 안 오면 그 라벨은 버려지지 않고 설명 빈 채로 쌍에
    들어간다(학생이 채울 빈칸으로 남는다)."""
    assert parse_pairs("[1] 인간의 지능") == [("[1] 인간의 지능", "")]
    assert parse_pairs("[1] 인간의 지능\n: 설명 A\n[2] 컴퓨터의 지능") == [
        ("[1] 인간의 지능", "설명 A"),
        ("[2] 컴퓨터의 지능", ""),
    ]


def test_라벨설명은_좁은_음영_라벨칸과_넓은_설명칸이다(문서):
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("라벨설명", {}, "[1] 인간의 지능\n: 설명 A\n[2] 컴퓨터의 지능\n: 설명 B"),
        base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    assert 표.row_count == 2 and 표.column_count == 2
    assert 표.cell(0, 0).text.strip() == "[1] 인간의 지능"
    assert 표.cell(1, 1).text.strip() == "설명 B"

    out = tmp_path / "label.hwpx"
    doc.save_to_path(out)
    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    마지막표 = xml[xml.rindex("<hp:tbl") :]
    assert 마지막표.count(f'borderFillIDRef="{kit.border_fill["shade"]}"') == 2
    assert HwpxDocument.open(out).validate().ok


def test_용어카드는_라벨행_설명행_가로배치다(문서):
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("용어카드", {"cols": "초기 상태|상태 공간|목표 상태"},
              "시작 상태\n모아 놓은 공간\n해결된 후 상태"),
        base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    assert 표.row_count == 2 and 표.column_count == 3
    assert 표.cell(0, 1).text.strip() == "상태 공간"
    assert 표.cell(1, 2).text.strip() == "해결된 후 상태"


def test_용어카드_설명이_모자라면_빈칸으로_둔다(문서):
    doc, kit, tmp_path = 문서
    render_node(doc, kit, Fence("용어카드", {"cols": "가|나|다"}, ""), base_dir=tmp_path)
    표 = doc.tables.all[-1]
    assert 표.row_count == 2 and 표.column_count == 3
    assert 표.cell(1, 0).text.strip() == ""


def test_비교표는_머리행과_머리열이_음영이다(문서):
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("비교표", {"cols": "맹목적 탐색|휴리스틱 탐색", "rows": "정의|탐색 방법|종류"}, ""),
        base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    assert 표.row_count == 4 and 표.column_count == 3
    assert 표.cell(0, 0).text.strip() == ""
    assert 표.cell(0, 2).text.strip() == "휴리스틱 탐색"
    assert 표.cell(3, 0).text.strip() == "종류"
    assert 표.cell(2, 1).text.strip() == ""

    out = tmp_path / "cmp.hwpx"
    doc.save_to_path(out)
    마지막표 = zipfile.ZipFile(out).read("Contents/section0.xml").decode().rsplit("<hp:tbl", 1)[1]
    assert 마지막표.count(f'borderFillIDRef="{kit.border_fill["shade"]}"') == 6  # 머리행 3 + 머리열 3
    assert HwpxDocument.open(out).validate().ok


def test_데이터표는_머리행_아래를_빈_격자로_둔다(문서):
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("데이터표", {"head": "단계|g(n)|h(n)|f(n)", "rows": "3"}, ""),
        base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    assert 표.row_count == 4 and 표.column_count == 4
    assert 표.cell(0, 3).text.strip() == "f(n)"
    assert all(표.cell(r, c).text.strip() == "" for r in range(1, 4) for c in range(4))


def test_데이터표_본문줄이_있으면_채운다(문서):
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("데이터표", {"head": "단계|g(n)|h(n)", "rows": "2"}, "STEP 1|0|5\nSTEP 2|2|3"),
        base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    assert 표.cell(1, 0).text.strip() == "STEP 1"
    assert 표.cell(2, 2).text.strip() == "3"


@pytest.mark.parametrize(
    "블록, 속성, 빠진",
    [
        ("비교표", {"cols": "가|나"}, "rows"),
        ("비교표", {"rows": "정의"}, "cols"),
        ("용어카드", {}, "cols"),
        ("데이터표", {"rows": "3"}, "head"),
    ],
)
def test_필수_속성이_없으면_md_문형으로_거부한다(문서, 블록, 속성, 빠진):
    """md.py와 같은 오류 문형 — 교사가 손으로 쓰는 파일이므로 KeyError 트레이스백 금지."""
    doc, kit, tmp_path = 문서
    with pytest.raises(ValueError, match=f"{블록} 블록에 {빠진}= 가 없다"):
        render_node(doc, kit, Fence(블록, 속성, ""), base_dir=tmp_path)


def test_답칸은_라벨_음영칸과_빈_답칸이다(문서):
    doc, kit, tmp_path = 문서
    render_node(doc, kit, Fence("답칸", {"label": "DFS 탐색 순서", "lines": "1"}, ""), base_dir=tmp_path)
    표 = doc.tables.all[-1]
    assert 표.row_count == 2 and 표.column_count == 1
    assert 표.cell(0, 0).text.strip() == "DFS 탐색 순서"
    assert 표.cell(1, 0).text.strip() == ""

    out = tmp_path / "ans.hwpx"
    doc.save_to_path(out)
    마지막표 = zipfile.ZipFile(out).read("Contents/section0.xml").decode().rsplit("<hp:tbl", 1)[1]
    assert f'borderFillIDRef="{kit.border_fill["shade"]}"' in 마지막표
    assert f'borderFillIDRef="{kit.border_fill["answer"]}"' in 마지막표


def test_답칸_줄수만큼_빈칸이_늘어난다(문서):
    doc, kit, tmp_path = 문서
    render_node(doc, kit, Fence("답칸", {"label": "풀이", "lines": "4"}, ""), base_dir=tmp_path)
    assert doc.tables.all[-1].row_count == 5


def test_라벨_없는_답칸은_거부한다(문서):
    doc, kit, tmp_path = 문서
    with pytest.raises(ValueError, match="라벨 없는 답칸"):
        render_node(doc, kit, Fence("답칸", {"lines": "1"}, ""), base_dir=tmp_path)


def test_강조박스는_제목칸과_중첩표를_갖는다(문서):
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("강조박스", {"title": "[튜링 테스트]"}, "• 첫 줄\n• 둘째 줄"),
        base_dir=tmp_path,
    )
    out = tmp_path / "box.hwpx"
    doc.save_to_path(out)

    saved = HwpxDocument.open(out)
    assert saved.validate().ok
    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    # 제목칸은 바깥 표에, 본문은 중첩표에 들어간다. `rsplit("<hp:tbl", 1)[1]` 는 **안쪽** 표를
    # 집으므로 제목은 거기 없다(실측 확인) — 제목은 문서 전체에서 본다.
    assert "[튜링 테스트]" in xml
    마지막표 = xml.rsplit("<hp:tbl", 1)[1]
    assert "• 첫 줄" in 마지막표
    assert "• 둘째 줄" in 마지막표
    assert f'borderFillIDRef="{kit.border_fill["grid"]}"' in 마지막표


# --- 블록 선언표 — SPECS·fence_problems가 렌더 전에 거짓 통과를 잡는다 ---------------------


def test_선언표와_렌더러_이름이_일치한다():
    """SPECS·PLANNERS·STRUCTURAL 이 vocab.py 의 이름 집합과 어긋나면 깨진다."""
    assert set(PLANNERS) == FENCE_BLOCKS
    assert set(STRUCTURAL) == STRUCTURAL_BLOCKS
    assert set(SPECS) == set(PLANNERS)


def test_엔진이_모르는_이름은_렌더_시점에_그렇게_말한다(문서):
    """이 문구는 "엔진이 모르는 블록"이라고 말한다 — 실제로 보는 대상이 kit이 아니라
    PLANNERS이기 때문이다."""
    doc, kit, tmp_path = 문서
    with pytest.raises(ValueError, match="엔진이 모르는 블록: 없는블록"):
        render_node(doc, kit, Fence("없는블록", {}, ""), base_dir=tmp_path)


@pytest.mark.parametrize(
    "블록, 속성, 본문, 조각",
    [
        ("비교표", {"rows": "정의|종류"}, "", "비교표 블록에 cols= 가 없다"),
        ("답칸", {"lines": "abc"}, "", "답칸 블록의 lines= 는 정수여야 한다: 'abc'"),
        ("답칸", {"lines": "-1"}, "", "답칸 블록의 lines= 는 1 이상이어야 한다: -1"),
        ("답칸", {"lines": "0"}, "", "답칸 블록의 lines= 는 1 이상이어야 한다: 0"),
        ("라벨설명", {}, "", "라벨설명 블록에 본문이 없다"),
        ("답칸", {"lines": "1"}, "무시될 줄", "답칸 블록은 본문을 쓰지 않는다 — 1줄이 무시된다"),
        ("라벨설명", {}, ": 시작줄", "라벨 없는 설명: : 시작줄"),
    ],
)
def test_fence_problems가_거짓_통과_입력을_잡는다(블록, 속성, 본문, 조각):
    """지금은 이 입력 전부가 render_node를 통과해 조판에서만 늦게 터진다(RED)."""
    문제 = fence_problems(Fence(블록, 속성, 본문))
    assert 문제, f"{블록}/{속성}/{본문!r} 은 문제가 있어야 한다"
    assert 조각 in 문제[0]


def test_fence_problems는_정상_입력에_빈_리스트다():
    assert fence_problems(Fence("비교표", {"cols": "가|나", "rows": "다"}, "")) == []
    assert fence_problems(Fence("답칸", {"label": "가", "lines": "3"}, "")) == []
    assert fence_problems(Fence("라벨설명", {}, "[1] 가\n: 나")) == []


def test_fence_problems는_엔진이_모르는_이름에_빈_리스트다():
    """이름 자체가 문제라는 건 check_markdown/render_node 쪽 몫이다 — 여기서 중복 보고하지 않는다."""
    assert fence_problems(Fence("없는블록", {}, "아무거나")) == []


def test_render_node는_그리기_전에_fence_problems의_첫_문제로_거부한다(문서):
    doc, kit, tmp_path = 문서
    표_전 = len(doc.tables)
    with pytest.raises(ValueError, match="비교표 블록에 cols= 가 없다"):
        render_node(doc, kit, Fence("비교표", {"rows": "정의"}, ""), base_dir=tmp_path)
    assert len(doc.tables) == 표_전  # 그리기 전에 거부됐다 — 표가 안 생겼다


# --- "있지만 빈" 정수 속성. fence_problems 와 렌더러가 같은 규칙을 쓴다 -----------------------
# fence_problems 와 렌더러가 "없음"의 규칙을 따로 정하면: fence_problems 는 빈 값을
# "없음 → 기본값"으로 보고 건너뛰는데, 렌더러가 fence.attrs.get(name, 기본값)으로 읽으면
# present-but-blank 값을 그대로 int()에 넣어 영문 invalid literal for int() 로 죽을 수
# 있다 — lines=abc 와 같은 실패 유형이다.


def test_int_attr는_빈_값도_기본값으로_읽는다():
    assert _int_attr(Fence("답칸", {"lines": ""}, ""), "lines", 1) == 1
    assert _int_attr(Fence("답칸", {"lines": " "}, ""), "lines", 1) == 1
    assert _int_attr(Fence("답칸", {}, ""), "lines", 1) == 1
    assert _int_attr(Fence("답칸", {"lines": "4"}, ""), "lines", 1) == 4


_C1_필요_속성 = {"데이터표": {"head": "가|나"}, "답칸": {"label": "라벨"}}


@pytest.mark.parametrize(
    "블록, 속성, 값",
    [
        (블록, 속성, 값)
        for 블록, spec in SPECS.items()
        for 속성, _최솟값 in spec.ints
        for 값 in ["", " ", "abc", "-1", "0", "3"]
    ],
)
def test_int_속성은_fence_problems와_렌더러가_같은_판정을_낸다(문서, 블록, 속성, 값):
    """SPECS 의 모든 ints 속성 × 값 조합 — fence_problems([]) ⇔ 렌더러가 예외 없이 그린다.

    렌더러를 실제로 불러 이 성질을 확인한다(문구가 아니라 부작용으로): 문제가 있으면
    render_node 가 예외를 내야 하고, 없으면 표가 실제로 하나 더 생겨야 한다. docx 렌더러도
    같은 계획으로 같은 판정을 내야 한다(이 파일의 양방향 성질 테스트 전부가 두 형식을 본다).
    """
    doc, kit, tmp_path = 문서
    fence = Fence(블록, {**_C1_필요_속성.get(블록, {}), 속성: 값}, "")
    문제 = fence_problems(fence)
    hwpx_그림 = _hwpx로_그린다(doc, kit, fence, tmp_path)
    assert (문제 == []) == hwpx_그림 == _docx로_그린다(kit, fence, tmp_path)


# --- 라벨설명 labelWidth= — 길이 속성(`3cm`·`30mm`)을 SPECS.lengths 로 선언한다 --------------
# fence_problems 는 kit 없이도 꼴·0 이하는 보지만, 본문 폭 대비 상한은 kit이 있어야만 아는
# 값이라 kit을 줬을 때만 본다.


def test_length_attr는_빈_값도_None으로_읽고_있으면_HWPUNIT으로_바꾼다():
    """정수 속성의 `_int_attr`와 같은 설계 — 빈 값 = 없음(None) = 렌더러가 기본값을 쓴다."""
    assert _length_attr(Fence("라벨설명", {"labelWidth": ""}, ""), "labelWidth") is None
    assert _length_attr(Fence("라벨설명", {"labelWidth": " "}, ""), "labelWidth") is None
    assert _length_attr(Fence("라벨설명", {}, ""), "labelWidth") is None
    assert _length_attr(
        Fence("라벨설명", {"labelWidth": "1cm"}, ""), "labelWidth"
    ) == round(10 * 7200 / 25.4)
    assert _length_attr(
        Fence("라벨설명", {"labelWidth": "5mm"}, ""), "labelWidth"
    ) == round(5 * 7200 / 25.4)


@pytest.mark.parametrize(
    "값, 조각",
    [
        ("30", "라벨설명 블록의 labelWidth= 는 '3cm' 또는 '30mm' 꼴이어야 한다: '30'"),
        ("abc", "라벨설명 블록의 labelWidth= 는 '3cm' 또는 '30mm' 꼴이어야 한다: 'abc'"),
        ("3inch", "라벨설명 블록의 labelWidth= 는 '3cm' 또는 '30mm' 꼴이어야 한다: '3inch'"),
        ("0cm", "라벨설명 블록의 labelWidth= 는 0보다 커야 한다: '0cm'"),
    ],
)
def test_라벨설명_labelWidth_꼴과_범위가_틀리면_문구가_정확하다(값, 조각):
    문제 = fence_problems(Fence("라벨설명", {"labelWidth": 값}, "[1] 가\n: 나"))
    assert 문제 == [조각]


def test_라벨설명_labelWidth가_너무_넓으면_킷이_있을_때만_잡는다(문서):
    """상한(본문 폭 대비)은 킷이 있어야 아는 값이다 — kit 없이 부르면 이 문제를 못 본다."""
    _doc, kit, _tmp_path = 문서
    fence = Fence("라벨설명", {"labelWidth": "200cm"}, "[1] 가\n: 나")

    assert fence_problems(fence) == []
    assert fence_problems(fence, kit) == [
        "라벨설명 블록의 labelWidth= 가 너무 넓다: '200cm' — 설명 칸이 남지 않는다"
    ]


@pytest.mark.parametrize("값", ["", " ", "3cm", "30mm", "2.5cm"])
def test_라벨설명_labelWidth_정상값은_문제가_없다(값):
    assert fence_problems(Fence("라벨설명", {"labelWidth": 값}, "[1] 가\n: 나")) == []


@pytest.mark.parametrize(
    "값", ["", " ", "3cm", "30mm", "2.5cm", "30", "abc", "0cm", "-1cm", "200cm"]
)
def test_labelWidth는_fence_problems와_렌더러가_같은_판정을_낸다(문서, 값):
    """SPECS 의 lengths 속성 — fence_problems(fence, kit) == [] ⇔ 렌더러가 예외 없이 그린다."""
    doc, kit, tmp_path = 문서
    fence = Fence("라벨설명", {"labelWidth": 값}, "[1] 가\n: 나")
    문제 = fence_problems(fence, kit)
    hwpx_그림 = _hwpx로_그린다(doc, kit, fence, tmp_path)
    assert (문제 == []) == hwpx_그림 == _docx로_그린다(kit, fence, tmp_path)


def test_render_node는_kit을_fence_problems에_넘겨_너무_넓은_labelWidth를_거부한다(문서):
    doc, kit, tmp_path = 문서
    with pytest.raises(ValueError, match="너무 넓다"):
        render_node(
            doc, kit, Fence("라벨설명", {"labelWidth": "200cm"}, "[1] 가\n: 나"),
            base_dir=tmp_path,
        )


def test_라벨설명_labelWidth는_저장_XML의_칸_폭에_그대로_쓰인다(문서):
    """라벨 칸 cellSz@width == 환산값, 설명 칸 == bodyWidth - 환산값, 한 행의 두 칸 높이는 같다."""
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("라벨설명", {"labelWidth": "3cm"}, "[1] 가\n: 나\n[2] 다\n: 라"),
        base_dir=tmp_path,
    )
    out = tmp_path / "labelwidth.hwpx"
    doc.save_to_path(out)

    환산값 = round(30 * 7200 / 25.4)  # 3cm = 30mm
    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    표 = list(ET.fromstring(xml).iter(f"{{{HP}}}tbl"))[-1]
    행들 = 표.findall(f"{{{HP}}}tr")
    assert 행들, "라벨설명 표에 행이 있어야 한다"
    for tr in 행들:
        라벨칸, 설명칸 = tr.findall(f"{{{HP}}}tc")
        assert 라벨칸.find(f"{{{HP}}}cellSz").get("width") == str(환산값)
        assert 설명칸.find(f"{{{HP}}}cellSz").get("width") == str(kit.body_width - 환산값)
        assert (
            라벨칸.find(f"{{{HP}}}cellSz").get("height")
            == 설명칸.find(f"{{{HP}}}cellSz").get("height")
        )

    assert HwpxDocument.open(out).validate().ok


# --- 모르는 속성 — 블록이 모르는 속성을 쓰면 조용히 버리지 않고 거부한다 ------------------------
# 허용 속성 = required ∪ ints ∪ lengths ∪ optional(BlockSpec) — 이 합집합 하나로만 정한다.


def test_모르는_속성_문구는_쓸_수_있는_속성이_없으면_다르게_말한다():
    assert _모르는_속성_문구("블록", "속성", frozenset()) == (
        "블록 블록이 모르는 속성: 속성 — 이 블록은 속성을 받지 않는다"
    )
    assert _모르는_속성_문구("블록", "속성", frozenset({"b", "a"})) == (
        "블록 블록이 모르는 속성: 속성 — 쓸 수 있는 속성: a, b"
    )


@pytest.mark.parametrize(
    "블록, 속성, 본문, 조각",
    [
        ("답칸", {"label": "가", "labelWidth": "3cm"}, "",
         "답칸 블록이 모르는 속성: labelWidth — 쓸 수 있는 속성: label, lines"),
        ("라벨설명", {"lable": "3cm"}, "[1] 가\n: 나",
         "라벨설명 블록이 모르는 속성: lable — 쓸 수 있는 속성: labelWidth"),
        ("강조박스", {"titel": "x"}, "",
         "강조박스 블록이 모르는 속성: titel — 쓸 수 있는 속성: title"),
    ],
)
def test_모르는_속성은_쓸_수_있는_속성_목록과_함께_거부된다(블록, 속성, 본문, 조각):
    문제 = fence_problems(Fence(블록, 속성, 본문))
    assert 문제 == [조각]


# --- png_size 는 너무 짧은 헤더도 struct.error 가 아니라 ValueError ------------------------


def test_png_크기는_너무_짧은_조각도_ValueError로_거부한다():
    """시그니처+IHDR 표만 있고 가로세로 4+4바이트가 없는 16바이트 조각(struct.error 방지)."""
    조각 = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0d" + b"IHDR"  # 16바이트, 크기 정보 없음
    assert len(조각) < 24
    with pytest.raises(ValueError, match="PNG만 지원한다"):
        png_size(조각)


# --- 블록 셀의 문단·글자 서식·행 높이 -------------------------------------------------------
# 원인: python-hwpx 의 add_table 은 셀 문단을 paraPr 0 / charPr 0(10pt 보통 바탕체·양쪽
# 정렬)으로 만든다. `add_band`(머리띠)와 달리, 블록 7종·키워드면의 셀은 이 서식을 따로
# 입히지 않으면 그 기본값에 그대로 남는다 — 이 절이 각 블록에서 실제로 입혀지는지 고정한다.


def test_셀_헬퍼는_역할별_서식과_높이를_입힌다(문서):
    doc, kit, tmp_path = 문서
    표 = doc.add_table(1, 3, width=kit.body_width, border_fill_id_ref=kit.border_fill["plain"])
    _셀(표, 0, 0, "라벨", kit=kit, 역할="label")
    _셀(표, 0, 1, "본문", kit=kit, 역할="cell")
    _셀(표, 0, 2, "", kit=kit, 역할="answer")

    기대 = [
        ("label", kit.border_fill["shade"], kit.para_pr["label"], kit.char_pr["label"],
         kit.furniture["rowHeight"]["label"]),
        ("cell", kit.border_fill["plain"], kit.para_pr["cell"], kit.char_pr["cell"],
         kit.furniture["rowHeight"]["cell"]),
        ("answer", kit.border_fill["answer"], kit.para_pr["cell"], kit.char_pr["cell"],
         kit.furniture["rowHeight"]["answer"]),
    ]
    for 열, (역할, _보더, 파라, 캐릭, 높이) in enumerate(기대):
        assert 표.cell(0, 열).height == 높이, 역할
        문단들 = 표.cell(0, 열).paragraphs
        assert 문단들, 역할
        for 문단 in 문단들:
            assert 문단.para_pr_id_ref == str(파라), 역할
            assert 문단.char_pr_id_ref == str(캐릭), 역할
    assert 표.cell(0, 0).text.strip() == "라벨"
    assert 표.cell(0, 1).text.strip() == "본문"

    out = tmp_path / "cell.hwpx"
    doc.save_to_path(out)
    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    칸들 = xml[xml.index("<hp:tbl") : xml.index("</hp:tbl>")].split("<hp:tc ")[1:]
    assert len(칸들) == 3
    for 칸, (역할, 보더, *_나머지) in zip(칸들, 기대):
        assert f'borderFillIDRef="{보더}"' in 칸, 역할


def test_셀_헬퍼는_높이와_폭을_따로_받을_수_있다(문서):
    doc, kit, _tmp_path = 문서
    표 = doc.add_table(1, 1, width=kit.body_width, border_fill_id_ref=kit.border_fill["plain"])
    _셀(표, 0, 0, "라벨", kit=kit, 역할="label", 폭=1000, 높이=kit.furniture["rowHeight"]["cell"])
    assert 표.cell(0, 0).width == 1000
    assert 표.cell(0, 0).height == kit.furniture["rowHeight"]["cell"]  # label 기본이 아니라 준 값


def test_셀_헬퍼는_모르는_역할을_거부한다(문서):
    doc, kit, _tmp_path = 문서
    표 = doc.add_table(1, 1, width=kit.body_width, border_fill_id_ref=kit.border_fill["plain"])
    with pytest.raises(ValueError, match="모르는 셀 역할"):
        _셀(표, 0, 0, "", kit=kit, 역할="굴림")


# --- 블록 10종 + 키워드면의 실제 렌더 결과가 킷 서식·행 높이를 쓴다 -------------------------

_전체_블록_렌더: list[tuple[str, object]] = [
    ("정의빈칸", Body("정의 테스트")),
    ("용어카드", Fence("용어카드", {"cols": "가|나"}, "설명1\n설명2")),
    ("라벨설명", Fence("라벨설명", {}, "[1] 가\n: 나")),
    ("비교표", Fence("비교표", {"cols": "가|나", "rows": "다|라"}, "1|2\n3|4")),
    ("데이터표", Fence("데이터표", {"head": "가|나", "rows": "2"}, "1|2\n3|4")),
    ("답칸", Fence("답칸", {"label": "라벨", "lines": "2"}, "")),
    ("강조박스", Fence("강조박스", {"title": "제목"}, "본문")),
    ("나란히", Fence("나란히", {"cols": "가|나"}, "1|2\n3|4")),
]


@pytest.mark.parametrize("이름, 노드", _전체_블록_렌더, ids=[n for n, _ in _전체_블록_렌더])
def test_블록은_표_안의_모든_문단에_킷_값과_같은_서식을_입힌다(문서, 이름, 노드):
    """블록이 표 안 문단에 입히는 서식은 "킷이 정한 값의 집합에 속한다"로 본다 —
    "!= '0'"처럼 특정 값을 배제하는 형태로 쓰면, 킷이 어떤 역할에 실제로 0을 고를 때
    (킷 어휘엔 이미 charPr.body=0이 있다) 엔진이 맞아도 테스트가 깨진다: 킷 교체
    가능성(원칙 1)을 테스트가 막는 사례다. 블록 10종 중 표를 그리는 8종(정의빈칸·나란히 포함)
    공통 — 전부 label/cell 역할만 쓴다(answer 는 border만 다르고 타이포그래피는 cell과
    같다 — worksheet/blocks.py의 _셀_역할 표 참고). (발문은 표가 아니라 문단이라 여기서
    다루지 않는다 — 발문 자신의 서식은 test_발문_run은_킷의_prompt_charPr를_쓴다가 본다.)"""
    doc, kit, tmp_path = 문서
    render_node(doc, kit, 노드, base_dir=tmp_path)
    out = tmp_path / f"{이름}.hwpx"
    doc.save_to_path(out)

    허용_para = {str(kit.para_pr[k]) for k in ("label", "cell")}
    허용_char = {str(kit.char_pr[k]) for k in ("label", "cell")}

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    root = ET.fromstring(xml)
    for tbl in root.iter(f"{{{HP}}}tbl"):
        for p in tbl.iter(f"{{{HP}}}p"):
            조각 = ET.tostring(p, encoding="unicode")[:200]
            assert p.get("paraPrIDRef") in 허용_para, f"{이름}: {조각}"
            for run in p.findall(f"{{{HP}}}run"):
                t = run.find(f"{{{HP}}}t")
                if t is not None and (t.text or "").strip():
                    assert run.get("charPrIDRef") in 허용_char, (
                        f"{이름}: 글자 있는 run의 charPr={run.get('charPrIDRef')!r}가 "
                        f"킷 값 집합 밖이다"
                    )
    assert HwpxDocument.open(out).validate().ok


def test_정의빈칸_셀은_cell_역할이다(문서):
    doc, kit, tmp_path = 문서
    render_node(doc, kit, Body("정의 테스트"), base_dir=tmp_path)
    표 = doc.tables.all[-1]
    assert 표.cell(0, 0).height == kit.furniture["rowHeight"]["cell"]
    문단 = 표.cell(0, 0).paragraphs[0]
    assert 문단.para_pr_id_ref == str(kit.para_pr["cell"])
    assert 문단.char_pr_id_ref == str(kit.char_pr["cell"])


def test_라벨설명은_두_칸_모두_cell_행높이로_통일한다(문서):
    """열0(label 서식)도 rowHeight.cell 을 쓴다 — 라벨과 설명이 같은 행이라 높이가 갈리면
    안 된다."""
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("라벨설명", {}, "[1] 인간의 지능\n: 설명 A\n[2] 컴퓨터의 지능\n: 설명 B"),
        base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    for 행 in range(2):
        assert 표.cell(행, 0).height == kit.furniture["rowHeight"]["cell"]
        assert 표.cell(행, 1).height == kit.furniture["rowHeight"]["cell"]
        라벨_문단 = 표.cell(행, 0).paragraphs[0]
        설명_문단 = 표.cell(행, 1).paragraphs[0]
        assert 라벨_문단.para_pr_id_ref == str(kit.para_pr["label"])
        assert 라벨_문단.char_pr_id_ref == str(kit.char_pr["label"])
        assert 설명_문단.para_pr_id_ref == str(kit.para_pr["cell"])
        assert 설명_문단.char_pr_id_ref == str(kit.char_pr["cell"])


def test_용어카드는_라벨행_설명행_높이가_다르다(문서):
    """높이뿐 아니라 역할별로 킷 값과 같다는 타깃 단언도 같이 본다 — borderFill도 리터럴이
    아니라 킷에서 읽어 본다(paraPr·charPr·borderFill 셋 다)."""
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("용어카드", {"cols": "초기 상태|상태 공간|목표 상태"},
              "시작 상태\n모아 놓은 공간\n해결된 후 상태"),
        base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    for 열 in range(3):
        assert 표.cell(0, 열).height == kit.furniture["rowHeight"]["label"]
        assert 표.cell(1, 열).height == kit.furniture["rowHeight"]["cell"]
        assert 표.cell(0, 열).element.get("borderFillIDRef") == str(kit.border_fill["shade"])
        # cell 역할은 테두리를 따로 안 입힌다 — 표 기본값(plain) 그대로 남아야 한다.
        assert 표.cell(1, 열).element.get("borderFillIDRef") == str(kit.border_fill["plain"])
        라벨_문단 = 표.cell(0, 열).paragraphs[0]
        설명_문단 = 표.cell(1, 열).paragraphs[0]
        assert 라벨_문단.para_pr_id_ref == str(kit.para_pr["label"])
        assert 라벨_문단.char_pr_id_ref == str(kit.char_pr["label"])
        assert 설명_문단.para_pr_id_ref == str(kit.para_pr["cell"])
        assert 설명_문단.char_pr_id_ref == str(kit.char_pr["cell"])


def test_비교표는_머리행_머리열이_label_나머지가_cell_역할이다(문서):
    """머리 칸(label 역할)의 문단/글자 서식과 borderFill까지 타깃 단언으로 본다. "한 행 =
    한 높이"가 일반 규칙이라 데이터 행의 열0(머리열, label 서식)도 그 행의 높이(cell)를
    쓴다(라벨설명과 같은 처리) — 그러지 않으면 한 행 안에서 라벨 칸과 본문 칸의 높이가
    2048/2131처럼 서로 달라진다."""
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("비교표", {"cols": "맹목적 탐색|휴리스틱 탐색", "rows": "정의|탐색 방법|종류"}, ""),
        base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    assert 표.cell(0, 0).height == kit.furniture["rowHeight"]["label"]
    assert 표.cell(0, 1).height == kit.furniture["rowHeight"]["label"]
    assert 표.cell(1, 0).height == kit.furniture["rowHeight"]["cell"]   # 머리열도 그 행의 높이
    assert 표.cell(1, 1).height == kit.furniture["rowHeight"]["cell"]   # 본문 칸
    머리_문단 = 표.cell(0, 0).paragraphs[0]
    머리열_문단 = 표.cell(0, 1).paragraphs[0]
    행머리_문단 = 표.cell(1, 0).paragraphs[0]
    본문_문단 = 표.cell(1, 1).paragraphs[0]
    for 행, 열 in ((0, 0), (0, 1), (1, 0)):
        assert 표.cell(행, 열).element.get("borderFillIDRef") == str(kit.border_fill["shade"])
    # cell 역할(본문 칸)은 테두리를 따로 안 입힌다 — 표 기본값(plain) 그대로 남아야 한다.
    assert 표.cell(1, 1).element.get("borderFillIDRef") == str(kit.border_fill["plain"])
    for 문단 in (머리_문단, 머리열_문단, 행머리_문단):
        assert 문단.para_pr_id_ref == str(kit.para_pr["label"])
        assert 문단.char_pr_id_ref == str(kit.char_pr["label"])
    assert 본문_문단.para_pr_id_ref == str(kit.para_pr["cell"])
    assert 본문_문단.char_pr_id_ref == str(kit.char_pr["cell"])


def test_비교표_본문이_있으면_행렬_순서로_채운다(문서):
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence(
            "비교표", {"cols": "맹목적 탐색|휴리스틱 탐색", "rows": "정의|종류"},
            "정보 없이 탐색|정보를 이용해 탐색\nDFS, BFS|언덕 등반, A*",
        ),
        base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    assert 표.cell(1, 1).text.strip() == "정보 없이 탐색"
    assert 표.cell(1, 2).text.strip() == "정보를 이용해 탐색"
    assert 표.cell(2, 1).text.strip() == "DFS, BFS"
    assert 표.cell(2, 2).text.strip() == "언덕 등반, A*"


def test_데이터표는_머리행만_label_나머지가_cell_역할이다(문서):
    """높이뿐 아니라 역할별 킷 값 타깃 단언, borderFill도 같이 본다."""
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("데이터표", {"head": "단계|g(n)|h(n)|f(n)", "rows": "3"}, ""),
        base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    assert 표.cell(0, 0).height == kit.furniture["rowHeight"]["label"]
    assert 표.cell(1, 0).height == kit.furniture["rowHeight"]["cell"]
    assert 표.cell(3, 3).height == kit.furniture["rowHeight"]["cell"]
    assert 표.cell(0, 0).element.get("borderFillIDRef") == str(kit.border_fill["shade"])
    # cell 역할(데이터 칸)은 테두리를 따로 안 입힌다 — 표 기본값(plain) 그대로 남아야 한다.
    assert 표.cell(1, 0).element.get("borderFillIDRef") == str(kit.border_fill["plain"])
    assert 표.cell(3, 3).element.get("borderFillIDRef") == str(kit.border_fill["plain"])
    머리_문단 = 표.cell(0, 0).paragraphs[0]
    데이터_문단 = 표.cell(1, 0).paragraphs[0]
    assert 머리_문단.para_pr_id_ref == str(kit.para_pr["label"])
    assert 머리_문단.char_pr_id_ref == str(kit.char_pr["label"])
    assert 데이터_문단.para_pr_id_ref == str(kit.para_pr["cell"])
    assert 데이터_문단.char_pr_id_ref == str(kit.char_pr["cell"])


def test_답칸은_라벨행_label_나머지가_answer_역할이다(문서):
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit, Fence("답칸", {"label": "DFS 탐색 순서", "lines": "2"}, ""), base_dir=tmp_path
    )
    표 = doc.tables.all[-1]
    assert 표.cell(0, 0).height == kit.furniture["rowHeight"]["label"]
    assert 표.cell(1, 0).height == kit.furniture["rowHeight"]["answer"]
    assert 표.cell(2, 0).height == kit.furniture["rowHeight"]["answer"]
    답_문단 = 표.cell(1, 0).paragraphs[0]
    assert 답_문단.para_pr_id_ref == str(kit.para_pr["cell"])   # answer 도 문단/글자 서식은 cell 역할과 같다
    assert 답_문단.char_pr_id_ref == str(kit.char_pr["cell"])


def test_강조박스는_제목칸_label_안쪽칸_cell_역할이고_중첩칸_테두리는_grid_그대로다(문서):
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit,
        Fence("강조박스", {"title": "[튜링 테스트]"}, "• 첫 줄\n• 둘째 줄"),
        base_dir=tmp_path,
    )
    바깥 = doc.tables.all[-1]
    담는칸 = 바깥.cell(1, 0)
    안쪽 = 담는칸.tables[0]  # doc.tables.all 은 최상위 표만 — 중첩표는 셀을 통해 찾는다

    assert 바깥.cell(0, 0).height == kit.furniture["rowHeight"]["label"]
    제목_문단 = 바깥.cell(0, 0).paragraphs[0]
    assert 제목_문단.para_pr_id_ref == str(kit.para_pr["label"])
    assert 제목_문단.char_pr_id_ref == str(kit.char_pr["label"])

    # 담는 칸엔 문단이 정확히 1개(중첩표를 담은 그 문단)여야 한다 — 그러지 않으면 _셀 이
    # 만든 빈 선행 문단이 남아 실한컴에서 제목칸과 상자 사이에 빈 줄로 보인다.
    assert len(담는칸.paragraphs) == 1
    담는칸_문단 = 담는칸.paragraphs[0]
    assert len(담는칸_문단.tables) == 1
    assert 담는칸_문단.para_pr_id_ref == str(kit.para_pr["cell"])

    안쪽_문단 = 안쪽.cell(0, 0).paragraphs[0]
    assert 안쪽_문단.para_pr_id_ref == str(kit.para_pr["cell"])
    assert 안쪽_문단.char_pr_id_ref == str(kit.char_pr["cell"])

    out = tmp_path / "box2.hwpx"
    doc.save_to_path(out)
    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    안쪽표 = xml.rsplit("<hp:tbl", 1)[1]
    assert f'borderFillIDRef="{kit.border_fill["grid"]}"' in 안쪽표
    assert HwpxDocument.open(out).validate().ok


def test_강조박스는_담는_칸_높이가_안쪽_표_높이와_같고_바깥_표_sz도_맞는다(문서):
    """담는 칸(행1)에 높이를 안 주면 표 sz@height 가 rows*라이브러리 기본값(7200)에 남아
    실제 행 높이 합(2048+3600=5648)과 달라진다. 담는 칸 높이를 안쪽 표 높이(rowHeight.cell)
    로 맞추고, 바깥 표 자체도 그 합을 height= 로 받아 다른 블록과 같은 "표 sz == 행 높이
    합" 규칙을 따른다."""
    doc, kit, tmp_path = 문서
    render_node(doc, kit, Fence("강조박스", {"title": "제목"}, "본문"), base_dir=tmp_path)
    바깥 = doc.tables.all[-1]

    assert 바깥.cell(1, 0).height == kit.furniture["rowHeight"]["cell"]
    안쪽 = 바깥.cell(1, 0).tables[0]
    assert 안쪽.cell(0, 0).height == kit.furniture["rowHeight"]["cell"]

    총높이 = kit.furniture["rowHeight"]["label"] + kit.furniture["rowHeight"]["cell"]
    assert 바깥.element.find(f"{{{HP}}}sz").get("height") == str(총높이)
    assert 안쪽.element.find(f"{{{HP}}}sz").get("height") == str(kit.furniture["rowHeight"]["cell"])


# --- "한 행 = 한 높이"가 일반 규칙이다(머리 행은 label, 데이터 행은 그 행의
# 본문 역할) — 저장 XML 에서 모든 블록의 모든 행 안 cellSz@height 가 전부 같은지 본다.


@pytest.mark.parametrize("이름, 노드", _전체_블록_렌더, ids=[n for n, _ in _전체_블록_렌더])
def test_모든_블록은_한_행_안에서_셀_높이가_같다(문서, 이름, 노드):
    doc, kit, tmp_path = 문서
    render_node(doc, kit, 노드, base_dir=tmp_path)
    out = tmp_path / f"{이름}-rowheight.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    root = ET.fromstring(xml)
    for tbl in root.iter(f"{{{HP}}}tbl"):
        for tr in tbl.findall(f"{{{HP}}}tr"):
            높이들 = {
                tc.find(f"{{{HP}}}cellSz").get("height") for tc in tr.findall(f"{{{HP}}}tc")
            }
            assert len(높이들) == 1, f"{이름}: 한 행 안에서 높이가 갈린다: {높이들}"


# --- 비교표 본문이 표보다 크면 fence_problems 가 렌더 전에 잡는다 ---------------------------


@pytest.mark.parametrize(
    "블록, 속성, 본문",
    [
        ("비교표", {"cols": "가|나", "rows": "다"}, ""),
        ("비교표", {"cols": "가|나", "rows": "다"}, "1|2"),
        ("비교표", {"cols": "가|나", "rows": "다"}, "1|2\n3|4"),      # 초과: 2줄 > rows 1
        ("비교표", {"cols": "가|나", "rows": "다|라"}, "1|2|3"),      # 초과: 3칸 > cols 2칸
        ("데이터표", {"head": "가|나", "rows": "2"}, "1|2\n3|4"),
        ("데이터표", {"head": "가|나", "rows": "1"}, "1|2\n3|4"),    # 초과: 2줄 > rows 1
        ("데이터표", {"head": "가|나"}, "1|2|3"),                     # 초과: 3칸 > head 2칸(rows 생략)
        ("데이터표", {"head": "가|나"}, "1|2\n3|4"),                 # 정상: rows 생략, 안 넘침
    ],
)
def test_비교표_데이터표_본문_크기는_fence_problems와_렌더러가_같은_판정을_낸다(
    문서, 블록, 속성, 본문
):
    """SPECS 의 int 속성과 같은 both-directions 성질 — fence_problems([]) ⇔ 렌더러가 그린다."""
    doc, kit, tmp_path = 문서
    fence = Fence(블록, 속성, 본문)
    문제 = fence_problems(fence)
    hwpx_그림 = _hwpx로_그린다(doc, kit, fence, tmp_path)
    assert (문제 == []) == hwpx_그림 == _docx로_그린다(kit, fence, tmp_path)


@pytest.mark.parametrize(
    "블록, 속성, 본문, 조각",
    [
        ("비교표", {"cols": "가|나", "rows": "다"}, "1|2\n3|4",
         "비교표 본문이 표보다 크다: 2줄 > rows 1"),
        ("비교표", {"cols": "가|나", "rows": "다|라"}, "1|2|3",
         "비교표 본문 1번째 줄이 표보다 넓다: 3칸 > cols 2칸"),
        ("데이터표", {"head": "가|나", "rows": "1"}, "1|2\n3|4",
         "데이터표 본문이 표보다 크다: 2줄 > rows 1"),
        ("데이터표", {"head": "가|나"}, "1|2|3",
         # 데이터표에는 cols= 속성이 없다(열은 head=로 준다) — 문구도 head를 말해야 한다.
         "데이터표 본문 1번째 줄이 표보다 넓다: 3칸 > head 2칸"),
    ],
)
def test_비교표_데이터표_본문_초과_문구가_정확하다(블록, 속성, 본문, 조각):
    문제 = fence_problems(Fence(블록, 속성, 본문))
    assert any(조각 in p for p in 문제), 문제


def test_비교표는_필수_속성_없어도_본문_검사가_중복_보고하지_않는다():
    """cols 가 없을 때(필수 속성 검사가 이미 잡는 자리) 본문 크기 검사가 겹쳐 보고하지 않는다."""
    문제 = fence_problems(Fence("비교표", {"rows": "가"}, "1|2\n3|4"))
    assert 문제 == ["비교표 블록에 cols= 가 없다"]


@pytest.mark.parametrize("값", ["0", "-1"])
def test_데이터표_rows가_범위_밖이면_본문_검사가_중복_보고하지_않는다(값):
    """rows=0/-1 이면 범위 검사가 이미 "1 이상이어야 한다"로 잡는다 — 본문 크기 검사까지
    더하면 교사가 손댈 수 없는 문구("> rows -1")가 같이 나온다. 필수 누락·형 오류와 같은
    설계(범위 검사가 이미 잡으면 본문 크기 검사는 건너뛴다)를 "1 미만"에도 적용한다."""
    문제 = fence_problems(Fence("데이터표", {"head": "가|나", "rows": 값}, "1|2\n3|4"))
    assert 문제 == [f"데이터표 블록의 rows= 는 1 이상이어야 한다: {값}"]


# --- 나란히 — 2~4단을 나란히 놓고 각 단에 머리·그림·답줄을 쌓는 구성("예제 1 | 예제 2") ---


def test_나란히는_머리행_label_본문행_cell_역할이다(문서):
    doc, kit, tmp_path = 문서
    render_node(
        doc, kit, Fence("나란히", {"cols": "예제 1|예제 2"}, "DFS :|BFS :"), base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    assert 표.row_count == 2 and 표.column_count == 2
    assert 표.cell(0, 0).text.strip() == "예제 1"
    assert 표.cell(0, 1).text.strip() == "예제 2"
    assert 표.cell(1, 0).text.strip() == "DFS :"
    assert 표.cell(1, 1).text.strip() == "BFS :"
    assert 표.cell(0, 0).element.get("borderFillIDRef") == str(kit.border_fill["shade"])
    # cell 역할은 테두리를 따로 안 입힌다 — 표 기본값(plain) 그대로 남아야 한다.
    assert 표.cell(1, 0).element.get("borderFillIDRef") == str(kit.border_fill["plain"])
    머리_문단 = 표.cell(0, 0).paragraphs[0]
    본문_문단 = 표.cell(1, 0).paragraphs[0]
    assert 머리_문단.para_pr_id_ref == str(kit.para_pr["label"])
    assert 머리_문단.char_pr_id_ref == str(kit.char_pr["label"])
    assert 본문_문단.para_pr_id_ref == str(kit.para_pr["cell"])
    assert 본문_문단.char_pr_id_ref == str(kit.char_pr["cell"])

    out = tmp_path / "narrahi.hwpx"
    doc.save_to_path(out)
    assert HwpxDocument.open(out).validate().ok


def test_나란히_행_높이는_머리는_label_본문은_cell이다(문서):
    doc, kit, tmp_path = 문서
    render_node(doc, kit, Fence("나란히", {"cols": "가|나"}, "1|2\n3|4"), base_dir=tmp_path)
    표 = doc.tables.all[-1]
    assert 표.cell(0, 0).height == kit.furniture["rowHeight"]["label"]
    assert 표.cell(1, 0).height == kit.furniture["rowHeight"]["cell"]
    assert 표.cell(2, 0).height == kit.furniture["rowHeight"]["cell"]


def test_나란히_cols_없으면_거부한다():
    assert fence_problems(Fence("나란히", {}, "")) == ["나란히 블록에 cols= 가 없다"]


def test_나란히_cols가_1칸이면_한_단짜리_대안을_알려주며_거부한다():
    """한 단짜리는 나란히로 쓸 뜻이 없다 — 정의빈칸·답칸으로 쓴다. cols= 가 1칸이면 그
    대안을 문구가 말한다."""
    문제 = fence_problems(Fence("나란히", {"cols": "예제 1"}, "아무거나"))
    assert 문제 == ["나란히 블록의 cols= 는 2칸 이상이어야 한다: 1칸"]


def test_나란히_cols_1칸이면_render_node가_그리기_전에_거부한다(문서):
    doc, kit, tmp_path = 문서
    표_전 = len(doc.tables)
    with pytest.raises(ValueError, match="나란히 블록의 cols= 는 2칸 이상이어야 한다: 1칸"):
        render_node(doc, kit, Fence("나란히", {"cols": "혼자"}, ""), base_dir=tmp_path)
    assert len(doc.tables) == 표_전  # 그리기 전에 거부됐다 — 표가 안 생겼다


def test_나란히_rows로_빈_본문행을_만든다(문서):
    doc, kit, tmp_path = 문서
    render_node(doc, kit, Fence("나란히", {"cols": "가|나", "rows": "3"}, ""), base_dir=tmp_path)
    표 = doc.tables.all[-1]
    assert 표.row_count == 4  # 머리행 1 + 본문행 3
    assert all(표.cell(r, c).text.strip() == "" for r in range(1, 4) for c in range(2))


@pytest.mark.parametrize(
    "속성, 본문",
    [
        ({"cols": "가|나", "rows": "1"}, ""),
        ({"cols": "가|나", "rows": "1"}, "1|2"),
        ({"cols": "가|나", "rows": "1"}, "1|2\n3|4"),   # 초과: 2줄 > rows 1
        ({"cols": "가|나", "rows": "2"}, "1|2|3"),       # 초과: 3칸 > cols 2칸
        ({"cols": "가|나|다"}, "1|2|3\n4|5|6"),          # 정상: rows 생략, 안 넘침
    ],
)
def test_나란히_본문_크기는_fence_problems와_렌더러가_같은_판정을_낸다(문서, 속성, 본문):
    """SPECS 의 body_shape 와 같은 both-directions 성질 — fence_problems([]) ⇔ 렌더러가 그린다."""
    doc, kit, tmp_path = 문서
    fence = Fence("나란히", 속성, 본문)
    문제 = fence_problems(fence)
    hwpx_그림 = _hwpx로_그린다(doc, kit, fence, tmp_path)
    assert (문제 == []) == hwpx_그림 == _docx로_그린다(kit, fence, tmp_path)


@pytest.mark.parametrize(
    "속성, 본문, 조각",
    [
        ({"cols": "가|나", "rows": "1"}, "1|2\n3|4", "나란히 본문이 표보다 크다: 2줄 > rows 1"),
        ({"cols": "가|나", "rows": "2"}, "1|2|3", "나란히 본문 1번째 줄이 표보다 넓다: 3칸 > cols 2칸"),
    ],
)
def test_나란히_본문_초과_문구가_정확하다(속성, 본문, 조각):
    문제 = fence_problems(Fence("나란히", 속성, 본문))
    assert any(조각 in p for p in 문제), 문제


def test_나란히는_저장_XML에서_열_폭이_균등하다(문서):
    doc, kit, tmp_path = 문서
    render_node(doc, kit, Fence("나란히", {"cols": "가|나|다"}, "1|2|3"), base_dir=tmp_path)
    out = tmp_path / "narrahi_width.hwpx"
    doc.save_to_path(out)
    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    표 = list(ET.fromstring(xml).iter(f"{{{HP}}}tbl"))[-1]
    행들 = 표.findall(f"{{{HP}}}tr")
    for tr in 행들:
        폭들 = {tc.find(f"{{{HP}}}cellSz").get("width") for tc in tr.findall(f"{{{HP}}}tc")}
        assert len(폭들) == 1, f"열 폭이 갈린다: {폭들}"
    assert HwpxDocument.open(out).validate().ok


# --- 칸 안에 그림 — 나란히·비교표·데이터표·용어카드·라벨설명(설명 칸) 다섯 블록 -----------------
# 각 블록의 "본문 칸" 자리에 그림 줄 하나를 심는 펜스를 만드는 공장 함수 — 그림 지원 여부와
# 무관한 나머지 칸(둘째 칸 등)은 보통 글자로 채워 그 블록이 정상적으로 그려지는 형태를 유지한다.


def _나란히_그림칸_펜스(칸_글자: str) -> Fence:
    return Fence("나란히", {"cols": "예제 1|예제 2"}, f"{칸_글자}|둘째 칸")


def _비교표_그림칸_펜스(칸_글자: str) -> Fence:
    return Fence("비교표", {"cols": "가|나", "rows": "정의"}, f"{칸_글자}|둘째 칸")


def _데이터표_그림칸_펜스(칸_글자: str) -> Fence:
    return Fence("데이터표", {"head": "가|나", "rows": "1"}, f"{칸_글자}|둘째 칸")


def _용어카드_그림칸_펜스(칸_글자: str) -> Fence:
    return Fence("용어카드", {"cols": "가|나"}, f"{칸_글자}\n둘째 칸")


def _라벨설명_그림칸_펜스(칸_글자: str) -> Fence:
    return Fence("라벨설명", {}, f"[1] 라벨\n: {칸_글자}")


_그림_지원_블록 = {
    "나란히": _나란히_그림칸_펜스,
    "비교표": _비교표_그림칸_펜스,
    "데이터표": _데이터표_그림칸_펜스,
    "용어카드": _용어카드_그림칸_펜스,
    "라벨설명": _라벨설명_그림칸_펜스,
}


@pytest.mark.parametrize("블록", sorted(_그림_지원_블록))
def test_칸_안_그림은_실제로_hp_pic으로_들어간다(문서, 블록):
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    fence = _그림_지원_블록[블록]("![](그림.png){width=3cm}")
    render_node(doc, kit, fence, base_dir=tmp_path)
    out = tmp_path / f"{블록}-그림.hwpx"
    doc.save_to_path(out)

    saved = HwpxDocument.open(out)
    assert saved.validate().ok
    assert len(saved.media.images) == 1
    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    assert "<hp:pic" in xml


def test_칸_안_그림_문단은_center_역할이고_같은_행의_글자_칸은_cell_역할이다(문서):
    """학습지 양식에서 그림을 담은 칸은 대개 가운데 정렬이다. 그림 칸은 킷의 center
    역할을, 같은 행의 글자 칸은 그대로 cell 역할을 쓴다 — 값은 항상 킷에서 읽는다
    (리터럴 ID를 직접 비교하지 않는다, 킷을 바꿔도 이 성질이 성립해야 한다)."""
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    render_node(
        doc, kit, _나란히_그림칸_펜스("![](그림.png){width=3cm}"), base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    그림_문단 = 표.cell(1, 0).paragraphs[0]
    글자_문단 = 표.cell(1, 1).paragraphs[0]
    assert 그림_문단.para_pr_id_ref == str(kit.para_pr["center"])
    assert 글자_문단.para_pr_id_ref == str(kit.para_pr["cell"])


@pytest.mark.parametrize("블록", sorted(_그림_지원_블록))
def test_칸_안_그림_문단은_블록마다_center_역할이다(문서, 블록):
    """위 단일 사례(나란히)를 그림을 받는 다섯 블록 전부로 넓힌다 — _셀 하나가 그림 배치를
    도맡으므로 한 곳만 고치면 다섯 블록이 같이 고쳐진다는 것을 직접 확인한다."""
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    fence = _그림_지원_블록[블록]("![](그림.png){width=3cm}")
    render_node(doc, kit, fence, base_dir=tmp_path)
    표 = doc.tables.all[-1]
    그림_칸_찾음 = False
    for tr행 in range(표.row_count):
        for tr열 in range(표.column_count):
            문단 = 표.cell(tr행, tr열).paragraphs[0]
            if 문단.tables:
                continue  # 강조박스처럼 중첩표를 담는 칸 — 그림 칸이 아니다
            런들 = 문단.runs
            if any(런.element.find(f"{{{HP}}}pic") is not None for 런 in 런들):
                assert 문단.para_pr_id_ref == str(kit.para_pr["center"]), f"{블록}[{tr행},{tr열}]"
                그림_칸_찾음 = True
    assert 그림_칸_찾음, f"{블록}: 그림 칸을 찾지 못했다"


def test_칸_안_그림은_비율을_유지한다(문서):
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))  # 가로:세로 = 2.5:1
    render_node(
        doc, kit, _나란히_그림칸_펜스("![](그림.png){width=4cm}"), base_dir=tmp_path,
    )
    out = tmp_path / "비율.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    pic = next(ET.fromstring(xml).iter(f"{{{HP}}}pic"))
    sz = pic.find(f"{{{HP}}}sz")
    폭, 높이 = int(sz.get("width")), int(sz.get("height"))
    assert 폭 == round(40 * _MM_HWPUNIT)  # 4cm = 40mm, 칸(25230-1020=24210)보다 좁아 안 줄었다
    assert 높이 == round(폭 * 120 / 300)


def test_라벨설명_그림_폭은_labelWidth_기본값에서_계산한_설명_열_폭이다(문서):
    """라벨설명은 그림 폭을 계산할 열 폭이 유일하게 bodyWidth를 그대로
    안 쓰고 `bodyWidth - labelWidth`(오른쪽 설명 칸 폭)에서 나온다. 이 값을 `bodyWidth //
    2`처럼 다른 블록과 같은 식으로 되돌려도 지금까지는 잡는 테스트가 없었다 — 여기서
    킷 값으로 다시 계산해 실제 그림 폭과 맞춘다(리터럴 상수 없음, 킷을 바꿔도 성립해야
    하는 성질이라서다). 실측(표준 킷): 45399."""
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    render_node(doc, kit, _라벨설명_그림칸_펜스("![](그림.png)"), base_dir=tmp_path)
    out = tmp_path / "labelwidth_기본_그림.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    pic = next(ET.fromstring(xml).iter(f"{{{HP}}}pic"))
    폭 = int(pic.find(f"{{{HP}}}sz").get("width"))
    설명폭 = kit.body_width - kit.furniture["labelWidth"]
    assert 폭 == 설명폭 - _칸_여백_좌우


def test_라벨설명_그림_폭은_labelWidth_명시값에서도_계산한_설명_열_폭이다(문서):
    """위 테스트의 형제 — `labelWidth=`를 회차가 명시하면(라벨설명만 회차마다 열 폭이
    달라진다) 그림 폭 계산도 그 값을 따라가야 한다. 실측(표준 킷,
    labelWidth=3cm): 40936."""
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    render_node(
        doc, kit,
        Fence("라벨설명", {"labelWidth": "3cm"}, "[1] 라벨\n: ![](그림.png)"),
        base_dir=tmp_path,
    )
    out = tmp_path / "labelwidth_명시_그림.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    pic = next(ET.fromstring(xml).iter(f"{{{HP}}}pic"))
    폭 = int(pic.find(f"{{{HP}}}sz").get("width"))
    라벨폭 = round(30 * _MM_HWPUNIT)  # labelWidth=3cm = 30mm — _length_attr와 같은 환산
    설명폭 = kit.body_width - 라벨폭
    assert 폭 == 설명폭 - _칸_여백_좌우


def test_칸_안_그림_폭_생략시_칸_폭에_맞춘다(문서):
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    render_node(doc, kit, _나란히_그림칸_펜스("![](그림.png)"), base_dir=tmp_path)
    out = tmp_path / "생략폭.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    pic = next(ET.fromstring(xml).iter(f"{{{HP}}}pic"))
    폭 = int(pic.find(f"{{{HP}}}sz").get("width"))
    기본_열폭 = kit.body_width // 2  # 나란히 cols="예제 1|예제 2" — 2열
    assert 폭 == 기본_열폭 - _칸_여백_좌우


def test_칸_안_그림_폭이_칸보다_넓으면_칸_폭으로_줄인다(문서):
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    render_node(
        doc, kit, _나란히_그림칸_펜스("![](그림.png){width=15cm}"), base_dir=tmp_path,
    )
    out = tmp_path / "초과폭.hwpx"
    doc.save_to_path(out)

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    pic = next(ET.fromstring(xml).iter(f"{{{HP}}}pic"))
    폭 = int(pic.find(f"{{{HP}}}sz").get("width"))
    기본_열폭 = kit.body_width // 2
    assert 폭 == 기본_열폭 - _칸_여백_좌우  # 15cm 그대로가 아니라 칸 폭으로 줄었다(잘리지 않는다)


def test_그림이_든_행의_높이는_그림_높이와_상하_여백의_합이다(문서):
    """계산값을 주는 쪽과 기본 rowHeight.cell을 그대로 두는 쪽을 실측해 골랐다 — 표준 킷의
    rowHeight.cell(2131)은 이 그림의 계산 높이보다 작아, 그대로 두면 그림이 칸보다 커서
    잘린다(모듈 docstring 없이 여기 테스트로 그 근거를 고정한다)."""
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    render_node(
        doc, kit, _나란히_그림칸_펜스("![](그림.png){width=4cm}"), base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    폭 = round(40 * _MM_HWPUNIT)
    그림_높이 = round(폭 * 120 / 300)
    기대_행높이 = 그림_높이 + _칸_여백_상하
    assert 표.cell(1, 0).height == 기대_행높이
    assert 표.cell(1, 1).height == 기대_행높이  # 같은 행의 둘째 칸(글자만)도 같은 높이다
    assert 기대_행높이 != kit.furniture["rowHeight"]["cell"]  # 기본값 그대로가 아니라 계산값이다
    assert 그림_높이 > kit.furniture["rowHeight"]["cell"]  # 이 그림은 기본값보다 크다(잘림 확인용)


def test_작은_그림이_든_행도_킷_행높이보다_낮아지지_않는다(문서):
    """그림이 기본 rowHeight.cell보다 작으면(예: 폭 1cm) 행 전체가 그
    작은 계산값으로 내려가, 같은 행의 글자 칸까지 킷 행높이 아래로 끌려 내려간다(실측:
    300×120px 그림 폭 1cm → 계산 높이 1416 < rowHeight.cell 2131). 킷의
    rowHeight는 바닥값이어야 한다 — 그림은 그 바닥을 넘어 키울 뿐, 낮추지 않는다."""
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    render_node(
        doc, kit, _나란히_그림칸_펜스("![](그림.png){width=1cm}"), base_dir=tmp_path,
    )
    표 = doc.tables.all[-1]
    폭 = round(10 * _MM_HWPUNIT)
    그림_높이 = round(폭 * 120 / 300)
    계산값 = 그림_높이 + _칸_여백_상하
    assert 계산값 < kit.furniture["rowHeight"]["cell"], "이 그림이 실제로 기본값보다 작아야 사고가 재현된다"
    assert 표.cell(1, 0).height == kit.furniture["rowHeight"]["cell"]  # 그림 칸도 바닥 아래로 안 내려간다
    assert 표.cell(1, 1).height == kit.furniture["rowHeight"]["cell"]  # 글자 칸이 특히 중요하다(사고의 핵심)


# 그림 후보 칸이 **둘** 있는 펜스를 만드는 전용 공장 — 위 _그림_지원_블록(칸 하나)과 달리
# 라벨설명은 칸 후보가 펜스당 하나뿐이라([N] 라벨/: 설명 쌍의 설명 칸 하나) "둘째 칸"을 같은
# 펜스 안에 문자열 치환으로 끼워 넣을 자리가 없다 — 그래서 두 쌍(행 2개)을 직접 쓴다. 다른
# 네 블록도 같은 이유로 "칸 하나짜리 펜스에 나중에 둘째 칸을 끼운다"가 아니라 처음부터
# 두 칸 모두를 같은 그림 줄로 채운 펜스를 만든다 — 어느 쪽이든 "같은 파일이 두 칸에 쓰인
# 펜스 하나"를 낸다는 결과는 같다.


def _나란히_그림_두칸_펜스(칸_글자: str) -> Fence:
    return Fence("나란히", {"cols": "예제 1|예제 2"}, f"{칸_글자}|{칸_글자}")


def _비교표_그림_두칸_펜스(칸_글자: str) -> Fence:
    return Fence("비교표", {"cols": "가|나", "rows": "정의"}, f"{칸_글자}|{칸_글자}")


def _데이터표_그림_두칸_펜스(칸_글자: str) -> Fence:
    return Fence("데이터표", {"head": "가|나", "rows": "1"}, f"{칸_글자}|{칸_글자}")


def _용어카드_그림_두칸_펜스(칸_글자: str) -> Fence:
    return Fence("용어카드", {"cols": "가|나"}, f"{칸_글자}\n{칸_글자}")


def _라벨설명_그림_두칸_펜스(칸_글자: str) -> Fence:
    return Fence("라벨설명", {}, f"[1] 라벨하나\n: {칸_글자}\n[2] 라벨둘\n: {칸_글자}")


_그림_두칸_지원_블록 = {
    "나란히": _나란히_그림_두칸_펜스,
    "비교표": _비교표_그림_두칸_펜스,
    "데이터표": _데이터표_그림_두칸_펜스,
    "용어카드": _용어카드_그림_두칸_펜스,
    "라벨설명": _라벨설명_그림_두칸_펜스,
}


@pytest.mark.parametrize("블록", sorted(_그림_두칸_지원_블록))
def test_같은_그림_파일을_두_칸에_쓰면_BinData가_하나다(문서, 블록):
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    fence = _그림_두칸_지원_블록[블록]("![](그림.png)")
    render_node(doc, kit, fence, base_dir=tmp_path)
    out = tmp_path / f"{블록}-dedupe.hwpx"
    doc.save_to_path(out)

    saved = HwpxDocument.open(out)
    assert saved.validate().ok
    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode()
    assert xml.count("<hp:pic ") == 2, "칸은 둘 다 그림이어야 한다"  # 캐시 적중 여부와 무관하게 참
    assert len(saved.media.images) == 1
    bindata = [n for n in zipfile.ZipFile(out).namelist() if n.startswith("BinData/")]
    assert len(bindata) == 1


def test_그림_캐시를_공유하면_여러_render_node_호출도_한_번만_등록한다(문서):
    """compose()가 하는 일과 같다 — 캐시 하나를 여러 render_node 호출에 계속 넘긴다."""
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    캐시: dict = {}
    render_node(
        doc, kit, _나란히_그림칸_펜스("![](그림.png){width=2cm}"),
        base_dir=tmp_path, 그림_캐시=캐시,
    )
    render_node(
        doc, kit, _용어카드_그림칸_펜스("![](그림.png){width=2cm}"),
        base_dir=tmp_path, 그림_캐시=캐시,
    )
    out = tmp_path / "공유캐시.hwpx"
    doc.save_to_path(out)
    saved = HwpxDocument.open(out)
    assert len(saved.media.images) == 1


@pytest.mark.parametrize(
    "칸_글자, 조각",
    [
        ("![](없는파일.png)", "그림 파일이 없다: 없는파일.png"),
        ("![나쁜형식", "나란히 블록의 칸에 쓴 그림 줄을 읽을 수 없다"),
        ("![](가짜.png)", "PNG만 지원한다"),
    ],
)
def test_칸_안_그림_문제_문구가_정확하다(tmp_path, 칸_글자, 조각):
    (tmp_path / "가짜.png").write_bytes(b"not a real png")
    문제 = fence_problems(_나란히_그림칸_펜스(칸_글자), base_dir=tmp_path)
    assert any(조각 in p for p in 문제), 문제


def test_칸_안_그림_폭이_본문_폭보다_넓으면_거부한다(킷_루트):
    kit = load_kit(킷_루트)
    문제 = fence_problems(_나란히_그림칸_펜스("![](그림.png){width=40cm}"), kit)
    assert 문제 == ["나란히 블록의 칸 그림 폭이 본문 폭보다 넓다: 40cm — 17.8cm 이하로 쓴다"]


@pytest.mark.parametrize("폭_mm", [80.0, 178.0, 179.0, 400.0])
def test_본문_그림_폭은_check_markdown과_두_렌더러가_같은_판정을_낸다(킷_루트, tmp_path, 폭_mm):
    """양방향 성질 — check_markdown 이 본문 그림을 거부 ⇔ 어느 렌더러도 그리지 않는다."""
    from worksheet.checks import check_markdown
    from worksheet.md import Sheet

    kit = load_kit(킷_루트)
    (tmp_path / "그림.png").write_bytes(_png(400, 200))
    그림 = Figure("그림.png", width_mm=폭_mm)
    문제 = check_markdown(Sheet("시험킷", "t", None, False, (그림,)), kit, base_dir=tmp_path)

    doc = HwpxDocument.open(kit.skeleton_path)
    try:
        render_node(doc, kit, 그림, base_dir=tmp_path)
        hwpx_그림 = True
    except ValueError:
        hwpx_그림 = False
    writer = DocxWriter(kit, resolve_kit(kit))
    try:
        writer.draw(plan_node(kit, 그림, base_dir=tmp_path))
        docx_그림 = True
    except ValueError:
        docx_그림 = False
    assert (문제 == []) == hwpx_그림 == docx_그림 == (폭_mm <= 178.0)
    if 문제:
        assert 문제 == [f"그림(그림.png) 폭이 본문 폭보다 넓다: {폭_mm / 10:g}cm — 17.8cm 이하로 쓴다"]


def test_칸_안_그림_형식_오류는_base_dir_없어도_잡는다():
    """형식 오류는 파일이 있어야 아는 게 아니다 — base_dir 없이도 본다."""
    문제 = fence_problems(_나란히_그림칸_펜스("![나쁜형식"))
    assert any("나란히 블록의 칸에 쓴 그림 줄을 읽을 수 없다" in p for p in 문제), 문제


def test_칸_안_그림_파일_검사는_base_dir_없으면_건너뛴다():
    """기존 호출·테스트 호환 — base_dir가 없으면 파일 존재·PNG 유효성만 건너뛴다."""
    assert fence_problems(_나란히_그림칸_펜스("![](없는파일.png)")) == []


@pytest.mark.parametrize(
    "블록, 칸_글자",
    [
        (블록, 글자)
        for 블록 in sorted(_그림_지원_블록)
        for 글자 in [
            "보통 글자",
            "![](그림.png)",
            "![](그림.png){width=2cm}",
            "![](그림.png){width=17.8cm}",  # 본문 폭(178.0mm) 이하 — 칸 폭으로 줄여 그린다
            "![](그림.png){width=17.9cm}",  # 본문 폭보다 넓다 — 거부
            "![](없는파일.png)",
            "![](가짜.png)",
            "![나쁜형식",
        ]
    ],
)
def test_칸_안_그림_문제는_fence_problems와_렌더러가_같은_판정을_낸다(문서, 블록, 칸_글자):
    """양방향 성질 — 그림 칸을 포함한 값 목록에 대해 fence_problems([]) ⇔ render_node가
    예외 없이 그린다(기존 int/length 속성의 both-directions 테스트를 본떴다)."""
    doc, kit, tmp_path = 문서
    (tmp_path / "그림.png").write_bytes(_png(300, 120))
    (tmp_path / "가짜.png").write_bytes(b"not a real png")
    fence = _그림_지원_블록[블록](칸_글자)
    문제 = fence_problems(fence, kit, base_dir=tmp_path)
    hwpx_그림 = _hwpx로_그린다(doc, kit, fence, tmp_path)
    assert (문제 == []) == hwpx_그림 == _docx로_그린다(kit, fence, tmp_path)
