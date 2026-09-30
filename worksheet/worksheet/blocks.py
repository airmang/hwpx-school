"""본문 블록 계획자 — 마크다운을 알지 못한다(노드만 받는다). 문서 객체도 모른다: 블록마다
무엇을 그릴지(`worksheet.plan`)만 내고, 그리기는 형식별 백엔드(`worksheet.backends.*`)가 한다.

블록 하나를 두 번 기술하지 않는다: 어떤 속성이 필수인지·정수여야 하는지·본문을 쓰는지는
아래 `SPECS`(선언표) 하나에만 적는다. `fence_problems()`가 그 표를 읽어 계획자를 실행하기
**전에** 거짓 통과를 잡고, `plan_node()`는 문제가 있으면 계획하지 않고 거부한다 — 펜스
속성 문법이 계획자 코드 안에만 있으면, M-1(`worksheet.checks.check_markdown`)이 계획자를
실행해 보지 않고는 이런 문제를 볼 수 없다 — 그 구멍을 구조적으로 닫는다.
"""

from __future__ import annotations

import math
import re
import struct
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from worksheet.kit import Kit
from worksheet.md import Body, Fence, Figure, FigureLine, Node, Prompt, parse_figure
from worksheet.plan import BlockPlan, CellPlan, FigurePlan, ParagraphPlan, PicturePlan, TablePlan
from worksheet.vocab import FENCE_BLOCKS, STRUCTURAL_BLOCKS


def png_size(data: bytes) -> tuple[int, int]:
    # 길이를 먼저 본다 — 시그니처+IHDR 표까지만 있고(16~23바이트) 가로세로 4+4바이트가
    # 없는 조각은 길이 확인 없이 struct.unpack에 곧장 넘기면 ValueError가 아니라
    # struct.error로 터진다 — [기계] 검사가 트레이스백을 내면 안 된다.
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("PNG만 지원한다 — 그림은 matplotlib/PIL로 PNG 생성")
    return struct.unpack(">II", data[16:24])


def 그림_폭_문제(kit: Kit, width_mm: float | None, 자리: str) -> str | None:
    """그림 폭이 본문 폭보다 넓은가 — 넓으면 문구를, 아니면 `None`.

    칸 안 그림은 계획자가 칸 폭으로 줄이지만, 본문 그림 줄은 그대로 그려져 용지 밖으로 나가고
    칸 안 그림도 본문보다 넓게 쓴 값은 오타에 가깝다 — 둘 다 조판 전에 거부한다. 상한 문구의
    cm 값은 0.1cm 단위로 내려 적어 그 값을 그대로 써도 통과한다.
    """
    if width_mm is None or round(width_mm * _MM_HWPUNIT) <= kit.body_width:
        return None
    상한_cm = math.floor(kit.body_width / _MM_HWPUNIT) / 10
    return f"{자리} 폭이 본문 폭보다 넓다: {width_mm / 10:g}cm — {상한_cm:g}cm 이하로 쓴다"


def _칸_그림_문제(
    블록: str, 글: str, *, base_dir: Path | None, kit: Kit | None = None,
) -> str | None:
    """칸 글자 하나가 그림 줄이면 그 파일·형식에 문제가 있는지 본다 — 없으면(보통 글자
    포함) `None`.

    `fence_problems`(M-1, 계획 전 검사)와 `_칸_그림_계획`(계획 시점, 아래) 둘이 이 함수를
    같이 쓴다 — `png_size`가 이미 `check_markdown`과 `plan_node`(본문 그림) 둘 다에게 하는 일과 같은
    역할이다. 판별은 `parse_figure`와 같은 규칙(`text.startswith("![")`)을 여기서 다시
    보는 이유: `parse_figure`는 "그림 줄이 아니다"와 "형식이 틀렸다"를 구별하지 않고 둘 다
    `None`을 내므로(md.py의 docstring 참고), 그 둘을 가르는 일은 맥락을 아는 호출자 몫이다
    — 이 칸 검사의 맥락은 "블록 이름 + 칸 글자 그대로"다(본문 그림 줄의 줄 번호 문형과 다르다).

    `base_dir`가 없으면 파일 존재·PNG 유효성은 건너뛴다(형식 오류는 파일이 있어야 아는 게
    아니므로 그대로 본다) — `check_markdown`의 기존 base_dir=None 호환 규칙과 같다. `kit`이
    있으면 본문 폭 대비 상한(`그림_폭_문제`)도 본다 — 길이 속성의 상한과 같은 규칙이다.
    """
    if not 글.startswith("!["):
        return None
    줄 = parse_figure(글)
    if 줄 is None:
        return (
            f"{블록} 블록의 칸에 쓴 그림 줄을 읽을 수 없다: {글} — 형식: ![](경로){{width=8cm}}"
        )
    if kit is not None and (폭_문제 := 그림_폭_문제(kit, 줄.width_mm, f"{블록} 블록의 칸 그림")):
        return 폭_문제
    if base_dir is None:
        return None
    경로 = Path(base_dir) / 줄.path
    if not 경로.is_file():
        return f"그림 파일이 없다: {줄.path}"
    try:
        png_size(경로.read_bytes())
    except ValueError as e:
        return f"{e}: {줄.path}"
    return None


def _필수_속성_없음(블록: str, 속성: str) -> str:
    """`_attr`과 `fence_problems`가 같은 문구를 내도록 — 문구를 만드는 함수는 하나만 둔다."""
    return f"{블록} 블록에 {속성}= 가 없다"


def _raw_attr(fence: Fence, 속성: str) -> str:
    """속성값을 읽어 앞뒤 공백을 지운다 — 빈 문자열이면 "없음"과 같은 뜻이다.

    `fence_problems`(필수·정수 검사)와 `_int_attr`(계획자의 정수 읽기)가 "없음"의 뜻을
    이 함수 하나로 같이 정한다 — 둘이 따로 정하면, `fence_problems`는 빈 값을 "없음 →
    기본값"으로 건너뛰는데 계획자가 `fence.attrs.get(name, 기본값)`으로 읽어 **있지만 빈**
    값을 그대로 `int()`에 넣어 영문 `invalid literal for int()`로 죽을 수 있다.
    """
    return fence.attrs.get(속성, "").strip()


