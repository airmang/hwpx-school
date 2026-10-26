"""씨앗 견본 — kits/standard/견본.hwpx 를 python-hwpx 기본 템플릿에서 새로 만든다.

    uv run python scripts/씨앗_견본.py

어느 기관·학교의 문서도 가공하지 않는다. 기본 템플릿에 보고서 꼴(제목, 날짜, 장 제목 띠,
□·ㅇ·-·※ 위계)을 자리표시와 함께 얹는다. 실제 학교 서식은 이 파일이 아니라 사용자가
한/글에서 자리표시를 적은 자기 견본으로 등록한다(스킬 `skills/report` 참고).

만든 뒤 `uv run python -m report_kit register kits/standard/견본.hwpx kits/standard` 로
킷을 다시 수확한다.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from hwpx import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"

DOTUM, BATANG = "0", "1"  # 기본 템플릿 글꼴 id
띠색 = "#2E4A7D"  # 합성 씨앗의 남색 — 실제 색은 각 견본이 정한다
선색 = "#2E4A7D"


def _문단모양(doc: HwpxDocument, 왼쪽: int, 내어: int, 줄: int, 위: int = 0, 정렬: str = "JUSTIFY") -> str:
    """기본 문단 모양을 복제해 정렬·왼쪽 여백·내어쓰기·줄간격·문단 위 간격을 정한다 (HWPUNIT)."""

    머리 = doc.oxml.headers[0]
    paraprs = next(머리.element.iter(HH + "paraProperties"))
    원형 = next(e for e in paraprs if e.get("id") == "0")
    새것 = deepcopy(원형)
    새것.set("id", str(max(int(e.get("id")) for e in paraprs) + 1))
    새것.find(HH + "align").set("horizontal", 정렬)
    case, default = 새것.find(HP + "switch")
    for 가지, 배 in ((case, 1), (default, 2)):  # case = HWPUNIT, default = 그 2배
        여백 = 가지.find(HH + "margin")
        여백.find(HC + "left").set("value", str(왼쪽 * 배))
        여백.find(HC + "intent").set("value", str(내어 * 배))
        여백.find(HC + "prev").set("value", str(위 * 배))
        가지.find(HH + "lineSpacing").set("value", str(줄))
    paraprs.append(새것)
    paraprs.set("itemCnt", str(len(paraprs)))
    머리.mark_dirty()
    return 새것.get("id")


def _문단(doc: HwpxDocument, 글: str, 글자: str, 문단: str | None = None):
    return doc.add_paragraph(글, char_pr_id_ref=글자, para_pr_id_ref=문단, inherit_style=False)


def _칸(table, 행: int, 열: int, 글: str, 글자: str, 문단: str | None = None) -> None:
    table.cell(행, 열).text = 글
    for p in table.cell(행, 열).paragraphs:
        if 문단 is not None:
            p.para_pr_id_ref = 문단
        for run in p.runs:
            run.char_pr_id_ref = 글자


def main() -> None:
    doc = HwpxDocument.new()
    글자 = {
        "표제": doc.styles.ensure_run(bold=True, size=20, font="함초롬돋움"),
        "날짜": doc.styles.ensure_run(bold=True, size=15, font="함초롬바탕"),
        "띠번호": doc.styles.ensure_run(bold=True, size=16, color="#FFFFFF", font="함초롬돋움"),
        "띠제목": doc.styles.ensure_run(bold=True, size=16, font="함초롬돋움"),
        "1단계": doc.styles.ensure_run(bold=True, size=15, font="함초롬돋움"),
        "2단계": doc.styles.ensure_run(size=14, font="함초롬바탕"),
        "3단계": doc.styles.ensure_run(size=13, font="함초롬바탕"),
        "참고": doc.styles.ensure_run(size=12, font="함초롬바탕"),
        "간격": doc.styles.ensure_run(size=6),
        "띠간격": doc.styles.ensure_run(size=12),
    }
    문단 = {
        "가운데": _문단모양(doc, 0, 0, 160, 0, "CENTER"),
        "1단계": _문단모양(doc, 0, 0, 160, 400),
        # 한/글은 첫 줄을 left에서, 둘째 줄부터 left+|내어쓰기|에서 시작한다(실렌더 확인).
        # 내어쓰기 = 부호와 뒤 빈칸 폭 → 둘째 줄이 내용 첫 글자에 맞는다. -·※ 는 ㅇ 내용 아래에서 시작.
        "2단계": _문단모양(doc, 700, -2000, 160, 200),
        "3단계": _문단모양(doc, 2700, -1100, 160, 100),
        "참고": _문단모양(doc, 2700, -1600, 150, 0),
    }
    띠채움 = doc.styles.ensure_border_fill(border_color=띠색, fill_color=띠색)
    띠선 = doc.styles.ensure_border_fill(border_color=선색, active_borders=("top", "bottom"))
    표제선 = doc.styles.ensure_border_fill(border_color=선색, border_width="0.7 mm", active_borders=("top", "bottom"))
    빈칸 = doc.styles.ensure_border_fill(border_color="#FFFFFF", active_borders=())

    # 제목표 — 위아래 굵은 선 사이에 두 줄 제목
    표제 = doc.add_table(1, 1)
    표제.set_cell_border_fill(0, 0, 표제선)
    셀 = 표제.cell(0, 0)
    셀.text = "{{표제.위}}"
    셀.add_paragraph("{{표제.아래}}")
    for p in 셀.paragraphs:
        p.para_pr_id_ref = 문단["가운데"]
        for run in p.runs:
            run.char_pr_id_ref = 글자["표제"]
    _문단(doc, "", 글자["간격"])
    _문단(doc, "{{날짜}}", 글자["날짜"], 문단["가운데"])

    # 쪽 나눔 — 표지 다음. 글이 없는 문단이 쪽을 넘긴다.
    _문단(doc, "", 글자["간격"])
    나눔 = _문단(doc, "{{쪽나눔}}", 글자["간격"])
    나눔.element.set("pageBreak", "1")

    # 장 제목 띠 — 색 채운 번호 칸 | 좁은 틈 | 아래위 선만 있는 제목 칸. 위 빈 줄이 앞 장과 띄운다.
    _문단(doc, "", 글자["띠간격"])
    띠 = doc.add_table(1, 3)
    띠.set_column_widths([2, 0.3, 17])
    _칸(띠, 0, 0, "{{띠.번호}}", 글자["띠번호"], 문단["가운데"])
    _칸(띠, 0, 2, " {{띠.제목}}", 글자["띠제목"])
    띠.set_cell_border_fill(0, 0, 띠채움)
    띠.set_cell_border_fill(0, 1, 빈칸)
    띠.set_cell_border_fill(0, 2, 띠선)

    _문단(doc, "", 글자["간격"])
    _문단(doc, "□ {{1단계}}", 글자["1단계"], 문단["1단계"])
    _문단(doc, "ㅇ {{2단계}}", 글자["2단계"], 문단["2단계"])
    _문단(doc, "- {{3단계}}", 글자["3단계"], 문단["3단계"])
    _문단(doc, "※ {{참고}}", 글자["참고"], 문단["참고"])

    킷.mkdir(parents=True, exist_ok=True)
    doc.save_to_path(str(킷 / "견본.hwpx"))
    doc.close()
    print(킷 / "견본.hwpx")


if __name__ == "__main__":
    main()
