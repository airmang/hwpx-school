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
from ._png import png
from .kit import Kit, sha256, style_ids

_OPF = {"opf": "http://www.idpf.org/2007/opf/"}


# ---- Task 5·6에서 옮겨 옴(변종 인자 없이 정리) ------------------------------

def _text(el) -> str:
    return "".join(el.itertext())


def _top_tables(p_el) -> list:
    return [t for run in p_el.findall(q("hp", "run")) for t in run.findall(q("hp", "tbl"))]


def _set_para_text(p_el, text: str) -> None:
    """첫 run의 charPr를 지키고 본문을 text 하나로 바꾼다(탭·형광펜 등 자식 제거)."""
    runs = p_el.findall(q("hp", "run"))
    if not runs:
        run = ET.SubElement(p_el, q("hp", "run"))
    else:
        run = runs[0]
        for extra in runs[1:]:
            p_el.remove(extra)
    for child in list(run):
        if child.tag == q("hp", "t"):
            run.remove(child)
    t = ET.SubElement(run, q("hp", "t"))
    t.text = text


def _replace_in_runs(p_el, old: str, new: str) -> int:
    n = 0
    for t in p_el.iter(q("hp", "t")):
        if t.text and old in t.text:
            t.text = t.text.replace(old, new)
            n += 1
        if t.tail and old in t.tail:
            t.tail = t.tail.replace(old, new)
            n += 1
    return n


def _remove_paragraphs(sec, wrappers) -> None:
    for w in reversed(list(wrappers)):
        sec.remove_paragraph(w)
    sec.mark_dirty()


def _find(paras, pred, *, what: str) -> int:
    for i, p in enumerate(paras):
        if pred(i, p):
            return i
    raise ValueError(f"양식에서 찾지 못함: {what}")


def _inner_style_ids(tbl) -> set[str]:
    return {p.get("styleIDRef") or "0" for p in tbl.iter(q("hp", "p"))}


def is_sample_box(tbl, spec: dict, style_id: str) -> bool:
    """양식 샘플 구역의 견본 박스 표인가 — 킷 boxes 한 항목(제목·표 모양·내용 스타일)으로 본다."""
    text = _text(tbl)
    return ([int(tbl.get("rowCnt")), int(tbl.get("colCnt"))] == spec["shape"]
            and (spec["title"] is None or spec["title"] in text)
            and ("sample_with" not in spec or spec["sample_with"] in text)
            and ("sample_without" not in spec or spec["sample_without"] not in text)
            and style_id in _inner_style_ids(tbl))


def _surgery_admin_box(doc: HwpxDocument, kit: Kit) -> None:
    a = kit.admin
    p0 = doc.sections[0].paragraphs[a["paragraph"]].element
    tables = _top_tables(p0)
    규격표 = [t for t in tables if any(w in _text(t) for w in a["delete_tables_with"])]
    for t in 규격표:
        # 결재란·유의·규격표 세 표가 run 하나를 공유한다(실측) — run째 지우면
        # 유의까지 함께 사라지므로 표 노드 하나만 그 run에서 뗀다.
        t.getparent().remove(t)
    # 문단 0의 줄 배치 캐시(linesegarray)는 규격표(글자처럼 취급, 높이 3130)를 품은 줄 높이 3410을
    # 기억한다. 한글은 이 캐시를 믿어 표를 지운 뒤에도 그만큼 비워 둔다(Task 22 렌더 실측: 1번 문항이
    # 제출본보다 약 1.5줄 아래). 캐시를 지우면 한글이 다시 잰다.
    for ls in p0.findall(q("hp", "linesegarray")):
        p0.remove(ls)
    유의 = next(t for t in _top_tables(p0) if a["notice_table_with"] in _text(t))
    # 유의의 셀 하나(subList)에 머리말·꼬리말 ctrl이 통째로 박혀 있다(정정 1 실측):
    # header/footer < ctrl < run < p < subList < tc < tr < tbl[유의]. 그 ctrl 안에는
    # 머리말/꼬리말 자기 레이아웃용 중첩 표가 따로 있어 .iter()로 훑으면 그 표의
    # cellSz까지 같이 잡혀 버린다. 그래서 유의 안의 편집은 전부 유의 자신의 직속
    # tr→tc, 그리고 각 tc의 subList 직속 p/cellSz로만 한정한다(.iter 금지) — 문단
    # 하나가 누름틀(fieldBegin/fieldEnd)도 품고 있어 hp:ctrl 유무로는 못 거르므로,
    # 머리말·꼬리말 자체(hp:header/hp:footer)가 있는 문단만 건드리지 않는다.
    for w in a["remove_text"]:  # 관리박스 문단 자신에 붙은 안내 글(학교 B: 빨강 "한칸 띄기")
        _replace_in_runs(p0, w, "")
    지울 = tuple(a["notice_delete_paras_with"])
    h = None if kit.notice_box_height is None else str(kit.notice_box_height)
    for tr in 유의.findall(q("hp", "tr")):
        for tc in tr.findall(q("hp", "tc")):
            sub = tc.find(q("hp", "subList"))
            for p in list(sub.findall(q("hp", "p"))):
                if p.find(f".//{q('hp', 'header')}") is not None or p.find(f".//{q('hp', 'footer')}") is not None:
                    continue
                if any(w in _text(p) for w in 지울):
                    sub.remove(p)
                else:
                    for old, new in a["notice_replace"]:
                        _replace_in_runs(p, old, new)
            cellsz = tc.find(q("hp", "cellSz"))
            if cellsz is not None and h is not None:
                cellsz.set("height", h)
    if h is not None:
        유의.find(q("hp", "sz")).set("height", h)
    doc.sections[0].mark_dirty()