def _int_attr(fence: Fence, 속성: str, 기본값: int) -> int:
    """정수 속성을 읽는다 — 없거나 빈 값이면 기본값, 있으면 `int(...)`.

    `plan_node`가 `fence_problems`로 미리 걸러 준 뒤라 여기서 `int()`가 실패할 일은
    정상 경로에 없다 — `_attr`과 같은 이유로 계획자를 직접 부르는 호출에 대비한 안전망이다.
    계획자에 `int(fence.attrs.get(...))` 직접 호출을 남기지 않는다 — 이 함수 하나로만 읽는다.
    """
    원본값 = _raw_attr(fence, 속성)
    return int(원본값) if 원본값 else 기본값


# --- 길이 속성(`3cm`·`30mm`) — HWPUNIT로 읽는다. 정수 속성과 같은 설계다: "빈 값 = 없음" ------

_길이값 = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(cm|mm)\s*$")
_MM_HWPUNIT = 7200 / 25.4  # mm → HWPUNIT 환산 상수 — 킷이 정하는 양식 값이 아니라 단위 정의다
# (tests/test_kit_swap.py 의 변이 킷 테스트가 "검사 대상에서 뺀 것"과 같은 이유다: kit.json
# 어디에도 없는 값이라 그 테스트의 원시·파생 값 걷기에 애초에 안 걸린다.)

# python-hwpx의 add_table()이 새로 만드는 모든 칸에 주는 셀 안쪽 여백(6.4.0 실측:
# oxml/_document_primitives.py의 _default_cell_inner_margin_attributes, "Hancom's new-table
# cell padding: 1.8mm left/right, 0.5mm top/bottom" — 실제 Hancom 문서에서 잰 값이라고
# 라이브러리 스스로 적어 뒀다). _MM_HWPUNIT과 같은 이유로 킷 값이 아니다: kit.json 이
# 어떻게 바뀌어도 이 여백은 그대로다(라이브러리가 구조적으로 고정한다) — 칸 안 그림의
# "칸 폭 − 좌우 여백"(폭 생략 시 기본)·"그림 높이 + 칸 상하 여백"(그림 행 높이) 계산에 쓴다.
_칸_여백_좌우 = 510 * 2
_칸_여백_상하 = 141 * 2


def _length_attr(fence: Fence, 속성: str) -> int | None:
    """길이 속성(`3cm`·`30mm` 꼴)을 HWPUNIT 정수로 읽는다 — 없거나 빈 값이면 None.

    `fence_problems`와 `_라벨설명`이 이 함수 하나를 같이 쓴다 — 정수 속성의 `_raw_attr`/
    `_int_attr`와 같은 설계다: "빈 값 = 없음 = 기본값". 꼴이 틀리거나 0 이하이면 (블록
    이름을 포함한) 최종 문구로 여기서 바로 거부한다 — `fence_problems`는 이 예외를 그대로
    문제 목록에 옮긴다(`_라벨설명`이 이 함수를 직접 부르는 정상 경로에서는 `fence_problems`가
    미리 걸러 준 뒤라 이 예외가 나올 일이 없다 — `_int_attr`와 같은 이유의 안전망이다).
    본문 폭 대비 상한(킷이 있어야 아는 값)은 여기서 보지 않는다 — 이 함수는 kit을 받지
    않는다. `fence_problems`가 kit이 있을 때만 따로 본다.
    """
    원본값 = _raw_attr(fence, 속성)
    if not 원본값:
        return None
    m = _길이값.match(원본값)
    if m is None:
        raise ValueError(
            f"{fence.name} 블록의 {속성}= 는 '3cm' 또는 '30mm' 꼴이어야 한다: {원본값!r}"
        )
    수, 단위 = float(m.group(1)), m.group(2)
    mm = 수 * 10 if 단위 == "cm" else 수
    값 = round(mm * _MM_HWPUNIT)
    if 값 <= 0:
        raise ValueError(f"{fence.name} 블록의 {속성}= 는 0보다 커야 한다: {원본값!r}")
    return 값


def _알려진_속성(spec: BlockSpec) -> frozenset[str]:
    """이 블록이 아는 속성 이름 전부 — required ∪ ints ∪ lengths ∪ 블록별 선택 속성.

    "모르는 속성" 판정이 이 함수 하나로 계산하므로, 허용 속성표를 `SPECS`와 따로 손으로
    관리하지 않는다.
    """
    return (
        frozenset(spec.required)
        | {속성 for 속성, _최솟값 in spec.ints}
        | frozenset(spec.lengths)
        | frozenset(spec.optional)
    )


def _모르는_속성_문구(블록: str, 속성: str, 알려진: frozenset[str]) -> str:
    if not 알려진:
        return f"{블록} 블록이 모르는 속성: {속성} — 이 블록은 속성을 받지 않는다"
    return f"{블록} 블록이 모르는 속성: {속성} — 쓸 수 있는 속성: {', '.join(sorted(알려진))}"


# --- 비교표·데이터표의 "펜스 본문이 표보다 크다" ---------------------------------------------
# fence_problems() 가 계획자보다 먼저 이 크기를 본다 — 계획자(_비교표_계획/_데이터표_계획)는 넘치는
# 값을 조용히 자르는 쪽(본문[:행수] 등)을 그대로 유지하지만, fence_problems 가 먼저 거부하는
# 정상 경로에서는 그 자름이 절대 일어나지 않는다(BlockSpec.body_shape로 SPECS 하나에 엮는다).


