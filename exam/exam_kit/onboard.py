"""학교 등록 ① 해부 — 빈 원안지 서식 hwpx의 사실을 모아 보고서(마크다운)로 낸다.

판단은 하지 않는다: 어느 스타일이 문항인지, 무슨 글이 지울 안내인지는 스킬이 이 보고서와 서식 렌더를 읽고
결정표로 사용자에게 묻는다(헌법 2 — 두뇌는 스킬, 파이썬은 손). 여기서 내는 '후보'는 구조에서 곧바로 보이는 것뿐이다.

    uv run python -m exam_kit.onboard scan <서식.hwpx> [--out 해부.md]
"""

from __future__ import annotations

import re
import zipfile
from collections import Counter
from pathlib import Path

import lxml.etree as ET

from .kit import sha256

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"
_그리기 = ("line", "rect", "ellipse", "arc", "polygon", "curve", "connectLine")


def _own_text(p) -> str:
    """문단 자신의 글(표·메모·머리말 안 글은 뺀다)."""
    return "".join(t.text or "" for r in p.findall(HP + "run") for t in r.findall(HP + "t"))


def _all_text(el) -> str:
    return "".join(t.text or "" for t in el.iter(HP + "t"))


def _case(el, tag):
    """hp:switch의 case 분기 값(없으면 첫 값) — 양식 paraPr 치수는 case가 실제 조판 값이다."""
    for sw in el.iter(HP + "switch"):
        c = sw.find(HP + "case")
        if c is not None and c.find(".//" + HH + tag) is not None:
            return c.find(".//" + HH + tag)
    return el.find(".//" + HH + tag)


