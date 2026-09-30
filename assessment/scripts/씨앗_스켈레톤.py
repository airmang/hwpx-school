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
from copy import deepcopy
from pathlib import Path

from hwpx import HwpxDocument

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from assessment.skeleton import extract_skeleton  # noqa: E402

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"

DOTUM = "0"                                     # 기본 템플릿 글꼴 id(함초롬돋움)
LANGS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")
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


def _더하기(묶음, 원형, 속성들: dict):
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

    번호: dict[str, dict[str, int]] = {"borderFill": {}, "charPr": {"blank": 0}, "paraPr": {}}
    이미: dict[tuple, str] = {}
    for 역할, 크기 in 글자.items():
        열쇠 = ("c", 크기)
        if 열쇠 not in 이미:
            e = _더하기(charprs, char0, {"height": str(크기), "textColor": 검정})
            for k in LANGS:
                e.find(HH + "fontRef").set(k, DOTUM)
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
                가지.find(HH + "lineSpacing").set("value", str(줄))  # 줄간격은 두 가지가 같다
            이미[열쇠] = e.get("id")
        번호["paraPr"][역할] = int(이미[열쇠])
    for 역할, (선색, 채움) in 테두리.items():
        e = _더하기(fills, fill1, {})
        for 쪽 in ("left", "right", "top", "bottom"):
            선 = e.find(f"{HH}{쪽}Border")
            선.set("type", "SOLID" if 선색 else "NONE")
            선.set("width", "0.12 mm")
            선.set("color", 선색 or 검정)
        if 채움:
            붓 = e.makeelement(HC + "fillBrush", {})
            붓.append(붓.makeelement(HC + "winBrush", {"faceColor": 채움, "hatchColor": 검정, "alpha": "0"}))
            e.append(붓)
        번호["borderFill"][역할] = int(e.get("id"))
    return 번호


def _2단_전환_문단(doc: HwpxDocument) -> None:
    """추출은 원본의 세 번째 문단에서 colCount=2 colPr 을 찾는다 — 빈 문단 하나 뒤에 짓는다."""
    빈, p = doc.add_paragraph(""), doc.add_paragraph("")
    for 번째, 문단_ in enumerate((빈, p), start=1):
        문단_.element.set("id", str(번째))  # 무작위 id 대신 고정 — 다시 돌려도 같은 스켈레톤
    run = p.element.find(HP + "run")
    ctrl = run.makeelement(HP + "ctrl", {})
    ctrl.append(ctrl.makeelement(HP + "colPr", {
        "id": "", "type": "NEWSPAPER", "layout": "LEFT", "colCount": "2",
        "sameSz": "1", "sameGap": str(단_간격),
    }))
    run.insert(0, ctrl)
    doc.sections[0].mark_dirty()


def main() -> None:
    doc = HwpxDocument.new()
    머리 = doc.oxml.headers[0]
    번호 = _모양들(머리.element)
    머리.mark_dirty()  # 요소를 직접 고쳤다 — 저장 때 다시 쓰게 한다
    margin = doc.sections[0].element.find(f".//{HP}secPr/{HP}pagePr/{HP}margin")
    for k, v in 여백.items():
        margin.set(k, str(v))
    doc.sections[0].mark_dirty()
    _2단_전환_문단(doc)
    with tempfile.TemporaryDirectory() as tmp:
        원형 = Path(tmp) / "seed.hwpx"
        doc.save_to_path(str(원형))
        보고 = extract_skeleton(원형, 킷 / "skeleton.hwpx")
        print(보고)
    번호["borderFill"]["underline"] = 보고["underline_border_fill"]

    킷_json = 킷 / "kit.json"
    데이터 = json.loads(킷_json.read_text(encoding="utf-8"))
    for 종류, 표 in 번호.items():
        데이터["styles"][종류] = {역할: 표[역할] for 역할 in 데이터["styles"][종류]}
    킷_json.write_text(json.dumps(데이터, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(데이터["styles"], ensure_ascii=False))


if __name__ == "__main__":
    main()