def _비교표_본문_문제(fence: Fence) -> list[str]:
    열원본 = _raw_attr(fence, "cols")
    행원본 = _raw_attr(fence, "rows")
    if not 열원본 or not 행원본:
        return []  # 필수 속성 검사(required)가 이미 잡는다 — 여기서 중복 보고하지 않는다

    열들 = 열원본.split("|")
    행들 = 행원본.split("|")
    본문 = [줄 for 줄 in fence.body.splitlines() if 줄.strip()]

    문제: list[str] = []
    if len(본문) > len(행들):
        문제.append(f"비교표 본문이 표보다 크다: {len(본문)}줄 > rows {len(행들)}")
    for i, 줄 in enumerate(본문[: len(행들)], start=1):
        칸수 = len(줄.split("|"))
        if 칸수 > len(열들):
            문제.append(f"비교표 본문 {i}번째 줄이 표보다 넓다: {칸수}칸 > cols {len(열들)}칸")
    return 문제


def _데이터표_본문_문제(fence: Fence) -> list[str]:
    머리원본 = _raw_attr(fence, "head")
    if not 머리원본:
        return []  # 필수 속성 검사가 이미 잡는다

    머리 = 머리원본.split("|")
    본문 = [줄 for 줄 in fence.body.splitlines() if 줄.strip()]
    행수원본 = _raw_attr(fence, "rows")
    if 행수원본:
        try:
            행수 = int(행수원본)
        except ValueError:
            return []  # 정수 검사(ints)가 이미 잡는다 — 형 오류를 두 번 보고하지 않는다
        if 행수 < 1:
            # 범위 검사(ints, 최솟값 1)가 이미 "1 이상이어야 한다"로 잡는다 — 여기서도
            # 행수=0/-1 을 그대로 쓰면 "본문이 표보다 크다: N줄 > rows -1"처럼 교사가
            # 손댈 수 없는 문구가 같이 나온다 — 형 오류와 같은 설계로 건너뛴다.
            return []
    else:
        행수 = len(본문) or 1  # rows= 없이 본문만 있으면 행수는 본문 줄 수라 넘칠 수 없다

    문제: list[str] = []
    if 행수원본 and len(본문) > 행수:
        문제.append(f"데이터표 본문이 표보다 크다: {len(본문)}줄 > rows {행수}")
    for i, 줄 in enumerate(본문[:행수], start=1):
        칸수 = len(줄.split("|"))
        if 칸수 > len(머리):
            # 데이터표에는 cols= 속성이 없다(열은 head=로 준다) — 문구가 없는 속성을
            # 가리키면 교사가 헤맨다.
            문제.append(f"데이터표 본문 {i}번째 줄이 표보다 넓다: {칸수}칸 > head {len(머리)}칸")
    return 문제


def _나란히_본문_문제(fence: Fence) -> list[str]:
    열원본 = _raw_attr(fence, "cols")
    if not 열원본:
        return []  # 필수 속성 검사(required)가 이미 잡는다

    열들 = 열원본.split("|")
    if len(열들) < 2:
        # 한 단짜리는 나란히로 쓸 뜻이 없다 — 정의빈칸·답칸으로 쓴다. cols 개수 자체가 근본 원인이라
        # 그 아래 "본문 줄이 넓다" 검사를 이 열 수 기준으로 계속하면 교사가 손댈 수 없는
        # 문구가 같이 나온다(범위 검사가 이미 잡으면 본문 크기 검사를 건너뛰는 것과 같은
        # 설계 — 데이터표의 rows=0/-1 처리 참고).
        return [f"나란히 블록의 cols= 는 2칸 이상이어야 한다: {len(열들)}칸"]

    본문 = [줄 for 줄 in fence.body.splitlines() if 줄.strip()]
    행수원본 = _raw_attr(fence, "rows")
    if 행수원본:
        try:
            행수 = int(행수원본)
        except ValueError:
            return []  # 정수 검사(ints)가 이미 잡는다
        if 행수 < 1:
            return []  # 범위 검사(ints, 최솟값 1)가 이미 잡는다
    else:
        행수 = len(본문) or 1  # rows= 없이 본문만 있으면 행수는 본문 줄 수다(데이터표와 같은 규약)

    문제: list[str] = []
    if 행수원본 and len(본문) > 행수:
        문제.append(f"나란히 본문이 표보다 크다: {len(본문)}줄 > rows {행수}")
    for i, 줄 in enumerate(본문[:행수], start=1):
        칸수 = len(줄.split("|"))
        if 칸수 > len(열들):
            문제.append(f"나란히 본문 {i}번째 줄이 표보다 넓다: {칸수}칸 > cols {len(열들)}칸")
    return 문제


# --- 칸 안 그림 후보 — 각 블록의 "본문 칸"(들어오는 값이 곧 셀 글자가 되는 자리) 중
# 그림 줄일 수 있는 자리만 고른다. 머리행·라벨열처럼 cols=/rows=/head= **속성값**으로
# 오는 칸은 후보에서 뺀다 — 그 값은 펜스 머리 줄(속성)에 적으므로 그림 줄 문법
# (`![](경로){width=8cm}`)을 쓸 자리가 아니다(펜스 본문 줄에서 오는 칸만 후보다). `fence_problems`가
# 이 후보 각각에 `_칸_그림_문제`를 적용하고, 계획자는 같은 후보를 `_행_계획`으로 다시
# 걸어 실제로 그림을 앉힌다 — 두 쪽이 같은 함수로 "어떤 칸이 후보인가"를 정하므로 어긋날
# 수 없다.


def _나란히_칸_후보(fence: Fence) -> list[str]:
    열원본 = _raw_attr(fence, "cols")
    if not 열원본:
        return []
    열들 = 열원본.split("|")
    if len(열들) < 2:
        return []  # cols 문제는 body_shape 가 이미 잡는다
    본문 = [줄 for 줄 in fence.body.splitlines() if 줄.strip()]
    행수원본 = _raw_attr(fence, "rows")
    try:
        행수 = int(행수원본) if 행수원본 else (len(본문) or 1)
    except ValueError:
        return []  # 정수 검사가 이미 잡는다
    if 행수 < 1:
        return []  # 범위 검사가 이미 잡는다
    후보: list[str] = []
    for 줄 in 본문[:행수]:
        후보 += [c.strip() for c in 줄.split("|")[: len(열들)]]
    return 후보


