"""md → 문항지·답 표시본 hwpx + 보고서(Task 27, 계획 Task 14 대체).

build : 규칙 검사(lint) → 스캔 → 양식 준비(prepare_document) → 누름틀(fill_slots) → refresh → 조판(compose, 형광펜 없이)
        → finalize_form → 렌더 루프(layout.settle — 자간 맞춤·배치·총쪽수를 굳혀 문항지 hwpx에 저장)
        → 답 표시본 = 굳힌 문항지 + 정답 형광펜만(compose.add_answer_marks) → 답 표시본 렌더 1회
        → 기계 검사(verify_document·verify_render) + 두 판 대조(본문 글자 동일, 렌더 쪽수·문항 머리 자리 ±0.5pt)
        → [--compare] 제출본 렌더 + 쪽별 좌우 PNG → 보고.md.
        시작할 때 이 원고(stem)의 옛 산출물을 지우고 '진행 중' 보고서를 먼저 쓴다. hwpx는 _렌더/에서 만들고 끝까지 간 뒤에만
        out_dir로 옮긴다 — 중간에 멈춘 실행이 멀쩡해 보이는 옛 파일·반쯤 된 파일을 남기지 않게.
        두 판을 따로 굳히지 않는다 — 한 번 굳힌 배치에 형광펜만 더해야 두 판의 나눔·간격·배치형이 같다.
        규칙 오류가 있으면 기본은 조판하지 않고 보고서만 쓴다(lint_block=False면 경고로 두고 진행).
기계 검사 통과는 '기계 잔존 0'일 뿐이다 — 판정은 사용자 검수 몫.
"""

from __future__ import annotations

import argparse
import glob
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from hwpx.document import HwpxDocument

from . import q
from .compose import add_answer_marks, choice_paragraphs, compose
from .fit import summary as spacing_summary
from .geometry import PageLayout, hancom_windows_pdf, measure
from .kit import Kit, load_kit, style_ids
from .layout import GAPS, PACKS, head_places, settle
from .lint import Violation, lint
from .lint import errors as lint_errors
from .prepare import finalize_form, prepare_document
from .render import render, side_by_side
from .scan import scan_markdown
from .slots import fill_slots
from .verify import Finding, _f, errors, question_heads, verify_document, verify_render

# 보고서 맨 위 단계 표시 — 기본 문구. 검수 단계는 `--stage`로 적는다.
STAGE = ("엔진 산출물 — 사용자 검수 전에는 제출·인쇄에 쓰지 않는다. "
         "한글에서 고친 나눔·간격은 남는다: 수정은 원고(md)에서 하고 다시 뽑는다.")
HEAD_TOL = 0.5  # 두 판 문항 머리 y 허용 차(pt)
MARKPEN_DRIFT = 0.4  # Windows 한/글: 형광펜 칠한 줄 하나가 아래 문항 머리를 미는 양의 상한(pt, 실측 약 0.3)
판 = ("문항지", "답표시본")


@dataclass
class BuildResult:
    보고: Path
    blocked: bool                                # 규칙 오류로 조판하지 않았다
    문항지: Path | None = None
    답표시본: Path | None = None
    page_count: int | None = None
    lint: list[Violation] = field(default_factory=list)
    findings: dict[str, list[Finding]] = field(default_factory=dict)  # 판 → 기계 검사(두 판 대조는 답표시본 쪽에)
    notes: list[str] = field(default_factory=list)                    # "조판: …" · "렌더: …" — 보고서 '확인 필요'
    layouts: dict[str, str] = field(default_factory=dict)             # 문항 → 최종 배치형(1·2·3·5행·답항표)
    spacing: dict[int, str] = field(default_factory=dict)             # 문항 → 자간 맞춤 요약('발문 −11 · 답지 −3')
    places: list[tuple[int, int]] = field(default_factory=list)       # 문항 → (쪽, 단)
    pngs: dict[str, list[Path]] = field(default_factory=dict)         # 판 → 최종 렌더 쪽 PNG
    compare: list[Path] = field(default_factory=list)                 # 제출본 쪽별 좌우 PNG
    renders: dict[str, int] = field(default_factory=dict)            # 판·제출본 → 실한컴 렌더 횟수
    draft: bool = False
    pages: tuple[int, int] | None = None                              # (첫 렌더 쪽수, 최종 쪽수)
    stage: str = STAGE                                                # 보고서 맨 위 단계 표시(--stage로 바꾼다)
    habits: str = ""                                                  # 교사 습관값 출처(kit.habits_source)
    school_rules: str = ""                                            # 학교 규칙 출처(rules.json source) — 없으면 "없음"

    @property
    def pages_added(self) -> bool:
        return self.pages is not None and self.pages[1] > self.pages[0]

    def residue(self, edition: str) -> int:
        return len(errors(self.findings.get(edition, [])))


