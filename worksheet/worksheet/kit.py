"""양식 킷 — 학교 양식을 데이터로 기술한다."""

from __future__ import annotations

import json
import string
from dataclasses import dataclass, field
from pathlib import Path

from hwpx import HwpxDocument

from worksheet.vocab import FENCE_BLOCKS, STRUCTURAL_BLOCKS

# 미치환 슬롯·TODO 흔적으로 볼 기본 표시. 정보 교과 코드에는 `# TODO`가, 국어식 표기에는
# 《책 제목》이 정상으로 나오는 킷도 있어 킷마다 kit.json의 residueMarkers 로 바꿀 수 있다
# (worksheet.checks.check_slot_residue 가 Kit.residue_markers 를 기본값으로 쓴다).
DEFAULT_RESIDUE_MARKERS: tuple[str, ...] = ("《", "》", "TODO", "TBD")

# docx 로 조판할 때 쓰는 글꼴 — kit.json 이 docx.font 를 안 주면 이 값을 쓴다.
DEFAULT_DOCX_FONT = "맑은 고딕"


def validate_docx(값: object) -> None:
    """`docx` 는 선택 키 — docx 로 조판할 때만 쓰는 값. 지금은 글꼴 하나."""
    문구 = 'kit.json 의 docx 는 {"font": "<글꼴 이름>"} 꼴이어야 한다'
    if not isinstance(값, dict) or set(값) - {"font"}:
        raise ValueError(문구)
    if "font" in 값 and (not isinstance(값["font"], str) or not 값["font"].strip()):
        raise ValueError(문구)


# load_kit()이 읽는 키 전부를 여기 한 곳에 적는다 — "if 'x' not in data"를 여기저기
# 흩어 놓지 않고, 이 목록 하나를 걸어 필수 키 누락을 한 번에 모아 보고한다. 점 경로는
# kit.json의 중첩 구조를 그대로 딴다. residueMarkers는 선택 키라 여기 없다.
REQUIRED_KEYS: tuple[str, ...] = (
    "kit",
    "slots",
    "bodyWidth",
    "fonts",
    "blocks",
    "styles.borderFill.plain",
    "styles.borderFill.shade",
    "styles.borderFill.grid",
    "styles.borderFill.answer",
    "styles.borderFill.rule_head",
    "styles.borderFill.rule_line",
    "styles.borderFill.rule_last",
    "styles.charPr.headline",
    "styles.charPr.circle_num",
    "styles.charPr.stamp",
    "styles.charPr.body",
    "styles.charPr.band_left",
    "styles.charPr.band_teacher",
    "styles.charPr.band_title",
    "styles.charPr.band_name",
    "styles.charPr.cell",
    "styles.charPr.label",
    "styles.charPr.heading_ref",
    "styles.charPr.keyword_head",
    "styles.charPr.prompt",
    "styles.paraPr.body",
    "styles.paraPr.prompt",
    "styles.paraPr.center",
    "styles.paraPr.band_title",
    "styles.paraPr.band_name",
    "styles.paraPr.cell",
    "styles.paraPr.label",
    "furniture.rowHeight.label",
    "furniture.rowHeight.cell",
    "furniture.rowHeight.answer",
    "furniture.heading.textbookFormat",
    "furniture.band.width",
    "furniture.band.height",
    "furniture.band.cols",
    "furniture.band.teacherLines",
    "furniture.band.nameLines",
    "furniture.stamp.curSz",
    "furniture.stamp.fill",
    "furniture.stamp.line",
    "furniture.stamp.lineWidth",
    "furniture.stamp.text",
    "furniture.stamp.pos.horzOffset",
    "furniture.stamp.pos.vertOffset",
    "furniture.circle.curSz",
    "furniture.circle.fill",
    "furniture.circle.line",
    "furniture.circle.lineWidth",
    "furniture.keywordPage.rows",
    "furniture.keywordPage.width",
    "furniture.keywordPage.height",
    "furniture.keywordPage.head",
    "furniture.labelWidth",
)