def _비교표_칸_후보(fence: Fence) -> list[str]:
    열원본 = _raw_attr(fence, "cols")
    행원본 = _raw_attr(fence, "rows")
    if not 열원본 or not 행원본:
        return []
    열들 = 열원본.split("|")
    행들 = 행원본.split("|")
    본문 = [줄 for 줄 in fence.body.splitlines() if 줄.strip()]
    후보: list[str] = []
    for 줄 in 본문[: len(행들)]:
        후보 += [c.strip() for c in 줄.split("|")[: len(열들)]]
    return 후보


def _데이터표_칸_후보(fence: Fence) -> list[str]:
    머리원본 = _raw_attr(fence, "head")
    if not 머리원본:
        return []
    머리 = 머리원본.split("|")
    본문 = [줄 for 줄 in fence.body.splitlines() if 줄.strip()]
    행수원본 = _raw_attr(fence, "rows")
    try:
        행수 = int(행수원본) if 행수원본 else (len(본문) or 1)
    except ValueError:
        return []
    if 행수 < 1:
        return []
    후보: list[str] = []
    for 줄 in 본문[:행수]:
        후보 += [c.strip() for c in 줄.split("|")[: len(머리)]]
    return 후보


def _용어카드_칸_후보(fence: Fence) -> list[str]:
    열원본 = _raw_attr(fence, "cols")
    if not 열원본:
        return []
    열들 = 열원본.split("|")
    설명들 = [줄.strip() for 줄 in fence.body.splitlines() if 줄.strip()]
    return 설명들[: len(열들)]


def _라벨설명_칸_후보(fence: Fence) -> list[str]:
    # 설명 칸만 후보다 — 라벨은 짧은 표제어 자리라 그림 줄을 쓸 자리로 보지 않는다.
    try:
        쌍 = parse_pairs(fence.body)
    except ValueError:
        return []  # 본문 형식 문제는 needs_body 검사가 이미 잡는다
    return [설명 for _라벨, 설명 in 쌍]


@dataclass(frozen=True)
class BlockSpec:
    required: tuple[str, ...] = ()          # 없으면 안 되는 속성(빈 문자열도 없는 것으로 본다)
    ints: tuple[tuple[str, int], ...] = ()  # (속성, 최솟값) — 있으면 정수여야 하는 속성
    lengths: tuple[str, ...] = ()           # 있으면 길이 값(`3cm`·`30mm`)이어야 하는 속성 — HWPUNIT로 읽는다
    optional: tuple[str, ...] = ()          # required·ints·lengths가 아닌, 이 블록이 아는 나머지 속성
    uses_body: bool = True                  # 펜스 본문을 읽는가
    needs_body: bool = False                # 본문이 비면 그릴 것이 없는가
    body_shape: Callable[[Fence], list[str]] | None = None    # 본문이 표 크기를 넘는가(위 절 참고)
    picture_cells: Callable[[Fence], list[str]] | None = None  # 그림 줄일 수 있는 본문 칸 후보(위 절 참고)


SPECS: dict[str, BlockSpec] = {
    "라벨설명": BlockSpec(needs_body=True, lengths=("labelWidth",), picture_cells=_라벨설명_칸_후보),
    "용어카드": BlockSpec(required=("cols",), picture_cells=_용어카드_칸_후보),
    "비교표": BlockSpec(
        required=("cols", "rows"), body_shape=_비교표_본문_문제, picture_cells=_비교표_칸_후보
    ),
    "데이터표": BlockSpec(
        required=("head",), ints=(("rows", 1),),
        body_shape=_데이터표_본문_문제, picture_cells=_데이터표_칸_후보,
    ),
    # label 은 M-4 와 전용 문구(_답칸)가 맡는다(required가 아니다) — optional에는 넣어
    # "모르는 속성" 판정만 면한다.
    "답칸": BlockSpec(ints=(("lines", 1),), uses_body=False, optional=("label",)),
    "강조박스": BlockSpec(optional=("title",)),
    # 열 수 = cols 칸 수(2 이상) · rows=N 은 데이터표와 같은 규약(빈 본문행 수, 기본 1).
    "나란히": BlockSpec(
        required=("cols",), ints=(("rows", 1),),
        body_shape=_나란히_본문_문제, picture_cells=_나란히_칸_후보,
    ),
}
STRUCTURAL: dict[str, type] = {"정의빈칸": Body, "발문": Prompt, "그림칸": Figure}


def _attr(fence: Fence, name: str) -> str:
    """펜스의 필수 속성을 읽는다. 없으면 md.py와 같은 오류 문형으로 거부한다.

    `plan_node`가 `fence_problems`로 미리 걸러 준 뒤라 이 예외는 정상 경로에서는 나오지
    않는다 — 그래도 계획자를 직접 부르는 호출(가령 미래의 리팩터)에 대비한 안전망으로 둔다.
    """
    값 = _raw_attr(fence, name)
    if not 값:
        raise ValueError(_필수_속성_없음(fence.name, name))
    return 값



def parse_pairs(body: str) -> list[tuple[str, str]]:
    """'[N] 라벨' 다음 줄 ': 설명' 쌍을 읽는다."""
    쌍: list[tuple[str, str]] = []
    라벨: str | None = None
    for 줄 in body.splitlines():
        벗김 = 줄.strip()
        if not 벗김:
            continue
        if 벗김.startswith(":"):
            if 라벨 is None:
                raise ValueError(f"라벨 없는 설명: {벗김}")
            쌍.append((라벨, 벗김[1:].strip()))
            라벨 = None
        else:
            라벨 = 벗김
    if 라벨 is not None:
        쌍.append((라벨, ""))
    return 쌍