class Form:
    def __init__(self, path: Path):
        self.path = Path(path)
        z = zipfile.ZipFile(self.path)
        self.head = ET.fromstring(z.read("Contents/header.xml"))
        self.sec = ET.fromstring(z.read("Contents/section0.xml"))
        self.tops = self.sec.findall(HP + "p")
        self.fonts = {f.get("id"): f.get("face") for ff in self.head.iter(HH + "fontface") if ff.get("lang") == "HANGUL"
                      for f in ff.iter(HH + "font")}
        self.char = {c.get("id"): c for c in self.head.iter(HH + "charPr")}
        self.para = {p.get("id"): p for p in self.head.iter(HH + "paraPr")}
        self.tabs = {t.get("id"): t for t in self.head.iter(HH + "tabPr")}
        self.styles = {s.get("id"): s for s in self.head.iter(HH + "style")}

    # ---- 글자 모양 ----
    def char_desc(self, cid: str | None) -> str:
        c = self.char.get(cid)
        if c is None:
            return "?"
        fr, ratio, sp = c.find(HH + "fontRef"), c.find(HH + "ratio"), c.find(HH + "spacing")
        bits = [f"{self.fonts.get(fr.get('hangul')) if fr is not None else '?'} {int(c.get('height')) / 100:g}pt",
                f"장평 {ratio.get('hangul') if ratio is not None else '?'}", f"자간 {sp.get('hangul') if sp is not None else '?'}"]
        if c.find(HH + "bold") is not None:
            bits.append("굵게")
        col = c.get("textColor")
        if col and col.upper() not in ("#000000",):
            bits.append(f"색 {col}")
        return " · ".join(bits)

    def color(self, cid: str | None) -> str | None:
        c = self.char.get(cid)
        col = None if c is None else (c.get("textColor") or "").upper()
        return None if not col or col == "#000000" else col

    # ---- 보고 ----
    def report(self) -> str:
        L: list[str] = [f"# 서식 해부 — {self.path.name}", "",
                        "> 사실만 적는다. 역할·지울 대상 판단은 스킬이 결정표로 사용자에게 묻는다.", ""]
        L += self._page() + self._style_table() + self._fields() + self._memos() + self._drawings()
        L += self._header_footer() + self._paragraphs() + self._tables() + self._hints()
        return "\n".join(L) + "\n"

    def _page(self) -> list[str]:
        pp = self.sec.find(f".//{HP}secPr/{HP}pagePr")
        m = pp.find(HP + "margin")
        col = self.sec.find(f".//{HP}colPr")
        return ["## 용지·단", f"- sha256 `{sha256(self.path)}`",
                f"- 용지 {pp.get('width')} × {pp.get('height')} (landscape 속성 `{pp.get('landscape')}`)",
                "- 여백 " + " · ".join(f"{k} {m.get(k)}" for k in ("left", "right", "top", "bottom", "header", "footer")),
                f"- 단 {col.get('colCount')}단 {col.get('type')} · 단 사이 {col.get('sameGap')}" if col is not None else "- 단 정보 없음",
                f"- 한글 글꼴: {', '.join(self.fonts.values())}", ""]

    def _style_table(self) -> list[str]:
        L = ["## 스타일", "| id | 이름 | 글자 | 줄간격 | 왼여백 | 내어쓰기 | 탭(case) | 자동번호 | 본문 사용 |", "|---|---|---|---|---|---|---|---|---|"]
        used = Counter(p.get("styleIDRef") for p in self.sec.iter(HP + "p"))
        for sid, s in self.styles.items():
            p = self.para.get(s.get("paraPrIDRef"))
            ls = None if p is None else _case(p, "lineSpacing")
            mg = None if p is None else _case(p, "margin")
            left = None if mg is None else mg.find(HC + "left")
            ind = None if mg is None else mg.find(HC + "intent")
            head = None if p is None else p.find(HH + "heading")
            tab = None if p is None else self.tabs.get(p.get("tabPrIDRef"))
            tabs = [] if tab is None else [i.get("pos") for sw in tab.iter(HP + "switch") for c in sw.findall(HP + "case")
                                           for i in c.findall(HH + "tabItem")] or [i.get("pos") for i in tab.iter(HH + "tabItem")]
            L.append(f"| {sid} | {s.get('name')} | {self.char_desc(s.get('charPrIDRef'))} | "
                     f"{'' if ls is None else ls.get('value') + ls.get('type', '')[:3]} | {'' if left is None else left.get('value')} | "
                     f"{'' if ind is None else ind.get('value')} | {' '.join(tabs[:6])} | "
                     f"{'NUMBER' if head is not None and head.get('type') == 'NUMBER' else ''} | {used.get(sid, 0)} |")
        return L + [""]

    def _fields(self) -> list[str]:
        fs = [f for f in self.sec.iter(HP + "fieldBegin") if f.get("type") == "CLICK_HERE"]
        L = [f"## 누름틀 {len(fs)}개"]
        for f in fs:
            L.append(f"- id `{f.get('id')}` 이름 {f.get('name')!r} — 둘러싼 문단 글 {_own_text(self._owner_p(f))[:40]!r}")
        return L + [""]

    def _owner_p(self, el):
        while el is not None and el.tag != HP + "p":
            el = el.getparent()
        return el

    def _memos(self) -> list[str]:
        ms = [f for f in self.sec.iter(HP + "fieldBegin") if f.get("type") == "MEMO"]
        L = [f"## 메모 {len(ms)}개 (글자 안 MEMO 필드)"]
        for f in ms:
            L.append(f"- {re.sub(r'\\s+', ' ', _all_text(f)).strip()[:120]}")
        return L + [""]

    def _drawings(self) -> list[str]:
        c = Counter(e.tag.split("}")[1] for e in self.sec.iter() if e.tag.split("}")[1] in _그리기)
        return ["## 그리기 개체", "- " + (", ".join(f"{k} {v}" for k, v in c.items()) or "없음"), ""]

    def _header_footer(self) -> list[str]:
        L = ["## 머리말·꼬리말"]
        for tag in ("header", "footer"):
            for i, h in enumerate(self.sec.iter(HP + tag)):
                auto = [a.get("numType") for a in h.iter(HP + "autoNum")]
                L.append(f"- {tag}{i} ({h.get('applyPageType')}): {_all_text(h)[:60]!r} 자동 번호 {auto}")
        return L + [""]

    def _paragraphs(self) -> list[str]:
        L = ["## 최상위 문단", "| # | 스타일 | 나눔 | 표 | 색 글자 | 글 |", "|---|---|---|---|---|---|"]
        for i, p in enumerate(self.tops):
            text = _own_text(p).strip()
            tbls = [f"{t.get('rowCnt')}×{t.get('colCnt')}" for t in p.iter(HP + "tbl")]
            colors = sorted({c for r in p.findall(HP + "run") for c in [self.color(r.get("charPrIDRef"))]
                             if c and "".join(t.text or "" for t in r.findall(HP + "t")).strip()})
            brk = "쪽" if p.get("pageBreak") == "1" else "단" if p.get("columnBreak") == "1" else ""
            if not (text or tbls or brk):
                continue
            style = self.styles.get(p.get("styleIDRef"))
            L.append(f"| {i} | {'' if style is None else style.get('name')} | {brk} | {' '.join(tbls[:4])} | "
                     f"{' '.join(colors)} | {text[:50].replace('|', '/')} |")
        return L + [""]

    def _tables(self) -> list[str]:
        L = ["## 표(최상위 문단의)", "| 문단 | 모양 | 크기 | 글자처럼 | 칸 수 | 안 문단 스타일 | 글 앞부분 |", "|---|---|---|---|---|---|---|"]
        for i, p in enumerate(self.tops):
            for t in p.findall(f"{HP}run/{HP}tbl"):
                sz, pos = t.find(HP + "sz"), t.find(HP + "pos")
                inner = Counter(self.styles[q.get("styleIDRef")].get("name") for q in t.iter(HP + "p")
                                if q.get("styleIDRef") in self.styles)
                L.append(f"| {i} | {t.get('rowCnt')}×{t.get('colCnt')} | {sz.get('width')}×{sz.get('height')} | "
                         f"{pos.get('treatAsChar')} | {len(list(t.iter(HP + 'tc')))} | "
                         f"{', '.join(f'{k} {v}' for k, v in inner.most_common(3))} | {_all_text(t)[:30].replace('|', '/')} |")
        return L + [""]

    def _hints(self) -> list[str]:
        L = ["## 구조에서 바로 보이는 후보(판단 아님)"]
        nums = [s.get("name") for s in self.styles.values() if (p := self.para.get(s.get("paraPrIDRef"))) is not None
                and (h := p.find(HH + "heading")) is not None and h.get("type") == "NUMBER"]
        literal = [i for i, p in enumerate(self.tops) if re.match(r"^\d{1,3}\.\s?$", next(
            (x for r in p.findall(HP + "run") for x in ["".join(t.text or "" for t in r.findall(HP + "t"))] if x), ""))]
        L.append(f"- 문항 번호: 자동번호 스타일 {nums or '없음'} · 글자 번호로 시작하는 문단 {len(literal)}개"
                 f" → number.mode 후보 {'autonumber' if nums else 'literal' if literal else '?'}")
        tails = [i for i, p in enumerate(self.tops) if i and p.findall(f"{HP}run/{HP}tbl")]
        if tails:
            t = tails[-1]
            L.append(f"- 꼬리 박스 후보: 표가 있는 마지막 문단 #{t} — {_all_text(self.tops[t])[:30]!r}"
                     f"(뒤에 빈 문단 {sum(1 for p in self.tops[t + 1:] if not _all_text(p).strip())}개)")
        pb = next((i for i, p in enumerate(self.tops) if i and p.get("pageBreak") == "1"), None)
        prefix = next((i for i, p in enumerate(self.tops) if _own_text(p).strip().startswith(("【논술형", "논술형", "서술형"))), None)
        L.append(f"- 지울 구역 시작 후보: 첫 쪽 나눔 문단 {'#' + str(pb) if pb is not None else '없음'} · 논술형/서술형으로 시작하는 문단 "
                 f"{'#' + str(prefix) if prefix is not None else '없음'}")
        return L + [""]