@dataclass(frozen=True)
class Kit:
    name: str
    root: Path
    slots: dict[str, str]
    border_fill: dict[str, int]
    char_pr: dict[str, int]
    para_pr: dict[str, int]
    furniture: dict[str, object]
    body_width: int
    fonts: tuple[str, ...]
    blocks: tuple[str, ...]
    residue_markers: tuple[str, ...] = DEFAULT_RESIDUE_MARKERS
    font_map: dict[str, str] = field(default_factory=dict)
    docx_font: str = DEFAULT_DOCX_FONT

    @property
    def skeleton_path(self) -> Path:
        return self.root / "skeleton.hwpx"


def seed_kit_path() -> Path:
    """씨앗 킷(kits/standard/kit.json)의 경로.

    `extract-kit`이 새 kit.json을 쓸 때 이 파일을 복사한다 — 양식의 상수표는
    엔진 코드가 아니라 이 데이터 파일이 갖는다(씨앗 값은 `scripts/씨앗_스켈레톤.py`가 쓴다).
    """
    path = Path(__file__).resolve().parents[1] / "kits" / "standard" / "kit.json"
    if not path.exists():
        raise FileNotFoundError(f"씨앗 킷이 없다: {path}")
    return path


def parse_slot_fields(text: str) -> list[str]:
    """줄 안의 `{필드}` 자리표시자 이름을 순서대로 낸다.

    `string.Formatter().parse`로 읽는다 — `load_kit`의 킷 스키마 검사와
    `worksheet.checks.check_empty_slots`가 이 함수 하나를 같이 불러, 자리표시자를 읽는
    규칙이 두 곳에서 갈라지지 않게 한다. 문법 오류(짝 없는 `{`)는 `string.Formatter`가
    그대로 `ValueError`를 던지므로 같은 문구로 감싸 다시 던지고, 필드 이름이 비었거나
    공백뿐이면(`{ }`처럼) 마찬가지로 거부한다 — 그런 이름은 `slots` 사전의 키가 될 수
    없어 나중에 `.format(**slots)`가 `KeyError`로 조용히 죽는 자리였다.
    """
    try:
        조각들 = list(string.Formatter().parse(text))
    except ValueError as e:
        raise ValueError(f"자리표시자를 읽을 수 없다: {text!r}") from e
    이름들: list[str] = []
    for _literal, 필드, _spec, _conv in 조각들:
        if 필드 is None:
            continue
        if not 필드.strip():
            raise ValueError(f"자리표시자를 읽을 수 없다: {text!r}")
        이름들.append(필드)
    return 이름들


def effective_slots(kit: Kit, *, grade: str | None = None) -> dict[str, str]:
    """킷 슬롯 위에 회차별 `grade`를 덮은 값.

    킷은 "학교-과목" 단위로 뽑지만(`extract-kit`) 학년은 회차(마크다운 한 장)마다 다를 수
    있다 — 같은 교사가 2·3학년을 같이 가르치는 경우가 그렇다. `grade`가 없으면 킷 슬롯을
    그대로 낸다.
    """
    슬롯 = dict(kit.slots)
    if grade is not None:
        슬롯["grade"] = grade
    return 슬롯


def _점경로_있음(data: object, 점경로: str) -> bool:
    노드 = data
    for 조각 in 점경로.split("."):
        if not isinstance(노드, dict) or 조각 not in 노드:
            return False
        노드 = 노드[조각]
    return True


def _필수_키_검사(data: object) -> None:
    누락 = [점경로 for 점경로 in REQUIRED_KEYS if not _점경로_있음(data, 점경로)]
    if 누락:
        raise ValueError("kit.json 에 필수 키가 없다: " + ", ".join(sorted(누락)))


def _정수인가(값: object) -> bool:
    return isinstance(값, int) and not isinstance(값, bool)


def _정수_검사(값: object, 점경로: str) -> None:
    """스칼라 정수 자리 하나가 실제로 정수(bool 제외)인지 본다 — 아니면 한국어 ValueError.

    band.width/height·keywordPage.rows/width/height처럼 다운스트림에서 len()·비교·int()에
    바로 쓰이는 자리들이 이 함수 하나를 공유한다 — 문자열·None·리스트가 들어오면 TypeError나
    영문 ValueError(int())가 load_kit() 밖으로 새는 자리이기 때문이다.
    """
    if not _정수인가(값):
        raise ValueError(f"kit.json 의 {점경로} 는 정수여야 한다: {값!r}")