def fence_problems(
    fence: Fence, kit: Kit | None = None, *, base_dir: Path | None = None
) -> list[str]:
    """펜스 하나가 실제로 그려질 수 있는지 — `SPECS`(선언표) 하나로 판정한다.

    `check_markdown`(M-1)과 `plan_node`가 이 함수 하나를 같이 불러야 "M-1 초록불 ⇒ 조판이
    거부하지 않는다"가 구조적으로 성립한다. `SPECS`에 없는 이름(엔진이 모르는 블록)에는
    빈 리스트를 낸다 — 이름 자체가 문제라는 판정은 호출자(check_markdown/plan_node)의
    몫이라 여기서 중복 보고하지 않는다.

    `kit`은 선택이다 — 없으면 길이 속성(`lengths`)의 꼴·0 이하까지만 보고, 본문 폭 대비
    상한(킷이 있어야 아는 값)은 건너뛴다. `check_markdown`과 `plan_node`는 항상 kit을
    넘긴다 — kit 없이 부르는 기존 호출·테스트는 그 상한 검사만 못 볼 뿐 그대로 동작한다.

    `base_dir`도 선택이다(기본 `None`) — 없으면 칸 안 그림의 파일 존재·PNG 유효성 검사만
    건너뛴다(형식 오류는 파일이 있어야 아는 게 아니므로 그대로 본다). `check_markdown`과
    `plan_node`는 둘 다 `base_dir`를 넘긴다 — 기존 호출·테스트는 그 파일 검사만 못 볼 뿐
    그대로 동작한다(`_칸_그림_문제`의 규칙과 같다).
    """
    spec = SPECS.get(fence.name)
    if spec is None:
        return []

    문제: list[str] = []

    알려진 = _알려진_속성(spec)
    문제 += [
        _모르는_속성_문구(fence.name, 속성, 알려진)
        for 속성 in sorted(fence.attrs)
        if 속성 not in 알려진
    ]

    for 속성 in spec.required:
        if not _raw_attr(fence, 속성):
            문제.append(_필수_속성_없음(fence.name, 속성))

    for 속성, 최솟값 in spec.ints:
        원본값 = _raw_attr(fence, 속성)
        if not 원본값:
            continue  # required 가 아니면 _int_attr 가 기본값을 쓴다 — 계획자와 규칙이 같다
        try:
            값 = int(원본값)
        except ValueError:
            문제.append(f"{fence.name} 블록의 {속성}= 는 정수여야 한다: {원본값!r}")
            continue
        if 값 < 최솟값:
            문제.append(f"{fence.name} 블록의 {속성}= 는 {최솟값} 이상이어야 한다: {값}")

    for 속성 in spec.lengths:
        원본값 = _raw_attr(fence, 속성)
        if not 원본값:
            continue  # required 가 아니면 _length_attr 가 None을 내고 계획자가 킷 기본값을 쓴다
        try:
            값 = _length_attr(fence, 속성)
        except ValueError as e:
            문제.append(str(e))
            continue
        if kit is not None and 값 >= kit.body_width - kit.furniture["labelWidth"]:
            문제.append(
                f"{fence.name} 블록의 {속성}= 가 너무 넓다: {원본값!r} — 설명 칸이 남지 않는다"
            )

    if spec.needs_body:
        try:
            쌍 = parse_pairs(fence.body)
        except ValueError as e:
            문제.append(str(e))
        else:
            if not fence.body.strip() or not 쌍:
                문제.append(f"{fence.name} 블록에 본문이 없다")

    if not spec.uses_body and fence.body.strip():
        줄수 = len(fence.body.splitlines())
        문제.append(f"{fence.name} 블록은 본문을 쓰지 않는다 — {줄수}줄이 무시된다")

    if spec.body_shape is not None:
        문제 += spec.body_shape(fence)

    if spec.picture_cells is not None:
        문제 += [
            그림문제
            for 후보 in spec.picture_cells(fence)
            if (그림문제 := _칸_그림_문제(fence.name, 후보, base_dir=base_dir, kit=kit)) is not None
        ]

    return 문제



# --- 칸 안 그림 — 계획은 파일 경로·배치 크기·원본 픽셀 크기만 정한다. 이진 항목 등록(같은
# 파일은 조판 1회 안에서 한 번만)은 형식별 백엔드가 맡는다 ------------------------------------


def _칸_그림_계획(블록: str, 글: str, 칸_폭: int, *, base_dir: Path) -> tuple[str, PicturePlan | None]:
    """칸 글자 하나를 계획한다 — 그림 줄이면 `("", 그림 계획)`을, 보통 글자면 `(글, None)`을 낸다.

    `plan_node`를 거치는 정상 경로에서는 `fence_problems`(base_dir 포함)가 이미 파일
    존재·PNG 유효성·형식을 검사했다 — 그래도 `_칸_그림_문제`를 여기서 다시 거친다(`_attr`·
    `_int_attr`·`_length_attr`와 같은 이유의 안전망: 계획자를 직접 부르는 호출에 대비한다).

    그림 경로는 절대경로로 둔다 — 백엔드가 이 경로를 등록 캐시 키로 쓰므로, 같은 파일을
    상대경로 표기만 다르게 적어도(예: `그림/a.png`와 `./그림/a.png`) 같은 파일로 묶인다.

    폭: `width=` 생략 시 칸 폭(− 좌우 여백)에 맞춘다. 주어진 폭이 칸보다 넓으면 칸 폭으로
    줄인다(잘리는 것보다 낫다) — `min()` 하나가 생략·초과 두 경우를 같이 처리한다. 높이는
    PNG 원본 비율로 계산한다.
    """
    if not 글.startswith("!["):
        return 글, None
    문제 = _칸_그림_문제(블록, 글, base_dir=base_dir)
    if 문제:
        raise ValueError(문제)
    줄: FigureLine = parse_figure(글)  # type: ignore[assignment]  # 위 _칸_그림_문제가 이미 형식을 확인했다
    경로 = (Path(base_dir) / 줄.path).resolve()
    가로, 세로 = png_size(경로.read_bytes())
    안쪽_폭 = 칸_폭 - _칸_여백_좌우
    요청_폭 = round(줄.width_mm * _MM_HWPUNIT) if 줄.width_mm is not None else 안쪽_폭
    배치_폭 = min(요청_폭, 안쪽_폭)
    return "", PicturePlan(경로, 배치_폭, round(배치_폭 * 세로 / 가로), 가로, 세로)