# ---- 두 판 대조 ----------------------------------------------------------------

def same_layout(a: list[PageLayout], b: list[PageLayout], *, tol: float = HEAD_TOL, drift: float = 0.0) -> list[str]:
    """두 렌더의 쪽 수·문항 머리 자리(쪽, 단, y ±tol)가 같은지 — 다른 점 목록(같으면 []).

    drift > 0이면 b의 머리가 아래로 tol + drift × (그 단에서 앞선 머리 수)까지 밀려도 같은 자리로 본다. Windows 한/글은 형광펜을
    칠한 줄을 조금 높게 그려, 답 표시본에서 앞선 문항의 정답 줄 수만큼 아래 머리가 밀린다(macOS 한/글은 밀지 않는다).
    쪽·단은 그대로 같아야 하고, 위로 밀리는 것은 tol까지다.
    """
    out = []
    if len(a) != len(b):
        out.append(f"쪽 수 {len(a)} ≠ {len(b)}")
    ha = [(c.page, c.col, y, i) for p in a for c in p.columns for i, y in enumerate(c.heads)]
    hb = [(c.page, c.col, y) for p in b for c in p.columns for y in c.heads]
    if len(ha) != len(hb):
        out.append(f"문항 머리 수 {len(ha)} ≠ {len(hb)}")
    for k, (x, y) in enumerate(zip(ha, hb), 1):
        d = y[2] - x[2]
        if x[:2] != y[:2] or d < -tol or d > tol + drift * x[3]:
            out.append(f"{k}번 머리 {x[0]}쪽 {x[1]}단 y {x[2]:.1f} ≠ {y[0]}쪽 {y[1]}단 y {y[2]:.1f}")
    return out


_형광펜_태그 = re.compile(rb"<hp:markpenBegin\b[^>]*/>|<hp:markpenEnd\s*/>")


def same_package(plain: Path, key: Path) -> list[str]:
    """두 판 hwpx가 형광펜만 다른지 — 절 XML은 형광펜 태그를 뺀 바이트가 같고, 나머지 zip 부분은 바이트가 같다."""
    out = []
    with zipfile.ZipFile(plain) as a, zipfile.ZipFile(key) as b:
        if a.namelist() != b.namelist():
            return [f"zip 부분 목록이 다르다: {sorted(set(a.namelist()) ^ set(b.namelist()))}"]
        for name in a.namelist():
            x, y = a.read(name), b.read(name)
            if name.startswith("Contents/section"):
                y = _형광펜_태그.sub(b"", y)
            if x != y:
                out.append(f"{name}가 다르다" + ("(형광펜을 빼고도)" if name.startswith("Contents/section") else ""))
    return out


def final_layouts(doc: HwpxDocument, kit: Kit) -> dict[str, str]:
    """문서에서 읽은 문항별 배치형 — 렌더 루프가 접힌 답지를 다시 쓴 뒤의 최종값."""
    ids = style_ids(doc)
    kinds = {ids[kit.styles[r]][0]: f"{r[-1]}행" for r in ("choice1", "choice2", "choice3", "choice5")}
    ps = list(doc.sections[0].paragraphs)
    out = {}
    for k in range(1, len(question_heads(doc)) + 1):
        rows = choice_paragraphs(doc, kit, k)
        if len(rows) == 1 and ps[rows[0]].element.find(f".//{q('hp', 'tbl')}") is not None:
            out[str(k)] = "답항표"
        elif rows:
            out[str(k)] = kinds.get(str(ps[rows[0]].element.get("styleIDRef")), "?")
    return out


