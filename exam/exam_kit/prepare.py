"""학교 원안지 양식 hwpx를 조판 직전 상태로 만든다(D-8) — 학교 안내가 지우라는 것만 지우고, 나머지는 양식 그대로.

prepare_form : 관리박스 정리(규격표·안내문·논술형 줄·유의 높이) → 논술형 샘플 구역~꼬리 앞 제거 → 꼬리 박스 고정 → 양식 이미지 id 기록.
                양식의 샘플 문항 구역은 남긴다(조판기가 교체하고, 그 안의 〈보기〉·자료 박스가 견본이다).
finalize_form: (조판 뒤) 잔여 문단 제거 → 양식 원본 이미지·프리뷰 세척 → 사후조건.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import lxml.etree as ET
from hwpx.document import HwpxDocument

from . import q
from .kit import Kit, sha256, style_ids
from .read import is_blank as _blank, nested_raw as _ptext, table_paragraphs as _table_paragraphs, table_text as _table_text



# ---- 문단·표 읽기(공개 API) ---------------------------------------------------

def _style_ids(table) -> set[str]:
    """표 안(칸 안 표·글상자까지) 모든 문단의 스타일 id — 옛 ``_inner_style_ids``."""
    out: set[str] = set()
    for p in _table_paragraphs(table):
        out.add(str(p.style_id_ref) if p.style_id_ref is not None else "0")
        for place in p.iter_objects(kinds="table"):
            out |= {str(q_.style_id_ref) if q_.style_id_ref is not None else "0" for q_ in _table_paragraphs(place.object)}
        for place in p.iter_objects(kinds="shape"):
            out |= {str(x.paragraph.style_id_ref) if x.paragraph.style_id_ref is not None else "0"
                    for x in place.object.iter_paragraphs()}
    return out


def _remove_paragraphs(sec, paragraphs) -> None:
    for p in reversed(list(paragraphs)):
        p.remove()
    sec.mark_dirty()


def _find(paras, pred, *, what: str) -> int:
    for i, p in enumerate(paras):
        if pred(i, p):
            return i
    raise ValueError(f"양식에서 찾지 못함: {what}")


def is_sample_table(table, spec: dict, style_id: str) -> bool:
    """양식 샘플 구역의 견본 박스 표인가 — 킷 boxes 한 항목(제목·표 모양·내용 스타일)으로 본다."""
    text = _table_text(table)
    return ([table.row_count, table.column_count] == spec["shape"]
            and (spec["title"] is None or spec["title"] in text)
            and ("sample_with" not in spec or spec["sample_with"] in text)
            and ("sample_without" not in spec or spec["sample_without"] not in text)
            and style_id in _style_ids(table))


def _holds_header_footer(paragraph) -> bool:
    """문단(그 안 표 칸까지)에 머리말·꼬리말 컨트롤이 있는가."""
    if any(item.kind in ("header", "footer") for run in paragraph.runs for item in run.content):
        return True
    return any(_holds_header_footer(p) for place in paragraph.iter_objects(kinds="table")
               for p in _table_paragraphs(place.object))


def _replace_text(paragraph, old: str, new: str) -> int:
    """문단과 그 안 표 칸 문단의 글에서 old를 new로(run.replace_text). 머리말·꼬리말 story는 건드리지 않는다."""
    n = sum(run.replace_text(old, new) for run in paragraph.runs)
    for place in paragraph.iter_objects(kinds="table"):
        n += sum(run.replace_text(old, new) for p in _table_paragraphs(place.object) for run in p.runs)
    return n


def _surgery_admin_box(doc: HwpxDocument, kit: Kit) -> None:
    a = kit.admin
    p0 = doc.sections[0].paragraphs[a["paragraph"]]
    규격표 = [t for t in p0.tables if any(w in _table_text(t) for w in a["delete_tables_with"])]
    for t in 규격표:
        # 결재란·유의·규격표 세 표가 run 하나를 공유한다(실측) — run째 지우면 유의까지 함께 사라지므로 표 노드 하나만
        # 그 run에서 뗀다. (공개 table.remove()는 비게 된 run도 지운다 — 바이트가 달라져 next7/form-x에 둔다.)
        t.element.getparent().remove(t.element)
    # 문단 0의 줄 배치 캐시(linesegarray)는 규격표(글자처럼 취급, 높이 3130)를 품은 줄 높이 3410을
    # 기억한다. 한글은 이 캐시를 믿어 표를 지운 뒤에도 그만큼 비워 둔다(Task 22 렌더 실측: 1번 문항이
    # 제출본보다 약 1.5줄 아래). 캐시를 지우면 한글이 다시 잰다.
    p0.clear_layout_cache()
    유의 = next(t for t in p0.tables if a["notice_table_with"] in _table_text(t))
    # 유의의 셀 하나에 머리말·꼬리말 ctrl이 통째로 박혀 있다(정정 1 실측): 그 ctrl 안에는 머리말/꼬리말 자기
    # 레이아웃용 중첩 표가 따로 있으므로, 유의 안의 편집은 유의 자신의 행·칸과 각 칸의 문단으로만 한정한다 —
    # 문단 하나가 누름틀도 품고 있어 컨트롤 유무로는 못 거르므로, 머리말·꼬리말이 있는 문단만 건드리지 않는다.
    for w in a["remove_text"]:  # 관리박스 문단 자신에 붙은 안내 글(학교 B: 빨강 "한칸 띄기")
        _replace_text(p0, w, "")
    지울 = tuple(a["notice_delete_paras_with"])
    for row in 유의.rows:
        for cell in row.cells:
            for p in list(cell.paragraphs):
                if _holds_header_footer(p):
                    continue
                if any(w in _ptext([p]) for w in 지울):
                    p.remove()
                else:
                    for old, new in a["notice_replace"]:
                        _replace_text(p, old, new)
    if kit.notice_box_height is not None:  # 유의는 한 줄 표 — 칸 높이와 표 높이를 함께
        if 유의.row_count != 1:
            raise ValueError(f"양식이 바뀌었다: 유의 표가 {유의.row_count}줄이다 — notice_box_height는 한 줄 표에만 준다")
        유의.set_row_heights([kit.notice_box_height])
    doc.sections[0].mark_dirty()


def pin_tailbox(tail_p, kit: Kit) -> None:
    """꼬리 박스를 오른쪽 단 맨 아래 자리(용지 기준)에 — 어느 쪽에 앉을지는 렌더 뒤 layout.settle이 정한다(설계 R-5).

    박스는 마지막 문단(닻)과 함께 흐르므로 마지막 문항이 끝난 쪽에 앉는다. 가로 = 오른쪽 단 왼끝(kit 단 상수),
    세로 = kit.tailbox.vertOffset(제출본 실측). 닻 문단의 줄 캐시(양식에서 글자처럼 취급하던 높이 9542)는
    지운다 — 남기면 한글이 그 높이만큼 닻 줄을 비워 두어 쪽이 넘어간다.
    """
    m, c = kit.page["margin"], kit.columns
    horz = m["left"] + (c["count"] - 1) * (c["width"] + c["gap"])
    if horz != kit.tailbox["horzOffset"]:
        raise ValueError(f"kit.tailbox.horzOffset {kit.tailbox['horzOffset']} ≠ 오른쪽 단 왼끝 {horz}")
    tail_p.tables[0].set_position(
        treat_as_char=False,
        vertical_relative_to=kit.tailbox["vertRelTo"], horizontal_relative_to=kit.tailbox["horzRelTo"],
        vertical_alignment="TOP", horizontal_alignment="LEFT",
        vertical_offset=kit.tailbox["vertOffset"], horizontal_offset=horz,
    )
    tail_p.clear_layout_cache()


# ---- D-8: 양식을 조판 직전 상태로 -------------------------------------------

@dataclass(frozen=True)
class Prepared:
    """prepare_form이 캡처한 상태 — finalize_form의 사후조건이 비교하는 기준선.

    누름틀을 채운 뒤에는 refresh(doc)로 다시 캡처한다 — 머리말 슬롯(머리_학년·머리_학기·
    머리_차·머리_과목)이 머리말(hp:header) 안에 있어서, fill_slots가 그 슬롯을 채우면
    header_footer가 (정당하게) 바뀐다. refresh 없이 finalize_form을 부르면 그 정당한
    변화를 "머리말/꼬리말 ctrl이 양식과 다르다"로 오판해 실패한다.
    """

    removed: int
    form_bindata: tuple[tuple[str, str], ...]   # (manifest id, part name) — 조판 뒤 지울 양식 원본 이미지
    header_footer: tuple[str, ...]              # 양식의 hp:header들 / hp:footer들 XML(불변식 기준선)

    def save(self, hwpx_path: Path) -> Path:
        p = Path(str(hwpx_path) + ".prepared.json")
        p.write_text(json.dumps({"removed": self.removed, "form_bindata": [list(x) for x in self.form_bindata],
                                 "header_footer": list(self.header_footer)}, ensure_ascii=False), encoding="utf-8")
        return p

    @staticmethod
    def load(hwpx_path: Path) -> "Prepared":
        d = json.loads(Path(str(hwpx_path) + ".prepared.json").read_text(encoding="utf-8"))
        return Prepared(d["removed"], tuple(tuple(x) for x in d["form_bindata"]), tuple(d["header_footer"]))

    def refresh(self, doc: HwpxDocument) -> "Prepared":
        """누름틀을 채운 뒤: header_footer만 doc의 현재 상태로 다시 캡처한 사본을 돌려준다."""
        return Prepared(self.removed, self.form_bindata, _header_footer_xml(doc))


def prepared_for(hwpx_path: Path) -> Prepared:
    return Prepared.load(hwpx_path)


def _header_footer_xml(doc: HwpxDocument) -> tuple[str, ...]:
    sec = doc.sections[0].element
    # 있는 머리말·꼬리말 전부(예: 머리말 1·꼬리말 1, 또는 머리말 0·꼬리말 2) — 차례는 머리말들 다음 꼬리말들
    return tuple(ET.tostring(el, encoding="unicode") for t in ("header", "footer") for el in sec.iter(q("hp", t)))


def _form_bindata(doc: HwpxDocument) -> tuple[tuple[str, str], ...]:
    return tuple((it.item_id, it.href) for it in doc.media.images if it.href.startswith("BinData/"))


def _check_form(doc: HwpxDocument, kit: Kit) -> None:
    """양식이 우리가 아는 그 양식인가 — 아니면 '양식이 바뀌었다'로 실패."""
    실패 = []
    sids = style_ids(doc)
    names = set(sids)
    for name in kit.styles.values():
        if name not in names:
            실패.append(f"스타일 없음: {name}")
    ids = {f.field_id for f in doc.fields.all}
    for slot, fid in kit.slots.items():
        if fid not in ids:
            실패.append(f"누름틀 없음: {slot}")
    paras = list(doc.sections[0].paragraphs)
    tables = [t for p in paras[1:] for t in p.tables]
    for kind, spec in kit.boxes.items():
        if kind in ("보기", "자료") and not any(is_sample_table(t, spec, sids[kit.styles[spec["style"]]][0]) for t in tables):
            실패.append(f"〈{kind}〉 견본 표 없음" if kind == "보기" else f"{kind} 견본 표 없음")
    box_styles = {sids[kit.styles[kit.boxes[k]["style"]]][0] for k in ("보기", "자료")}
    if kit.box_min_height is not None:  # 견본 박스 내용 셀 높이 = kit.box_min_height(박스 최소 높이의 출처)
        for t in tables:
            shape = [t.row_count, t.column_count]
            addr = next((tuple(sp["content_cell"]) for k, sp in kit.boxes.items()  # 킷은 [열, 행]
                         if k in ("보기", "자료") and sp["shape"] == shape), None)
            cell = None if addr is None else next(
                (c for row in t.rows for c in row.cells if c.address == (addr[1], addr[0])), None)
            if cell is not None and _style_ids(t) & box_styles:
                h = cell.height
                if h != kit.box_min_height:
                    실패.append(f"견본 박스 내용 셀 높이 {h} ≠ kit box_min_height {kit.box_min_height}")
    if tail_index(doc, kit) is None:
        실패.append("꼬리 박스가 마지막 글 문단이 아님")
    if _trim_start(paras, kit) is None:
        실패.append(f"지울 구역 시작 문단 없음({kit.trim})")
    if 실패:
        raise ValueError("양식이 바뀌었다: " + "; ".join(실패))


def tail_index(doc: HwpxDocument, kit: Kit) -> int | None:
    """꼬리 박스 문단 = 킷 식별어를 품은 표가 있는 마지막 문단. 그 뒤에는 빈 문단만 있어야 한다(아니면 None)."""
    paras = list(doc.sections[0].paragraphs)
    for i in range(len(paras) - 1, 0, -1):
        if any(kit.tailbox["match_text"] in _table_text(t) for t in paras[i].tables):
            return i if all(_blank(p) for p in paras[i + 1:]) else None
    return None


def _trim_start(paras, kit: Kit) -> int | None:
    """지울 구역(논술형 샘플 ~ 꼬리 앞)의 첫 문단 — 킷 trim 규칙."""
    rule = kit.trim["rule"]
    for i, p in enumerate(paras):
        if i == 0:
            continue
        if rule == "first_page_break" and p.page_break:
            return i
        if rule == "text_prefix" and _ptext([p]).strip().startswith(kit.trim["prefix"]):
            return i
    return None


def _trim_body(doc: HwpxDocument, kit: Kit) -> int:
    """지울 구역 첫 문단(킷 trim)부터 꼬리 박스 앞까지, 그리고 꼬리 박스 뒤 빈 문단을 지운다 — 논술형 샘플·안내 박스·
    빈 문단·'마지막 장' 안내 줄이 여기 있다. 꼬리 박스가 마지막 문단이 된다."""
    sec = doc.sections[0]
    paras = list(sec.paragraphs)
    start = _trim_start(paras, kit)
    if start is None:
        raise ValueError(f"양식에서 찾지 못함: 지울 구역 시작({kit.trim})")
    tail_i = tail_index(doc, kit)
    remove = paras[start:tail_i] + paras[tail_i + 1:]
    _remove_paragraphs(sec, remove)
    return len(remove)


_그리기 = ("line", "rect", "ellipse", "arc", "polygon", "curve", "connectLine")


def _remove_marks(doc: HwpxDocument, kit: Kit) -> None:
    """킷 remove: 메모(MEMO 필드 — 앵커 글은 남기고 필드 틀과 메모 글만)·그리기 개체(안내 화살표·동그라미)를 머리말·꼬리말
    안까지 모두 지운다. python-hwpx notes.memos는 HWP 변환본의 MEMO 필드를 보지 못해 XML로 지운다."""
    sec = doc.sections[0].element
    if kit.remove["memos"]:
        begins = [f for f in sec.iter(q("hp", "fieldBegin")) if f.get("type") == "MEMO"]
        ids = {f.get("id") for f in begins}
        ends = [f for f in sec.iter(q("hp", "fieldEnd")) if f.get("beginIDRef") in ids]
        for el in begins + ends:
            ctrl = el.getparent()
            ctrl.remove(el)
            if len(ctrl) == 0:
                ctrl.getparent().remove(ctrl)
    if kit.remove["drawings"]:
        for el in [e for e in sec.iter() if e.tag in {q("hp", t) for t in _그리기}]:
            el.getparent().remove(el)
    doc.sections[0].mark_dirty()


def prepare_form(doc: HwpxDocument, kit: Kit) -> Prepared:
    _remove_marks(doc, kit)  # 머리말·꼬리말 안 안내 개체까지 — 불변식 기준선(hf)을 잡기 전에
    _check_form(doc, kit)
    hf = _header_footer_xml(doc)
    _surgery_admin_box(doc, kit)
    if _header_footer_xml(doc) != hf:
        raise ValueError("관리박스 정리가 머리말/꼬리말을 건드렸다")
    n = _trim_body(doc, kit)
    pin_tailbox(doc.sections[0].paragraphs[-1], kit)
    return Prepared(removed=n, form_bindata=_form_bindata(doc), header_footer=hf)


def prepare_document(form: Path, kit: Kit) -> tuple[HwpxDocument, Prepared]:
    got = sha256(form)
    if got != kit.form_sha256:
        raise ValueError(f"양식 sha256 불일치 — kit.json을 다시 재라: {got}")
    doc = HwpxDocument.open(str(form))
    return doc, prepare_form(doc, kit)


def _drop_leftovers(doc: HwpxDocument, kit: Kit) -> int:
    """마지막 문항과 꼬리 박스 사이의 빈 문단·"마지막 장" 안내 문단을 뒤에서부터 걷어낸다.

    kit.forbidden_text 전체로 거르면 진짜 마지막 문항의 정당한 내용(예: 답지 안에 우연히 "글자체"
    같은 낱말이 있는 경우)까지 조용히 삭제될 수 있다. 그래서 여기서는 빈 문단과 정확히
    그 "마지막 장" 안내 문단만 지운다 — 남는 금지 문구는 _postcheck가 시끄럽게 실패시킨다
    (조용한 삭제보다 시끄러운 실패가 낫다).
    """
    sec = doc.sections[0]
    paras = list(sec.paragraphs)
    i = len(paras) - 2
    victims = []
    while i > 0:
        text = _ptext([paras[i]]).strip()
        if _blank(paras[i]) or text.startswith(kit.leftover_prefix):
            victims.append(paras[i]); i -= 1
        else:
            break
    _remove_paragraphs(sec, victims)
    return len(victims)


def _scrub_form_bindata(doc: HwpxDocument, prepared: Prepared) -> None:
    # (공개 doc.media.remove_image는 header binDataList의 binItem도 지운다 — 바이트가 달라져 next7/form-x에 둔다.)
    sec = doc.sections[0].element
    refs = {e.get("binaryItemIDRef") for e in sec.iter() if e.get("binaryItemIDRef")}
    for item_id, href in prepared.form_bindata:
        if item_id in refs:
            raise ValueError(f"양식 원본 이미지가 아직 참조된다: {item_id}")
    pkg = doc.package
    for item_id, href in prepared.form_bindata:
        pkg.remove_manifest_item(item_id)
        if pkg.has_part(href):
            pkg.delete(href)
    doc.parts.clear_preview()  # PrvText.txt는 빈 글, PrvImage.png는 1×1 흰 그림(옛 set_part와 같은 바이트)


def _postcheck(doc: HwpxDocument, kit: Kit, prepared: Prepared) -> None:
    실패 = []
    sec = doc.sections[0]
    stories = [*doc.page.headers(section=sec), *doc.page.footers(section=sec)]
    text = _ptext(sec.paragraphs) + "".join(_ptext(s.paragraphs) for s in stories)
    for w in kit.forbidden_text:
        if w in text:
            실패.append(f"금지 문구 잔존: {w!r}")
    if _header_footer_xml(doc) != prepared.header_footer:
        실패.append("머리말/꼬리말 ctrl이 양식과 다르다")
    n = len(doc.fields.all)
    if n != len(kit.slot_ids()):
        실패.append(f"누름틀 {n}개 (기대 {len(kit.slot_ids())})")
    names = set(style_ids(doc))
    for name in kit.styles.values():
        if name not in names:
            실패.append(f"스타일 없음: {name}")
    ps = list(doc.sections[0].paragraphs)
    if not any(kit.tailbox["match_text"] in _table_text(t) for t in ps[-1].tables):
        실패.append("꼬리 박스가 마지막 문단이 아님")
    if kit.remove["memos"] and doc.sections[0].memos:
        실패.append("메모 잔존")
    pos = ps[-1].tables[0].position
    if pos.vertical_relative_to != kit.tailbox["vertRelTo"] or pos.vertical_offset != kit.tailbox["vertOffset"]:
        실패.append("꼬리 박스 고정이 풀렸다")
    for item_id, href in prepared.form_bindata:
        if doc.package.has_part(href):
            실패.append(f"양식 이미지 잔존: {href}")
    if not doc.validate().ok:
        실패.append("validate().ok == False")
    if 실패:
        raise ValueError("마무리 사후조건 실패: " + "; ".join(실패))


def finalize_form(doc: HwpxDocument, kit: Kit, prepared: Prepared) -> None:
    _drop_leftovers(doc, kit)
    _scrub_form_bindata(doc, prepared)
    _postcheck(doc, kit, prepared)