def _행_계획(
    블록: str, 칸_글자들: list[str], 칸_폭: int, *, base_dir: Path, 기본_높이: int,
) -> tuple[list[tuple[str, PicturePlan | None]], int]:
    """한 행의 칸 글자를 전부 계획해 (칸별 (글, 그림) 목록, 이 행에 필요한 높이)를 낸다.

    표 높이(행 높이 합)를 표보다 먼저 알아야 한다 — 그래서 계획자는 행마다 이 함수로 높이를
    먼저 정하고 그 합을 `TablePlan.height`에 적는다. `기본_높이`
    (역할의 kit rowHeight)는 **바닥값**이다 — 그림이 하나도 없는 행은 그대로 쓰고, 그림이
    있는 행은 "그림 높이 + 칸 상하 여백" 중 가장 큰 값과 `기본_높이`를 같이 비교해 더 큰
    쪽을 쓴다(그림이 여럿이면 그중 최댓값도 같이 겨룬다). 큰 그림 쪽은 실측해 골랐다:
    표준 킷의 rowHeight.cell(2131
    HWPUNIT ≈ 7.5mm)은 한 줄 글자 높이로 튜닝된 값이라, 보통 크기의 그림(예: 폭 3cm에 흔한
    가로세로비)보다 훨씬 작다 — 그대로 두면 그림이 칸보다 커서 잘린다(실측: tests/
    test_blocks.py의 나란히 그림 행 높이 테스트가 이 계산값을 그대로 확인한다). **작은
    그림 쪽도 실측으로 확인했다**: 그림이 `기본_높이`보다 작을 수 있고
    (예: 폭 1cm), 그때 계산값만 쓰면 행 전체가 `기본_높이` 아래로 내려가 같은 행의 **글자
    칸**까지 킷 행높이보다 낮아진다 — `기본_높이`를 바닥으로 같이 겨루면 이 사고가 없다.
    """
    칸들 = [_칸_그림_계획(블록, 글, 칸_폭, base_dir=base_dir) for 글 in 칸_글자들]
    그림_높이들 = [그림.height + _칸_여백_상하 for _글, 그림 in 칸들 if 그림 is not None]
    return 칸들, max(그림_높이들 + [기본_높이])


def _본문_칸_글자들(본문: list[str], 행: int, 열수: int) -> list[str]:
    """펜스 본문의 `행`번째 줄을 `|`로 나눠 정확히 `열수`칸으로 맞춘다 — 모자라면 빈칸(학생이
    채울 칸), 줄이 아예 없어도 빈칸 행이다(빈 칸에도 서식을 입힌다는 원칙)."""
    return [c.strip() for c in ((본문[행].split("|") if 행 < len(본문) else []) + [""] * 열수)[:열수]]


# --- 블록 계획자 — 행은 위에서 아래, 칸은 왼쪽에서 오른쪽 순서다 --------------------------------


def _정의빈칸_계획(kit: Kit, node: Body) -> TablePlan:
    return TablePlan(
        "정의빈칸", ((CellPlan("cell", node.text),),), height=kit.furniture["rowHeight"]["cell"]
    )


def _라벨설명_계획(kit: Kit, fence: Fence, base_dir: Path) -> TablePlan:
    쌍 = parse_pairs(fence.body)
    # labelWidth= 를 회차가 주면 그 폭을, 생략하면 킷의 기본 라벨 칸 폭을 쓴다 — fence_problems
    # 가 계획 전에 꼴·범위(0 이하·본문 폭 대비 상한)를 이미 확인했으므로 여기서는 값 하나만
    # 고르면 된다.
    라벨폭 = _length_attr(fence, "labelWidth")
    if 라벨폭 is None:
        라벨폭 = kit.furniture["labelWidth"]
    설명폭 = kit.body_width - 라벨폭

    # 설명 칸만 그림 줄 후보다(라벨은 표제어라 받지 않는다 — _라벨설명_칸_후보와 같은 범위).
    행들 = [
        _행_계획(fence.name, [설명], 설명폭, base_dir=base_dir, 기본_높이=kit.furniture["rowHeight"]["cell"])
        for _라벨, 설명 in 쌍
    ]
    # 라벨 칸도 설명 칸과 같은 행높이를 쓴다 — 한 행의 두 칸이 높이만 다르면
    # 안 된다(label 기본 높이를 쓰면 셀마다 어긋난다).
    rows = tuple(
        (
            CellPlan("label", 라벨, width=라벨폭, height=행높이),
            CellPlan("cell", 칸들[0][0], picture=칸들[0][1], width=설명폭, height=행높이),
        )
        for (라벨, _설명), (칸들, 행높이) in zip(쌍, 행들)
    )
    return TablePlan("라벨설명", rows, height=sum(높이 for _칸들, 높이 in 행들))


