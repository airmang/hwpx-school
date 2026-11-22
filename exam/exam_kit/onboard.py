"""학교 등록 ① 해부 — 빈 원안지 서식 hwpx의 사실을 모아 보고서(마크다운)로 낸다.

판단은 하지 않는다: 어느 스타일이 문항인지, 무슨 글이 지울 안내인지는 스킬이 이 보고서와 서식 렌더를 읽고
결정표로 사용자에게 묻는다(헌법 2 — 두뇌는 스킬, 파이썬은 손). 여기서 내는 '후보'는 구조에서 곧바로 보이는 것뿐이다.

    uv run python -m exam_kit.onboard scan <서식.hwpx> [--out 해부.md]
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from hwpx import HwpxDocument

from .kit import sha256

_그리기 = ("line", "rect", "ellipse", "arc", "polygon", "curve", "connectLine")


def _t_lead(run) -> str:
    """run의 hp:t마다 첫 글(형광펜·탭 같은 표시 뒤의 글은 빼고)을 이은 것 — 옛 ``t.text`` 읽기와 같다.

    ``run.content``에서 hp:t 안의 글 조각 가운데, 바로 앞 조각이 같은 hp:t의 표시·글리프가 아닌 것이 hp:t의 첫 글이다."""
    out, previous = [], None
    for item in run.content:
        if item.container == "t" and item.kind == "text":
            if previous is None or previous.container != "t" or previous.kind == "text":
                out.append(item.text)
        previous = item
    return "".join(out)


def _own_text(p) -> str:
    """문단 자신의 글(표·메모·머리말 안 글은 뺀다)."""
    return "".join(_t_lead(r) for r in p.runs)


def _inside(item, paragraph) -> list:
    """run.content 조각 하나가 품은 문단(문서 차례): 표는 캡션·칸, 그림·도형은 캡션·글상자, 각주·미주·메모는 그 글,
    머리말·꼬리말 컨트롤은 그 story(구역 설정에서 id로 찾는다 — 양식은 머리말을 표 칸 안에도 둔다)."""
    obj = item.object
    if item.kind in ("header", "footer"):
        props = paragraph.section.properties
        story = next((x for x in (*props.headers, *props.footers) if x.id == item.attribute("id")), None)
        return [] if story is None else list(story.paragraphs)
    if obj is None:
        return []
    if item.kind == "table":
        heads = list(obj.caption.paragraphs) if obj.caption is not None else []
        return heads + [p for row in obj.rows for cell in row.cells for p in cell.paragraphs]
    out = []
    caption = getattr(obj, "caption", None)
    if caption is not None and hasattr(caption, "paragraphs"):
        out += list(caption.paragraphs)
    if hasattr(obj, "iter_paragraphs"):
        out += [place.paragraph for place in obj.iter_paragraphs() if place.where != "caption"]
    elif item.kind in ("footnote", "endnote", "field_begin") and hasattr(obj, "paragraphs"):
        out += list(obj.paragraphs)
    return out


#: 품은 문단을 다시 걸어 들어가야 하는 조각(글상자 iter_paragraphs는 이미 깊이 내놓는다)
_DEEP_KINDS = ("table", "footnote", "endnote", "field_begin", "header", "footer")


def _table_paragraphs(table) -> list:
    """표 안 모든 문단을 문서 차례로(캡션, 행·칸, 칸 문단 안의 표·글상자·각주·메모는 그 문단 바로 뒤에)."""
    heads = list(table.caption.paragraphs) if table.caption is not None else []
    out = []
    for p in heads + [p for row in table.rows for cell in row.cells for p in cell.paragraphs]:
        out += _with_inner(p)
    return out


def _with_inner(paragraph) -> list:
    out = [paragraph]
    for run in paragraph.runs:
        for item in run.content:
            for q in _inside(item, paragraph):
                out += [q] if item.kind not in _DEEP_KINDS and hasattr(item.object, "iter_paragraphs") else _with_inner(q)
    return out


def _all_text(paragraphs) -> str:
    """문단들 아래 모든 글을 문서 차례로 — hp:t마다 첫 글(옛 ``t.text``), 표(캡션·칸)·글상자·각주·메모 글은 그것이 놓인
    자리에서. 문단 안 머리말·꼬리말의 글은 넣지 않는다(옛 판은 문단 0의 머리말 글도 넣었다)."""
    return "".join(_walk(p) for p in paragraphs)


def _walk(paragraph) -> str:
    out = []
    for run in paragraph.runs:
        previous = None
        for item in run.content:
            if item.container == "t" and item.kind == "text":
                if previous is None or previous.container != "t" or previous.kind == "text":
                    out.append(item.text)
            elif item.object is not None or item.kind in ("header", "footer"):
                inner = _inside(item, paragraph)
                flat = item.kind not in _DEEP_KINDS and hasattr(item.object, "iter_paragraphs")
                out.append("".join(_own_text(q) for q in inner) if flat else _all_text(inner))
            previous = item
    return "".join(out)


def _table_text(table) -> str:
    heads = list(table.caption.paragraphs) if table.caption is not None else []
    return _all_text(heads + [p for row in table.rows for cell in row.cells for p in cell.paragraphs])


def _cells(table) -> int:
    """표의 칸 수(칸 안 표·칸 안 머리말의 표의 칸까지)."""
    return sum(1 + sum(_paragraph_cells(p) for p in cell.paragraphs) for row in table.rows for cell in row.cells)


def _paragraph_cells(paragraph) -> int:
    n = 0
    for run in paragraph.runs:
        for item in run.content:
            if item.kind == "table" and item.object is not None:
                n += _cells(item.object)
            elif item.kind in _DEEP_KINDS:
                n += sum(_paragraph_cells(q) for q in _inside(item, paragraph))
            elif item.object is not None:  # 글상자: iter_paragraphs가 이미 깊이 내놓는다
                n += sum(1 for q in _inside(item, paragraph) for t in q.tables for row in t.rows for _ in row.cells)
    return n



def _body_columns(cols):
    """본문 단 정의 — 단 수가 가장 많은 것(같으면 먼저 나온 것). 머리만 1단으로 두고 본문을 2단으로 여는 서식이 있다."""
    return max(cols, key=lambda c: c.count) if cols else None

class Form:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.doc = HwpxDocument.open(str(self.path))
        self.section = self.doc.sections[0]
        self.tops = list(self.section.paragraphs)
        self.fonts = {fid: f.face for fid, f in self.doc.styles.fonts("HANGUL").items()}
        self.styles = {str(s.raw_id if s.raw_id is not None else s.id): s for s in self.doc.styles.values()}

    # ---- 글자 모양 ----
    def char_desc(self, cid) -> str:
        c = None if cid is None else self.doc.styles.char_property(cid)
        if c is None:
            return "?"
        ch = c.child_attributes
        fr, ratio, sp = ch.get("fontRef"), ch.get("ratio"), ch.get("spacing")
        bits = [f"{self.fonts.get(fr.get('hangul')) if fr is not None else '?'} {int(c.attributes.get('height')) / 100:g}pt",
                f"장평 {ratio.get('hangul') if ratio is not None else '?'}", f"자간 {sp.get('hangul') if sp is not None else '?'}"]
        if "bold" in ch:
            bits.append("굵게")
        col = c.attributes.get("textColor")
        if col and col.upper() not in ("#000000",):
            bits.append(f"색 {col}")
        return " · ".join(bits)

    def color(self, cid) -> str | None:
        c = None if cid is None else self.doc.styles.char_property(cid)
        col = None if c is None else (c.attributes.get("textColor") or "").upper()
        return None if not col or col == "#000000" else col

    # ---- 보고 ----
    def report(self) -> str:
        L: list[str] = [f"# 서식 해부 — {self.path.name}", "",
                        "> 사실만 적는다. 역할·지울 대상 판단은 스킬이 결정표로 사용자에게 묻는다.", ""]
        L += self._page() + self._style_table() + self._fields() + self._memos() + self._drawings()
        L += self._header_footer() + self._paragraphs() + self._tables() + self._hints()
        return "\n".join(L) + "\n"

    def _page(self) -> list[str]:
        size, m = self.doc.page.size(section=0), self.doc.page.margins(section=0)
        cols = self.doc.page.columns(section=0)
        단 = [f"- 단 {c.count}단 {c.type} · 단 사이 {c.gap}" for c in cols] or ["- 단 정보 없음"]
        if len(cols) > 1:  # 머리(결재란·제목) 1단 뒤에 본문 2단을 여는 서식 — 본문 단은 단 수가 가장 많은 정의
            단[-1] += f" (단 정의 {len(cols)}개 — 본문 단 후보: {_body_columns(cols).count}단)"
        return ["## 용지·단", f"- sha256 `{sha256(self.path)}`",
                f"- 용지 {size.width} × {size.height} (landscape 속성 `{size.orientation}`)",
                "- 여백 " + " · ".join(f"{k} {getattr(m, k)}" for k in ("left", "right", "top", "bottom", "header", "footer")),
                *단,
                f"- 한글 글꼴: {', '.join(self.fonts.values())}", ""]

    def _para_parts(self, s):
        """스타일의 (줄간격, 왼여백, 내어쓰기, 자동번호인가, 탭 자리들) — 양식 paraPr 치수는 switch의 case가 실제 조판 값이다."""
        p = None if s.para_pr_id_ref is None else self.doc.styles.paragraph_property(s.para_pr_id_ref)
        if p is None:
            return None, None, None, False, []
        case = p.version_switch.case if p.version_switch is not None else None
        ls = case.line_spacing if case is not None and case.line_spacing is not None else p.line_spacing
        mg = case.margin if case is not None and case.margin is not None else p.margin
        tab = None if p.tab_pr_id_ref is None else self.doc.styles.tab_property(p.tab_pr_id_ref)
        vs = None if tab is None else tab.version_switch
        stops = [] if tab is None else (vs.case.tab_stops if vs is not None and vs.case is not None else tab.tab_stops)
        heading = p.heading is not None and p.heading.type == "NUMBER"
        return ls, (None if mg is None else mg.left), (None if mg is None else mg.intent), heading, [str(t.pos) for t in stops]

    def _style_table(self) -> list[str]:
        L = ["## 스타일", "| id | 이름 | 글자 | 줄간격 | 왼여백 | 내어쓰기 | 탭(case) | 자동번호 | 본문 사용 |", "|---|---|---|---|---|---|---|---|---|"]
        used = Counter(None if pl.paragraph.style_id_ref is None else str(pl.paragraph.style_id_ref)
                       for pl in self.doc.text.iter_paragraphs() if pl.section == self.section)
        for sid, s in self.styles.items():
            ls, left, ind, head, tabs = self._para_parts(s)
            L.append(f"| {sid} | {s.name} | {self.char_desc(s.char_pr_id_ref)} | "
                     f"{'' if ls is None else str(ls.value) + (ls.spacing_type or '')[:3]} | {'' if left is None else left} | "
                     f"{'' if ind is None else ind} | {' '.join(tabs[:6])} | "
                     f"{'NUMBER' if head else ''} | {used.get(sid, 0)} |")
        return L + [""]

    def _fields(self) -> list[str]:
        fs = [f for f in self.doc.fields.all if f.field_type == "CLICK_HERE" and f.location.section_index == 0]
        L = [f"## 누름틀 {len(fs)}개"]
        for f in fs:
            L.append(f"- id `{f.field_id}` 이름 {f.name!r} — 둘러싼 문단 글 {_own_text(f.paragraph)[:40]!r}")
        return L + [""]

    def _memos(self) -> list[str]:
        ms = self.section.memos
        L = [f"## 메모 {len(ms)}개 (글자 안 MEMO 필드)"]
        for m in ms:
            # 옛 판의 정규식(r'\s+')은 공백이 아니라 글자 '\s'를 찾아 공백을 접지 않았다 — 보고가 같도록 접지 않는다.
            L.append("- " + _all_text(m.paragraphs).strip()[:120])
        return L + [""]

    def _drawings(self) -> list[str]:
        c = Counter(pl.object.shape_type for pl in self.doc.text.iter_objects(kinds="shape")
                    if pl.section == self.section and pl.object.shape_type in _그리기)
        return ["## 그리기 개체", "- " + (", ".join(f"{k} {v}" for k, v in c.items()) or "없음"), ""]

    def _header_footer(self) -> list[str]:
        L = ["## 머리말·꼬리말"]
        stories = {"header": self.doc.page.headers(section=0), "footer": self.doc.page.footers(section=0)}
        nums = self.doc.page.auto_numbers(section=0)
        for tag in ("header", "footer"):
            for i, h in enumerate(stories[tag]):
                inside = set(h.paragraphs)
                auto = [a.kind for a in nums if a.paragraph in inside]
                L.append(f"- {tag}{i} ({h.page_type}): {_all_text(h.paragraphs)[:60]!r} 자동 번호 {auto}")
        return L + [""]

    def _paragraphs(self) -> list[str]:
        L = ["## 최상위 문단", "| # | 스타일 | 나눔 | 표 | 색 글자 | 글 |", "|---|---|---|---|---|---|"]
        for i, p in enumerate(self.tops):
            text = _own_text(p).strip()
            tbls = [f"{pl.object.row_count}×{pl.object.column_count}" for pl in p.iter_objects(kinds="table")]
            colors = sorted({c for r in p.runs for c in [self.color(r.char_pr_id_ref)] if c and _t_lead(r).strip()})
            brk = "쪽" if p.page_break else "단" if p.column_break else ""
            if not (text or tbls or brk):
                continue
            style = self.styles.get(None if p.style_id_ref is None else str(p.style_id_ref))
            L.append(f"| {i} | {'' if style is None else style.name} | {brk} | {' '.join(tbls[:4])} | "
                     f"{' '.join(colors)} | {text[:50].replace('|', '/')} |")
        return L + [""]

    def _tables(self) -> list[str]:
        L = ["## 표(최상위 문단의)", "| 문단 | 모양 | 크기 | 글자처럼 | 칸 수 | 안 문단 스타일 | 글 앞부분 |", "|---|---|---|---|---|---|---|"]
        for i, p in enumerate(self.tops):
            for t in p.tables:
                inner = Counter(self.styles[str(x.style_id_ref)].name for x in _table_paragraphs(t)
                                if x.style_id_ref is not None and str(x.style_id_ref) in self.styles)
                L.append(f"| {i} | {t.row_count}×{t.column_count} | {t.width}×{t.height} | "
                         f"{'1' if t.position.treat_as_char else '0'} | {_cells(t)} | "
                         f"{', '.join(f'{k} {v}' for k, v in inner.most_common(3))} | "
                         f"{_table_text(t)[:30].replace('|', '/')} |")
        return L + [""]

    def _hints(self) -> list[str]:
        L = ["## 구조에서 바로 보이는 후보(판단 아님)"]
        nums = [s.name for s in self.styles.values() if self._para_parts(s)[3]]
        literal = [i for i, p in enumerate(self.tops) if re.match(r"^\d{1,3}\.\s?$", next(
            (x for r in p.runs for x in [_t_lead(r)] if x), ""))]
        L.append(f"- 문항 번호: 자동번호 스타일 {nums or '없음'} · 글자 번호로 시작하는 문단 {len(literal)}개"
                 f" → number.mode 후보 {'autonumber' if nums else 'literal' if literal else '?'}")
        tails = [i for i, p in enumerate(self.tops) if i and p.tables]
        if tails:
            t = tails[-1]
            L.append(f"- 꼬리 박스 후보: 표가 있는 마지막 문단 #{t} — {_deep_text(self.tops[t])[:30]!r}"
                     f"(뒤에 빈 문단 {sum(1 for p in self.tops[t + 1:] if not _deep_text(p).strip())}개)")
        pb = next((i for i, p in enumerate(self.tops) if i and p.page_break), None)
        prefix = next((i for i, p in enumerate(self.tops) if _own_text(p).strip().startswith(("【논술형", "논술형", "서술형"))), None)
        L.append(f"- 지울 구역 시작 후보: 첫 쪽 나눔 문단 {'#' + str(pb) if pb is not None else '없음'} · 논술형/서술형으로 시작하는 문단 "
                 f"{'#' + str(prefix) if prefix is not None else '없음'}")
        return L + [""]


def _deep_text(p) -> str:
    """문단 아래 모든 글(옛 '문단 아래 모든 hp:t의 첫 글')."""
    return _walk(p)


def scan(path: Path) -> str:
    return Form(path).report()


TODO = "TODO"


def draft_kit(path: Path, name: str) -> dict:
    """킷 초안 — 서식에서 사실로 정해지는 값(sha·용지·여백·단)만 채우고, 판단이 필요한 항목은 TODO로 둔다.

    스킬이 해부 보고와 결정표(사용자 확정)로 TODO를 채운다. 채우기 전에는 load_kit이 멈춘다(모르는 값·형식).
    값의 뜻은 skills/exam/references/학교-등록.md와 exam/README.md의 킷 항목 설명.
    """
    f = Form(path)
    size, margins = f.doc.page.size(section=0), f.doc.page.margins(section=0)
    m = {k: getattr(margins, k) for k in ("top", "bottom", "left", "right", "header", "footer")}
    col = _body_columns(f.doc.page.columns(section=0))
    n, gap = col.count, col.gap or 0
    width = (size.width - m["left"] - m["right"] - gap * (n - 1)) // n
    return {
        "kit": name, "version": "0.1.0", "schema": 2,
        "form": {"basename": Path(path).name, "sha256": sha256(path), "note": "서식 파일은 저장소에 넣지 않는다"},
        "page": {"width": size.width, "height": size.height, "margin": m},
        "columns": {"count": n, "gap": gap, "width": width, "body_table_width": TODO},
        "styles": dict.fromkeys(("normal", "number", "choice1", "choice2", "choice3", "choice5", "box_guide", "box"), TODO),
        "number": {"mode": TODO},
        "slots": {}, "slots_removed": [], "placeholders": {}, "text_slots": [], "teacher_cell": None,
        "front_matter": {"required": ["양식", "학년도", "학년", "학기", "차", "과목", "시행", "출제교사"],
                         "optional": ["만점", "논술형", "과목코드", "대상", "인쇄"]},
        "admin": {"paragraph": 0, "delete_tables_with": [], "notice_table_with": TODO, "notice_delete_paras_with": [],
                  "notice_replace": [], "remove_text": []},
        "guidance_text": [], "sample_text": [],
        "trim": {"rule": TODO}, "sample_region": TODO, "remove": {"memos": TODO, "drawings": TODO},
        "leftover_prefix": TODO,
        "boxes": {"보기": TODO, "자료": TODO},
        "set_marker": {"pattern": "^\\[\\d+∼\\d+\\]$", "char_height": TODO, "bold": TODO},
        "typeset": {"score_suffix": " [{points:.1f}점]", "set_head": "[{a}∼{b}]", "text_replace": [["~", "∼"]],
                    "grayscale_pictures": True, "stem_hanging": None, "equation_font": "HancomEQN"},
        "metrics": {"full": TODO, "half": TODO, "space": TODO, "upper": TODO, "char_height": TODO,
                    "line_pitch": {"160": TODO}, "box_extra": TODO, "mark_col": TODO,
                    "note": "실한컴 렌더로 잰다(학교-등록.md: 텍스트 층 글자 간격)"},
        "render": {"glyphs": TODO, "text_fonts": [], "choice_dx": TODO},
        "notice_box_height": None, "box_min_height": None, "code_font": "굴림체",
        "tailbox": {"vertRelTo": "PAPER", "horzRelTo": "PAPER", "horzOffset": m["left"] + (n - 1) * (width + gap),
                    "vertOffset": TODO, "width": TODO, "height": TODO, "outMargin": 0, "room": 980, "match_text": TODO},
    }


def todo_paths(d, prefix: str = "") -> list[str]:
    """킷 초안에 남은 TODO 자리들."""
    if d == TODO:
        return [prefix or "(뿌리)"]
    if isinstance(d, dict):
        return [x for k, v in d.items() for x in todo_paths(v, f"{prefix}.{k}" if prefix else k)]
    if isinstance(d, list):
        return [x for i, v in enumerate(d) for x in todo_paths(v, f"{prefix}[{i}]")]
    return []


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m exam_kit.onboard", description="학교 등록 ① — 빈 원안지 서식 해부")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="서식 hwpx의 사실을 해부 보고(마크다운)로")
    s.add_argument("form", type=Path)
    s.add_argument("--out", type=Path, help="보고서 파일(없으면 표준 출력). 서식이 실학교 문서면 미추적 위치에")
    d = sub.add_parser("draft", help="킷 초안(kit.json) — 사실만 채우고 판단 항목은 TODO")
    d.add_argument("form", type=Path)
    d.add_argument("--name", required=True, help="킷 이름(예: ○○고-원안지)")
    d.add_argument("--out", type=Path, required=True, help="킷 폴더(kits/<이름>)")
    a = ap.parse_args(argv)
    if a.cmd == "draft":
        import json

        kit = draft_kit(a.form, a.name)
        a.out.mkdir(parents=True, exist_ok=True)
        if (a.out / "kit.json").exists():
            raise SystemExit(f"{a.out / 'kit.json'}이 이미 있다 — 덮어쓰지 않는다")
        (a.out / "kit.json").write_text(json.dumps(kit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        todo = todo_paths(kit)
        print(f"wrote {a.out / 'kit.json'} — TODO {len(todo)}곳: {', '.join(todo)}")
        return 0
    text = scan(a.form)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
        print(f"wrote {a.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
