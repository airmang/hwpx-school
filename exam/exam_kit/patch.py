"""작은 수정 — 이미 조판한 원안지에서 고친 글만 갈아 끼우고, 나머지 배치(쪽·단 나눔, 답지 배치형, 간격, 자간)는 그대로 둔다.

    uv run python -W ignore -m exam_kit.patch <고친 원고.md> --prev <기존 산출 폴더> --kit <학교 킷> --form <서식.hwpx> \\
        --out <새 폴더> [--draft]

막바지(검토·결재 뒤) 오탈자·숫자·표현 같은 글 수정용이다. 원고가 정본이다 — 원고를 고치고 이 도구를 돌린다(산출물 손편집 금지).

1. 견준다: 기존 답 표시본을 역변환한 원고 ↔ 고친 원고. 머리 값·문항 수·세트·블록 구성(종류·줄 수)·발문 문단 수·답지 수·
   그림이 같아야 한다. 배점은 문항별로 바뀌어도 되지만 합은 같아야 한다. 다르면 멈춘다 — 다시 조판(build)할 일이다.
2. 고친 원고를 기존 문서의 최종 답지 배치형 그대로 렌더 없이 조판한다. 렌더 루프는 문단을 더하거나 빼지 않으므로
   문항마다 문단(박스·표 칸 안 문단 포함)이 차례대로 짝지어진다.
3. 글이 달라진 문단만 기존 문항지에서 run을 갈아 끼운다(글자 모양 id는 내용으로 맞춘다, 줄 캐시는 지운다). 표·그림이 든
   문단의 글이 바뀌었으면 멈춘다. 답 표시본은 고친 문항지 + 새 정답 형광펜으로 다시 만든다.
4. 확인: 기존·고친 문항지를 렌더해 문항 머리 자리(쪽·단·y)가 하나라도 움직였으면 '다시 조판 필요'(끝 코드 3).
   그다음 build와 같은 [기계] 검사(두 판). 끝 코드 0 = 기계 잔존 0 · 1 = 원고 규칙 오류 · 2 = 기계 잔존 · 3 = 다시 조판.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import lxml.etree as ET
from hwpx.document import HwpxDocument

from . import q
from .build import final_layouts, same_layout, same_package
from .compose import add_answer_marks, compose
from .fit import Spacer, _spacing, para_text
from .geometry import hancom_windows_pdf, measure
from .kit import Kit, load_kit
from .lint import errors as lint_errors
from .lint import lint
from .prepare import finalize_form, prepare_document
from .render import render
from .reverse import kit_profile, reverse
from .scan import Scan, scan_markdown
from .slots import fill_slots
from .verify import _tail_index, errors, question_heads, verify_document, verify_render

MARKPEN_DRIFT = 0.4  # build와 같다 — Windows 한/글 형광펜 줄 밀림


class NeedsRebuild(ValueError):
    """작은 수정으로는 안 된다 — 구조나 배치가 바뀐다. 다시 조판(build)한다."""


# ---- 1. 견주기 -------------------------------------------------------------------------------

def _shape(s: Scan) -> dict:
    """작은 수정에서 같아야 하는 구조 — 글은 빼고 모양만."""
    return {
        "문항 수": len(s.questions),
        "세트": [(st.rng, len(st.passage), [(b.kind, len(b.lines)) for b in st.blocks]) for st in s.sets],
        **{f"{x.number}번": (x.set_rng, len(x.stem), [(b.kind, len(b.lines)) for b in x.blocks if b.kind != "답항표"],
                             len(x.choices)) for x in s.questions},
        "보존 블록": len(s.preserved),
    }


def check_small(old: Scan, new: Scan, layouts: dict[str, str]) -> list[str]:
    """작은 수정으로 할 수 없는 까닭 — 빈 목록이면 된다."""
    out = []
    def 값(fm, k):  # 시행·대상·인쇄는 표기가 달라도(4.20. ↔ 4월 20일) 뜻이 같으면 같다
        return {"시행": fm.시행_분해, "대상": fm.대상_분해, "인쇄": fm.인쇄_분해}.get(k, lambda: getattr(fm, k, None))()

    keys = ("학년도", "학년", "학기", "차", "과목", "과목코드", "시행", "대상", "인쇄", "출제교사", "만점")
    changed = [k for k in keys if 값(old.front, k) != 값(new.front, k)]
    if changed:
        out.append(f"머리 값이 바뀌었다({', '.join(changed)})")
    a, b = _shape(old), _shape(new)
    out += [f"{k} 구성이 바뀌었다" for k in dict.fromkeys([*a, *b]) if a.get(k) != b.get(k)]
    if abs(sum(x.points or 0 for x in old.questions) - sum(x.points or 0 for x in new.questions)) > 1e-9:
        out.append("배점 합이 바뀌었다")
    for x in new.questions:
        if x.override and x.override != layouts.get(x.number):
            out.append(f"{x.number}번 답지 배치형 지시가 기존({layouts.get(x.number)})과 다르다({x.override})")
        if x.brk:
            out.append(f"{x.number}번 나눔 지시({{단나눔}}·{{쪽나눔}})는 배치를 바꾼다")
    return out


# ---- 2·3. 갈아 끼우기 -------------------------------------------------------------------------

def _regions(doc: HwpxDocument, kit: Kit) -> list[list]:
    """문항마다 최상위 문단들 — 머리부터 다음 머리 앞까지(마지막은 꼬리 박스 앞까지)."""
    ps = [p.element for p in doc.sections[0].paragraphs]
    heads = question_heads(doc)
    ends = heads[1:] + [_tail_index(doc, kit.tailbox["match_text"])]
    return [ps[a:b] for a, b in zip(heads, ends)]


def _units(region: list) -> list:
    """문항 안의 글 단위 — 최상위 문단과 그 안(박스·표 칸)의 문단, 문서 차례대로."""
    return [p for top in region for p in top.iter(q("hp", "p"))]


def _pictures(region: list) -> list[str]:
    return [pic.find(f".//{q('hc', 'img')}").get("binaryItemIDRef") for top in region for pic in top.iter(q("hp", "pic"))]


def _bin_hashes(doc: HwpxDocument) -> dict[str, str]:
    """BinData id → 내용 sha1 — 그림이 바뀌었는지 견준다."""
    out = {}
    for item in doc.package.manifest_tree().iter("{http://www.idpf.org/2007/opf/}item"):
        href = item.get("href") or ""
        if href.startswith("BinData/"):
            out[item.get("id")] = hashlib.sha1(doc.package.get_part(href)).hexdigest()
    return out


def _c14n_key(el) -> str:
    c = deepcopy(el)
    c.attrib.pop("id", None)
    return hashlib.sha1(ET.tostring(c, method="c14n")).hexdigest()


class _CharMap:
    """고친 문서의 charPr id → 기존 문서의 같은 내용 charPr id(없으면 기존 머리에 새 id로 더한다)."""

    def __init__(self, old: HwpxDocument, new: HwpxDocument):
        self.old_head = old.oxml.headers[0]
        self.box = next(self.old_head.element.iter(q("hh", "charProperties")))
        self.by_key = {_c14n_key(c): c.get("id") for c in self.box.findall(q("hh", "charPr"))}
        self.new = {c.get("id"): c for c in new.oxml.headers[0].element.iter(q("hh", "charPr"))}
        self.added = 0

    def __call__(self, cid: str) -> str:
        src = self.new[cid]
        key = _c14n_key(src)
        if key not in self.by_key:
            copy = deepcopy(src)
            copy.set("id", str(max(int(c.get("id")) for c in self.box.findall(q("hh", "charPr"))) + 1))
            self.box.append(copy)
            self.box.set("itemCnt", str(len(self.box.findall(q("hh", "charPr")))))
            self.by_key[key] = copy.get("id")
            self.added += 1
            self.old_head.mark_dirty()
        return self.by_key[key]


def apply_patch(old: HwpxDocument, new: HwpxDocument, kit: Kit) -> list[str]:
    """new(고친 원고를 기존 배치형으로 조판한 문서)의 글을 old(기존 문항지)에 옮긴다 — 글이 달라진 문단만. 바꾼 자리 목록.
    문단이 짝지어지지 않거나, 표·그림이 든 문단의 글이 바뀌었거나, 그림이 바뀌었으면 NeedsRebuild."""
    ro, rn = _regions(old, kit), _regions(new, kit)
    if len(ro) != len(rn):
        raise NeedsRebuild(f"문항 수 {len(ro)} ≠ {len(rn)}")
    ho, hn = _bin_hashes(old), _bin_hashes(new)
    cmap = _CharMap(old, new)
    spacer = Spacer(old)  # 기존 문단의 자간 맞춤(렌더 루프가 줄을 당긴 값)을 새 글에도 그대로 — 줄 수를 지키려고
    box = next(old.oxml.headers[0].element.iter(q("hh", "charProperties")))

    def 자간(p) -> int:
        vals = [_spacing(box.find(f"{q('hh', 'charPr')}[@id='{r.get('charPrIDRef')}']")) for r in p.findall(q("hp", "run"))]
        return max(vals, key=abs, default=0)

    changed: list[str] = []
    for k, (a, b) in enumerate(zip(ro, rn), 1):
        if [ho.get(x) for x in _pictures(a)] != [hn.get(x) for x in _pictures(b)]:
            raise NeedsRebuild(f"{k}번 그림이 바뀌었다")
        ua, ub = _units(a), _units(b)
        if len(ua) != len(ub):
            raise NeedsRebuild(f"{k}번 문단 수 {len(ua)} ≠ {len(ub)}")
        for j, (x, y) in enumerate(zip(ua, ub)):
            if re.sub(r"\s", "", para_text(x)) == re.sub(r"\s", "", para_text(y)):
                continue
            if any(r.find(q("hp", t)) is not None for r in x.findall(q("hp", "run")) for t in ("tbl", "pic")):
                raise NeedsRebuild(f"{k}번 표·그림이 든 문단의 글이 바뀌었다")
            s = 자간(x)
            for r in x.findall(q("hp", "run")):
                x.remove(r)
            for seg in x.findall(q("hp", "linesegarray")):  # 줄 캐시 — 한/글이 다시 잰다
                x.remove(seg)
            anchor = next((c for c in x if c.tag != q("hp", "run")), None)
            for r in y.findall(q("hp", "run")):
                r2 = deepcopy(r)
                for el in r2.iter():
                    if el.get("charPrIDRef") is not None:
                        el.set("charPrIDRef", cmap(el.get("charPrIDRef")))
                if s:
                    r2.set("charPrIDRef", spacer.charpr(r2.get("charPrIDRef"), s))
                if anchor is None:
                    x.append(r2)
                else:
                    anchor.addprevious(r2)
            changed.append(f"{k}번 문단 {j + 1}" + (f"(자간 {s}% 유지)" if s else ""))
    old.sections[0].mark_dirty()
    return changed


# ---- 4. 파이프라인 -----------------------------------------------------------------------------

@dataclass
class PatchResult:
    문항지: Path | None = None
    답표시본: Path | None = None
    changed: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)   # 바뀐 정답(답 표시본 형광펜 자리)
    rebuild: list[str] = field(default_factory=list)   # 다시 조판해야 하는 까닭(있으면 산출물 없음)
    lint: list = field(default_factory=list)
    findings: dict[str, list] = field(default_factory=dict)

    def residue(self, edition: str) -> int:
        return len(errors(self.findings.get(edition, [])))


def _prev(prev: Path, stem: str | None) -> tuple[Path, Path]:
    plains = sorted(Path(prev).glob("*_문항지.hwpx"))
    if stem:
        plains = [p for p in plains if p.name == f"{stem}_문항지.hwpx"]
    if len(plains) != 1:
        raise ValueError(f"기존 산출 폴더에서 문항지를 하나로 고를 수 없다: {[p.name for p in plains]}")
    key = plains[0].with_name(plains[0].name.replace("_문항지.hwpx", "_답표시본.hwpx"))
    if not key.is_file():
        raise ValueError(f"기존 답 표시본이 없다: {key.name}")
    return plains[0], key


def patch(md_path: Path, prev: Path, kit: Kit | Path, *, form: Path, out_dir: Path, draft: bool = False,
          render_fn=render, stem: str | None = None, lint_block: bool = True) -> PatchResult:
    md_path, out_dir = Path(md_path).resolve(), Path(out_dir).resolve()
    kit = kit if isinstance(kit, Kit) else load_kit(Path(kit))
    r = PatchResult()
    md = md_path.read_text(encoding="utf-8")
    new_scan = scan_markdown(md, kit.front_matter)
    draft = draft or new_scan.front.is_draft
    r.lint = lint(md, md_dir=md_path.parent, rules=kit.rules, draft=draft)
    if lint_errors(r.lint) and lint_block:
        return r
    old_plain_path, old_key_path = _prev(prev, stem)
    work = out_dir / "_작업"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    old_md = reverse(old_key_path, kit_profile(kit), image_dir=work / "기존", front=None)
    old = HwpxDocument.open(str(old_plain_path))
    layouts = final_layouts(old, kit)
    old_scan = scan_markdown(old_md, kit.front_matter)
    r.rebuild = check_small(old_scan, new_scan, layouts)
    if r.rebuild:
        return r
    def 정답(s: Scan) -> dict[str, str]:
        return {x.number: next((c.mark for c in x.choices if c.correct), "없음") for x in s.questions}

    oa, na = 정답(old_scan), 정답(new_scan)
    r.answers = [f"{k}번 {oa[k]}→{na[k]}" for k in na if oa.get(k) != na[k]]

    # 고친 원고를 기존 배치형으로 조판(렌더 없이)
    pinned = dataclasses.replace(new_scan, questions=tuple(
        dataclasses.replace(x, override=layouts[x.number] if layouts.get(x.number) not in (None, "답항표", "?") else x.override)
        for x in new_scan.questions))
    doc, prepared = prepare_document(Path(form), kit)
    fill_slots(doc, kit, new_scan.front, question_count=len(new_scan.questions),
               total_points=sum(x.points or 0.0 for x in new_scan.questions))
    prepared = prepared.refresh(doc)
    res = compose(doc, pinned, kit, answer_key=False, image_root=md_path.parent)
    finalize_form(doc, kit, prepared)
    try:
        r.changed = apply_patch(old, doc, kit)
    except NeedsRebuild as e:
        r.rebuild = [str(e)]
        return r

    out_dir.mkdir(parents=True, exist_ok=True)
    plain_path, key_path = work / old_plain_path.name, work / old_key_path.name
    old.save_to_path(str(plain_path))
    key = HwpxDocument.open(str(plain_path))
    add_answer_marks(key, kit, res.answers, draft=draft)
    key.save_to_path(str(key_path))

    # 확인 — 배치가 그대로인가, 그다음 기계 검사
    before = render_fn(old_plain_path, work / "기존_렌더")
    after = render_fn(plain_path, work / "고친_렌더")
    lay_before, lay_after = measure(before.pdf, kit), measure(after.pdf, kit)
    moved = same_layout(lay_before, lay_after)
    if moved:
        r.rebuild = [f"배치가 움직였다: {d}" for d in moved]
        return r
    key_rr = render_fn(key_path, work / "답표시본_렌더")
    plain, keyd = HwpxDocument.open(str(plain_path)), HwpxDocument.open(str(key_path))
    r.findings["문항지"] = (verify_document(plain, kit, expect_answers=None, answer_key=False, draft=draft)
                          + verify_render(after, plain, kit, expected_pages=before.page_count))
    fs = (verify_document(keyd, kit, expect_answers=res.answers, answer_key=True, draft=draft)
          + verify_render(key_rr, keyd, kit, expected_pages=after.page_count))
    from .verify import _f

    fs += [_f("M8", f"두 판이 형광펜 말고도 다르다: {d}") for d in same_package(plain_path, key_path)]
    drift = MARKPEN_DRIFT if hancom_windows_pdf(key_rr.pdf) else 0.0
    fs += [_f("M8", f"두 판 배치가 다르다: {d}") for d in same_layout(lay_after, measure(key_rr.pdf, kit), drift=drift)]
    r.findings["답표시본"] = fs
    r.문항지, r.답표시본 = out_dir / plain_path.name, out_dir / key_path.name
    shutil.copyfile(plain_path, r.문항지)
    shutil.copyfile(key_path, r.답표시본)
    return r


def write_report(r: PatchResult, out_dir: Path, md_path: Path, *, lint_block: bool = True) -> Path:
    p = Path(out_dir) / "보고.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    L = [f"# 작은 수정 보고 — {Path(md_path).name}", "",
         "> 기계 검사 결과는 '기계 잔존 N'으로만 적는다. 판정은 사용자 검수 몫이다.", ""]
    errs = lint_errors(r.lint)
    if errs and lint_block:
        L += ["## 원고 규칙 오류 — 고치지 않았다", *[f"- {v.code} L{v.line_no} {v.msg}" for v in errs], ""]
    elif r.rebuild:
        L += ["## 다시 조판 필요 — 작은 수정으로는 안 된다(산출물을 쓰지 않았다)", *[f"- {x}" for x in r.rebuild],
              "", "원고 그대로 `exam_kit.build`로 다시 조판한다.", ""]
    else:
        L += ["## 바꾼 문단", *([f"- {x}" for x in r.changed] or ["- 없음(글이 그대로다)"]), "",
              "## 바뀐 정답(답 표시본 형광펜)", *([f"- {x}" for x in r.answers] or ["- 없음"]), "",
              "## 기계 검사(두 판)"]
        for ed in ("문항지", "답표시본"):
            fs = r.findings.get(ed, [])
            L.append(f"- {ed}: 기계 잔존 {r.residue(ed)}")
            L += [f"  - {f.code} [{f.level}] {f.msg}" for f in fs]
        L += ["", "## 파일", f"- 문항지: {r.문항지}", f"- 답 표시본: {r.답표시본}", ""]
    if errs and not lint_block:
        L.insert(4, f"**[규칙 오류 무시] 규칙 오류 {len(errs)}건을 --lint-warn으로 넘기고 고쳤다**\n")
    warns = [v for v in r.lint if v.level == "W"]
    if warns:
        L += ["## 원고 규칙 경고", *[f"- {v.code} L{v.line_no} {v.msg}" for v in warns], ""]
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="작은 수정 — 고친 글만 갈아 끼우고 배치는 그대로. "
                                             "끝 코드 0 잔존 0 · 1 원고 규칙 오류 · 2 기계 잔존 · 3 다시 조판 필요")
    ap.add_argument("md", help="고친 원고 md")
    ap.add_argument("--prev", required=True, help="기존 산출 폴더(…_문항지.hwpx·…_답표시본.hwpx)")
    ap.add_argument("--kit", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--out", required=True, help="새 산출 폴더(git 미추적 자리)")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--lint-warn", action="store_true", help="원고 규칙 오류가 있어도 고친다(build의 --lint-warn과 같다)")
    ap.add_argument("--stem", help="기존 폴더에 문항지가 여럿이면 그 이름 앞부분")
    a = ap.parse_args(argv)
    r = patch(Path(a.md), Path(a.prev), Path(a.kit), form=Path(a.form), out_dir=Path(a.out), draft=a.draft, stem=a.stem,
              lint_block=not a.lint_warn)
    rep = write_report(r, Path(a.out), Path(a.md), lint_block=not a.lint_warn)
    if lint_errors(r.lint) and not a.lint_warn:
        print(f"원고 규칙 오류 — 고치지 않았다. 보고서: {rep}")
        return 1
    if r.rebuild:
        print("다시 조판 필요 — " + "; ".join(r.rebuild) + f"\n보고서: {rep}")
        return 3
    print(f"바꾼 문단 {len(r.changed)} · 바뀐 정답 {len(r.answers)} · 기계 잔존 문항지 {r.residue('문항지')} · 답표시본 {r.residue('답표시본')}\n보고서: {rep}")
    return 0 if r.residue("문항지") == 0 and r.residue("답표시본") == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
