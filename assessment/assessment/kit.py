"""양식 킷 — 스타일 번호·폭·높이·고정 문구를 데이터로 둔다. 코드는 숫자를 모른다."""

from __future__ import annotations

import json
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from assessment.ns import HH

_최상위 = {"kit", "styles", "furniture", "fontMap"}
REQUIRED_KEYS: tuple[str, ...] = (
    "kit",
    *(f"styles.borderFill.{k}" for k in ("box", "underline", "none", "shade", "rule")),
    *(f"styles.paraPr.{k}" for k in ("title", "id_line", "body", "passage", "center", "footer_gap", "score_value", "memo", "caption_left")),
    *(f"styles.charPr.{k}" for k in ("title", "title_suffix", "score", "note", "body", "answer_label", "hint", "blank")),
    "styles.memoStyle",
    "furniture.titleMarkpen", "furniture.idLine", "furniture.cellInnerMargin", "furniture.tableOutMargin",
    *(f"furniture.widths.{k}" for k in ("passage", "answerLine", "answerGap", "box", "gridLabel", "dataLabel", "score")),
    *(f"furniture.rowHeight.{k}" for k in ("auto", "grid", "rule", "single", "labeled", "score")),
    *(f"furniture.footer.{k}" for k in ("lines", "scoreHead", "signLabel", "signLines")),
)
# kit.json 종류 이름 → header.xml 태그 이름
_헤더_태그 = {"borderFill": "borderFill", "paraPr": "paraPr", "charPr": "charPr"}


def _찾기(data: dict, 경로: str):
    cur = data
    for 조각 in 경로.split("."):
        if not isinstance(cur, dict) or 조각 not in cur:
            return None
        cur = cur[조각]
    return cur


def _header_ids(skeleton: Path) -> dict[str, set[int]]:
    with zipfile.ZipFile(skeleton) as z:
        뿌리 = ET.fromstring(z.read("Contents/header.xml"))
    return {
        종류: {int(e.get("id")) for e in 뿌리.iter(f"{{{HH}}}{태그}")}
        for 종류, 태그 in _헤더_태그.items()
    }


@dataclass(frozen=True)
class Kit:
    root: Path
    name: str
    border_fill: dict[str, int]
    para_pr: dict[str, int]
    char_pr: dict[str, int]
    furniture: dict
    memo_style: int

    @property
    def skeleton(self) -> Path:
        return self.root / "skeleton.hwpx"


def validate_font_map(값: object) -> None:
    """`fontMap`은 선택 최상위 키다(양식의 글꼴 중 배포 환경에 없는 것을 있는 글꼴로
    옮긴다) — 있으면 "원래 글꼴 이름 → 바꿀 글꼴 이름"의 문자열→문자열 사전이어야 한다.

    `load_kit()`뿐 아니라 `scripts/뽑기_스켈레톤.py`도 스켈레톤을 뽑기 **전에** 이 함수를
    직접 불러 fontMap 형태를 먼저 본다 — 검사 없이 그대로 `extract_skeleton`에 넘기면 값이
    문자열이 아닌 항목이 header.xml에 hh:font를 지으려 할 때 라이브러리의 원문 오류가 그대로
    새기 때문이다.
    """
    형식_오류_문구 = 'kit.json 의 fontMap 은 {"원래 글꼴": "바꿀 글꼴"} 꼴이어야 한다'
    if not isinstance(값, dict):
        raise ValueError(형식_오류_문구)
    for 원래, 대상 in 값.items():
        if not isinstance(원래, str) or not 원래 or not isinstance(대상, str) or not 대상:
            raise ValueError(형식_오류_문구)


def load_kit(root: Path) -> Kit:
    root = Path(root)
    data = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    모름 = sorted(set(data) - _최상위)
    if 모름:
        raise ValueError(f"kit.json 에 모르는 항목: {', '.join(모름)}")
    if "fontMap" in data:
        validate_font_map(data["fontMap"])
    빠짐 = [k for k in REQUIRED_KEYS if _찾기(data, k) is None]
    if 빠짐:
        raise ValueError(f"kit.json 에 필수 항목이 없다: {', '.join(빠짐)}")
    틈, 안여백 = data["furniture"]["widths"]["answerGap"], data["furniture"]["cellInnerMargin"]
    for 이름, 값 in (("widths.answerGap", 틈), ("cellInnerMargin", 안여백)):
        if isinstance(값, bool) or not isinstance(값, int):
            raise ValueError(f"kit.json 의 furniture.{이름} 은 정수여야 한다(HWPUNIT) — {값!r}")
    if 틈 <= 안여백:
        # 빈 틈 칸이 안 여백(좌+우)보다 좁으면 한컴이 칸을 넓혀 표가 단 밖으로 삐져나간다.
        raise ValueError(f"kit.json 의 widths.answerGap={틈} 은 cellInnerMargin={안여백} 보다 커야 한다")
    skeleton = root / "skeleton.hwpx"
    if not skeleton.exists():
        raise ValueError(f"킷에 skeleton.hwpx 가 없다: {root}")
    있는_id = _header_ids(skeleton)
    for 종류 in _헤더_태그:
        for 키, 값 in data["styles"][종류].items():
            if int(값) not in 있는_id[종류]:
                raise ValueError(f"kit.json 의 {종류}.{키}={값} 가 스켈레톤 header 에 없다")
    s = data["styles"]
    return Kit(
        root=root, name=data["kit"],
        border_fill={k: int(v) for k, v in s["borderFill"].items()},
        para_pr={k: int(v) for k, v in s["paraPr"].items()},
        char_pr={k: int(v) for k, v in s["charPr"].items()},
        furniture=data["furniture"], memo_style=int(s["memoStyle"]),
    )