def pin_tailbox(tail_p_el, kit: Kit) -> None:
    """꼬리 박스를 오른쪽 단 맨 아래 자리(용지 기준)에 — 어느 쪽에 앉을지는 렌더 뒤 layout.settle이 정한다(설계 R-5).

    박스는 마지막 문단(닻)과 함께 흐르므로 마지막 문항이 끝난 쪽에 앉는다. 가로 = 오른쪽 단 왼끝(kit 단 상수),
    세로 = kit.tailbox.vertOffset(제출본 실측). 닻 문단의 줄 캐시(양식에서 글자처럼 취급하던 높이 9542)는
    지운다 — 남기면 한글이 그 높이만큼 닻 줄을 비워 두어 쪽이 넘어간다.
    """
    tbl = _top_tables(tail_p_el)[0]
    pos = tbl.find(q("hp", "pos"))
    pos.set("treatAsChar", "0")
    pos.set("vertRelTo", kit.tailbox["vertRelTo"])
    pos.set("horzRelTo", kit.tailbox["horzRelTo"])
    pos.set("vertAlign", "TOP")
    pos.set("horzAlign", "LEFT")
    pos.set("vertOffset", str(kit.tailbox["vertOffset"]))
    m, c = kit.page["margin"], kit.columns
    horz = m["left"] + (c["count"] - 1) * (c["width"] + c["gap"])
    if horz != kit.tailbox["horzOffset"]:
        raise ValueError(f"kit.tailbox.horzOffset {kit.tailbox['horzOffset']} ≠ 오른쪽 단 왼끝 {horz}")
    pos.set("horzOffset", str(horz))
    for ls in tail_p_el.findall(q("hp", "linesegarray")):
        tail_p_el.remove(ls)


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


def _form_bindata(pkg) -> tuple[tuple[str, str], ...]:
    manifest = pkg.manifest_tree().find("opf:manifest", _OPF)
    if manifest is None:
        return ()
    return tuple((it.get("id"), it.get("href")) for it in manifest.findall("opf:item", _OPF)
                 if (it.get("href") or "").startswith("BinData/"))


