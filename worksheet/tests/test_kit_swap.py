"""킷 교체 가능성(원칙 1: 양식 고유 값은 킷에만 있고 코드에는 없다) 회귀 테스트.

지금까지 이 원칙의 위반(`line_width="0"`, 라벨폭 `4041`, 이름칸·교사칸 문구, `band_*` 미적용,
제목의 `교과서` 문구, 셀 서식 0/0)은 전부 사람 눈이 잡았다 — 모든 기존 테스트가 같은 값의
표준 킷 하나로 돌고 단언도 그 킷의 리터럴 값이라 구조적으로 못 잡는 사각이었다. 이 파일은
표준 킷의 값을 **전부 다른 값으로** 바꾼 변이 킷 하나로 블록 10종 + 가구 3종을 조판해, 원래
값이 하나도 안 남고 바뀐 값이 실제로 쓰였는지, 그리고 표 안 서식 참조가 전부 변이 킷이 준
ID 집합 안에 있는지(라이브러리 기본값 0이 새는 것도 여기서 걸린다)를 한 번에 본다.

원래 값 목록은 여기 리터럴로 다시 적지 않는다 — `kits/standard/kit.json`에서 읽어 재귀로
걷는다(`_킷_값_걷기`). 킷이 바뀌면 이 테스트의 "원래 값"도 따라간다.

**검사 대상에서 뺀 것 — 킷 값이 아니라 엔진이 구조상 갖는 값**: `numberingType="PICTURE"`
(원문자 타원 번호 매김 방식) · `textWrap`(TOP_AND_BOTTOM/IN_FRONT_OF_TEXT) ·
`vertRelTo`/`horzRelTo`(도장의 용지 기준 배치) · 머리띠가 4칸이라는 것(칸 각각의 폭은
킷 값이라 아래에서 바뀌지만, "4칸"이라는 모양 자체는 `furniture.band.cols`가 4개여야
한다는 스키마 제약이지 이 킷 저 킷에 따라 달라지는 값이 아니다). 이런 값은 kit.json 어디에도
없으므로 애초에 아래 재귀 값 걷기에 걸리지 않는다 — 걸리지 않는 이유를 밝히려고 여기 적는다.
라벨설명의 `labelWidth=`를 HWPUNIT으로 바꾸는 mm→HWPUNIT 환산 상수 `7200/25.4`
(`worksheet/blocks.py`의 `_MM_HWPUNIT`)도 같은 이유로 뺀다 — 1인치=7200 HWPUNIT·
1인치=25.4mm라는 단위 정의이지, 킷마다 고르는 양식 값이 아니다. 나란히의 칸 안 그림
(아래 `_전체_블록_MD`)이 쓰는 셀 안쪽 여백 510(좌우)·141(상하)도 같은 이유로 뺀다 —
python-hwpx의 `add_table()`이 모든 칸에 구조적으로 고정하는 값이고(`_칸_여백_좌우`·
`_칸_여백_상하`), 그림 자체의 계산 크기·행 높이도 이 여백 + 그림.png의 픽셀 비율 +
펜스에 명시한 `width=2cm`로만 정해져 어느 킷으로 조판해도 같다(위 `_전체_블록_MD`의
"나란히의 그림 칸은 폭을 생략하지 않는다" 주석 참고) — kit.json 어디에도 없으므로
아래 재귀 값 걷기·파생값 집합 둘 다에 애초에 안 걸린다.

**정수 0도 뺀다(구조상 흔한 값)**: 원본 킷의 `circle.lineWidth`가 마침 문자열 `"0"`이라
"원래 값"에 정수 0이 자연히 들어오는데, 실측(이 파일의 md로 조판한 section0.xml 1건)에서
`="0"`은 무관한 속성(`styleIDRef`·`pageBreak`·`protect`·`textWidth`…) 1413곳에서 나온다 —
라이브러리 전역 기본값이라 "남았다/생겼다"의 증거가 못 된다. 표 안 서식 참조(paraPr·charPr·
borderFill)의 라이브러리 기본값 0 유출은 이 정수 잔존 검사가 아니라 별도의 "스타일" ID
집합-소속 검사(`_표_안_스타일_확인`)가 잡는다 — 변이 킷은 0을 어떤 역할에도 주지 않으므로,
거기서는 0이 그대로 유효한 신호다.

**파생값(원시 필드 두 개 이상을 연산한 결과)도 이제 본다 — 무엇을, 어디까지**: `_킷_값_걷기`
는 kit.json에 **적힌** 값만 걷는다. 엔진이 원시 필드를 연산해서 쓰는 자리(라벨설명의
설명칸 폭 = `bodyWidth - labelWidth`, 블록마다의 표 전체 높이 = `rowHeight` 값들의 합/곱,
키워드면 줄 높이 = `keywordPage.height // keywordPage.rows`)는 연산 결과 자체가 kit.json
어디에도 안 적혀 있어서, 그 결과를 코드에 하드코딩해도(원칙 1 위반의 파생값 버전) 원시값
걷기로는 못 잡는다 — `_파생_값_집합`이 이 세 종류를 엔진과 같은 식으로 다시 계산해 따로
검사한다(아래 "파생값" 절 참고). **아직도 안 보는 파생값**: 용어카드·비교표·데이터표의
열 폭은 `표.equalize_column_widths()`가 `bodyWidth`를 열 수로 고르게 나눠 정하는데, 이건
엔진이 직접 연산하는 값이 아니라 python-hwpx가 표 생성 시점에 라이브러리 코드로 계산하는
값이라 이번에도 범위 밖이다 — 열 폭 하드코딩 회귀가 생겨도 이 테스트는 못 잡는다.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from hwpx.document import HwpxDocument

import worksheet.compose as compose_module
from _helpers import _png
from worksheet.backends.docx import twip
from worksheet.compose import compose
from worksheet.kit import REQUIRED_KEYS, load_kit, verify_kit
from worksheet.ns import HP
from worksheet.kit_style import resolve_kit

표준킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"

# --- 값 걷기 — 재귀 함수 하나로 정수(숫자 문자열 포함)·색·문구 세 버킷을 모은다 -----------------

_색_패턴 = re.compile(r"^#[0-9A-Fa-f]{6}$")
_숫자_문자열_패턴 = re.compile(r"^\d+$")
_자리표시자 = re.compile(r"\{[^}]*\}")


def _킷_값_걷기(data: object) -> tuple[set[int], set[str], set[str]]:
    """kit.json 서브트리를 재귀로 걸어 정수·색(`#RRGGBB`)·문구 문자열로 나눈다.

    dict는 값만 보고 키는 안 본다(키는 역할 이름이지 값이 아니다). `lineWidth`처럼 정수를
    문자열로 적은 자리(`"33"`·`"0"`)도 정수 버킷에 합친다 — XML에 속성값(`lineWidth="33"`)
    으로 나오는 건 색과 마찬가지로 치수 계열이지, 본문 글자로 나오는 "문구"가 아니다.
    """
    정수들: set[int] = set()
    색들: set[str] = set()
    문구들: set[str] = set()

    def _걷기(node: object) -> None:
        if isinstance(node, dict):
            for v in node.values():
                _걷기(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _걷기(v)
        elif isinstance(node, bool):
            return
        elif isinstance(node, int):
            정수들.add(node)
        elif isinstance(node, str):
            if _색_패턴.match(node):
                색들.add(node)
            elif _숫자_문자열_패턴.match(node):
                정수들.add(int(node))
            elif node.strip():
                문구들.add(node)

    _걷기(data)
    return 정수들, 색들, 문구들


def _리터럴_조각들(문자열: str) -> list[str]:
    """포맷 템플릿(`teacherLines`·`nameLines`·`heading.textbookFormat`)에서 `{자리표시자}`를
    지우고 남는 글자 조각들.

    조판은 `.format(**slots)`로 자리표시자만 치환하고 둘레 글자는 그대로 두므로, 이 조각들은
    치환 결과에 그대로 살아남는다. 공백만 남거나 두 글자 미만인 조각은 뺀다 — 쉼표 하나처럼
    너무 흔한 조각은 "문구가 남았다/생겼다"의 증거가 못 된다.
    """
    return [조각.strip() for 조각 in _자리표시자.split(문자열) if len(조각.strip()) >= 2]


def _관련_값(kit_데이터: dict) -> dict:
    """치수·색·문구가 실제로 나오는 서브트리만 골라낸다.

    `kit`(킷 이름)·`styles`(스타일 ID는 별도의 ID 집합-소속 검사가 맡는다 — 아래 "스타일"
    절)·`fonts`·`blocks`(이 회차의 값이 아니라 엔진 어휘·글꼴 이름표다)는 뺀다 — 이 셋을
    같이 걸으면 짧은 낱말(글꼴 이름 등)이 본문과 우연히 겹쳐 거짓 신호를 낼 수 있다.
    """
    return {
        "furniture": kit_데이터["furniture"],
        "bodyWidth": kit_데이터["bodyWidth"],
        "slots": kit_데이터["slots"],
    }


def _값_집합(kit_데이터: dict) -> tuple[set[int], set[str], set[str]]:
    """`_관련_값`을 걸어 (정수, 색, 문구 조각) 세 집합을 낸다 — 잔존 검사·존재 검사가 같이 쓴다."""
    정수들, 색들, 원문구들 = _킷_값_걷기(_관련_값(kit_데이터))
    문구_조각들 = {조각 for 문자열 in 원문구들 for 조각 in _리터럴_조각들(문자열)}
    정수들.discard(0)  # 모듈 docstring 참고 — 0은 라이브러리 전역 기본값이라 신호가 못 된다
    # "#000000"·"#FFFFFF"도 같은 이유로 뺀다 — 둘 다 킷이 아니라 엔진(정확히는 그 밑의
    # python-hwpx)이 구조상 갖는 값이라 kit.json을 어떻게 바꿔도 산출물에 그대로 남는다.
    # 실측: (1) "#000000"은 킷을 전혀 안 거친 kits/standard/skeleton.hwpx 씨앗에도 각주/미주
    # 선 색 기본값으로 이미 2건 있다(이 스킬이 안 쓰는 secPr 자리). (2) "#FFFFFF"는
    # python-hwpx 자신이 `add_ellipse()`가 그리는 도형마다 해치 색으로 하드코딩한다
    # (.venv/.../hwpx/oxml/objects.py:280, `"hatchColor": "#FFFFFF"` — 우리가 넘기는
    # fill_color와 무관하게 항상 이 값이다). 그래서 이 둘은 stamp.line="#000000"·
    # circle.line="#FFFFFF"가 산출물에 남았는지를 못 가린다 — 그 둘의 "존재" 신호는 잃지만,
    # circle.fill 처럼 씨앗에 0건인 색은 그대로 유효한 신호로 남는다.
    색들 -= {"#000000", "#FFFFFF"}
    return 정수들, 색들, 문구_조각들


# --- 파생값 — kit.json 원시 필드 두 개 이상을 엔진이 연산해서 쓰는 자리 ----------------------------
# `_킷_값_걷기`는 kit.json에 **적힌** 값만 걷는다 — 그런데 엔진은 원시 필드를 연산해서 쓰는
# 자리가 있다(뺄셈·덧셈·정수 나눗셈). 연산 결과 자체는 kit.json 어디에도 안 적혀 있으므로,
# 그 결과를 코드에 하드코딩해도(원칙 1 위반의 파생값 버전) 원시값 걷기로는 절대 못 잡는다.
# 아래 상수 넷(_라벨설명_행수·_비교표_행수·_데이터표_행수·_답칸_줄수)은 `_전체_블록_MD`의
# 라벨설명(2쌍)·비교표(rows="행가|행나"=2행)·데이터표(rows=3)·답칸(lines=2)과 정확히 맞아야
# 한다 — md의 그 줄들을 고치면 이 상수도 같이 고친다(어긋나면 아래 파생값 자체가 틀려
# "존재" 검사가 트리비얼하게 실패한다 — 그 실패가 곧 어긋났다는 신호다).

_라벨설명_행수 = 2
_비교표_행수 = 2
_데이터표_행수 = 3
_답칸_줄수 = 2


def _파생_값_집합(kit_데이터: dict) -> set[int]:
    """엔진이 실제로 연산해서 쓰는 자리를 그 연산 그대로 다시 계산한다(실측으로 확인한
    식이다 — 아래 각 줄 옆에 실제 코드 자리를 적는다):

    - 라벨설명 설명칸 폭 = `bodyWidth - labelWidth`(뺄셈, `worksheet/blocks.py`의
      `_라벨설명`).
    - 라벨설명·용어카드·비교표·데이터표·답칸·강조박스 표 전체 높이 = 역할별 `rowHeight`
      값의 합/곱(덧셈·곱셈, 각 블록 렌더러의 `총높이`) — `add_table`이 이 합을 표의
      `<hp:sz height=...>`로 그대로 쓰고, 각 셀의 `cellSz height`는 `_셀()`이 역할별
      원시값으로 다시 덮어써서(원시 rowHeight 값 그대로) 표 **전체** 높이만 파생값으로
      남는다(실측으로 확인함 — python-hwpx의 `add_table`은 표 높이를 행 수만큼 자동으로
      고르게 나눠 각 셀에 먼저 넣지만, `_셀()`이 그 뒤에 역할별 높이로 다시 쓴다).
    - 키워드면 줄 높이 = `keywordPage.height // keywordPage.rows`(정수 나눗셈,
      `worksheet/furniture.py`의 `add_keyword_page` — 이 함수는 `_셀()`을 안 써서
      python-hwpx의 자동 균등분배 값이 그대로 각 줄의 `cellSz height`로 남는다).

    용어카드와 강조박스는 같은 식(`label + cell`, 곱셈 항이 없다)이라 파생값이 우연이
    아니라 **필연적으로** 같다 — `_리터럴_조각들`처럼 "이 값이 어느 블록에서 왔는지"는
    안 가리고 "존재하는가/안 남았는가"만 본다(이 파일의 기존 검사 전부가 같은 설계다).
    """
    furniture = kit_데이터["furniture"]
    row = furniture["rowHeight"]
    return {
        kit_데이터["bodyWidth"] - furniture["labelWidth"],
        _라벨설명_행수 * row["cell"],
        row["label"] + row["cell"],  # 용어카드·강조박스(outer) 둘 다 이 식이다
        row["label"] + _비교표_행수 * row["cell"],
        row["label"] + _데이터표_행수 * row["cell"],
        row["label"] + _답칸_줄수 * row["answer"],
        furniture["keywordPage"]["height"] // furniture["keywordPage"]["rows"],
    }


# --- 이 파일이 아직 안 보는 파생값(정직하게 남겨 둔다) --------------------------------------------
# 용어카드·비교표·데이터표는 열 폭을 `표.equalize_column_widths()`로 정한다 — bodyWidth를
# 열 수로 고르게 나눈 몫도 kit 값(`bodyWidth`)에서 파생되지만, 이건 python-hwpx가 표
# 생성 시점에 라이브러리 코드로 계산하는 값이라(엔진이 직접 연산하는 값이 아니다) 이번
# 보강 범위 밖이다 — 열 폭 하드코딩 회귀가 생겨도 이 테스트는 못 잡는다.


# --- 변이 킷 — 표준 킷과 같은 구조, 값만 전부 다르다 --------------------------------------------


# 변이 킷의 글자 크기(1/100 pt) — 역할마다 새로 심는 charPr 의 height. label 은 11pt 다 — 원본
# label·cell(12pt)과도, 변이 cell(10pt)과도 크기가 달라야 docx 판 테스트의 역할별 글자 크기
# 검사가 "원래 킷을 읽었다"·"역할을 바꿔 읽었다"를 가린다. 나머지도 원본 킷의 같은 역할과 다르다.
_변이_글자_크기 = {
    "headline": 1600, "circle_num": 900, "stamp": 2000, "body": 900,
    "band_left": 1050, "band_teacher": 1300, "band_title": 1700, "band_name": 1400,
    "cell": 1000, "label": 1100, "heading_ref": 1150, "keyword_head": 1650, "prompt": 1050,
}
# 변이 킷의 borderFill 원형 — 역할마다 표준 킷의 어느 역할을 복제해 새 번호로 심는가. answer 는
# 흰 채움이 있는 원본 answer 대신 plain 을 복제한다 — 흰색(원본 answer 의 채움색)이 docx 에
# 나오면 "원래 색이 남았다"와 구별이 안 된다. shade 는 복제한 뒤 채움색을 `_새_채움색`으로 바꾼다.
_변이_테두리_원형 = {
    "plain": "plain", "shade": "shade", "grid": "grid", "answer": "plain",
    "rule_head": "rule_head", "rule_line": "rule_line", "rule_last": "rule_last",
}
_새_채움색 = "#C0FFEE"
_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
_HC = "{http://www.hancom.co.kr/hwpml/2011/core}"


def _변이_모양_심기(스켈레톤: Path, 원본_스타일: dict) -> dict[str, dict[str, int]]:
    """변이 킷이 쓸 charPr·borderFill 을 스켈레톤 사본의 header.xml 끝에 새 번호로 심는다.

    씨앗 스켈레톤은 킷 역할이 쓰는 모양만 갖고 있어, 원본 킷과 안 겹치는 번호가 역할 수만큼
    남아 있지 않다 — 그래서 변이 킷의 모양은 테스트가 직접 합성한다. 새 번호는 기존 최댓값
    다음부터라 원본 킷의 번호 집합과 구조적으로 안 겹치고 0도 아니다. charPr 은 본문 모양(0)을
    복제해 크기만 `_변이_글자_크기`로 바꾸고, borderFill 은 `_변이_테두리_원형`대로 복제한다.
    paraPr 은 기본 템플릿이 남긴 번호로 충분해 심지 않는다. 역할 → 새 번호를 돌려준다.
    """
    with zipfile.ZipFile(스켈레톤) as z:
        항목들 = [(정보, z.read(정보.filename)) for 정보 in z.infolist()]
    위치 = next(i for i, (정보, _) in enumerate(항목들) if 정보.filename == "Contents/header.xml")
    뿌리 = ET.fromstring(항목들[위치][1])

    def _복제(묶음_태그: str, 원형_id: int) -> ET.Element:
        묶음 = next(뿌리.iter(f"{_HH}{묶음_태그}"))
        원형 = next(e for e in 묶음 if e.get("id") == str(원형_id))
        새것 = copy.deepcopy(원형)
        새것.set("id", str(max(int(e.get("id")) for e in 묶음) + 1))
        묶음.append(새것)
        묶음.set("itemCnt", str(len(묶음)))
        return 새것

    번호: dict[str, dict[str, int]] = {"charPr": {}, "borderFill": {}}
    for 역할, 크기 in _변이_글자_크기.items():
        e = _복제("charProperties", 원본_스타일["charPr"]["body"])
        e.set("height", str(크기))
        번호["charPr"][역할] = int(e.get("id"))
    for 역할, 원형_역할 in _변이_테두리_원형.items():
        e = _복제("borderFills", 원본_스타일["borderFill"][원형_역할])
        if 역할 == "shade":
            (붓,) = e.iter(f"{_HC}winBrush")
            붓.set("faceColor", _새_채움색)
        번호["borderFill"][역할] = int(e.get("id"))

    새_헤더 = ET.tostring(뿌리, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(스켈레톤, "w") as z:
        for i, (정보, 내용) in enumerate(항목들):
            z.writestr(정보, 새_헤더 if i == 위치 else 내용)
    return 번호


def _변이_kit_데이터(원본: dict, 심은_번호: dict[str, dict[str, int]]) -> dict:
    """`kits/standard/kit.json`의 값을 전부 원본과 안 겹치는 값으로 바꾼다.

    구조(블록 10종 이름, band 4칸, fonts 목록)는 그대로 둔다 — 이 테스트가 흔드는 것은
    "값"이지 "구조"가 아니다. 문구 계열은 전부 "변이" 표식으로 시작해 원본 문구(확인도장·
    오늘의 키워드·교과서 등)와 우연히도 안 겹치게 한다. 스타일 ID는 역할마다 스켈레톤에
    실재하는 다른 ID를 고르되, 카테고리(borderFill/charPr/paraPr)별로 **원본이 쓴 값의
    집합과 아예 겹치지 않게** 고른다 — 겹치면 변이 킷이 우연히 원래 ID를 재사용해도 "변이
    킷이 준 ID 집합 안에 있다"는 이 파일의 스타일 검사가 하드코딩 유출을 못 가릴 수 있다.
    0도 어떤 역할에도 주지 않는다(라이브러리 기본값과 안 겹쳐야 그 유출이 걸린다).
    charPr·borderFill 은 `_변이_모양_심기`가 심은 새 번호(`심은_번호`)를 쓴다.
    """
    데이터 = copy.deepcopy(원본)
    데이터["kit"] = "변이킷"
    데이터["slots"] = {
        "school": "변이고등학교", "teacher": "변이김T",
        "subject": "변이과목", "grade": "변이1학년",
    }
    데이터["styles"]["borderFill"] = dict(심은_번호["borderFill"])
    데이터["styles"]["charPr"] = dict(심은_번호["charPr"])
    # paraPr 은 기본 템플릿이 남긴 1..7 — 씨앗이 킷 역할에 더한 번호는 그 뒤에 온다(아래 단언).
    데이터["styles"]["paraPr"] = {
        "body": 1, "prompt": 2, "center": 3, "band_title": 4,
        "band_name": 5, "cell": 6, "label": 7,
    }
    for 종류 in ("borderFill", "charPr", "paraPr"):
        새, 옛 = set(데이터["styles"][종류].values()), set(원본["styles"][종류].values())
        assert not (새 & 옛) and 0 not in 새, f"변이 {종류} 번호가 원본과 겹치거나 0 이다: {새 & 옛}"
    데이터["furniture"] = {
        "rowHeight": {"label": 2200, "cell": 2300, "answer": 2800},
        "heading": {"textbookFormat": " 변이참조 {textbook}"},
        "band": {
            "width": 40000, "height": 6200,
            "cols": [6000, 8000, 16000, 10000],  # 합 40000 == width
            "teacherLines": ["변이학교 {school}", "변이교과 {subject} 변이교사 {teacher}"],
            "nameLines": ["변이학년 {grade}", "변이성명란"],
        },
        "stamp": {
            "curSz": [9200, 6100], "fill": "#FFCC00", "line": "#4477AA", "lineWidth": "70",
            "text": "변이확인표시", "pos": {"horzOffset": 50000, "vertOffset": 7000},
        },
        "circle": {"curSz": [2000, 1900], "fill": "#2E8B57", "line": "#111111", "lineWidth": "15"},
        "keywordPage": {"rows": 20, "width": 45000, "height": 70000, "head": "변이키워드목록 : "},
        "labelWidth": 5000,  # < bodyWidth(48000)
    }
    데이터["bodyWidth"] = 48000
    return 데이터


def _변이_킷_만들기(tmp_path: Path) -> tuple[dict, dict, Path]:
    """표준 킷을 복사해 변이 모양을 심고 변이 kit.json 을 쓴다 — (원본 데이터, 변이 데이터, 변이 킷 루트)."""
    원본_데이터 = json.loads((표준킷 / "kit.json").read_text(encoding="utf-8"))
    변이_루트 = tmp_path / "변이킷"
    shutil.copytree(표준킷, 변이_루트)
    심은_번호 = _변이_모양_심기(변이_루트 / "skeleton.hwpx", 원본_데이터["styles"])
    변이_데이터 = _변이_kit_데이터(원본_데이터, 심은_번호)
    (변이_루트 / "kit.json").write_text(
        json.dumps(변이_데이터, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 원본_데이터, 변이_데이터, 변이_루트


# 블록 10종(라벨설명·용어카드·비교표·데이터표·답칸·강조박스·나란히 + 정의빈칸·발문·그림칸)
# 전부와 가구 3종(머리띠는 compose()가 항상 그린다, 제목+도장+출처 표기는 첫 제목 하나로,
# 키워드면은 front matter)을 다 쓰는 회차 한 장 — 킷 이름만 바꿔 아래 두 테스트(변이 킷
# 값 잔존/존재 검사·런타임 키 기록 커버리지 검사)가 같이 쓴다(둘 다 "블록 10종 + 가구
# 3종을 전부 조판한다"는 같은 전제가 있어야 뜻이 있다). 나란히의 그림 칸은 폭을
# 생략하지 않고 항상 명시한다({width=2cm}) — 생략하면 칸 폭(bodyWidth에서 유도)에 맞추는데,
# 원본·변이 두 킷이 bodyWidth가 다르므로(50460 vs 48000) 그림 크기가 킷마다 달라져 이 파일의
# "원래 값이 하나도 안 남는다" 잔존 검사와 얽힌다 — 명시한 폭(mm→HWPUNIT은 킷 값이 아니라
# 단위 정의)과 그림.png의 픽셀 비율만으로 정해지면 어느 킷으로 조판해도 같은 값이라 이 얽힘이
# 없다(칸 폭에 맞추는 갈래 자체는 tests/test_blocks.py가 따로, 전용 킷 픽스처로 본다).
def _전체_블록_MD(kit_이름: str) -> str:
    return f"""---