def _문자열_검사(값: object, 점경로: str) -> None:
    """스칼라 문자열 자리 하나가 실제로 str 인지 본다 — 아니면 한국어 ValueError.

    `_정수_검사`와 같은 이유다: `parse_slot_fields`가 내부에서 쓰는
    `string.Formatter().parse`는 str이 아니면 bare `TypeError`를 던진다 — `textbookFormat`·
    `teacherLines`·`nameLines`의 각 줄처럼 자리표시자를 읽는 모든 자리가 이 함수를 먼저
    거친다.
    """
    if not isinstance(값, str):
        raise ValueError(f"kit.json 의 {점경로} 는 문자열이어야 한다: {값!r}")


def _band_cols_검사(band: dict) -> None:
    _정수_검사(band["width"], "furniture.band.width")
    _정수_검사(band["height"], "furniture.band.height")

    cols = band["cols"]
    if not (isinstance(cols, (list, tuple)) and all(_정수인가(v) for v in cols)):
        raise ValueError("kit.json 의 furniture.band.cols 는 정수 4개의 목록이어야 한다")
    if len(cols) != 4:
        raise ValueError(f"kit.json 의 furniture.band.cols 는 4칸이어야 한다: {len(cols)}칸")
    width = band["width"]
    if sum(cols) != width:
        raise ValueError(
            f"kit.json 의 furniture.band.cols 합({sum(cols)})이 width({width})와 다르다"
        )


def _keywordPage_숫자_검사(keyword_page: dict) -> None:
    for 키 in ("rows", "width", "height"):
        _정수_검사(keyword_page[키], f"furniture.keywordPage.{키}")


def _rowHeight_숫자_검사(row_height: dict) -> None:
    """label·cell·answer 세 칸 높이도 band/keywordPage와 같은 정수 가드를 받는다."""
    for 키 in ("label", "cell", "answer"):
        _정수_검사(row_height[키], f"furniture.rowHeight.{키}")


def _heading_textbookFormat_검사(heading: dict) -> None:
    """제목의 출처 표기 문구는 `{textbook}` 을 반드시 포함해야 하고, 그 말고 다른
    자리표시자는 쓸 수 없다.

    `parse_slot_fields`(band 자리표시자 검사와 같은 함수)로 읽는다 — 문법 오류(짝 없는
    `{`)는 그 함수가 이미 한국어 ValueError로 감싼다. 값이 str이 아니면 `parse_slot_fields`
    에 넘기기 전에 `_문자열_검사`가 먼저 거부한다 — 아니면 bare TypeError가 샌다.

    인자로 `furniture` 전체가 아니라 `furniture["heading"]` 하나만 받는다 —
    `_rowHeight_숫자_검사(furniture["rowHeight"])`·`_keywordPage_숫자_검사
    (furniture["keywordPage"])`와 같은 모양(하위 dict 하나)으로 형제 함수들과 맞춘다.
    """
    텍스트 = heading["textbookFormat"]
    _문자열_검사(텍스트, "furniture.heading.textbookFormat")
    try:
        필드들 = parse_slot_fields(텍스트)
    except ValueError as e:
        raise ValueError(f"kit.json 의 furniture.heading.textbookFormat {e}") from e
    if "textbook" not in 필드들:
        # 자리표시자가 하나도 없는 문구를 그냥 두면, 교사가 md 제목 줄 다음에 적은 출처
        # 표기가 모든 학습지에서 증발한다({textbook}이 없으니 값이 끼워질 자리 자체가
        # 없다). "허용되지 않은 자리표시자만 본다"만으로는 "자리표시자가 아예 없다"를
        # 못 잡는다 — 별도로 확인한다.
        raise ValueError(
            "kit.json 의 furniture.heading.textbookFormat 에 {textbook} 이 없다: " + repr(텍스트)
        )
    허용되지_않은 = sorted(set(필드들) - {"textbook"})
    if 허용되지_않은:
        raise ValueError(
            "kit.json 의 furniture.heading.textbookFormat 은 {textbook} 만 쓸 수 있다: "
            + ", ".join(허용되지_않은)
        )