# ---- 파이프라인 ----------------------------------------------------------------

def _copy_pages(pages: list[Path], dest: Path, stem: str) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for i, p in enumerate(pages, 1):
        target = dest / f"{stem}_p{i}.png"
        shutil.copyfile(p, target)
        out.append(target)
    return out


def _clean(out_dir: Path, stem: str) -> None:
    """이 원고의 옛 산출물 — 두 판 hwpx·보고.md·렌더/{stem}_{문항지,답표시본}_p*·대조/{stem}_vs_제출본_p*·_렌더/.

    이름 틀을 정확히 맞춘다 — `시험`이 `시험_2`의 산출물을 지우지 않게, stem의 `[`·`]`가 glob 문법으로 읽히지 않게.
    """
    for p in (out_dir / f"{stem}_문항지.hwpx", out_dir / f"{stem}_답표시본.hwpx", out_dir / "보고.md"):
        p.unlink(missing_ok=True)
    for sub, kind in (("렌더", "문항지"), ("렌더", "답표시본"), ("대조", "vs_제출본")):
        exact = re.compile(re.escape(f"{stem}_{kind}_p") + r"\d+\.png")
        for p in (out_dir / sub).glob(f"{glob.escape(stem)}_{kind}_p*.png"):
            if exact.fullmatch(p.name):
                p.unlink()
    shutil.rmtree(out_dir / "_렌더", ignore_errors=True)