def _check_form(doc: HwpxDocument, kit: Kit) -> None:
    """양식이 우리가 아는 그 양식인가 — 아니면 '양식이 바뀌었다'로 실패."""
    실패 = []
    sids = style_ids(doc)
    names = set(sids)
    for name in kit.styles.values():
        if name not in names:
            실패.append(f"스타일 없음: {name}")
    ids = {f.field_id for f in doc.list_form_fields()}
    for slot, fid in kit.slots.items():
        if fid not in ids:
            실패.append(f"누름틀 없음: {slot}")
    paras = list(doc.sections[0].paragraphs)
    tables = [t for p in paras[1:] for t in _top_tables(p.element)]
    for kind, spec in kit.boxes.items():
        if kind in ("보기", "자료") and not any(is_sample_box(t, spec, sids[kit.styles[spec["style"]]][0]) for t in tables):
            실패.append(f"〈{kind}〉 견본 표 없음" if kind == "보기" else f"{kind} 견본 표 없음")
    box_styles = {sids[kit.styles[kit.boxes[k]["style"]]][0] for k in ("보기", "자료")}
    if kit.box_min_height is not None:  # 견본 박스 내용 셀 높이 = kit.box_min_height(박스 최소 높이의 출처)
        for t in tables:
            shape = [int(t.get("rowCnt")), int(t.get("colCnt"))]
            addr = next((tuple(map(str, sp["content_cell"])) for k, sp in kit.boxes.items()
                         if k in ("보기", "자료") and sp["shape"] == shape), None)
            cell = None if addr is None else next(
                (tc for tc in t.iter(q("hp", "tc")) for a in [tc.find(q("hp", "cellAddr"))]
                 if (a.get("colAddr"), a.get("rowAddr")) == addr), None)
            if cell is not None and _inner_style_ids(t) & box_styles:
                h = int(cell.find(q("hp", "cellSz")).get("height"))
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
        if any(kit.tailbox["match_text"] in _text(t) for t in _top_tables(paras[i].element)):
            return i if all(_is_blank(p.element) for p in paras[i + 1:]) else None
    return None


def _trim_start(paras, kit: Kit) -> int | None:
    """지울 구역(논술형 샘플 ~ 꼬리 앞)의 첫 문단 — 킷 trim 규칙."""
    rule = kit.trim["rule"]
    for i, p in enumerate(paras):
        if i == 0:
            continue
        if rule == "first_page_break" and p.element.get("pageBreak") == "1":
            return i
        if rule == "text_prefix" and _text(p.element).strip().startswith(kit.trim["prefix"]):
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
    pin_tailbox(doc.sections[0].paragraphs[-1].element, kit)
    return Prepared(removed=n, form_bindata=_form_bindata(doc.package), header_footer=hf)


def prepare_document(form: Path, kit: Kit) -> tuple[HwpxDocument, Prepared]:
    got = sha256(form)
    if got != kit.form_sha256:
        raise ValueError(f"양식 sha256 불일치 — kit.json을 다시 재라: {got}")
    doc = HwpxDocument.open(str(form))
    return doc, prepare_form(doc, kit)


def _is_blank(p_el) -> bool:
    return "".join(p_el.itertext()).strip() == "" and p_el.find(f".//{q('hp', 'tbl')}") is None and p_el.find(f".//{q('hp', 'pic')}") is None


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
        el = paras[i].element
        text = "".join(el.itertext()).strip()
        if _is_blank(el) or text.startswith(kit.leftover_prefix):
            victims.append(paras[i]); i -= 1
        else:
            break
    _remove_paragraphs(sec, victims)
    return len(victims)


def _scrub_form_bindata(doc: HwpxDocument, prepared: Prepared) -> None:
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
    if pkg.has_part("Preview/PrvText.txt"):
        pkg.set_part("Preview/PrvText.txt", b"")
    if pkg.has_part("Preview/PrvImage.png"):
        pkg.set_part("Preview/PrvImage.png", png(1, 1))


def _postcheck(doc: HwpxDocument, kit: Kit, prepared: Prepared) -> None:
    실패 = []
    text = "".join(doc.sections[0].element.itertext())
    for w in kit.forbidden_text:
        if w in text:
            실패.append(f"금지 문구 잔존: {w!r}")
    if _header_footer_xml(doc) != prepared.header_footer:
        실패.append("머리말/꼬리말 ctrl이 양식과 다르다")
    n = len(doc.list_form_fields())
    if n != len(kit.slot_ids()):
        실패.append(f"누름틀 {n}개 (기대 {len(kit.slot_ids())})")
    names = set(style_ids(doc))
    for name in kit.styles.values():
        if name not in names:
            실패.append(f"스타일 없음: {name}")
    ps = list(doc.sections[0].paragraphs)
    if not any(kit.tailbox["match_text"] in _text(t) for t in _top_tables(ps[-1].element)):
        실패.append("꼬리 박스가 마지막 문단이 아님")
    if kit.remove["memos"] and any(f.get("type") == "MEMO" for f in doc.sections[0].element.iter(q("hp", "fieldBegin"))):
        실패.append("메모 잔존")
    pos = _top_tables(ps[-1].element)[0].find(q("hp", "pos"))
    if pos.get("vertRelTo") != kit.tailbox["vertRelTo"] or pos.get("vertOffset") != str(kit.tailbox["vertOffset"]):
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