def _band_자리표시자_검사(band: dict, slots: dict) -> None:
    for 키 in ("teacherLines", "nameLines"):
        for 줄 in band[키]:
            _문자열_검사(줄, f"furniture.band.{키}")  # str이 아니면 여기서 먼저 거부한다 — 아니면 bare TypeError가 샌다
            try:
                필드들 = parse_slot_fields(줄)
            except ValueError as e:
                raise ValueError(f"kit.json 의 furniture.band.{키} {e}") from e
            for 필드 in 필드들:
                if 필드 not in slots:
                    raise ValueError(
                        f"kit.json 의 furniture.band.{키} 가 모르는 슬롯을 쓴다: {필드}"
                    )


def _curSz_검사(설정: dict, 점경로: str) -> None:
    curSz = 설정["curSz"]
    옳음 = (
        isinstance(curSz, (list, tuple))
        and len(curSz) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) for v in curSz)
    )
    if not 옳음:
        raise ValueError(f"kit.json 의 {점경로} 는 [가로, 세로] 여야 한다")


def _labelWidth_검사(라벨폭: object, 본문폭: object) -> None:
    if not (_정수인가(라벨폭) and _정수인가(본문폭)):
        raise ValueError("kit.json 의 furniture.labelWidth 와 bodyWidth 는 정수여야 한다")
    if not (라벨폭 < 본문폭):
        raise ValueError(
            f"kit.json 의 furniture.labelWidth({라벨폭})가 bodyWidth({본문폭})보다 작아야 한다"
        )


def validate_font_map(값: object) -> None:
    """`fontMap`은 선택 키다 — 있으면 "비어 있지 않은 문자열 → 비어 있지 않은 문자열"의
    객체여야 하고, 원래·대상 글꼴이 같은 항목이나 연쇄하는 항목(아래)은 거부한다.

    `load_kit()`뿐 아니라 `worksheet.cli._extract_kit`도 이 함수를 직접 부른다 — dest의
    kept kit.json을 쓸 때는 아직 skeleton.hwpx가 없어(추출 중이므로) `load_kit()` 전체를
    부를 수 없고, 그래도 `extract_skeleton`에 넘기기 전에 형태는 검사해야 하기 때문이다
    (검사 없이 넘기면, 값이 문자열이 아닌 항목이 `header.xml`의 `hh:font`를 지으려 할 때
    라이브러리의 `TypeError`가 트레이스백으로 그대로 샌다 — `cli.py`의 "한 줄 오류" 계약을
    깬다). 그래서 함수 이름에 밑줄을 안 붙였다.

    `_문자열_검사`처럼 점경로별 함수를 따로 두지 않고 값 하나만 받는 이유: `fontMap`은
    dict 자체의 형태(키·값이 전부 문자열)가 틀린 자리라, 기존 함수들(스칼라 하나 검사)과
    모양이 다르다.
    """
    형식_오류_문구 = 'kit.json 의 fontMap 은 {"원래 글꼴": "바꿀 글꼴"} 꼴이어야 한다'
    if not isinstance(값, dict):
        raise ValueError(형식_오류_문구)
    for 원래, 대상 in 값.items():
        if not isinstance(원래, str) or not 원래 or not isinstance(대상, str) or not 대상:
            raise ValueError(형식_오류_문구)
        if 원래 == 대상:
            raise ValueError(f"kit.json 의 fontMap 에서 원래 글꼴과 바꿀 글꼴이 같다: '{원래}'")

    # 연쇄 검사 — 어떤 항목의 대상 글꼴이 다른 항목의 원래 글꼴이면, extract_skeleton이
    # (원래,대상) 쌍을 dict 순서대로 순차 적용해 최종 글꼴이 한 단계가 아니라 그 다음
    # 단계까지 흘러간다(A→B→C면 A를 참조하던 자리도 결국 C를 가리키게 된다) — 한 단계로만
    # 적으라고 미리 막는다. items() 순서대로 훑어 "대상이 곧 다른 항목의 원래"인 첫 쌍부터
    # 최대 len(값)걸음까지 앞으로 걸어 실제 연쇄를 문구로 보여준다(사이클 방어로 이미 지난
    # 글꼴을 다시 만나면 멈춘다).
    for 원래, 대상 in 값.items():
        if 대상 not in 값:
            continue
        체인 = [원래, 대상]
        cur = 대상
        for _ in range(len(값)):
            다음 = 값.get(cur)
            if 다음 is None or 다음 in 체인:
                break
            체인.append(다음)
            cur = 다음
        raise ValueError(
            "kit.json 의 fontMap 항목이 연쇄한다: "
            + " → ".join(f"'{x}'" for x in 체인)
            + " — 한 단계로만 적는다"
        )


