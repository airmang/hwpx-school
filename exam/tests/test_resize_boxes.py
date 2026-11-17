"""박스 높이 다시 맞추기(compose.resize_boxes) — 레일 칸이 내용 행에 걸친 모양을 합성 서식 위에 지어 옛 길(XML)과 견준다.
학교 킷 없이 돈다(합성 킷·합성 서식)."""

from pathlib import Path

import pytest
from hwpx.document import HwpxDocument

from exam_kit import q
from exam_kit.fit import Lines
from exam_kit.kit import load_kit

루트 = Path(__file__).resolve().parents[1]
킷 = 루트 / "kits" / "synthetic"
서식 = 킷 / "synthetic_form.hwpx"


def _옛_resize_boxes(doc, kit, lines) -> int:
    """resize_boxes의 옛 길(r6 전 — XML로 내용 칸·레일 칸(내용 행에 앵커가 있는 것)·표 높이를 직접 고친다). 새 길과 견주는 기준."""
    from exam_kit.compose import _Composer, Samples, _박스
    from exam_kit.kit import style_ids

    ids = style_ids(doc)
    c = _Composer(doc, kit, Samples(None, None, None), answer_key=False)
    shapes = {tuple(str(n) for n in spec["shape"]): k for k, spec in kit.boxes.items() if isinstance(spec, dict)}
    changed = 0
    paras = list(doc.sections[0].paragraphs)
    for i, p in enumerate(paras):
        if i == 0 or i == len(paras) - 1:
            continue
        subs = list(p.element.iter(q("hp", "p")))[1:]
        for tbl in [x for r in p.element.findall(q("hp", "run")) for x in r if x.tag == q("hp", "tbl")]:
            kind = shapes.get((tbl.get("rowCnt"), tbl.get("colCnt")))
            if kind is None:
                continue
            _, (cc, cr), rails, role = _박스(kit, kind)
            cells = {(int(a.get("colAddr")), int(a.get("rowAddr"))): tc
                     for tc in tbl.iter(q("hp", "tc")) for a in [tc.find(q("hp", "cellAddr"))]}
            content = cells.get((cc, cr))
            ps = content.find(q("hp", "subList")).findall(q("hp", "p"))
            if not ps or ids[kit.styles[role]][0] not in {x.get("styleIDRef") for x in ps}:
                continue
            pitch, h = c._line_pitch(role), 0
            for para in ps:
                j = next(n for n, e in enumerate(subs) if e is para)
                h += lines[(i, j)].n * pitch
            h += kit.metrics.box_extra - pitch
            old = int(content.find(q("hp", "cellSz")).get("height"))
            if old == h:
                continue
            for col in (cc, *rails):
                if (col, cr) in cells:
                    cells[(col, cr)].find(q("hp", "cellSz")).set("height", str(h))
            sz = tbl.find(q("hp", "sz"))
            sz.set("height", str(int(sz.get("height")) - old + h))
            changed += 1
    return changed


@pytest.mark.parametrize("레일", ["한 칸", "위에서 걸침", "아래로 걸침", "칸 높이 어긋남"])
def test_박스_높이_레일_칸_옛_길과_견주기(레일):
    """3×3 박스(가운데 열 = 제목·내용·꼬리, 양옆 열 = 레일) — resize_boxes(새 길: table.set_row_height)를 옛 길과 견준다.
    레일이 내용 행 한 칸이든 여러 행에 걸치든(rowSpan > 1) 모든 칸·표 높이가 옛 길과 같아야 한다 — 옛 길은 내용 칸과 내용 행에
    앵커가 있는 레일 칸만 새 높이로, 표 높이는 그 차이만큼 바꾸고 다른 칸은 두었다."""
    import dataclasses

    from exam_kit.compose import resize_boxes
    from exam_kit.fit import inner_paragraphs
    from exam_kit.kit import style_ids

    def 짓기():
        doc = HwpxDocument.open(str(서식))
        kit = dataclasses.replace(load_kit(킷), boxes={"레일박스": {"shape": [3, 3], "content_cell": [1, 1], "rails": [0, 2],
                                                     "style": "box_guide"}}, box_min_height=None)
        sec = doc.sections[0]
        holder = sec.add_paragraph("")
        sec.add_paragraph("")  # 박스 문단이 마지막(꼬리) 문단이 되지 않게
        t = holder.add_table(3, 3, width=30000)
        for r, h in enumerate((1400, 4800, 1400)):
            t.set_row_height(r, h)
        if 레일 == "위에서 걸침":
            t.merge_cells(0, 0, 2, 0)
            t.merge_cells(0, 2, 2, 2)
        elif 레일 == "아래로 걸침":
            t.merge_cells(1, 0, 2, 0)
            t.merge_cells(1, 2, 2, 2)
        elif 레일 == "칸 높이 어긋남":  # 내용 칸만 행보다 높게 적힌 양식(격자와 칸 높이가 어긋남)
            t.cell(1, 1).set_size(height=5300)
        sid = style_ids(doc)[kit.styles["box_guide"]][0]
        cell_p = t.cell(1, 1).paragraphs[0]
        cell_p.style_id_ref = sid
        cell_p.text = "ㄱ. 합성 항목"
        i = len(sec.paragraphs) - 2
        j = next(n for n, x in enumerate(inner_paragraphs(doc)[i]) if x == cell_p)
        return kit, doc, i, {(i, j): Lines(3, "", 1, "ㄱ. 합성 항목")}

    def 높이(doc, i):
        tbl = doc.sections[0].paragraphs[i].element.find(f".//{q('hp', 'tbl')}")
        cells = {(a.get("colAddr"), a.get("rowAddr")): int(tc.find(q("hp", "cellSz")).get("height"))
                 for tc in tbl.iter(q("hp", "tc")) for a in [tc.find(q("hp", "cellAddr"))]}
        return int(tbl.find(q("hp", "sz")).get("height")), cells

    kit, a, i, lines = 짓기()
    _, b, _, _ = 짓기()
    assert _옛_resize_boxes(a, kit, lines) == 1 and resize_boxes(b, kit, lines) == 1
    (ta, ca), (tb, cb) = 높이(a, i), 높이(b, i)
    assert (ta, ca) == (tb, cb)  # 레일이 어떻게 걸쳐도 칸·표 높이가 옛 길과 같다(기준 1)
