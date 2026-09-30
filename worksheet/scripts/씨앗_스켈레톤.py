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
from copy import deepcopy
from pathlib import Path

from hwpx import HwpxDocument

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worksheet.skeleton import extract_skeleton  # noqa: E402

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"

DOTUM, BATANG = "0", "1"                       # 기본 템플릿 글꼴 id
LANGS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")
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


def _더하기(묶음, 원형, 속성들: dict) -> str:
    새것 = deepcopy(원형)
    새것.set("id", str(max(int(e.get("id")) for e in 묶음) + 1))
    for k, v in 속성들.items():
        새것.set(k, v)
    묶음.append(새것)
    묶음.set("itemCnt", str(len(묶음)))
    return 새것


def _모양들(머리):
    charprs = next(머리.iter(HH + "charProperties"))
    paraprs = next(머리.iter(HH + "paraProperties"))
    fills = next(머리.iter(HH + "borderFills"))
    char0 = next(e for e in charprs if e.get("id") == "0")
    para0 = next(e for e in paraprs if e.get("id") == "0")
    fill1 = next(e for e in fills if e.get("id") == "1")

    번호: dict[str, dict[str, int]] = {"borderFill": {}, "charPr": {"body": 0}, "paraPr": {}}
    이미: dict[tuple, str] = {}
    for 역할, (크기, 굵게, 색, 자간, 글꼴) in 글자.items():
        열쇠 = ("c", 크기, 굵게, 색, 자간, 글꼴)
        if 열쇠 not in 이미:
            e = _더하기(charprs, char0, {"height": str(크기), "textColor": 색})
            for k in LANGS:
                e.find(HH + "fontRef").set(k, 글꼴)
                e.find(HH + "spacing").set(k, str(자간))
            if 굵게:
                e.find(HH + "underline").addprevious(e.makeelement(HH + "bold", {}))
            이미[열쇠] = e.get("id")
        번호["charPr"][역할] = int(이미[열쇠])
    for 역할, (정렬, 내어, 줄) in 문단.items():
        열쇠 = ("p", 정렬, 내어, 줄)
        if 열쇠 not in 이미:
            e = _더하기(paraprs, para0, {})
            e.find(HH + "align").set("horizontal", 정렬)
            case, default = e.find(HP + "switch")
            for 가지, 배 in ((case, 1), (default, 2)):  # case = HWPUNIT, default = 2배
                가지.find(f"{HH}margin/{HC}intent").set("value", str(내어 * 배))
                가지.find(HH + "lineSpacing").set("value", str(줄))
            이미[열쇠] = e.get("id")
        번호["paraPr"][역할] = int(이미[열쇠])
    for 역할, (위, 아래, 좌우, 채움) in 테두리.items():
        e = _더하기(fills, fill1, {})
        for 쪽, 색 in (("left", 좌우), ("right", 좌우), ("top", 위), ("bottom", 아래)):
            선 = e.find(f"{HH}{쪽}Border")
            선.set("type", "SOLID"), 선.set("width", "0.12 mm"), 선.set("color", 색)
        if 채움:
            붓 = e.makeelement(HC + "fillBrush", {})
            붓.append(붓.makeelement(HC + "winBrush", {"faceColor": 채움, "hatchColor": 검정, "alpha": "0"}))
            e.append(붓)
        번호["borderFill"][역할] = int(e.get("id"))
    return 번호


def main() -> None:
    doc = HwpxDocument.new()
    머리 = doc.oxml.headers[0]
    번호 = _모양들(머리.element)
    머리.mark_dirty()  # 요소를 직접 고쳤다 — 저장 때 다시 쓰게 한다
    margin = doc.sections[0].element.find(f".//{HP}secPr/{HP}pagePr/{HP}margin")
    for k, v in 여백.items():
        margin.set(k, str(v))
    doc.sections[0].mark_dirty()
    with tempfile.TemporaryDirectory() as tmp:
        원형 = Path(tmp) / "seed.hwpx"
        doc.save_to_path(str(원형))
        print(extract_skeleton(원형, 킷 / "skeleton.hwpx"))

    킷_json = 킷 / "kit.json"
    데이터 = json.loads(킷_json.read_text(encoding="utf-8"))
    for 종류, 표 in 번호.items():
        데이터["styles"][종류] = {역할: 표[역할] for 역할 in 데이터["styles"][종류]}
    킷_json.write_text(json.dumps(데이터, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(데이터["styles"], ensure_ascii=False))


if __name__ == "__main__":
    main()