def load_kit(root: Path) -> Kit:
    root = Path(root)
    skeleton = root / "skeleton.hwpx"
    if not skeleton.exists():
        raise FileNotFoundError(f"킷에 스켈레톤이 없다: {skeleton}")

    kit_json_path = root / "kit.json"
    try:
        원문 = kit_json_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"kit.json 을 읽을 수 없다: {kit_json_path} — {e}") from e
    try:
        data = json.loads(원문)
    except json.JSONDecodeError as e:
        raise ValueError(f"kit.json 을 읽을 수 없다: {kit_json_path} — {e}") from e

    _필수_키_검사(data)
    if "fontMap" in data:
        validate_font_map(data["fontMap"])
    if "docx" in data:
        validate_docx(data["docx"])

    furniture = data["furniture"]
    band = furniture["band"]
    _band_cols_검사(band)
    _band_자리표시자_검사(band, data["slots"])
    _keywordPage_숫자_검사(furniture["keywordPage"])
    _curSz_검사(furniture["stamp"], "furniture.stamp.curSz")
    _curSz_검사(furniture["circle"], "furniture.circle.curSz")
    _labelWidth_검사(furniture["labelWidth"], data["bodyWidth"])
    _rowHeight_숫자_검사(furniture["rowHeight"])
    _heading_textbookFormat_검사(furniture["heading"])

    styles = data["styles"]
    return Kit(
        name=data["kit"],
        root=root,
        slots=dict(data["slots"]),
        border_fill={k: int(v) for k, v in styles["borderFill"].items()},
        char_pr={k: int(v) for k, v in styles["charPr"].items()},
        para_pr={k: int(v) for k, v in styles["paraPr"].items()},
        furniture=furniture,
        body_width=int(data["bodyWidth"]),
        fonts=tuple(data["fonts"]),
        blocks=tuple(data["blocks"]),
        residue_markers=tuple(data.get("residueMarkers", DEFAULT_RESIDUE_MARKERS)),
        font_map=dict(data.get("fontMap", {})),
        docx_font=data.get("docx", {}).get("font", DEFAULT_DOCX_FONT),
    )


def verify_kit(kit: Kit) -> list[str]:
    """킷이 가리키는 스타일 ID가 스켈레톤에 실재하고, blocks 의 이름을 엔진이 아는지 [기계] 검사.

    `worksheet.blocks`를 직접 import하면 순환(blocks.py가 이미 kit.py를 import한다)이라
    이름 집합만 담은 `worksheet.vocab`을 대신 읽는다.
    """
    doc = HwpxDocument.open(kit.skeleton_path)
    # doc.styles 의 단건 조회는 없는 ID 에 None 을 낸다.
    찾기 = {
        "borderFill": doc.styles.border_fill,
        "charPr": doc.styles.char_property,
        "paraPr": doc.styles.paragraph_property,
    }
    문제: list[str] = []
    for 종류, 표 in (
        ("borderFill", kit.border_fill),
        ("charPr", kit.char_pr),
        ("paraPr", kit.para_pr),
    ):
        for 이름, 번호 in sorted(표.items()):
            if 찾기[종류](번호) is None:
                문제.append(f"스켈레톤에 없는 스타일: {종류}.{이름}={번호}")

    알려진_블록 = FENCE_BLOCKS | STRUCTURAL_BLOCKS
    문제 += [
        f"엔진이 모르는 블록 이름: {이름}" for 이름 in kit.blocks if 이름 not in 알려진_블록
    ]
    return 문제