def scan(path: Path) -> str:
    return Form(path).report()


TODO = "TODO"


def draft_kit(path: Path, name: str) -> dict:
    """킷 초안 — 서식에서 사실로 정해지는 값(sha·용지·여백·단)만 채우고, 판단이 필요한 항목은 TODO로 둔다.

    스킬이 해부 보고와 결정표(사용자 확정)로 TODO를 채운다. 채우기 전에는 load_kit이 멈춘다(모르는 값·형식).
    값의 뜻은 skills/exam/references/학교-등록.md와 exam/README.md의 킷 항목 설명.
    """
    f = Form(path)
    pp = f.sec.find(f".//{HP}secPr/{HP}pagePr")
    m = {k: int(pp.find(HP + "margin").get(k)) for k in ("top", "bottom", "left", "right", "header", "footer")}
    col = f.sec.find(f".//{HP}colPr")
    n, gap = int(col.get("colCount")), int(col.get("sameGap") or 0)
    width = (int(pp.get("width")) - m["left"] - m["right"] - gap * (n - 1)) // n
    return {
        "kit": name, "version": "0.1.0", "schema": 2,
        "form": {"basename": Path(path).name, "sha256": sha256(path), "note": "서식 파일은 저장소에 넣지 않는다"},
        "page": {"width": int(pp.get("width")), "height": int(pp.get("height")), "margin": m},
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
                    "grayscale_pictures": True, "stem_hanging": None},
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
