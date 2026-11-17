"""씨앗 킷 스켈레톤 — kits/standard/skeleton.hwpx 를 python-hwpx 기본 템플릿에서 새로 만든다.

    uv run --python 3.13 python scripts/씨앗_스켈레톤.py

어느 학교·교사의 양식도 가공하지 않는다. 기본 템플릿(한컴 기본 스타일표)에 킷 역할이 쓰는
글자·문단·테두리 모양만 정해진 차례로 더하고, 1단 머리 → 2단 본문 전환 문단을 지은 뒤
엔진의 `extract_skeleton`으로 마무리한다(밑줄 답칸 borderFill 은 추출이 더한다).
더한 모양의 번호는 kits/standard/kit.json 의 `styles`에 다시 쓴다 — 스켈레톤과 킷이 늘 짝이다.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from hwpx import HwpxDocument

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.kit import stamp_kit  # noqa: E402
from assessment.skeleton import extract_skeleton  # noqa: E402

킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"

DOTUM_NAME = "함초롬돋움"                         # 기본 템플릿 글꼴(모든 언어)
검정, 회색 = "#000000", "#808080"
음영 = "#DEE7F1"                                # 합성 씨앗의 옅은 청회색
# A4(기본 템플릿 그대로) 여백. 단 사이 간격은 템플릿 secPr 의 spaceColumns 와 같게 둔다.
여백 = {"left": 2835, "right": 2835, "top": 1417, "bottom": 1417, "header": 2835, "footer": 2835}
단_간격 = 1134

# 역할 → 크기(모두 함초롬돋움, 굵게 없음). blank 는 템플릿 charPr 0 을 그대로 쓴다.
# answer_label 은 밑줄 글자가 아니다 — 밑줄은 답칸 아래 테두리가 그린다.
글자 = {
    "title": 3000,
    "title_suffix": 2900,
    "score": 1200,
    "note": 1500,
    "body": 1100,
    "answer_label": 1000,
    "hint": 900,
}
# 역할 → (정렬, 내어쓰기, 줄간격 %). 같은 값이면 같은 모양을 쓴다.
문단 = {
    "title": ("CENTER", 0, 160),
    "id_line": ("LEFT", 0, 160),
    "body": ("JUSTIFY", 0, 160),
    "passage": ("JUSTIFY", 0, 150),
    "center": ("CENTER", 0, 160),
    "footer_gap": ("LEFT", 0, 160),
    "score_value": ("CENTER", 0, 100),
    "memo": ("JUSTIFY", 0, 160),
    "caption_left": ("LEFT", 0, 160),
}
# 역할 → (선 색, 채움). 선 색이 None 이면 네 변 모두 NONE, 아니면 네 변 SOLID 0.12 mm.
테두리 = {
    "box": (검정, None),
    "none": (None, None),
    "shade": (검정, 음영),
    "rule": (회색, None),
}


def _모양들(doc: HwpxDocument) -> dict[str, dict[str, int]]:
    """킷 역할의 글자·문단·테두리 모양을 정해진 차례로 보장하고 그 번호를 돌려준다(`doc.styles.ensure_*`).

    기준은 기본 템플릿의 글자 모양 0·문단 모양 0이다. 내용이 같은 모양이 이미 있으면 그 번호를 쓴다."""
    번호: dict[str, dict[str, int]] = {"borderFill": {}, "charPr": {"blank": 0}, "paraPr": {}}
    for 역할, 크기 in 글자.items():
        번호["charPr"][역할] = int(doc.styles.ensure_run(
            base_char_pr_id_ref="0", size=크기 / 100, color=검정, font=DOTUM_NAME))
    for 역할, (정렬, 내어, 줄) in 문단.items():
        번호["paraPr"][역할] = int(doc.styles.ensure_paragraph_format(
            base_para_pr_id_ref="0", alignment=정렬, margins={"intent": 내어}, line_spacing=줄))
    for 역할, (선색, 채움) in 테두리.items():
        번호["borderFill"][역할] = int(doc.styles.ensure_border_fill(
            border_color=선색 or 검정, border_width_mm=0.12,
            active_borders=None if 선색 else (), fill_color=채움))
    return 번호


def _2단_전환_문단(doc: HwpxDocument) -> None:
    """추출은 원본의 세 번째 문단에서 colCount=2 colPr 을 찾는다 — 빈 문단 하나 뒤에 짓는다.
    문단·단 정의 id는 `HwpxDocument.new(seed=)`가 정한다 — 다시 돌려도 같은 스켈레톤."""
    doc.add_paragraph("")
    p = doc.add_paragraph("")
    doc.page.set_columns(2, same_gap=단_간격, paragraph=p)


def main() -> None:
    doc = HwpxDocument.new(empty_first_line=True, seed=0)
    번호 = _모양들(doc)
    doc.page.set_margins(**여백)
    _2단_전환_문단(doc)
    with tempfile.TemporaryDirectory() as tmp:
        원형 = Path(tmp) / "seed.hwpx"
        doc.save(str(원형))
        보고 = extract_skeleton(원형, 킷 / "skeleton.hwpx")
        print(보고)
    번호["borderFill"]["underline"] = 보고["underline_border_fill"]

    킷_json = 킷 / "kit.json"
    데이터 = json.loads(킷_json.read_text(encoding="utf-8"))
    for 종류, 표 in 번호.items():
        데이터["styles"][종류] = {역할: 표[역할] for 역할 in 데이터["styles"][종류]}
    킷_json.write_text(json.dumps(데이터, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stamp_kit(킷)  # 스켈레톤과 kit.json을 함께 새로 썼다 — 지문을 적는다
    print(json.dumps(데이터["styles"], ensure_ascii=False))


if __name__ == "__main__":
    main()