def _용어카드_계획(kit: Kit, fence: Fence, base_dir: Path) -> TablePlan:
    라벨들 = [c.strip() for c in _attr(fence, "cols").split("|")]
    설명들 = [줄.strip() for 줄 in fence.body.splitlines() if 줄.strip()]
    후보 = (설명들 + [""] * len(라벨들))[: len(라벨들)]  # 모자라면 빈칸, 넘치면 자른다(기존과 같다)
    # 그림 칸 크기 계산에 쓸 열 폭 — `plan.column_widths`의 균등 분배(python-hwpx
    # equalize_column_widths()와 같다)는 앞 n-1개 열이 round(W/n), 마지막 열이
    # W - round(W/n)*(n-1)이다 — 그래서 마지막 열이 `W // n`보다 최대 몇 HWPUNIT 작을 수 있다
    # (실측: bodyWidth 50460·7열이면 7209×6 + 마지막 7206, `W // 7`=7208보다 2 작다).
    # `bodyWidth // 열수`는 그래서 엄밀한 하한이 아니다 — 다만 이 차이는 몇 HWPUNIT
    # (≈0.01mm 이하) 수준이라 그림이 칸 안쪽 폭(칸 여백 1020을 뺀 값)보다 그만큼 넓게
    # 잡힐 수 있는 자리는 인쇄·화면에서 안 보인다(격차가 여백 자체보다 두 자릿수 이상
    # 작다). 그래도 우연히 정확한 하한이 필요해지면 이 식이 아니라 마지막 열 너비
    # (`bodyWidth - round(bodyWidth/열수)*(열수-1)`)로 다시 계산해야 한다.
    칸들, 설명_높이 = _행_계획(
        fence.name, 후보, kit.body_width // len(라벨들),
        base_dir=base_dir, 기본_높이=kit.furniture["rowHeight"]["cell"],
    )
    rows = (
        tuple(CellPlan("label", 라벨) for 라벨 in 라벨들),
        tuple(CellPlan("cell", 글, picture=그림, height=설명_높이) for 글, 그림 in 칸들),
    )
    return TablePlan(
        "용어카드", rows, height=kit.furniture["rowHeight"]["label"] + 설명_높이, equal_columns=True
    )


def _비교표_계획(kit: Kit, fence: Fence, base_dir: Path) -> TablePlan:
    열들 = [c.strip() for c in _attr(fence, "cols").split("|")]
    행들 = [r.strip() for r in _attr(fence, "rows").split("|")]
    # 펜스 안이 비면 학생이 채울 빈칸, 내용이 있으면 그 내용을 앉힌다.
    # fence_problems(body_shape=_비교표_본문_문제)가 계획 전에 이미 크기를 확인했으므로
    # 여기서는 자르지 않고 그대로 채운다.
    본문 = [줄 for 줄 in fence.body.splitlines() if 줄.strip()]
    기본_열폭 = kit.body_width // (len(열들) + 1)  # 용어카드의 같은 주석 참고 — 엄밀한 하한이 아니라 근사, 그 이유가 거기 있다
    # 머리열(열0)은 그림 후보가 아니다(_비교표_칸_후보와 같은 범위) — 본문 칸(열 1..)만 계획한다.
    데이터 = [
        _행_계획(fence.name, _본문_칸_글자들(본문, 행, len(열들)), 기본_열폭,
                 base_dir=base_dir, 기본_높이=kit.furniture["rowHeight"]["cell"])
        for 행 in range(len(행들))
    ]
    # "한 행 = 한 높이"가 일반 규칙이다: 머리 행은 label 높이, 데이터 행은 그 행의
    # 실제 필요 높이(글자면 rowHeight.cell, 그림이 있으면 그 중 가장 큰 계산값) — 머리열
    # (열0)도 예외가 아니다(라벨설명과 같은 처리). 그렇지 않으면 한 행 안에서 라벨 칸과
    # 본문 칸의 높이가 서로 달라진다.
    머리 = (CellPlan("label", ""),) + tuple(CellPlan("label", 이름) for 이름 in 열들)
    몸 = tuple(
        (CellPlan("label", 이름, height=행높이),)
        + tuple(CellPlan("cell", 값, picture=그림, height=행높이) for 값, 그림 in 칸들)
        for 이름, (칸들, 행높이) in zip(행들, 데이터)
    )
    return TablePlan(
        "비교표", (머리, *몸),
        height=kit.furniture["rowHeight"]["label"] + sum(h for _c, h in 데이터), equal_columns=True,
    )


def _데이터표_계획(kit: Kit, fence: Fence, base_dir: Path) -> TablePlan:
    머리 = [h.strip() for h in _attr(fence, "head").split("|")]
    본문 = [줄 for 줄 in fence.body.splitlines() if 줄.strip()]
    행수 = _int_attr(fence, "rows", len(본문) or 1)
    # 행 전체(0..행수-1)를 돈다 — 본문 줄이 모자라도(또는 아예 없어도) 빈 칸까지 계획해야
    # 한다(빈 칸에도 서식을 입힌다는 원칙).
    데이터 = [
        _행_계획(fence.name, _본문_칸_글자들(본문, 행, len(머리)), kit.body_width // len(머리),
                 base_dir=base_dir, 기본_높이=kit.furniture["rowHeight"]["cell"])
        for 행 in range(행수)
    ]
    rows = (
        tuple(CellPlan("label", 이름) for 이름 in 머리),
        *(tuple(CellPlan("cell", 값, picture=그림, height=h) for 값, 그림 in 칸들) for 칸들, h in 데이터),
    )
    return TablePlan(
        "데이터표", rows,
        height=kit.furniture["rowHeight"]["label"] + sum(h for _c, h in 데이터), equal_columns=True,
    )


def _답칸_계획(kit: Kit, fence: Fence, base_dir: Path) -> TablePlan:
    # base_dir 는 안 쓴다 — 답칸은 본문을 아예 안 읽으므로 칸 안 그림 자체가 성립하지 않는다.
    # PLANNERS 딕셔너리 하나로 모든 펜스 계획자를 같은 모양으로 부르기 때문에 인자는 받는다.
    # 답칸만 `_attr`을 안 쓰고 전용 문구를 쓴다 — 라벨 없는 답칸은 단순 오타가 아니라
    # 채점 불가(M-4)라서, 왜 안 되는지까지 말해 줘야 한다.
    라벨 = fence.attrs.get("label", "").strip()
    if not 라벨:
        raise ValueError("라벨 없는 답칸 — 모든 답칸은 label= 을 가진다")
    줄수 = _int_attr(fence, "lines", 1)
    rows = ((CellPlan("label", 라벨),),) + tuple((CellPlan("answer", ""),) for _ in range(줄수))
    높이 = kit.furniture["rowHeight"]["label"] + 줄수 * kit.furniture["rowHeight"]["answer"]
    return TablePlan("답칸", rows, height=높이)


