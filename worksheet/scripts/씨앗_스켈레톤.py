"""씨앗 킷 스켈레톤 — kits/standard/skeleton.hwpx 를 python-hwpx 기본 템플릿에서 새로 만든다.

    uv run --python 3.13 python scripts/씨앗_스켈레톤.py

어느 학교·교사의 양식도 가공하지 않는다. 기본 템플릿(한컴 기본 스타일표)에 킷 역할이 쓰는
글자·문단·테두리 모양만 정해진 차례로 더하고, 엔진의 `extract_skeleton`으로 마무리한다.
더한 모양의 번호는 kits/standard/kit.json 의 `styles`에 다시 쓴다 — 스켈레톤과 킷이 늘 짝이다.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from hwpx import HwpxDocument

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worksheet.skeleton import extract_skeleton  # noqa: E402

킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"

DOTUM, BATANG = "함초롬돋움", "함초롬바탕"         # 기본 템플릿 글꼴(모든 언어)
검정, 옅은회색, 회색 = "#000000", "#BFBFBF", "#808080"
음영 = "#DEE7F1"                                # 합성 씨앗의 옅은 청회색
여백 = {"left": 4251, "right": 4251, "top": 2834, "bottom": 2834, "header": 2834, "footer": 2834}

# 역할 → (크기, 굵게, 색, 자간, 글꼴). 같은 값이면 같은 모양을 쓴다.
글자 = {
    "circle_num": (1100, True, "#FFFFFF", 0, DOTUM),
    "band_left": (1000, False, 검정, 0, DOTUM),
    "band_teacher": (1200, True, 검정, 0, DOTUM),
    "band_title": (1500, True, 검정, 0, DOTUM),
    "keyword_head": (1500, True, 검정, 0, DOTUM),
    "band_name": (1200, True, 검정, 0, DOTUM),
    "cell": (1200, True, 검정, 0, DOTUM),
    "label": (1200, True, 검정, 0, DOTUM),
    "stamp": (1800, False, 회색, 0, DOTUM),
    "prompt": (1000, True, 검정, -10, DOTUM),
    "headline": (1500, True, 검정, -10, DOTUM),
    "heading_ref": (1200, True, 검정, -10, DOTUM),
}
# 역할 → (정렬, 내어쓰기, 줄간격 %)
문단 = {
    "center": ("CENTER", 0, 160),
    "label": ("CENTER", 0, 160),
    "band_title": ("CENTER", 0, 160),
    "band_name": ("LEFT", 0, 160),
    "cell": ("LEFT", 0, 160),
    "body": ("JUSTIFY", -2688, 180),
    "prompt": ("JUSTIFY", 0, 180),
}
# 역할 → (위, 아래, 좌우, 채움). 선은 모두 SOLID 0.12 mm.
테두리 = {
    "plain": (검정, 검정, 검정, None),
    "rule_head": (검정, 옅은회색, 검정, None),
    "rule_line": (옅은회색, 옅은회색, 검정, None),
    "rule_last": (옅은회색, 검정, 검정, None),
    "shade": (검정, 검정, 검정, 음영),
    "grid": (회색, 회색, 회색, None),
    "answer": (검정, 검정, 검정, "#FFFFFF"),
}


def _모양들(doc: HwpxDocument) -> dict[str, dict[str, int]]:
    """킷 역할의 글자·문단·테두리 모양을 정해진 차례로 보장하고 그 번호를 돌려준다(`doc.styles.ensure_*`).
    기준은 기본 템플릿의 글자 모양 0·문단 모양 0이다. 내용이 같은 모양이 이미 있으면 그 번호를 쓴다."""
    번호: dict[str, dict[str, int]] = {"borderFill": {}, "charPr": {"body": 0}, "paraPr": {}}
    for 역할, (크기, 굵게, 색, 자간, 글꼴) in 글자.items():
        번호["charPr"][역할] = int(doc.styles.ensure_run(
            base_char_pr_id_ref="0", size=크기 / 100, bold=굵게, color=색, letter_spacing=자간, font=글꼴))
    for 역할, (정렬, 내어, 줄) in 문단.items():
        번호["paraPr"][역할] = int(doc.styles.ensure_paragraph_format(
            base_para_pr_id_ref="0", alignment=정렬, margins={"intent": 내어}, line_spacing=줄))
    for 역할, (위, 아래, 좌우, 채움) in 테두리.items():
        면 = {쪽: {"type": "SOLID", "width_mm": 0.12, "color": 색}
             for 쪽, 색 in (("left", 좌우), ("right", 좌우), ("top", 위), ("bottom", 아래))}
        번호["borderFill"][역할] = int(doc.styles.ensure_border_fill(sides=면, fill_color=채움))
    return 번호


def main() -> None:
    doc = HwpxDocument.new(empty_first_line=True, seed=0)
    번호 = _모양들(doc)
    doc.page.set_margins(**여백)
    with tempfile.TemporaryDirectory() as tmp:
        원형 = Path(tmp) / "seed.hwpx"
        doc.save(str(원형))
        print(extract_skeleton(원형, 킷 / "skeleton.hwpx"))

    킷_json = 킷 / "kit.json"
    데이터 = json.loads(킷_json.read_text(encoding="utf-8"))
    for 종류, 표 in 번호.items():
        데이터["styles"][종류] = {역할: 표[역할] for 역할 in 데이터["styles"][종류]}
    킷_json.write_text(json.dumps(데이터, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(데이터["styles"], ensure_ascii=False))


if __name__ == "__main__":
    main()
