"""합성 원안지 서식 — 학교와 무관한 시험지 빈 서식을 python-hwpx 기본 템플릿에서 새로 만든다.

    uv run --no-project --with "python-hwpx>=7.0,<8" --with lxml python tools/make_synthetic_form.py kits/synthetic/synthetic_form.hwpx

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
from pathlib import Path

import lxml.etree as ET
from hwpx.document import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

W, H = 72852, 103180
M = {"left": 5000, "right": 5000, "top": 5669, "bottom": 4000, "header": 0, "footer": 2000}
GAP = 1400
COLW = (W - M["left"] - M["right"] - GAP) // 2          # 30726
BATANG, DOTUM = "1", "0"                                   # 기본 템플릿 글꼴 id


def _char(doc, *, height: int, font: str, bold: bool = False) -> str:
    """기본 글자 모양(0)에서 크기·글꼴(모든 언어)·굵게만 바꾼 글자 모양(doc.styles.ensure_run — 스키마 차례로 쓴다)."""
    face = doc.styles.fonts("HANGUL")[font].face
    return doc.styles.ensure_run(base_char_pr_id_ref="0", size=height / 100, font=face, bold=bold)


def _tab(doc, positions: list[int]) -> str:
    """한컴 저장본과 같은 탭 모양 — 탭마다 hp:switch(case = HWPUNIT, default = 2배)(doc.styles.ensure_tab_definition)."""
    return doc.styles.ensure_tab_definition(tab_stops=[{"pos": pos, "type": "LEFT", "leader": "NONE"} for pos in positions])


def _tab_run(par, text: str, cp: str) -> None:
    """탭 든 run — 한/글 저장본처럼 hp:tab에 width·leader·type을 적는다. core add_run은 속성 없는 hp:tab을 써서
    (CORE-ASKS) 이 run만 직접 쓴다."""
    run = ET.SubElement(par.element, HP + "run", {"charPrIDRef": cp})
    te = ET.SubElement(run, HP + "t")
    pieces = text.split("	")
    te.text = pieces[0]
    for piece in pieces[1:]:
        tab = ET.SubElement(te, HP + "tab", {"width": "0", "leader": "0", "type": "1"})
        tab.tail = piece


def _para(doc, *, line: int, left: int = 0, intent: int = 0, tab: str | None = None) -> str:
    return str(doc.styles.ensure_paragraph_format(base_para_pr_id_ref="0", line_spacing=line,
                                                  margins={"left": left, "intent": intent}, tab_pr_id_ref=tab))


def build(out: Path) -> None:
    doc = HwpxDocument.new(empty_first_line=True)  # 7.0: 6.x처럼 빈 첫 줄(구역 설정)에서 시작한다
    sec = doc.sections[0]

    # ---- 쪽·단 ----
    doc.page.set_size(width=W, height=H, orientation="PORTRAIT")
    doc.page.set_margins(**M, gutter=0)
    doc.page.set_columns(2, same_gap=GAP, separator_type="SOLID", separator_width_mm=0.12)

    # ---- 글자·문단·스타일 ----
    body = _char(doc, height=1100, font=BATANG)
    num = _char(doc, height=1200, font=BATANG, bold=True)
    admin = _char(doc, height=1000, font=DOTUM)
    admin_b = _char(doc, height=1200, font=DOTUM, bold=True)
    roles = {
        "문항": _para(doc, line=160),
        "5행답항": _para(doc, line=160, left=1000, intent=-1600, tab=_tab(doc, [17000])),
        "3행답항": _para(doc, line=160, left=1000, tab=_tab(doc, [15500])),
        "2행답항": _para(doc, line=160, left=1000, tab=_tab(doc, [10500, 20000])),
        "1행답항": _para(doc, line=160, left=1000, tab=_tab(doc, [6400, 11800, 17200, 22600])),
        "보기안": _para(doc, line=160, left=0, intent=-1800),
        "자료안": _para(doc, line=150),
    }
    style = {name: doc.styles.ensure_style(name, style_type="PARA", para_pr_id_ref=pid, char_pr_id_ref=body)
             for name, pid in roles.items()}
    normal = "0"

    def p(text_runs, st=normal, pid=None):
        """문단 하나 — text_runs = [(글, charPr)]. 탭은 hp:t 안 hp:tab(paragraph.add_run)."""
        par = doc.add_paragraph("", para_pr_id_ref=pid or roles.get(st, "0"),
                                char_pr_id_ref=body, include_run=False, inherit_style=False)
        par.style_id_ref = style.get(st, st)
        for t, cp in text_runs:
            if "	" in t:
                _tab_run(par, t, cp)
            else:
                par.add_run(t, char_pr_id_ref=cp)
        return par

    def table_in(par, rows, cols, widths, heights, *, inline=True):
        """par 문단 끝에 표를 넣는다(doc.add_table로 만들어 table.move_to로 옮기고, 빈 자리 문단은 지운다). 칸 글은 뒤에서 채운다."""
        tmp = doc.add_table(rows, cols, width=sum(widths), height=sum(heights))
        tmp.set_column_widths(widths)
        for r in range(rows):
            for c in range(cols):
                tmp.cell(r, c).set_size(height=heights[r])
        holder = tmp.paragraph
        tmp.move_to(par)
        holder.remove()
        if inline:
            tmp.set_treat_as_char(True)
        return tmp

    def cell_text(tbl, r, c, lines, cp, st=normal, align=None):
        """칸 글 — 칸의 첫 문단을 첫 줄로 고쳐 쓰고, 나머지 줄은 문단을 더한다(같은 문단 모양·스타일·글자 모양)."""
        cell = tbl.cell(r, c)
        first = cell.paragraphs[0]
        for extra in cell.paragraphs[1:]:
            extra.remove()
        first.para_pr_id_ref = roles.get(st, "0")
        first.style_id_ref = style.get(st, st)
        for run in first.runs:
            run.remove()
        first.add_run(lines[0], char_pr_id_ref=cp)
        for line in lines[1:]:
            ap = cell.add_paragraph(line, para_pr_id_ref=roles.get(st, "0"), char_pr_id_ref=cp)
            ap.style_id_ref = style.get(st, st)

    # ---- 문단 0: 관리박스 ----
    p0 = sec.paragraphs[0]
    p0.add_run("", char_pr_id_ref=admin)  # 표는 관리 글자 런에(옛 서식처럼 구역 설정 런 뒤 따로)
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
    보기_p = p([("", admin)])
    보기 = table_in(보기_p, 2, 1, [29400], [1400, 4800])
    cell_text(보기, 0, 0, ["< 보 기 >"], body)
    cell_text(보기, 1, 0, ["ㄱ. 합성 항목 하나.", "ㄴ. 합성 항목 둘."], body, "보기안")
    p([("2. ", num), ("합성 발문 둘. [3.0점]", body)], "문항")
    p([("① 가\t② 나\t③ 다", body)], "2행답항")
    p([("④ 라\t⑤ 마", body)], "2행답항")
    자료_p = p([("", admin)])
    자료 = table_in(자료_p, 1, 1, [29400], [4200])
    cell_text(자료, 0, 0, ["합성 자료 글이 들어가는 자리."], body, "자료안")
    조건_p = p([("", admin)])  # 〈조건〉 견본 — 〈보기〉와 같은 2×1(제목 줄 + 내용 칸)
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
    꼬리_p = p([("", admin)])
    꼬리 = table_in(꼬리_p, 1, 1, [29400], [3400])
    cell_text(꼬리, 0, 0, ["※ 확인 사항", "∘ 합성 확인 문구 — 답안지 기입을 확인하시오."], admin)

    # ---- 꼬리말 ----
    doc.page.set_footer(content=[{"align": "CENTER", "children": [
        {"type": "run", "text": "과목명 1학년 (1쪽 중 "}, {"page_number": "page"}, {"type": "run", "text": "쪽)"}]}])

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    print(f"wrote {out}")


if __name__ == "__main__":
    build(Path(sys.argv[1]))