def _강조박스_계획(kit: Kit, fence: Fence, base_dir: Path) -> TablePlan:
    # 담는 칸(행1) 높이를 안쪽 표 높이(rowHeight.cell)로 맞춘다. 안쪽 표는 셀이 하나뿐이라
    # 그 값이 곧 "행 높이 합"이다 — 담는 칸에 높이를 안 주면 표 sz가 rows*라이브러리
    # 기본값(7200)에 남아 실제 합(5648)과 달라진다. 담는 칸도 같은 값을 받아야 바깥 표도
    # 다른 블록과 같은 규칙(표 sz == 행 높이 합)을 따른다.
    칸높이 = kit.furniture["rowHeight"]["cell"]
    안쪽 = TablePlan("강조박스", ((CellPlan("cell", fence.body),),), height=칸높이, border="grid")
    rows = (
        (CellPlan("label", fence.attrs.get("title", "").strip()),),
        (CellPlan("cell", "", height=칸높이, nested=안쪽),),
    )
    return TablePlan("강조박스", rows, height=kit.furniture["rowHeight"]["label"] + 칸높이)


def _나란히_계획(kit: Kit, fence: Fence, base_dir: Path) -> TablePlan:
    """여러 단(2~4)을 나란히 놓고 각 단에 머리·그림·답줄을 쌓는 구성 — "예제 1 |
    예제 2" 모양. 표 구조는 데이터표와 같은 규약이다: 머리행 1(역할 label, cols= 그대로) +
    본문행 N(역할 cell, rows= 로 빈 본문행 수를 준다·기본 1). 열 폭은 균등하다."""
    열들 = [c.strip() for c in _attr(fence, "cols").split("|")]
    본문 = [줄 for 줄 in fence.body.splitlines() if 줄.strip()]
    행수 = _int_attr(fence, "rows", len(본문) or 1)
    데이터 = [
        _행_계획(fence.name, _본문_칸_글자들(본문, 행, len(열들)), kit.body_width // len(열들),
                 base_dir=base_dir, 기본_높이=kit.furniture["rowHeight"]["cell"])
        for 행 in range(행수)
    ]
    rows = (
        tuple(CellPlan("label", 이름) for 이름 in 열들),
        *(tuple(CellPlan("cell", 값, picture=그림, height=h) for 값, 그림 in 칸들) for 칸들, h in 데이터),
    )
    return TablePlan(
        "나란히", rows,
        height=kit.furniture["rowHeight"]["label"] + sum(h for _c, h in 데이터), equal_columns=True,
    )


PLANNERS: dict[str, Callable[[Kit, Fence, Path], TablePlan]] = {
    "라벨설명": _라벨설명_계획, "용어카드": _용어카드_계획, "비교표": _비교표_계획,
    "데이터표": _데이터표_계획, "답칸": _답칸_계획, "강조박스": _강조박스_계획, "나란히": _나란히_계획,
}


def plan_node(kit: Kit, node: Node, *, base_dir: Path) -> BlockPlan:
    """노드 하나의 조판 계획. 펜스는 `fence_problems`의 첫 문제로 계획 전에 거부한다."""
    if isinstance(node, Body):
        return _정의빈칸_계획(kit, node)
    if isinstance(node, Prompt):
        # charPr.body(=0)를 쓰면, 그 0이 킷이 고른 서식인지 "아무것도 안 입힌" 라이브러리
        # 기본값과 우연히 같은 값인지 저장 XML만 봐서는 구별이 안 된다(실제로 발문이 10pt
        # 바탕체로 렌더된 적이 있다 — 실한컴에서만 드러난다). 전용 키 charPr.prompt(씨앗
        # 킷은 10pt 굵게)를 쓴다.
        return ParagraphPlan(node.text, para="prompt", char="prompt")
    if isinstance(node, Figure):
        # check_markdown 과 같은 판정 — M-1 을 거치지 않고 부르는 호출도 용지 밖 그림을 그리지 않는다
        if (폭_문제 := 그림_폭_문제(kit, node.width_mm, f"그림({node.path})")) is not None:
            raise ValueError(폭_문제)
        경로 = (Path(base_dir) / node.path).resolve()
        가로, 세로 = png_size(경로.read_bytes())
        return FigurePlan(경로, node.width_mm, node.width_mm * 세로 / 가로)
    if isinstance(node, Fence):
        계획자 = PLANNERS.get(node.name)
        if 계획자 is None:
            raise ValueError(f"엔진이 모르는 블록: {node.name}")
        문제 = fence_problems(node, kit=kit, base_dir=base_dir)
        if 문제:
            raise ValueError(문제[0])
        return 계획자(kit, node, base_dir)
    raise TypeError(f"알 수 없는 노드: {type(node).__name__}")


# 선언표(SPECS·STRUCTURAL)가 vocab.py 의 이름 집합과 어긋나면 import 시점에 바로 터진다 —
# "선언표 하나를 M-1 과 조판이 같이 읽는다"는 성질을 지키는 쪽은 사람이 아니라 이 검사다.
# (같은 사실을 tests/test_blocks.py 도 asserts 로 확인한다 — 여긴 배포본에서도 살아 있는
# 방어선이고, 테스트 쪽은 깨졌을 때 원인을 짚어 주는 진단이다.)
if set(PLANNERS) != FENCE_BLOCKS:
    raise RuntimeError(
        f"PLANNERS 가 vocab.FENCE_BLOCKS 와 어긋났다: {set(PLANNERS) ^ FENCE_BLOCKS}"
    )
if set(STRUCTURAL) != STRUCTURAL_BLOCKS:
    raise RuntimeError(
        f"STRUCTURAL 이 vocab.STRUCTURAL_BLOCKS 와 어긋났다: {set(STRUCTURAL) ^ STRUCTURAL_BLOCKS}"
    )
if set(SPECS) != set(PLANNERS):
    raise RuntimeError(f"SPECS 가 PLANNERS 와 어긋났다: {set(SPECS) ^ set(PLANNERS)}")