def git_ignored(path: Path) -> bool | None:
    """path가 git 무시 대상인가 — git 저장소 밖이거나 git이 없으면 None."""
    path = Path(path)
    try:
        r = subprocess.run(["git", "-C", str(path if path.is_dir() else path.parent), "check-ignore", "-q", str(path)],
                           capture_output=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {0: True, 1: False}.get(r.returncode)


def build(md_path: Path, kit: Kit | Path, out_dir: Path, *, form_path: Path, draft: bool = False,
          lint_block: bool = True, gap: str | None = None, compare: Path | None = None, render_fn=render,
          stage: str | None = None, pack: str | None = None) -> BuildResult:
    """원고 md 하나 → out_dir에 문항지·답 표시본 hwpx, 렌더 PNG, (compare면) 제출본 대조 PNG, 보고.md."""
    md_path, out_dir = Path(md_path).resolve(), Path(out_dir).resolve()
    kit = kit if isinstance(kit, Kit) else load_kit(Path(kit))
    gap, pack = gap or kit.gap_mode, pack or kit.pack  # 없으면 킷 교사 습관(habits.json)의 기본
    if gap not in GAPS:
        raise ValueError(f"gap은 {GAPS} 가운데 하나: {gap!r}")
    if pack not in PACKS:
        raise ValueError(f"pack은 {PACKS} 가운데 하나: {pack!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    md = md_path.read_text(encoding="utf-8")
    stem = md_path.stem
    _clean(out_dir, stem)
    r = BuildResult(보고=out_dir / "보고.md", blocked=False, stage=stage or STAGE, habits=kit.habits_source,
                    school_rules=(kit.rules or {}).get("source", "") if kit.rules else "없음(엔진 규칙만)")
    r.보고.write_text(f"# 시험지 조판 보고 — {md_path.name}\n\n> **진행 중** — 이 줄이 남아 있으면 조판이 중간에 멈췄다"
                     "(예외). 이 폴더의 산출물을 쓰지 않는다.\n", encoding="utf-8")
    if git_ignored(out_dir) is False:
        r.notes.append(f"출력: 출력 폴더가 git 무시 대상이 아니다 — 실제 문항이 커밋될 수 있다: {out_dir}")
    r.lint = lint(md, md_dir=md_path.parent, rules=kit.rules, draft=draft)
    if lint_errors(r.lint) and lint_block:
        r.blocked = True
        write_report(r, md_path=md_path)
        return r
    scan = scan_markdown(md, kit.front_matter)
    r.draft = draft or scan.front.is_draft

    # 문항지: 준비 → 누름틀 → 조판(형광펜 없이) → 마무리 → 렌더 루프로 굳힘
    doc, prepared = prepare_document(Path(form_path), kit)
    fill_slots(doc, kit, scan.front, question_count=len(scan.questions),
               total_points=sum(x.points or 0.0 for x in scan.questions))
    prepared = prepared.refresh(doc)
    res = compose(doc, scan, kit, answer_key=False, image_root=md_path.parent)
    finalize_form(doc, kit, prepared)
    r.notes += [f"조판: {n}" for n in res.notes]
    work = out_dir / "_렌더"  # 끝까지 간 뒤에만 hwpx를 out_dir로 옮긴다
    plain_path, key_path = work / f"{stem}_문항지.hwpx", work / f"{stem}_답표시본.hwpx"
    s = settle(doc, kit, plain_path, work / "문항지", gap=gap, render_fn=render_fn, scan=scan,
               balance=pack == "balanced")
    r.notes += [f"렌더: {n}" for n in s.notes]
    r.renders["문항지"], r.page_count, r.places = s.renders, s.render.page_count, head_places(s.layout)
    r.renders["자간 측정"] = s.measures
    r.spacing = spacing_summary(s.spacing, s.spacing_words)
    r.pages = (s.first_pages, s.render.page_count)

    # 답 표시본: 굳힌 문항지 파일 + 형광펜만
    key = HwpxDocument.open(str(plain_path))
    add_answer_marks(key, kit, res.answers, draft=r.draft)
    key.save_to_path(str(key_path))
    key_rr = render_fn(key_path, work / "답표시본")
    r.renders["답표시본"] = 1

    # 기계 검사 — 저장된 파일을 다시 열어 본다
    plain, key = HwpxDocument.open(str(plain_path)), HwpxDocument.open(str(key_path))
    r.layouts = final_layouts(plain, kit)
    r.findings["문항지"] = (verify_document(plain, kit, expect_answers=None, answer_key=False, draft=r.draft)
                          + verify_render(s.render, plain, kit, expected_pages=None))
    fs = (verify_document(key, kit, expect_answers=res.answers, answer_key=True, draft=r.draft)
          + verify_render(key_rr, key, kit, expected_pages=s.render.page_count))
    fs += [_f("M8", f"두 판이 형광펜 말고도 다르다: {d}") for d in same_package(plain_path, key_path)]
    drift = MARKPEN_DRIFT if hancom_windows_pdf(key_rr.pdf) else 0.0  # Windows 한/글은 형광펜 줄이 머리를 조금 민다
    fs += [_f("M8", f"두 판 배치가 다르다: {d}") for d in same_layout(s.layout, measure(key_rr.pdf, kit), drift=drift)]
    r.findings["답표시본"] = fs

    r.pngs = {"문항지": _copy_pages(s.render.pages, out_dir / "렌더", f"{stem}_문항지"),
              "답표시본": _copy_pages(key_rr.pages, out_dir / "렌더", f"{stem}_답표시본")}
    if compare is not None:
        sub = render_fn(Path(compare).resolve(), work / "제출본")
        r.renders["제출본"] = 1
        r.compare = side_by_side(s.render.pdf, sub.pdf, out_dir / "대조", stem=f"{stem}_vs_제출본")
    r.문항지, r.답표시본 = out_dir / plain_path.name, out_dir / key_path.name
    shutil.copyfile(plain_path, r.문항지)
    shutil.copyfile(key_path, r.답표시본)
    write_report(r, md_path=md_path, gap=gap, compare=compare, pack=pack)
    return r


# ---- 보고서 --------------------------------------------------------------------

def _q(p: Path) -> str:
    return f'"{Path(p).resolve()}"'


def _reveal(p: Path) -> str:
    """파일 자리를 여는 명령 — macOS는 Finder(open -R), Windows는 탐색기에서 그 파일을 골라 둔다(explorer /select,)."""
    return f"explorer /select,{_q(p)}" if sys.platform == "win32" else f"open -R {_q(p)}"


def _open(p: Path) -> str:
    """파일을 기본 앱으로 여는 명령 — macOS open, Windows explorer."""
    return f"explorer {_q(p)}" if sys.platform == "win32" else f"open {_q(p)}"


def headlines(r: BuildResult) -> list[str]:
    """'확인 필요' 맨 앞에 굵게 둘 줄 — 글귀가 아니라 상태로 정한다(규칙 오류를 넘겼는가, 쪽수가 늘었는가)."""
    out = []
    n_err = len(lint_errors(r.lint))
    if n_err and not r.blocked:
        out.append(f"[규칙 오류 무시] 규칙 오류 {n_err}건을 --lint-warn으로 넘기고 조판했다")
    if r.pages_added:
        out.append(f"[쪽 추가] 최종 쪽수가 첫 렌더 본문 기준보다 늘었다: {r.pages[0]}쪽 → {r.pages[1]}쪽"
                   " — 까닭은 아래 렌더 note(문항 넘김이면 최후 수단, 박스만 앉은 빈 쪽이 남았으면 기계 검사 M10)")
    return out


def write_report(r: BuildResult, *, md_path: Path, gap: str = "distribute", compare: Path | None = None,
                 pack: str = "balanced") -> Path:
    L = [f"# 시험지 조판 보고 — {Path(md_path).name}", "",
         f"> 단계: {r.stage}",
         "> 초안: " + ("**예** — 미확정 누름틀(시행일·인쇄 매수 등)은 오류가 아니라 경고로만 잡았다" if r.draft else "아니오"),
         "> 기계 검사 결과는 '기계 잔존 N'으로만 적는다. 판정은 사용자 검수 몫이다.",
         *([f"> 교사 습관값: {r.habits}"] if r.habits else []),
         *([f"> 학교 규칙: {r.school_rules}"] if r.school_rules else []), ""]
    L += ["## 파일", f"- 원고: `{_reveal(md_path)}`"]
    if r.blocked:
        L += ["- 규칙 오류가 있어 **조판하지 않았다**(`--lint-warn`이면 경고로 두고 조판한다).", ""]
    else:
        for name, p in (("문항지", r.문항지), ("답 표시본", r.답표시본)):
            L.append(f"- {name}: `{_reveal(p)}`")
        L += [f"- 보고서: `{_reveal(r.보고)}`", ""]

    items = [f"**{h}**" for h in headlines(r)] + list(r.notes)
    L += [f"## 확인 필요 ({len(items)})"]
    L += [f"- {n}" for n in items] or ["- 없음"]
    L.append("")

    n_err = len(lint_errors(r.lint))
    L += [f"## 규칙 검사 — 오류 {n_err} · 경고 {len(r.lint) - n_err}"]
    L += [f"- {v.code} L{v.line_no} {v.msg}" for v in r.lint] or ["- 없음"]
    L.append("")
    if r.blocked:
        r.보고.write_text("\n".join(L), encoding="utf-8")
        return r.보고

    L += ["## 기계 검사"]
    for ed in 판:
        fs = r.findings.get(ed, [])
        warn = [f for f in fs if f.level != "E"]
        L.append(f"- {ed}: 기계 잔존 {r.residue(ed)}" + (f" · 경고 {len(warn)}" if warn else ""))
        L += [f"  - {f.code} [{f.level}] {f.msg}" for f in fs]
    L += ["- 두 판 대조는 답표시본 줄의 M8에 든다: hwpx는 절 XML에서 형광펜 태그를 빼면 바이트가 같고 나머지 zip 부분도 "
          "바이트가 같아야 하며, 렌더는 쪽 수와 문항 머리 자리(쪽·단·y ±0.5pt)가 같아야 한다. Windows 한/글 PDF는 형광펜 줄이 "
          "머리를 조금 밀어, 그 단에서 앞선 정답 줄마다 아래로 0.4pt씩 더 둔다.",
          "- 형광펜은 macOS 한컴 PDF에 그려지지 않는다(Windows는 그린다) — 답 표시본의 정답은 hwpx에서 뽑아 대조했다(M11).", ""]

    L += ["## 배치", f"- 쪽수 {r.page_count}" + (f"(첫 렌더 {r.pages[0]}쪽)" if r.pages else "") + f" · 단 나눔 {pack} · 간격 {gap} · 렌더 "
          + " · ".join(f"{k} {n}회" for k, n in r.renders.items() if n)]
    L += [f"- 두 판 배치: {'같다' if not [f for f in r.findings.get('답표시본', []) if f.code == 'M8' and '두 판' in f.msg] else '다르다(기계 검사 M8)'}"]
    L += ["- 자간: 끝줄이 짧아 자간을 줄여 한 줄을 당긴 문단(%), '(낱말)'은 줄 수는 그대로 두고 벌어진 줄에 다음 낱말을 "
          "끌어올린 문단 — 둘 다 찾은 최소값에 여유 1%를 더했다. 못 당긴 문단은 '확인 필요'에 있다"]
    L += ["", "| 문항 | 쪽 | 단 | 답지 배치형 | 자간 |", "|---|---|---|---|---|"]
    for k, lay in r.layouts.items():
        p, c = r.places[int(k) - 1] if int(k) - 1 < len(r.places) else ("?", "?")
        L.append(f"| {k} | {p} | {c} | {lay} | {r.spacing.get(int(k), '')} |")
    L.append("")

    L += ["## 렌더 PNG"]
    for ed in 판:
        for p in r.pngs.get(ed, []):
            L.append(f"- `{_open(p)}`")
    L.append("")
    if compare is not None or r.compare:
        L += ["## 제출본 대조(왼쪽 = 엔진 문항지, 오른쪽 = 제출본)"]
        if compare is not None:
            L.append(f"- 제출본: `{_reveal(compare)}`")
        L += [f"- `{_open(p)}`" for p in r.compare]
        L.append("")
    r.보고.write_text("\n".join(L), encoding="utf-8")
    return r.보고


# ---- CLI -----------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m exam_kit.build", description="원고 md → 문항지·답 표시본 hwpx + 보고서")
    ap.add_argument("md", type=Path)
    ap.add_argument("--kit", type=Path, required=True)
    ap.add_argument("--form", type=Path, required=True, help="학교 원안지 양식 hwpx")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--draft", action="store_true", help="미확정 누름틀을 오류가 아닌 경고로")
    ap.add_argument("--lint-warn", action="store_true", help="규칙 오류를 경고로 두고 조판")
    ap.add_argument("--gap", choices=GAPS, default=None,
                    help="문항 간격: distribute(단 끝을 맞춰 고르게) · fixed(한 줄 고정). 없으면 킷 habits.json의 gap_mode")
    ap.add_argument("--pack", choices=PACKS, default=None,
                    help="단 나눔: balanced(최소 쪽수에서 단마다 고르게) · greedy(앞에서부터). 없으면 킷 habits.json의 pack")
    ap.add_argument("--compare", type=Path, help="쪽별 좌우 대조할 제출본 hwpx")
    ap.add_argument("--stage", help="보고서 맨 위 단계 표시(기본: 엔진 단계 STAGE) — 예: '원고 미확정 — 형태 검증용'")
    a = ap.parse_args(argv)
    r = build(a.md, a.kit, a.out, form_path=a.form, draft=a.draft, lint_block=not a.lint_warn, gap=a.gap,
              compare=a.compare, stage=a.stage, pack=a.pack)
    n_err = len(lint_errors(r.lint))
    print(f"규칙 검사: 오류 {n_err} · 경고 {len(r.lint) - n_err}")
    if r.blocked:
        for v in lint_errors(r.lint):
            print(f"  {v.code} L{v.line_no} {v.msg}")
        print(f"조판하지 않았다 — 보고서: {r.보고}")
        return 1
    renders = sum(n for k, n in r.renders.items() if k != "자간 측정")
    print(f"쪽수 {r.page_count} · 렌더 {renders}회 · 자간 측정 {r.renders.get('자간 측정', 0)}회 · "
          f"기계 잔존 문항지 {r.residue('문항지')} · 답표시본 {r.residue('답표시본')}")
    items = headlines(r) + r.notes
    print(("초안 · " if r.draft else "") + f"확인 필요 {len(items)}건" + (":" if items else ""))
    for n in items:
        print("  " + n)
    print(f"보고서: {r.보고}")
    return 0 if r.residue("문항지") == 0 and r.residue("답표시본") == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