kit: {kit_이름}
title: 변이회차제목
keywordPage: true
---

## 변이 섹션 제목
교과서: 12P

■ 변이 정의문단 내용

> 변이 발문 내용

![](그림.png){{width=6cm}}

:::라벨설명
[1] 변이라벨
: 변이설명
[2] 변이라벨둘
: 변이설명둘
:::

:::용어카드 cols="가|나|다"
설명가
설명나
설명다
:::

:::비교표 cols="열가|열나" rows="행가|행나"
값1|값2
값3|값4
:::

:::데이터표 head="칼가|칼나|칼다" rows=3
d1|d2|d3
:::

:::답칸 label="정답란" lines=2
:::

:::강조박스 title="강조제목"
강조내용입니다
:::

:::나란히 cols="변이단1|변이단2"
![](그림.png){{width=2cm}}|변이나란히본문
:::
"""


def _표_안_스타일_확인(
    xml: str, *, 허용_보더: set[str], 허용_파라: set[str], 허용_캐릭: set[str]
) -> None:
    """표 안 모든 셀의 borderFillIDRef · 모든 문단의 paraPrIDRef · 글자 있는 run의
    charPrIDRef가 전부 변이 킷이 준 ID 집합 안에 있는지 본다.

    `hp:tc`(표 셀)는 구조상 표 안에만 있으므로, `root.iter()`로 전체 문서에서 곧장 찾아도
    "표 안"이라는 조건이 저절로 지켜진다(test_blocks.py의 표 서식 검사와 같은 방식 —
    `tbl.iter(f"{HP}p")`처럼 여기서도 `.iter()`가 강조박스 중첩표까지 재귀로 들어간다).
    표 밖 문단(제목 문단·발문·스켈레톤이 남긴 첫 문단)은 이 검사의 대상이 아니다 — "표 안"만
    본다.
    """
    root = ET.fromstring(xml)
    for tc in root.iter(f"{{{HP}}}tc"):
        보더 = tc.get("borderFillIDRef")
        assert 보더 in 허용_보더, f"표 셀의 borderFillIDRef={보더!r}가 변이 킷이 준 ID 밖이다"
        for p in tc.iter(f"{{{HP}}}p"):
            파라 = p.get("paraPrIDRef")
            assert 파라 in 허용_파라, f"표 안 문단의 paraPrIDRef={파라!r}가 변이 킷이 준 ID 밖이다"
            for run in p.findall(f"{{{HP}}}run"):
                t = run.find(f"{{{HP}}}t")
                if t is not None and (t.text or "").strip():
                    캐릭 = run.get("charPrIDRef")
                    assert 캐릭 in 허용_캐릭, (
                        f"표 안 글자 있는 run의 charPrIDRef={캐릭!r}가 변이 킷이 준 ID 밖이다"
                    )


def test_변이_킷으로_조판하면_원래_값은_안_남고_바뀐_값만_쓰인다(tmp_path):
    원본_데이터, 변이_데이터, 변이_루트 = _변이_킷_만들기(tmp_path)

    kit = load_kit(변이_루트)
    assert verify_kit(kit) == []  # 스타일 ID가 전부 스켈레톤에 실재한다

    (tmp_path / "그림.png").write_bytes(_png(20, 20))
    md_경로 = tmp_path / "회차.md"
    md_경로.write_text(_전체_블록_MD("변이킷"), encoding="utf-8")

    out = tmp_path / "결과.hwpx"
    보고 = compose(md_경로, 변이_루트, out)
    assert 보고.validate_ok is True
    assert 보고.blocks == 10  # 정의빈칸·발문·그림칸 + 펜스 7종
    assert 보고.headings == 1

    xml = zipfile.ZipFile(out).read("Contents/section0.xml").decode("utf-8")

    원본_정수, 원본_색, 원본_문구 = _값_집합(원본_데이터)
    변이_정수, 변이_색, 변이_문구 = _값_집합(변이_데이터)
    원본_파생 = _파생_값_집합(원본_데이터)
    변이_파생 = _파생_값_집합(변이_데이터)

    # --- 파생값이 원시값·서로와 안 겹치는지 먼저 확인한다 — 안 겹치는지 손으로 계산해 확인한
    # 게 아니라 여기서 직접 단언한다. 값 선택이 나빠 우연히 겹치면(예: 어떤 블록의 총높이가
    # 다른 블록의 원시 rowHeight와 같아짐) 아래 잔존/존재 검사가 트리비얼하게 (통과하거나
    # 실패)해서 이 테스트 자체가 뭘 확인했는지 알 수 없게 된다 — 그런 값 선택은 여기서
    # 시끄럽게 죽는다.
    assert not (원본_파생 & 변이_파생), f"원본·변이 파생값이 겹친다: {원본_파생 & 변이_파생}"
    assert not (원본_파생 & 변이_정수), f"원본 파생값이 변이 원시값과 겹친다: {원본_파생 & 변이_정수}"
    assert not (변이_파생 & 원본_정수), f"변이 파생값이 원본 원시값과 겹친다: {변이_파생 & 원본_정수}"

    # --- 원래 값 잔존 0 — 속성값으로 나타나는 것은 따옴표까지 붙여 센다(우연히 다른 수의
    # 부분 문자열로 걸리지 않게: "460"이 "50460" 안에서 우연히 걸리는 일을 막는다). 파생값도
    # 원시값과 같은 규칙으로 본다 — 표 sz의 height 속성값으로 나오는 것도 똑같이 따옴표
    # 붙여 정확히 매칭한다. -------------------------------------------------------------------
    for 값 in sorted(원본_정수 | 원본_파생):
        조각 = f'="{값}"'
        assert 조각 not in xml, f"원래 치수/선 값(파생 포함)이 산출물에 남아 있다: {값}"
    for 값 in sorted(원본_색):
        조각 = f'="{값}"'
        assert 조각 not in xml, f"원래 색이 산출물에 남아 있다: {값}"
    for 값 in sorted(원본_문구):
        assert 값 not in xml, f"원래 문구가 산출물에 남아 있다: {값!r}"

    # --- 바뀐 값 존재 — 치수·색·문구·파생값이 각각 1건 이상 -------------------------------------
    for 값 in sorted(변이_정수 | 변이_파생):
        조각 = f'="{값}"'
        assert 조각 in xml, f"바뀐 치수/선 값(파생 포함)이 산출물에 안 보인다: {값}"
    for 값 in sorted(변이_색):
        조각 = f'="{값}"'
        assert 조각 in xml, f"바뀐 색이 산출물에 안 보인다: {값}"
    for 값 in sorted(변이_문구):
        assert 값 in xml, f"바뀐 문구가 산출물에 안 보인다: {값!r}"

    # --- 스타일 — 표 안 모든 서식 참조가 변이 킷이 준 ID 집합 안(라이브러리 기본값 0 유출도
    # 여기서 걸린다: 변이 킷은 0을 어떤 역할에도 주지 않았다). ------------------------------------
    _표_안_스타일_확인(
        xml,
        허용_보더={str(v) for v in kit.border_fill.values()},
        허용_파라={str(v) for v in kit.para_pr.values()},
        허용_캐릭={str(v) for v in kit.char_pr.values()},
    )

    assert HwpxDocument.open(out).validate().ok


# --- 변이 킷 — docx 판 ------------------------------------------------------------------------
# docx 는 스타일 번호가 아니라 `resolve_kit`이 푼 실제 값(글자 크기·채움색)을 XML에 적는다. 그래서
# 같은 변이 킷으로 docx 를 조판해 네 가지를 본다 — 문구(`w:t`), 색(`w:color`·`w:fill`), 치수
# (twip 으로 바꾼 표 칸 폭·행 높이·표 폭), 역할별 글자 크기(`w:sz`). 색은 대문자 6자리로 맞춰
# 비교한다(docx 는 `#` 없이 적는다).

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
def _docx_색(값: str | None) -> str | None:
    return 값.lstrip("#").upper() if 값 else None


def _docx_색_집합(kit_데이터: dict, 해석) -> set[str]:
    """킷이 docx 에 칠하게 하는 색 — 원문자 색·도장 선·도장 채움, 해석한 borderFill 채움색.

    검은색(000000)은 뺀다 — 해석한 글자색·표 테두리 색으로 문서 곳곳에 구조적으로 나와(원본 킷의
    stamp.line 이 마침 검정이다) "남았다/생겼다"의 증거가 못 된다.
    """
    furniture = kit_데이터["furniture"]
    색들 = {furniture["circle"]["fill"], furniture["stamp"]["line"], furniture["stamp"]["fill"]}
    색들 |= {상자.fill for 상자 in 해석.box.values()}
    return {_docx_색(c) for c in 색들 if c} - {"000000"}


def _docx_치수_집합(kit_데이터: dict, 해석) -> set[int]:
    """킷이 docx 표에 적게 하는 치수(twip) — 원시값과 엔진이 연산해 쓰는 파생값.

    원시: 머리띠 칸 폭·높이, 본문 폭, 라벨 폭, 역할별 행 높이, 키워드면 폭. 파생: 라벨설명 설명 칸
    (bodyWidth − labelWidth), 키워드면 줄 높이(height // rows), 강조박스 안쪽 표 폭(bodyWidth −
    칸 좌우 여백), 머리띠 끝과 도장 칸 사이 간격(stamp 가로 위치 − (왼쪽 여백 + band 폭), 음수는 0 — docx 와 같다), 도장 칸
    폭(bodyWidth − band 폭 − 간격). `band.width` 자체는 표에 안 적힌다(간격 계산에만 쓴다).
    """
    furniture = kit_데이터["furniture"]
    band, row, 키워드 = furniture["band"], furniture["rowHeight"], furniture["keywordPage"]
    본문 = kit_데이터["bodyWidth"]
    간격 = max(0, furniture["stamp"]["pos"]["horzOffset"] - (해석.page.left + band["width"]))
    hwp = [
        *band["cols"], band["height"], 본문, furniture["labelWidth"],
        row["label"], row["cell"], row["answer"], 키워드["width"],
        본문 - furniture["labelWidth"], 키워드["height"] // 키워드["rows"], 본문 - 2 * 510,
        간격, 본문 - band["width"] - 간격,
    ]
    return {twip(v) for v in hwp}


def test_변이_킷으로_docx를_조판하면_서식이_변이_킷의_해석값이다(tmp_path):
    원본_데이터, 변이_데이터, 변이_루트 = _변이_킷_만들기(tmp_path)

    원본_kit, 변이_kit = load_kit(표준킷), load_kit(변이_루트)
    assert verify_kit(변이_kit) == []
    원본_해석, 변이_해석 = resolve_kit(원본_kit), resolve_kit(변이_kit)
    assert 변이_해석.box["shade"].fill == _새_채움색

    (tmp_path / "그림.png").write_bytes(_png(20, 20))
    md_경로 = tmp_path / "회차.md"
    md_경로.write_text(_전체_블록_MD("변이킷"), encoding="utf-8")
    out = tmp_path / "결과.docx"
    보고 = compose(md_경로, 변이_루트, out)
    assert 보고.validate_ok is True
    assert 보고.blocks == 10
    assert 보고.headings == 1

    root = ET.fromstring(zipfile.ZipFile(out).read("word/document.xml"))

    # --- 준비: 원본·변이 값이 docx 단위로 바꾼 뒤에도 안 겹치는지 먼저 단언한다(twip 은 5로 나눠
    # 반올림하므로 서로 다른 HWPUNIT 이 같은 twip 이 될 수 있다) ---------------------------------
    _, _, 원본_문구 = _값_집합(원본_데이터)
    _, _, 변이_문구 = _값_집합(변이_데이터)
    원본_색, 변이_색 = _docx_색_집합(원본_데이터, 원본_해석), _docx_색_집합(변이_데이터, 변이_해석)
    원본_치수, 변이_치수 = _docx_치수_집합(원본_데이터, 원본_해석), _docx_치수_집합(변이_데이터, 변이_해석)
    assert 원본_문구 and 원본_색 and 원본_치수
    assert 변이_문구 and 변이_색 and 변이_치수
    assert not (원본_색 & 변이_색), f"원본·변이 색이 겹친다: {원본_색 & 변이_색}"
    assert not (원본_치수 & 변이_치수), f"원본·변이 치수가 twip 으로 겹친다: {원본_치수 & 변이_치수}"

    # --- 문구 — 문단마다 w:t 를 이어 붙인 글자에서 찾는다 -------------------------------------------
    문단_글들 = ["".join(t.text or "" for t in p.iter(f"{W}t")) for p in root.iter(f"{W}p")]
    for 값 in sorted(원본_문구):
        assert not any(값 in 글 for 글 in 문단_글들), f"원래 문구가 docx 에 남아 있다: {값!r}"
    for 값 in sorted(변이_문구):
        assert any(값 in 글 for 글 in 문단_글들), f"바뀐 문구가 docx 에 안 보인다: {값!r}"

    # --- 색 — 글자색·테두리색(w:color)과 칸 음영(w:fill) ----------------------------------------------
    docx_색 = {
        v.upper() for e in root.iter()
        for k in (f"{W}color", f"{W}val", f"{W}fill")
        if (v := e.get(k)) is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", v)
        and (k != f"{W}val" or e.tag == f"{W}color")
    }
    assert not (원본_색 & docx_색), f"원래 색이 docx 에 남아 있다: {원본_색 & docx_색}"
    assert 변이_색 <= docx_색, f"바뀐 색이 docx 에 안 보인다: {변이_색 - docx_색}"

    # --- 치수 — 칸 폭·열 폭·표 폭·행 높이(twip) -------------------------------------------------------
    docx_치수 = {
        int(e.get(f"{W}{속성}"))
        for 태그, 속성 in (("tcW", "w"), ("gridCol", "w"), ("tblW", "w"), ("trHeight", "val"))
        for e in root.iter(f"{W}{태그}")
    }
    assert not (원본_치수 & docx_치수), f"원래 치수가 docx 에 남아 있다: {sorted(원본_치수 & docx_치수)}"
    assert 변이_치수 <= docx_치수, f"바뀐 치수가 docx 에 안 보인다: {sorted(변이_치수 - docx_치수)}"

    # --- 서식 — 표 안 글자 있는 run 마다 w:sz 가 그 역할의 변이 해석값(pt × 2)이다. 역할은 칸 글자로
    # 찾는다: 블록의 머리 행·라벨 칸은 label, 나머지 블록 칸은 cell, 머리띠·도장·키워드면은 제 역할.
    teacher, name = 변이_데이터["furniture"]["band"]["teacherLines"], 변이_데이터["furniture"]["band"]["nameLines"]
    slots = 변이_데이터["slots"]
    가구_역할 = {
        **{줄.format(**slots): "band_teacher" for 줄 in teacher},
        **{줄.format(**slots): "band_name" for 줄 in name},
        "변이회차제목": "band_title",
        변이_데이터["furniture"]["stamp"]["text"]: "stamp",
        변이_데이터["furniture"]["keywordPage"]["head"]: "keyword_head",
    }
    라벨_글자 = {
        "[1] 변이라벨", "[2] 변이라벨둘", "가", "나", "다", "열가", "열나", "행가", "행나",
        "칼가", "칼나", "칼다", "정답란", "강조제목", "변이단1", "변이단2",
    }
    본 = set()
    for tc in root.iter(f"{W}tc"):
        for run in tc.findall(f"{W}p/{W}r"):  # 중첩표의 run 은 그 안쪽 칸이 따로 본다
            글 = "".join(t.text or "" for t in run.iter(f"{W}t"))
            if not 글.strip():
                continue
            역할 = 가구_역할.get(글) or ("label" if 글 in 라벨_글자 else "cell")
            원본_크기, 변이_크기 = 원본_해석.char[역할].size_pt, 변이_해석.char[역할].size_pt
            assert 원본_크기 != 변이_크기, f"{역할} 의 원본·변이 글자 크기가 같아 가리지 못한다"
            sz = run.find(f"{W}rPr/{W}sz")
            assert sz is not None, f"{글!r} run 에 글자 크기가 없다"
            assert int(sz.get(f"{W}val")) == round(변이_크기 * 2), (
                f"{글!r}({역할})의 w:sz={sz.get(f'{W}val')} 가 변이 킷 해석값 {변이_크기}pt 가 아니다"
            )
            본.add(역할)
    assert 본 == {"label", "cell", "band_teacher", "band_name", "band_title", "stamp", "keyword_head"}


# --- 런타임 키 기록 — REQUIRED_KEYS 커버리지를 양방향으로 본다 ---------------------------------
#
# tests/test_kit.py의 test_엔진이_읽는_킷_스타일_키는_모두_REQUIRED_KEYS에_선언돼_있다는
# 소스를 정규식(`kit\.(char_pr|para_pr|border_fill)\["(\w+)"\]`)으로 훑는 [기계] 감사다 —
# 하지만 이 정규식은 세 가지를 구조적으로 못 본다: ① `kit.furniture[...]` 읽기(애초에
# char_pr/para_pr/border_fill만 본다) ② 지역 별칭을 거친 접근(`설정 = kit.furniture["band"]`
# 다음 `설정["cols"]`) ③ 변수로 키를 넘기는 동적 호출 — `worksheet/blocks.py`의 `_셀_역할`
# 표가 바로 이 경로다(`kit.border_fill[보더_키]`처럼 대괄호 안이 문자열 리터럴이 아니라
# 변수라 애초에 매치되지 않는다). 실측으로 확인했다: 위 정규식은 `border_fill.answer`·
# `char_pr.cell`·`char_pr.label`·`para_pr.label` 네 키를 하나도 못 찾는다 — 이 넷은
# `_셀_역할` 동적 호출로만 읽히고, 다른 리터럴 호출로는 안 읽힌다(예를 들어
# `border_fill.shade`·`.plain`·`.grid`는 `add_band`·강조박스의 리터럴 호출도 있어 그
# 정규식으로도 잡히지만, `.answer`는 그런 리터럴 짝이 아예 없다). 정적 스캔으로는 이 사각을
# 못 없앤다 — 그래서 여기서는 실제로 조판을 돌려 무엇이 **진짜로 읽혔는지** 런타임에 본다.


class _기록_딕셔너리(dict):
    """dict를 감싸 읽힌 키의 점 경로 전체를 `기록`(바깥에서 준 공유 set)에 남긴다.

    `__getitem__`·`get` 둘 다 기록한다 — `.get()`으로 읽는 자리도 REQUIRED_KEYS 커버리지
    관점에서는 "읽었다"와 같고, 음성 대조(존재하지 않는 키를 `.get()`으로 조용히 두드리는
    코드)도 이 감싸기를 지나가야 걸린다. 중첩 dict 값은 같은 방식으로 다시 감싸 돌려준다 —
    그래야 `설정 = kit.furniture["band"]`처럼 지역 변수에 옮겨 담은 뒤 `설정["cols"]`로
    읽어도 잡힌다(별칭이 가리키는 객체 자체가 이미 감싸여 있으므로 변수 이름은 상관없다).
    list·문자열·정수 값은 그대로 돌려준다 — 리스트 원소 하나하나를 킷 키로 보지 않는다.

    **list를 그대로 돌려줘도 지금은 안전하다**: kit.json의 리스트 값(`band.cols`·
    `teacherLines`·`nameLines`·`stamp.curSz`·`circle.curSz`·`fonts`·`blocks`)은 전부 원소가
    스칼라(정수·문자열)뿐이고, dict를 원소로 갖는 리스트가 없다 — 그래서 "list는 안 감싼다"
    는 이 설계가 지금은 어떤 키 읽기도 놓치지 않는다. 이 전제를 사람이 눈으로만 지키는 대신
    `test_킷json의_리스트_원소는_dict가_아니다`가 `kits/standard/kit.json`을 직접 걸어
    확인한다 — 나중에 리스트 원소로 dict가 생기면(예: `band.cols`가 `[{"width":...}, ...]`
    처럼 바뀌면) 그 안의 키는 이 감싸기를 그냥 통과해 버려 읽혀도 기록이 안 될 텐데, 그
    테스트가 조용히 그러지 않고 시끄럽게 실패해 이 설계를 다시 봐야 한다고 알린다.
    """

    def __init__(self, data: dict, 경로: str, 기록: set[str]) -> None:
        super().__init__(data)
        self._경로 = 경로
        self._기록 = 기록

    def _자식_경로(self, key: object) -> str:
        return f"{self._경로}.{key}" if self._경로 else str(key)

    def __getitem__(self, key):
        자식_경로 = self._자식_경로(key)
        self._기록.add(자식_경로)
        return _감싸기(dict.__getitem__(self, key), 자식_경로, self._기록)

    def get(self, key, default=None):
        자식_경로 = self._자식_경로(key)
        self._기록.add(자식_경로)
        if dict.__contains__(self, key):
            return _감싸기(dict.__getitem__(self, key), 자식_경로, self._기록)
        return default


def _감싸기(값: object, 경로: str, 기록: set[str]) -> object:
    if isinstance(값, dict):
        return _기록_딕셔너리(값, 경로, 기록)
    return 값  # list·문자열·정수는 그대로 — 값 자체가 아니라 "어떤 키를 읽었는가"만 본다


def test_킷json의_리스트_원소는_dict가_아니다():
    """`_기록_딕셔너리`가 list를 안 감싸는 전제를 실측으로 고정한다 — `_기록_딕셔너리`의
    docstring 참고. `kits/standard/kit.json`을 직접 재귀로 걸어, 리스트 원소 중 dict가
    하나라도 있으면 어느 경로인지 짚어서 실패한다(사람이 눈으로 확인하는 대신)."""
    데이터 = json.loads((표준킷 / "kit.json").read_text(encoding="utf-8"))
    dict_원소_있는_리스트: list[str] = []

    def _걷기(node: object, 경로: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                _걷기(v, f"{경로}.{k}" if 경로 else str(k))
        elif isinstance(node, list):
            if any(isinstance(원소, dict) for 원소 in node):
                dict_원소_있는_리스트.append(경로)
            for i, 원소 in enumerate(node):
                _걷기(원소, f"{경로}[{i}]")

    _걷기(데이터, "")
    assert dict_원소_있는_리스트 == [], (
        f"kit.json 리스트 안에 dict 원소가 생겼다 — _기록_딕셔너리가 그 안의 키 읽기를 "
        f"놓친다(리스트는 안 감싸므로): {dict_원소_있는_리스트}"
    )


def _문서_경로로(기록_경로: str) -> str:
    """기록된 점 경로(`char_pr.x` 등)를 kit.json 문서 경로(`styles.charPr.x` 등)로 바꾼다.

    `furniture.*`는 애초에 기록 경로와 문서 경로가 같다(둘 다 `kit.furniture["band"]["cols"]`
    → `furniture.band.cols`) — border_fill/char_pr/para_pr 셋만 `Kit` 데이터클래스 필드
    이름(`snake_case`)과 kit.json의 `styles.<camelCase 그룹>` 경로가 다르다.
    """
    분류표 = {
        "border_fill": "styles.borderFill", "char_pr": "styles.charPr", "para_pr": "styles.paraPr",
    }
    머리, _, 나머지 = 기록_경로.partition(".")
    if 머리 in 분류표:
        return f"{분류표[머리]}.{나머지}" if 나머지 else 분류표[머리]
    return 기록_경로


def _접두어_또는_일치(경로: str, 후보들: set[str]) -> bool:
    """assertion (a) 전용(대칭) — `경로`가 `후보들` 중 하나와 같거나, 그중 하나의 접두어이거나,
    그중 하나를 접두어로 갖는가.

    "읽힌 경로가 선언 안에 있는가"(assertion (a))에서는 방향이 둘 다 필요하다 — 예를 들어
    `add_heading`이 `도장 = kit.furniture["stamp"]`로 하위 dict 전체를 먼저 꺼내 쥐면
    "furniture.stamp"가 기록되는데, REQUIRED_KEYS에는 그 자체가 아니라 그 자식들
    (`furniture.stamp.curSz` 등)만 있다 — 그래서 "경로가 후보의 접두어"도 커버로 본다.
    거꾸로(경로가 후보보다 깊음)도 대칭으로 인정한다.

    **assertion (b)에는 이 함수를 쓰지 않는다** — 대칭이라 "부모 dict를 통째로 한 번
    건드렸다"는 기록만으로 그 밑 모든 자식 선언이 "읽힘"으로 덮여 버린다(실측 재현:
    `test_비대칭_읽음_판정은_부모_통째_접근을_자식_개별_읽음으로_안_친다` 참고). "선언된
    키가 실제로 읽혔는가"는 `_자식으로_읽힘`(아래, 방향이 하나뿐이다)이 대신 본다.
    """
    if 경로 in 후보들:
        return True
    return any(후보.startswith(경로 + ".") or 경로.startswith(후보 + ".") for 후보 in 후보들)


def _자식으로_읽힘(선언: str, 기록됨: set[str]) -> bool:
    """assertion (b) 전용(비대칭) — `선언`(REQUIRED_KEYS의 한 키)이 실제로 읽혔는가.

    기록된 경로가 `선언`과 정확히 같거나, `선언`보다 **더 깊은**(자식) 경우만 "읽혔다"로
    본다. `_접두어_또는_일치`와 달리 방향이 하나뿐이어야 한다 — 그러지 않으면(대칭으로
    보면) `furniture.band`처럼 부모 dict를 통째로 한 번이라도 건드린 기록이, 그 밑에서
    실제로는 한 번도 개별 키로 안 읽힌 자식 선언(예: 오타 난 `furniture.band.typo_dead`)
    까지 "안 죽었다"로 잘못 덮어써 버린다.
    """
    return any(기록 == 선언 or 기록.startswith(선언 + ".") for 기록 in 기록됨)


def test_비대칭_읽음_판정은_부모_통째_접근을_자식_개별_읽음으로_안_친다():
    """`_자식으로_읽힘`의 계약을 실측 그대로 고정한다 — 세 사례:

    ① 부모(`furniture.band`)만 기록되고 자식(`furniture.band.typo_dead`)은 개별적으로
    한 번도 안 읽힌 경우 — 죽은 자식을 "안 죽음"으로 잘못 덮으면 안 된다(False가 맞다).
    ② 그 키 자체가 정확히 기록된 경우(True). ③ 선언보다 **더 깊은** 자손만 기록된 경우 —
    선언이 `furniture.stamp.pos`인데 엔진이 `도장["pos"]["horzOffset"]`까지 내려가
    "furniture.stamp.pos.horzOffset"만 남긴 모양이다(True가 맞다). ④ 이름이 접두어로만
    겹치는 남남(`furniture.band` ↔ `furniture.bandwidth`)은 자식이 아니다(False가 맞다) —
    비교에 `"."`을 붙이는 이유다.
    """
    assert _자식으로_읽힘("furniture.band.typo_dead", {"furniture.band"}) is False
    assert _자식으로_읽힘("furniture.band.cols", {"furniture.band.cols"}) is True
    assert _자식으로_읽힘("furniture.stamp.pos", {"furniture.stamp.pos.horzOffset"}) is True
    assert _자식으로_읽힘("furniture.band", {"furniture.bandwidth"}) is False


# 선언됐지만(REQUIRED_KEYS) 이 회차가 절대 안 읽는 styles.*/furniture.* 키 — 이름 하나하나에
# 이유를 단다(뭉뚱그린 제외 금지). 채워 보고 실측으로 빈 채 남으면 그것 자체가 "죽은 데이터
# 없음"의 증거이고, 뭔가 남으면 여기 이름과 이유를 적은 뒤 DONE_WITH_CONCERNS로 보고한다.
_죽은_키_제외: dict[str, str] = {}

# docx 판의 (b)에서만 빼는 키 — hwpx 의 떠 있는 도형(원문자 타원·확인도장 글상자)에만 쓰는 값이다.
# docx 는 떠 있는 도형을 쓰지 않아(Word·구글 문서 둘 다 열리게) 이 값들이 들어갈 자리가 없다. 목록은
# 빈 채로 docx 판을 돌려 "안 읽힘"으로 나온 키를 그대로 옮기고 하나씩 이유를 확인해 적었다 — 여기
# 없는 키가 안 읽히면 그것은 docx 백엔드가 킷 값을 빠뜨린 것이다.
_docx_가_안_읽는_키: dict[str, str] = {
    "furniture.circle.curSz": "docx 는 원문자를 글자(❶…)로 쓴다 — 떠 있는 타원의 크기가 없다",
    "furniture.circle.line": "같은 이유 — 타원 테두리가 없다(글자의 안쪽 흰 숫자는 글꼴 모양이다)",
    "furniture.circle.lineWidth": "같은 이유 — 타원 테두리가 없다",
    "furniture.stamp.curSz": "docx 의 도장은 머리띠 표의 칸이라 폭은 본문 폭·band 폭·간격에서, 높이는 머리띠 높이에서 나온다",
    "furniture.stamp.pos.vertOffset": "도장이 표 칸이라 세로 위치가 없다(가로 위치는 간격 칸 계산에 쓴다)",
    "styles.charPr.circle_num": "타원 안 번호 글자 서식 — docx 의 번호 글자는 제목(headline) run 이라 그 크기를 쓴다",
}


@pytest.mark.parametrize("형식", [".hwpx", ".docx"])
def test_런타임_기록으로_REQUIRED_KEYS_커버리지를_양방향으로_본다(킷_루트, tmp_path, monkeypatch, 형식):
    """정적 정규식 감사(test_kit.py)가 구조적으로 못 보는 것 — furniture 읽기·별칭을 거친
    접근·`_셀_역할` 동적 호출 — 을 실제 조판으로 채운다. 블록 10종 + 가구 3종을 전부 쓰는
    같은 회차(`_전체_블록_MD` — 변이 킷 테스트와 같은 문서)를 조판하며 `Kit`의 border_fill·char_pr·para_pr·
    furniture를 읽힌 키를 기록하는 dict로 감싼다. 두 방향을 함께 본다:

    (a) 실제로 읽힌 키 전부가 REQUIRED_KEYS 안(또는 그 접두어/자식)에 있는가 — 선언 안 된
        킷 값에 기대는 코드가 있으면 여기서 걸린다. 대칭 규칙(`_접두어_또는_일치`)을 쓴다 —
        부모 dict를 통째로 쥐어 읽는 코드(예: `도장 = kit.furniture["stamp"]`)가 있으면
        기록된 경로가 REQUIRED_KEYS 개별 leaf보다 얕을 수 있어, 그 경우도 커버로 봐야 한다.
    (b) REQUIRED_KEYS가 선언한 `styles.*`·`furniture.*` 키가 전부 실제로 읽히는가 — 선언만
        되고 한 번도 안 읽히는 키는 죽은 데이터다(이 프로젝트에서 실제로 두 번 있었던
        결함 유형: `accent_shade`/`accent_line`, 그리고 `band_*`가 `add_band`에 실제로
        입혀지기 전). 비대칭 규칙(`_자식으로_읽힘`)을 쓴다 — (a)의 대칭 규칙을 그대로
        재사용하면 부모를 한 번이라도 건드린 기록이 그 밑의 안 읽힌 자식 선언까지
        "읽힘"으로 잘못 덮어써 버린다(실측 재현: 위 `test_비대칭_읽음_판정은_...` 참고).

    두 형식(hwpx·docx)을 따로 조판해 본다 — docx 는 hwpx 의 떠 있는 도형에만 쓰는 키
    (`_docx_가_안_읽는_키`, 이름마다 이유)를 (b)에서 뺀다.
    """
    원본_kit = load_kit(킷_루트)
    기록: set[str] = set()
    기록_킷 = dataclasses.replace(
        원본_kit,
        name="기록킷",
        border_fill=_기록_딕셔너리(dict(원본_kit.border_fill), "border_fill", 기록),
        char_pr=_기록_딕셔너리(dict(원본_kit.char_pr), "char_pr", 기록),
        para_pr=_기록_딕셔너리(dict(원본_kit.para_pr), "para_pr", 기록),
        furniture=_기록_딕셔너리(dict(원본_kit.furniture), "furniture", 기록),
    )
    monkeypatch.setattr(compose_module, "load_kit", lambda root: 기록_킷)
    # docx 는 스타일 번호를 `resolve_kit`이 한꺼번에 푼 값으로 읽는다(`.items()`로 전부 돌아 기록이
    # 안 남는다) — 그래서 푼 값의 dict 를 같은 경로 이름으로 감싸 docx 가 실제로 어느 역할을 쓰는지 본다.
    진짜_resolve_kit = compose_module.resolve_kit
    monkeypatch.setattr(compose_module, "resolve_kit", lambda kit: dataclasses.replace(
        해석 := 진짜_resolve_kit(kit),
        char=_기록_딕셔너리(dict(해석.char), "char_pr", 기록),
        para=_기록_딕셔너리(dict(해석.para), "para_pr", 기록),
        box=_기록_딕셔너리(dict(해석.box), "border_fill", 기록),
    ))

    (tmp_path / "그림.png").write_bytes(_png(20, 20))
    md_경로 = tmp_path / "회차.md"
    md_경로.write_text(_전체_블록_MD("기록킷"), encoding="utf-8")
    out = tmp_path / f"결과{형식}"
    # kit_root 인자는 monkeypatch 탓에 실제로 안 쓰인다 — load_kit이 무엇을 받든 기록_킷을 낸다.
    보고 = compose(md_경로, 킷_루트, out)
    assert 보고.validate_ok is True

    기록_문서_경로 = {_문서_경로로(p) for p in 기록}

    # (a) 실제로 읽힌 키 전부가 REQUIRED_KEYS 커버 안에 있다.
    선언됨 = set(REQUIRED_KEYS)
    커버_안됨 = sorted(경로 for 경로 in 기록_문서_경로 if not _접두어_또는_일치(경로, 선언됨))
    assert 커버_안됨 == [], f"REQUIRED_KEYS에 없는 킷 키를 엔진이 실제로 읽었다: {커버_안됨}"

    # (b) REQUIRED_KEYS가 선언한 styles.*·furniture.* 키가 전부 실제로 읽혔다 — 비대칭 규칙.
    죽은_키 = sorted(
        키 for 키 in 선언됨
        if (키.startswith("styles.") or 키.startswith("furniture."))
        and 키 not in _죽은_키_제외
        and (형식 != ".docx" or 키 not in _docx_가_안_읽는_키)
        and not _자식으로_읽힘(키, 기록_문서_경로)
    )
    assert 죽은_키 == [], (
        f"선언됐지만 이 회차에서 한 번도 안 읽힌 킷 키(죽은 데이터 의심): {죽은_키}"
    )
    if 형식 == ".docx":
        # 빼 둔 키가 나중에 docx 에서 읽히게 되면 목록에서 지운다 — 목록이 낡아 결함을 가리지 않게.
        읽힌_제외 = sorted(키 for 키 in _docx_가_안_읽는_키 if _자식으로_읽힘(키, 기록_문서_경로))
        assert 읽힌_제외 == [], f"docx 가 안 읽는다고 빼 둔 키를 실제로는 읽는다: {읽힌_제외}"
