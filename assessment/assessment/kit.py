"""양식 킷 — 스타일 번호·폭·높이·고정 문구를 데이터로 둔다. 코드는 숫자를 모른다."""

from __future__ import annotations

import json
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from assessment.ns import HH

_최상위 = {"kit", "styles", "furniture", "fontMap", "skeleton"}
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
    _지문_검사(root, data, skeleton, "python -m assessment.cli stamp-kit")
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


# ---- 스켈레톤 지문 ------------------------------------------------------------
# kit.json의 역할 번호(styles)는 그 킷의 skeleton.hwpx header 번호다. 다른 스켈레톤과 섞이면(옛 kit.json + 새
# 스켈레톤) 멈추지 않고 다른 글자·문단 모양으로 조판한다 — 그래서 exam의 양식 지문(form.sha256)과 같은 꼴로
# kit.json `skeleton.sha256`에 스켈레톤 파일의 sha256을 적고, 킷을 읽을 때 맞춰 본다.

def skeleton_sha256(path: Path) -> str:
    """스켈레톤 파일 바이트의 sha256(16진) — exam `kit.sha256`과 같은 계산."""
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp_kit(root: Path) -> str:
    """<킷 폴더>/skeleton.hwpx의 지문을 kit.json `skeleton.sha256`에 적고 그 값을 돌려준다. 다른 값은 건드리지 않는다."""
    root = Path(root)
    kit_json = root / "kit.json"
    data = json.loads(kit_json.read_text(encoding="utf-8"))
    sha = skeleton_sha256(root / "skeleton.hwpx")
    data["skeleton"] = {**(data.get("skeleton") or {}), "sha256": sha}
    kit_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sha


def _지문_검사(root: Path, data: dict, skeleton: Path, 명령: str) -> None:
    적힌 = (data.get("skeleton") or {}).get("sha256") if isinstance(data.get("skeleton"), dict) else None
    다시 = (f"씨앗 스크립트(scripts/씨앗_스켈레톤.py)나 extract-kit으로 스켈레톤과 kit.json을 함께 다시 만들거나, "
          f"둘이 짝임을 확인했다면 `{명령} {root}`로 지문을 적는다")
    if not 적힌:
        raise ValueError(f"kit.json 에 스켈레톤 지문(skeleton.sha256)이 없다: {root / 'kit.json'} — 이 킷 설정이 지금 "
                         f"skeleton.hwpx와 짝인지 알 수 없어 조판하지 않는다. {다시}")
    실제 = skeleton_sha256(skeleton)
    if 실제 != 적힌:
        raise ValueError(f"스켈레톤과 킷 설정이 짝이 아니다: skeleton.hwpx sha256 {실제} ≠ kit.json skeleton.sha256 {적힌} "
                         f"({root}) — 역할 번호가 다른 모양을 가리킬 수 있어 조판하지 않는다. {다시}")
