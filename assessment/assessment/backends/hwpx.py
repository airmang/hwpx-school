"""계획 → hwpx. 스켈레톤(1단 머리 문단 + 2단 전환 문단) 위에 python-hwpx 로 쌓는다.
worksheet/backends/hwpx.py 의 `_셀` 순서 규칙(내용 먼저, 서식 나중)을 따른다."""

from __future__ import annotations

from pathlib import Path

from hwpx.document import HwpxDocument
from lxml import etree

from assessment.blocks import InputError
from assessment.kit import Kit
from assessment.memo import append_memo_run
from assessment.ns import HP
from assessment.plan import CELL_ROLES, CellPlan, ColumnBreakPlan, ParaPlan, Plan, TablePlan, TitlePlan


def _q(tag: str) -> str:
    return f"{{{HP}}}{tag}"


class HwpxWriter:
    def __init__(self, kit: Kit) -> None:
        self.kit = kit
        self.doc = HwpxDocument.open(kit.skeleton)
        self.section = self.doc.sections[0]
        문단 = self.section.element.findall(_q("p"))
        assert len(문단) == 2, "스켈레톤은 문단 2개(1단 머리 + 2단 전환)여야 한다"
        self._머리, self._2단 = 문단
        # 2단 전환 문단을 떼어 두었다가 제목·학번 뒤에 다시 붙인다.
        self.section.element.remove(self._2단)
        self.section.mark_dirty()
        self._단나눔_대기 = False
        self._메모_번호 = 0
        self._그림_캐시: dict[Path, str] = {}

    # --- 머리 ---------------------------------------------------------------
    def _title(self, plan: TitlePlan) -> None:
        k, 머리 = self.kit, self._머리
        머리.set("paraPrIDRef", str(k.para_pr["title"]))

        def run(char: str) -> etree._Element:
            return etree.SubElement(머리, _q("run"), {"charPrIDRef": str(k.char_pr[char])})

        t = etree.SubElement(run("title"), _q("t"))
        etree.SubElement(t, _q("markpenBegin"), {"color": k.furniture["titleMarkpen"]})
        # ElementTree 에서 markpenBegin 뒤 글은 tail 이다.
        t[-1].tail = plan.main
        끝_t = t
        if plan.suffix:
            끝_t = etree.SubElement(run("title_suffix"), _q("t"))
            끝_t.text = plan.suffix
        etree.SubElement(끝_t, _q("markpenEnd")).tail = " "
        if plan.score:
            etree.SubElement(run("score"), _q("t")).text = plan.score
        self.section.mark_dirty()
        self.doc.add_paragraph(k.furniture["idLine"], para_pr_id_ref=k.para_pr["id_line"], char_pr_id_ref=k.char_pr["note"])
        self.section.element.append(self._2단)
        self.section.mark_dirty()

    # --- 본문 ---------------------------------------------------------------
    def _새_문단_표시(self, 전_개수: int) -> None:
        """이번 draw 로 생긴 첫 최상위 문단에 대기 중인 단 나눔을 건다."""
        if not self._단나눔_대기:
            return
        문단 = self.section.element.findall(_q("p"))
        if len(문단) > 전_개수:
            문단[전_개수].set("columnBreak", "1")
            self.section.mark_dirty()
            self._단나눔_대기 = False

    def _para(self, plan: ParaPlan) -> None:
        k = self.kit
        첫 = plan.runs[0]
        p = self.doc.add_paragraph(첫.text, para_pr_id_ref=k.para_pr[plan.para], char_pr_id_ref=k.char_pr[첫.char])
        for r in plan.runs[1:]:
            if r.memo:
                run = p.add_run("", char_pr_id_ref=k.char_pr[r.char])
                # add_run("") 이 만든 빈 t 를 지우고 메모 구조로 채운다.
                for t in run.element.findall(_q("t")):
                    run.element.remove(t)
                self._메모_번호 += 1
                append_memo_run(run.element, r.text, r.memo, number=self._메모_번호, kit=k)
                self.section.mark_dirty()
            else:
                p.add_run(r.text, char_pr_id_ref=k.char_pr[r.char])

    def _그림_id(self, path: Path) -> str:
        if path not in self._그림_캐시:
            self._그림_캐시[path] = self.doc.media.add_image(path.read_bytes(), "png").item_id
        return self._그림_캐시[path]

    def _셀(self, 표, r: int, c: int, 칸: CellPlan, 폭: int | None, 높이: int) -> None:
        k = self.kit
        보더, 파라, 캐릭, _ = CELL_ROLES[칸.role]
        if 칸.picture is not None:
            표.set_cell_text(r, c, "\n".join(["", *칸.lines]), split_paragraphs=True)
            표.cell(r, c).paragraphs[0].add_picture(self._그림_id(칸.picture.path), width=칸.picture.width, height=칸.picture.height)
        elif len(칸.lines) > 1:
            표.set_cell_text(r, c, "\n".join(칸.lines), split_paragraphs=True)
        else:
            # 밑줄 답칸의 밑줄은 칸 아래 테두리(borderFill underline)다 — 글자는 라벨뿐.
            표.set_cell_text(r, c, 칸.lines[0] if 칸.lines else "")
        표.set_cell_border_fill(r, c, k.border_fill[보더])
        표.cell(r, c).set_size(width=폭, height=높이)
        for i, 문단 in enumerate(표.cell(r, c).paragraphs):
            # 그림 문단(0번)은 role 대로 가운데, 캡션 문단(1번~)은 caption_para 가 있으면 그걸로.
            캡션_문단 = 칸.picture is not None and i > 0 and 칸.caption_para is not None
            문단.para_pr_id_ref = k.para_pr[칸.caption_para if 캡션_문단 else 파라]
            문단.char_pr_id_ref = k.char_pr[캐릭]

    def _table(self, plan: TablePlan) -> None:
        k = self.kit
        # 그림은 표보다 먼저, 위 행·왼쪽 칸부터 등록 — BinData 번호가 늘 같게.
        for 행 in plan.rows:
            for 칸 in 행:
                if 칸.picture is not None:
                    self._그림_id(칸.picture.path)
        표 = self.doc.add_table(
            len(plan.rows), len(plan.col_widths), width=plan.width,
            border_fill_id_ref=k.border_fill["box"], para_pr_id_ref=k.para_pr["body"],
        )
        # python-hwpx 는 표 바깥 여백을 0 으로 만든다 — 양식처럼 킷 값으로 사방을 채운다.
        바깥 = str(k.furniture["tableOutMargin"])
        표.element.find(_q("outMargin")).attrib.update({"left": 바깥, "right": 바깥, "top": 바깥, "bottom": 바깥})
        표.mark_dirty()
        병합된: set[tuple[int, int]] = set()
        for r0, c0, r1, c1 in plan.merges:
            표.merge_cells(r0, c0, r1, c1)
            병합된 |= {(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)} - {(r0, c0)}
        for r, 행 in enumerate(plan.rows):
            for c, 칸 in enumerate(행):
                if (r, c) in 병합된:
                    continue
                self._셀(표, r, c, 칸, *self._칸_크기(plan, r, c))

    def _행_높이(self, 칸: CellPlan) -> int:
        return self.kit.furniture["rowHeight"][CELL_ROLES[칸.role][3]]

    def _칸_크기(self, plan: TablePlan, r: int, c: int) -> tuple[int, int]:
        """(폭, 높이). 병합 칸은 가로로 덮은 열 폭의 합, 세로로 덮은 행 높이(병합 첫 열 칸의 역할대로)의 합."""
        for r0, c0, r1, c1 in plan.merges:
            if (r0, c0) == (r, c):
                폭 = sum(plan.col_widths[c0 : c1 + 1])
                return 폭, sum(self._행_높이(plan.rows[rr][c0]) for rr in range(r0, r1 + 1))
        return plan.col_widths[c], self._행_높이(plan.rows[r][c])

    def draw(self, plan: Plan) -> None:
        if isinstance(plan, TitlePlan):
            self._title(plan)
            return
        if isinstance(plan, ColumnBreakPlan):
            self._단나눔_대기 = True
            return
        전 = len(self.section.element.findall(_q("p")))
        if isinstance(plan, ParaPlan):
            self._para(plan)
        elif isinstance(plan, TablePlan):
            self._table(plan)
        else:
            raise TypeError(f"그릴 수 없는 계획: {type(plan).__name__}")
        self._새_문단_표시(전)

    def save(self, path: Path) -> None:
        if self._단나눔_대기:
            raise InputError(":::단나눔 뒤에 아무 내용이 없다 — 마지막 단나눔을 지운다")
        self.doc.save_to_path(path)
