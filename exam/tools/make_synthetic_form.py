"""합성 원안지 서식 — 학교와 무관한 시험지 빈 서식을 python-hwpx 기본 템플릿에서 새로 만든다.

    uv run --no-project --with "python-hwpx==6.6.0" --with lxml python tools/make_synthetic_form.py kits/synthetic/synthetic_form.hwpx

실제 학교 서식을 가공하지 않는다(구조·디자인도 학교 것이 아니다). 엔진 테스트가 학교 킷 없이 돌도록
kits/synthetic(킷)과 짝을 이룬다. 서식을 다시 만들면 킷의 form.sha256을 갱신한다.

모양(글자 자리 슬롯 양식 — 누름틀 없음):
  문단 0  관리박스: 결재 표(시험명·학년/과목·일시·출제교사) + 유의 상자(총점·선택형·논술형 줄) — 함초롬돋움
  문단 1~ 샘플 문항 구역: 글자 번호 `1. `(12pt 굵게) 문항, 5·2·3·1행 답항, 〈보기〉·〈조건〉 2×1 견본, 자료 1×1 견본, 세트 표지 `[3∼4]`
  `【논술형` 문단부터 꼬리 앞까지: 논술형 샘플(조판 때 지운다)
  마지막 문단: 꼬리 박스 1×1 `※ 확인 사항`
  꼬리말: `과목명 1학년 (1쪽 중 N쪽)`(N = 자동 쪽 번호)
  B4 세로 2단(단 사이 실선). 본문 함초롬바탕 11pt.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import lxml.etree as ET
from hwpx.document import HwpxDocument

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HPNS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
UNITCHAR = "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"

W, H = 72852, 103180
M = {"left": 5000, "right": 5000, "top": 5669, "bottom": 4000, "header": 0, "footer": 2000}
GAP = 1400
COLW = (W - M["left"] - M["right"] - GAP) // 2          # 30726
BATANG, DOTUM = "1", "0"                                   # 기본 템플릿 글꼴 id


def _char(h, *, height: int, font: str, bold: bool = False) -> str:
    def modify(el):
        el.set("height", str(height))
        fr = el.find(HH + "fontRef")
        for k in list(fr.attrib):
            fr.set(k, font)
        if bold and el.find(HH + "bold") is None:
            el.insert(0, ET.Element(HH + "bold"))

    def match(el):
        fr = el.find(HH + "fontRef")
        return (el.get("height") == str(height) and fr is not None and fr.get("hangul") == font
                and (el.find(HH + "bold") is not None) == bold and el.get("textColor", "#000000") == "#000000")

    return h.ensure_char_property(predicate=match, modifier=modify, base_char_pr_id="0").get("id")


def _tab(h, positions: list[int]) -> str:
    """한컴 저장본과 같은 탭 모양 — 탭마다 hp:switch(case = HWPUNIT, default = 2배)."""
    box = next(h.element.iter(HH + "tabProperties"))
    t = ET.SubElement(box, HH + "tabPr", {"id": str(max(int(x.get("id")) for x in box) + 1),
                                          "autoTabLeft": "0", "autoTabRight": "0"})
    for pos in positions:
        sw = ET.SubElement(t, HP + "switch")
        case = ET.SubElement(sw, HP + "case", {f"{{{HPNS}}}required-namespace": UNITCHAR})
        ET.SubElement(case, HH + "tabItem", {"pos": str(pos), "type": "LEFT", "leader": "NONE", "unit": "HWPUNIT"})
        default = ET.SubElement(sw, HP + "default")
        ET.SubElement(default, HH + "tabItem", {"pos": str(2 * pos), "type": "LEFT", "leader": "NONE"})
    box.set("itemCnt", str(len(box.findall(HH + "tabPr"))))
    return t.get("id")


def _para(h, *, line: int, left: int = 0, intent: int = 0, tab: str | None = None) -> str:
    pid = h.ensure_paragraph_format(base_para_pr_id="0", line_spacing_percent=line,
                                    margins={"left": left, "intent": intent})
    if tab is not None:
        pp = next(p for p in h.element.iter(HH + "paraPr") if p.get("id") == str(pid))
        pp.set("tabPrIDRef", tab)
    return str(pid)


def build(out: Path) -> None:
    doc = HwpxDocument.new()
    h = doc.oxml.headers[0]
    sec = doc.sections[0]

    # ---- 쪽·단 ----
    pp = sec.element.find(f".//{HP}secPr/{HP}pagePr")
    pp.set("width", str(W)), pp.set("height", str(H)), pp.set("landscape", "WIDELY")
    mg = pp.find(HP + "margin")
    for k, v in M.items():
        mg.set(k, str(v))
    mg.set("gutter", "0")
    doc.set_columns(2, same_gap=GAP, separator_type="SOLID", separator_width="0.12 mm")

    # ---- 글자·문단·스타일 ----
    body = _char(h, height=1100, font=BATANG)
    num = _char(h, height=1200, font=BATANG, bold=True)
    admin = _char(h, height=1000, font=DOTUM)
    admin_b = _char(h, height=1200, font=DOTUM, bold=True)
    roles = {
        "문항": _para(h, line=160),
        "5행답항": _para(h, line=160, left=1000, intent=-1600, tab=_tab(h, [17000])),
        "3행답항": _para(h, line=160, left=1000, tab=_tab(h, [15500])),
        "2행답항": _para(h, line=160, left=1000, tab=_tab(h, [10500, 20000])),
        "1행답항": _para(h, line=160, left=1000, tab=_tab(h, [6400, 11800, 17200, 22600])),
        "보기안": _para(h, line=160, left=0, intent=-1800),
        "자료안": _para(h, line=150),
    }
    style = {name: h.ensure_style(name, style_type="PARA", para_pr_id_ref=pid, char_pr_id_ref=body)
             for name, pid in roles.items()}
    normal = "0"

    def p(text_runs, st=normal, pid=None):
        """문단 하나 — text_runs = [(글, charPr)]."""
        par = doc.add_paragraph("", style_id_ref=style.get(st, st), para_pr_id_ref=pid or roles.get(st, "0"),
                                char_pr_id_ref=body, include_run=False, inherit_style=False)
        for t, cp in text_runs:
            run = ET.SubElement(par.element, HP + "run", {"charPrIDRef": cp})
            te = ET.SubElement(run, HP + "t")
            pieces = t.split("\t")  # 탭은 글자가 아니라 hp:tab 요소
            te.text = pieces[0]
            for piece in pieces[1:]:
                tab = ET.SubElement(te, HP + "tab", {"width": "0", "leader": "0", "type": "1"})
                tab.tail = piece
        return par

    def table_in(par, rows, cols, widths, heights, *, inline=True):
        """par 문단에 표를 넣는다(add_table로 만들어 옮긴다). 칸 글은 뒤에서 채운다."""
        tmp = doc.add_table(rows, cols, width=sum(widths), height=sum(heights))
        tmp.set_column_widths(widths)
        for r in range(rows):
            for c in range(cols):
                tmp.cell(r, c).set_size(height=heights[r])
        tbl = tmp.element
        holder = tbl.getparent()
        temp_p = holder.getparent()
        run = ET.SubElement(par.element, HP + "run", {"charPrIDRef": admin})
        run.append(tbl)
        sec.element.remove(temp_p)
        if inline:
            tmp.set_treat_as_char(True)
        return tmp

    def cell_text(tbl, r, c, lines, cp, st=normal, align=None):
        cell = tbl.cell(r, c)
        sub = cell.element.find(HP + "subList")
        for old in sub.findall(HP + "p"):
            sub.remove(old)
        for line in lines:
            ap = ET.SubElement(sub, HP + "p", {"id": "0", "paraPrIDRef": roles.get(st, "0"), "styleIDRef": style.get(st, st),
                                               "pageBreak": "0", "columnBreak": "0", "merged": "0"})
            run = ET.SubElement(ap, HP + "run", {"charPrIDRef": cp})
            ET.SubElement(run, HP + "t").text = line

    # ---- 문단 0: 관리박스 ----
    p0 = sec.paragraphs[0]
    결재 = table_in(p0, 2, 3, [12000, 12726, 6000], [2400, 2400])
    cell_text(결재, 0, 0, ["2026학년도 1학기 1차", "정기시험"], admin)
    cell_text(결재, 0, 1, ["1학년", "과목명"], admin_b)
    cell_text(결재, 0, 2, ["결  재"], admin)
    cell_text(결재, 1, 0, ["3월 2일 (월) 1교시"], admin)
    cell_text(결재, 1, 1, ["출제교사 : 홍길동"], admin)
    cell_text(결재, 1, 2, [" "], admin)
    유의 = table_in(p0, 1, 1, [COLW], [5200])
    cell_text(유의, 0, 0, ["◆ 합성 서식 — 유의 사항이 들어가는 자리입니다.",
                          "◆ 총점 : 100점  선택형 : 100점(○○문항)",
                          "   논술형 : 0점(○문항)"], admin)

    # ---- 샘플 문항 구역 ----
    p([("1. ", num), ("합성 발문이 들어가는 자리이다. 알맞은 것은? [4.0점]", body)], "문항")
    # 답지 글은 글자 폭 측정에도 쓴다(대문자·소문자·숫자 — 샘플 구역이라 조판 때 사라진다)
    for mark, t in zip("①②③④⑤", ("가나다라마바사아자차", "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz",
                                   "0123456789 0123456789", "합성 답지 마")):
        p([(f"{mark} {t}", body)], "5행답항")
    보기_p = p([("", body)])
    보기 = table_in(보기_p, 2, 1, [29400], [1400, 4800])
    cell_text(보기, 0, 0, ["< 보 기 >"], body)
    cell_text(보기, 1, 0, ["ㄱ. 합성 항목 하나.", "ㄴ. 합성 항목 둘."], body, "보기안")
    p([("2. ", num), ("합성 발문 둘. [3.0점]", body)], "문항")
    p([("① 가\t② 나\t③ 다", body)], "2행답항")
    p([("④ 라\t⑤ 마", body)], "2행답항")
    자료_p = p([("", body)])
    자료 = table_in(자료_p, 1, 1, [29400], [4200])
    cell_text(자료, 0, 0, ["합성 자료 글이 들어가는 자리."], body, "자료안")
    조건_p = p([("", body)])  # 〈조건〉 견본 — 〈보기〉와 같은 2×1(제목 줄 + 내용 칸)
    조건 = table_in(조건_p, 2, 1, [29400], [1400, 4800])
    cell_text(조건, 0, 0, ["< 조 건 >"], body)
    cell_text(조건, 1, 0, ["(가) 합성 조건 하나.", "(나) 합성 조건 둘."], body, "보기안")
    p([("[3∼4]", num), (" 다음 글을 읽고, 물음에 답하시오.", body)])
    p([("3. ", num), ("합성 세트 문항. [3.0점]", body)], "문항")
    p([("① 가\t② 나", body)], "3행답항")
    p([("③ 다\t④ 라", body)], "3행답항")
    p([("⑤ 마", body)], "3행답항")
    p([("① 가\t② 나\t③ 다\t④ 라\t⑤ 마", body)], "1행답항")

    # ---- 논술형 샘플(조판 때 지운다) ----
    p([("【논술형 1】 합성 논술형 자리입니다.", body)])
    p([("(1) 합성 논술 물음.", body)])

    # ---- 꼬리 박스 ----
    꼬리_p = p([("", body)])
    꼬리 = table_in(꼬리_p, 1, 1, [29400], [3400])
    cell_text(꼬리, 0, 0, ["※ 확인 사항", "∘ 합성 확인 문구 — 답안지 기입을 확인하시오."], admin)

    # ---- 꼬리말 ----
    doc.set_footer_content([{"align": "CENTER", "children": [
        {"type": "run", "text": "과목명 1학년 (1쪽 중 "}, {"page_number": "page"}, {"type": "run", "text": "쪽)"}]}])

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save_to_path(str(out))
    print(f"wrote {out}")


if __name__ == "__main__":
    build(Path(sys.argv[1]))
