"""지필 원고(문제지·정답키 v3 형식) → 시험지 md v2.

원고 형식: `# Ⅱ. 학생 문제지` 절에 `**N.** 발문 (N.N점)` 머리, 그 아래 `〈보기〉`(뒤에 글이 붙을 수 있다)와
그림·md 표·`~~~` 코드·`- ` 목록, 답지는 한 줄에 하나 또는 한 줄에 여럿(`①…　②…`), 짝짓기형은 첫 열이 ①~⑤인 표.
`# Ⅲ.` 절의 정답 일람 표(`| 정답 |`·`| 배점 |` 행)가 정답·배점이다. 문항 사이 `---`·`[[PAGEBREAK]]`·유의사항은 버린다.

옮김 규칙(제작계획 Task 19 단계 1 표): 머리 → `## N. [N.N점]` + 발문(`**굵게**` 제거, `__밑줄__`은 그대로) ·
`- ㄱ.`~`- ㅁ.` 목록 → `:::보기` · 그 밖의 〈보기〉 내용(글·그림·표·코드·`- ` 목록 글) → `:::자료`(원고 차례대로) ·
`~~~`·```` ``` ```` 코드 → ```` ``` ```` 코드 블록 · 답지 표 → `:::답항표 머리="…"` · 정답 → 답지 앞 `*`.
그림은 `figures`가 있으면 같은 문항 번호(`qNN_`)의 `*_print.png`로 바꾸고 폭은 그 파일의 원래 크기(px ÷ 300dpi)다.

**문항 내용 불변 검사**(`check_invariance`): 문항마다 표기 기호를 걷은 글 줄이 차례까지 원고와 같은지, 정답이 정답 일람과
같은지, 배점이 머리·정답 일람과 같고 합이 만점인지 — 어긋나면 ValueError로 멈춘다. 옮김이 글을 바꾸지 못하게 하는 장치다.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .frontmatter import 조판

원문자 = "①②③④⑤"
_머리 = re.compile(r"^\*\*(?P<n>\d+)\.\*\*\s*(?P<stem>.*?)\s*\((?P<p>\d+\.\d)점\)\s*$")
_보기_표지 = "〈보기〉"
_보기_항목 = re.compile(r"^[ㄱㄴㄷㄹㅁ]\.\s")
_자음_항목 = re.compile(r"^([ㄱ-ㅎ])\.\s")
_그림 = re.compile(r"^!\[[^\]]*\]\((?P<src>[^)]+)\)(?:\{width=(?P<w>[\d.]+)cm\})?\s*$")
_펜스 = re.compile(r"^(?:~~~|```)(?P<lang>\S*)\s*$")
_구분행 = re.compile(r"^\|?(\s*:?-{3,}:?\s*\|)+\s*(:?-{3,}:?\s*)?$")
_답지_나눔 = re.compile(r"(?=[①②③④⑤])")
_굵게 = re.compile(r"\*\*(.+?)\*\*")
_제목 = re.compile(r"(?P<y>\d{4})학년도\s*(?P<s>\d)학기\s*(?P<g>\d)학년\s*「(?P<subj>[^」]+)」\s*(?P<c>\d)차\s*지필")
머리_차례 = ("양식", "학년도", "학년", "학기", "차", "과목", "과목코드", "시행", "대상", "인쇄", "출제교사")


@dataclass
class Item:
    number: int
    points: str
    stem: list[str] = field(default_factory=list)
    jaryo: list[tuple[str, object]] = field(default_factory=list)  # ("글", 줄) | ("그림", (src, w)) | ("표", 줄들) | ("코드", 줄들)
    bogi: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # 〈보기〉 항목 뒤 참고 줄(09-29 결정) — v2에서 :::보기 바로 아래 본문 줄
    choices: list[str] = field(default_factory=list)  # 원문자로 시작하는 답지 글
    table_head: list[str] | None = None  # 짝짓기형 답항표 머리
    source: list[str] = field(default_factory=list)  # 원고 줄(불변 검사용)


# ---- 원고 읽기 ------------------------------------------------------------------

def _section(lines: list[str], mark: str) -> tuple[int, int]:
    """`# Ⅱ.`처럼 mark로 시작하는 `# ` 절의 [시작, 끝) — 없으면 ValueError."""
    start = next((i for i, ln in enumerate(lines) if ln.startswith("# ") and mark in ln), None)
    if start is None:
        raise ValueError(f"원고에 '# {mark}' 절이 없다")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("# ")), len(lines))
    return start + 1, end


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def parse_items(md: str) -> list[Item]:
    """`# Ⅱ.` 학생 문제지 절 → 문항 목록. 귀속시킬 수 없는 줄은 오류(조용히 버리지 않는다).

    문항 안의 차례는 발문 → 〈보기〉 내용(자료 → 〈보기〉 항목 → 참고 줄) → 답지로 고정이다. 참고 줄은 〈보기〉 항목 뒤의
    글 줄로, 빈 줄 뒤이거나 `※`로 시작한다(09-29 결정 — v2에서 :::보기 바로 아래 본문 줄). 이 차례를 벗어난 줄 — 답지나 〈보기〉 항목
    다음에 이어진 줄(두 줄로 접힌 답지·항목), 〈보기〉 항목 뒤의 자료, 답지 뒤의 줄, 〈보기〉 밖의 `ㄱ.` 항목 — 은 옮기면 글이
    제자리를 떠나므로 이어 붙이거나 옮기지 않고 오류로 멈춘다(원고에서 고친다)."""
    lines = md.splitlines()
    a, b = _section(lines, "Ⅱ.")
    items: list[Item] = []
    cur: Item | None = None
    state = "발문"  # 발문 → 자료(〈보기〉 표지나 첫 블록 뒤) → 보기(항목) → 답지
    in_bogi = False  # 〈보기〉 표지를 지났는가
    prev = ""  # 바로 앞 줄의 종류: "답지" · "항목" · "" — 빈 줄이면 ""
    i = a
    while i < b:
        ln = lines[i].rstrip()
        s = ln.strip()
        i += 1
        m = _머리.match(s)
        if m:
            cur = Item(int(m.group("n")), m.group("p"), [_굵게.sub(r"\1", m.group("stem"))], source=[s])
            items.append(cur)
            state, in_bogi, prev = "발문", False, ""
            continue
        if not s or s == "---" or s == "[[PAGEBREAK]]":
            prev = ""
            continue
        if cur is None:
            if s.startswith("**유의사항**"):
                continue
            raise ValueError(f"L{i} 문항 앞의 줄: {s[:30]!r}")
        n = cur.number
        is_choice = s[0] in 원문자
        t_item = s[2:].strip() if s.startswith("- ") else s
        is_item = bool(_보기_항목.match(_굵게.sub(r"\1", t_item)))
        other = _자음_항목.match(_굵게.sub(r"\1", t_item))
        if other and not is_item:
            raise ValueError(f"{n}번 〈보기〉 항목 기호 {other.group(1)}은 지원하지 않는다(ㄱ~ㅁ): {s[:20]!r}")
        if prev == "답지" and not is_choice:
            raise ValueError(f"{n}번 {cur.choices[-1][0]} 다음 줄이 이어진 줄이다 — 원고에서 한 줄로: {s[:20]!r}")
        plain = not (s.startswith(("- ", "|", "![", "~~~", "```", _보기_표지)) or is_choice or is_item)
        is_note = state in ("보기", "주") and plain and (prev == "" or s.startswith("※"))
        if prev == "항목" and not (is_item or is_choice or is_note):
            raise ValueError(f"{n}번 〈보기〉 {cur.bogi[-1][:2]} 다음 줄이 이어진 줄이다 — 원고에서 한 줄로: {s[:20]!r}")
        if state == "답지" and not is_choice:
            raise ValueError(f"{n}번 답지 뒤에 줄이 있다: {s[:20]!r}")
        cur.source.append(s)
        if is_choice:
            for part in _답지_나눔.split(s):
                part = _굵게.sub(r"\1", part.strip().rstrip("　").strip())
                if part:
                    cur.choices.append(part)
            state, prev = "답지", "답지"
            continue
        if is_note:  # 〈보기〉 항목 뒤 참고 줄 — 빈 줄 뒤이거나 ※로 시작해야 한다(바로 붙은 다른 줄은 접힌 항목으로 본다)
            cur.notes.append(_굵게.sub(r"\1", s))
            state, prev = "주", ""
            continue
        if is_item and state == "주":
            raise ValueError(f"{n}번 〈보기〉 항목이 참고 줄 뒤에 있다 — 원고 차례를 〈보기〉 항목 → 참고 줄로: {s[:20]!r}")
        if is_item:
            if not in_bogi:
                raise ValueError(f"{n}번 〈보기〉 표지 밖의 항목: {s[:20]!r}")
            cur.bogi.append(_굵게.sub(r"\1", t_item))
            state, prev = "보기", "항목"
            continue
        if state in ("보기", "주"):
            raise ValueError(f"{n}번 〈보기〉 항목 뒤에 자료가 있다 — 원고 차례를 자료 → 〈보기〉 항목으로(항목 뒤에는 참고 줄만): {s[:20]!r}")
        prev = ""
        fm = _펜스.match(s)
        if fm:  # 코드 — 닫는 펜스까지 줄 그대로(앞 공백 포함)
            code = []
            while i < b and not _펜스.match(lines[i].strip()):
                code.append(lines[i].rstrip())
                cur.source.append(lines[i].strip())
                i += 1
            if i >= b:
                raise ValueError(f"{n}번 닫히지 않은 코드 펜스")
            cur.source.append(lines[i].strip())
            i += 1
            cur.jaryo.append(("코드", code))
            state = "자료"
            continue
        if s.startswith(_보기_표지):
            in_bogi, state = True, "자료"
            rest = s[len(_보기_표지):].strip()
            if rest:
                cur.jaryo.append(("글", _굵게.sub(r"\1", rest)))
            continue
        gm = _그림.match(s)
        if gm:
            cur.jaryo.append(("그림", (gm.group("src"), gm.group("w"))))
            state = "자료"
            continue
        if s.startswith("|"):
            rows = [s]
            while i < b and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                cur.source.append(lines[i].strip())
                i += 1
            rows = [_굵게.sub(r"\1", r) for r in rows]
            body = [r for r in rows[1:] if not _구분행.match(r)]
            if body and all(_cells(r)[0] in 원문자 for r in body):  # 첫 열이 원문자 = 짝짓기형 답지 표
                if [_cells(r)[0] for r in body] != list(원문자):
                    raise ValueError(f"{n}번 답지 표의 원문자가 ①~⑤ 차례가 아니다")
                cur.table_head = _cells(rows[0])[1:]
                cur.choices = [f"{_cells(r)[0]} " + " | ".join(_cells(r)[1:]) for r in body]
                state = "답지"
            else:
                cur.jaryo.append(("표", rows))
                state = "자료"
            continue
        t = _굵게.sub(r"\1", t_item)
        if state == "발문" and not s.startswith("- "):
            cur.stem.append(t)
        else:
            cur.jaryo.append(("글", t))
            state = "자료"
    for it in items:
        marks = [c[0] for c in it.choices]
        if marks != list(원문자):
            raise ValueError(f"{it.number}번 답지 {''.join(marks)!r} — ①~⑤ 다섯 개여야 한다")
    return items


_해설 = re.compile(r"^(?P<n>\d+)\.\s*\*\*(?P<a>[①②③④⑤])\*\*")


def parse_explained(md: str) -> dict[int, str]:
    """`# Ⅲ.` 절 해설 줄 `N. **③** …`의 정답 — 있으면 정답 일람과 대조한다."""
    lines = md.splitlines()
    a, b = _section(lines, "Ⅲ.")
    out = {}
    for ln in lines[a:b]:
        m = _해설.match(ln.strip())
        if m:
            out[int(m.group("n"))] = m.group("a")
    return out


def parse_key(md: str) -> tuple[dict[int, str], dict[int, str]]:
    """`# Ⅲ.` 절의 정답 일람 표 → ({문항: 원문자}, {문항: 배점})."""
    lines = md.splitlines()
    a, b = _section(lines, "Ⅲ.")
    rows = {}
    for ln in lines[a:b]:
        s = ln.strip()
        if s.startswith("|") and not _구분행.match(s):
            c = _cells(s)
            rows[c[0]] = c[1:]
    if "문항" not in rows or "정답" not in rows:
        raise ValueError("정답 일람 표(| 문항 | … · | 정답 | …)가 없다")
    nums = [int(x) for x in rows["문항"]]
    answers = dict(zip(nums, rows["정답"]))
    points = dict(zip(nums, rows.get("배점", [])))
    return answers, points


# ---- 머리(front-matter) --------------------------------------------------------

def front_matter(md: str, given: dict[str, str]) -> dict[str, str]:
    """원고 제목에서 학년도·학기·학년·과목·차를, 나머지는 given에서. 미정 슬롯은 자리표시(초안)."""
    title = next((ln for ln in md.splitlines() if ln.startswith("# ")), "")
    m = _제목.search(title)
    out: dict[str, str] = {}  # 양식(킷 이름)은 given에서 — main은 --kit의 킷 이름을 넣는다
    if m:
        out.update(학년도=m.group("y"), 학기=m.group("s"), 학년=m.group("g"), 과목=m.group("subj").strip(), 차=m.group("c"))
    학년 = given.get("학년", out.get("학년", "_"))
    out.update(시행="__.__.(_) _교시", 대상=f"{학년}학년 _반~_반", 인쇄="__매 * _묶음")
    out.update(given)
    missing = [k for k in 머리_차례 if not out.get(k)]
    if missing:
        raise ValueError(f"머리 값이 없다: {missing} — --front 키=값으로 준다")
    unknown = set(out) - set(머리_차례) - {"만점", *조판}
    if unknown:
        raise ValueError(f"모르는 머리 키: {sorted(unknown)}")
    return out


# ---- 쓰기 ------------------------------------------------------------------------

def _figure_line(src: str, w: str | None, number: int, figures: Path | None, out_dir: Path) -> str:
    if figures is None:
        return f"![]({src})" + (f"{{width={w}cm}}" if w else "")
    from PIL import Image

    from .compose import natural_width_cm

    tag = f"q{number:02d}_"
    found = sorted(p for p in Path(figures).glob("*_print.png") if tag in p.name)
    if len(found) != 1:
        raise ValueError(f"{number}번 그림: {figures}에 '{tag}…_print.png'가 {len(found)}개다(하나여야 한다)")
    with Image.open(found[0]) as im:
        cm = natural_width_cm(im.width)
    rel = os.path.relpath(found[0], out_dir)
    return f"![]({rel}){{width={cm:.1f}cm}}"


def render_md(items: list[Item], answers: dict[int, str], front: dict[str, str], *,
              figures: Path | None = None, out_dir: Path = Path(".")) -> str:
    if figures is not None:
        for it in items:
            k = sum(1 for kind, _ in it.jaryo if kind == "그림")
            if k > 1:
                raise ValueError(f"{it.number}번 그림이 {k}장 — --figures는 문항당 한 장만 바꾼다(qNN_ 한 파일). 그림을 합치거나 --figures 없이 옮긴다")
    out = (["---"] + [f"{k}: {front[k]}" for k in 머리_차례] + ([f"만점: {front['만점']}"] if "만점" in front else [])
           + [f"{k}: {front[k]}" for k in 조판 if k in front] + ["---", ""])
    for it in items:
        ans = answers.get(it.number)
        if ans not in 원문자:
            raise ValueError(f"{it.number}번 정답이 정답 일람에 없다: {ans!r}")
        out.append(f"## {it.number}. [{it.points}점]")
        out.append(" ".join(it.stem))
        out.append("")
        if it.jaryo:
            out.append(":::자료")
            for kind, v in it.jaryo:
                if kind == "글":
                    out.append(v)
                elif kind == "그림":
                    out.append(_figure_line(v[0], v[1], it.number, figures, out_dir))
                elif kind == "표":
                    out.extend(v)
                else:
                    out += ["```", *v, "```"]
            out += [":::", ""]
        if it.bogi:
            out += [":::보기", *it.bogi, ":::", *it.notes, ""]
        choices = [("*" if c[0] == ans else "") + c for c in it.choices]
        if it.table_head is not None:
            out += [f':::답항표 머리="{"|".join(it.table_head)}"', *choices, ":::", ""]
        else:
            out += [*choices, ""]
    return "\n".join(out).rstrip("\n") + "\n"


# ---- 문항 내용 불변 검사 ----------------------------------------------------------

def _norm_lines(lines: list[str], *, v2: bool) -> list[str]:
    """표기 기호를 걷은 글 줄들 — 공백·`**`·`__`·`|`·목록 표지·펜스·표 구분행·그림 줄·머리 번호/배점·정답 `*`를 뺀다.
    답지는 원문자마다 한 줄로 나눈다(원고의 한 줄 여러 답지와 v2의 한 줄 하나를 같게 본다)."""
    out = []
    for ln in lines:
        s = ln.strip()
        if not s or _구분행.match(s) or _펜스.match(s) or _그림.match(s) or s in ("---", "[[PAGEBREAK]]"):
            continue
        if v2:
            if s.startswith("## "):
                continue
            if s.startswith(":::답항표"):
                s = re.sub(r'^:::답항표\s+머리="(.*)"$', r"\1", s)
            elif s.startswith(":::"):
                continue
            s = re.sub(r"^\*(?=[①②③④⑤])", "", s)
        else:
            m = _머리.match(s)
            if m:
                s = m.group("stem")
            if s.startswith(_보기_표지):
                s = s[len(_보기_표지):]
            if s.startswith("- "):
                s = s[2:]
        for part in _답지_나눔.split(s):
            t = re.sub(r"\s+", "", part.replace("**", "").replace("__", "").replace("|", ""))
            if t:
                out.append(t)
    return out


def split_v2(md: str) -> dict[int, list[str]]:
    """v2 md → {문항 번호: 줄들}(머리 줄 포함)."""
    out: dict[int, list[str]] = {}
    cur = None
    body = md.split("\n---\n", 1)[1] if md.startswith("---") else md
    for ln in body.splitlines():
        m = re.match(r"^##\s+(\d+)\.", ln)
        if m:
            cur = int(m.group(1))
            out[cur] = []
        if cur is not None:
            out[cur].append(ln)
    return out


def check_invariance(items: list[Item], answers: dict[int, str], key_points: dict[int, str], v2_md: str,
                     *, full: float = 100.0) -> list[str]:
    """변환 전후 문항 내용 불변 — 어긋남 목록(빈 목록이면 통과). 글(차례까지)·정답·배점·그림 수."""
    from .scan import scan_markdown

    bad: list[str] = []
    parts = split_v2(v2_md)
    if sorted(parts) != [it.number for it in items]:
        bad.append(f"문항 번호 {sorted(parts)} ≠ 원고 {[it.number for it in items]}")
    for it in items:
        mine = _norm_lines(parts.get(it.number, []), v2=True)
        # 발문이 여러 줄이면 결과는 한 줄로 잇는다(render_md) — 원고 쪽도 이어서 본다
        theirs = _norm_lines([" ".join(it.stem)] + it.source[len(it.stem):], v2=False)
        if mine != theirs:  # 차례까지 — 원고 차례(발문 → 자료 → 〈보기〉 항목 → 답지)가 곧 결과 차례다
            k = next((j for j, (x, y) in enumerate(zip(mine, theirs)) if x != y), min(len(mine), len(theirs)))
            bad.append(f"{it.number}번 글이 다르다 — {k + 1}번째 줄부터(결과 {len(mine)}줄 · 원고 {len(theirs)}줄, 차례까지 본다)")
        n_src = sum(1 for s in it.source if _그림.match(s))
        n_out = sum(1 for s in parts.get(it.number, []) if _그림.match(s.strip()))
        if n_src != n_out:
            bad.append(f"{it.number}번 그림 {n_out}장 ≠ 원고 {n_src}장")
    s = scan_markdown(v2_md)
    if s.errors:
        bad.append(f"변환 결과 문법 오류 {len(s.errors)}개: {[e.reason for e in s.errors[:3]]}")
    got = {int(q.number): next((c.mark for c in q.choices if c.correct), None) for q in s.questions}
    for n, a in answers.items():
        if got.get(n) != a:
            bad.append(f"{n}번 정답 {got.get(n)} ≠ 정답 일람 {a}")
    pts = {int(q.number): q.points for q in s.questions}
    for it in items:
        kp = key_points.get(it.number) if key_points else None
        if kp is not None and float(kp) != float(it.points):
            bad.append(f"{it.number}번 배점: 머리 {it.points} ≠ 정답 일람 {key_points[it.number]}")
        if pts.get(it.number) != float(it.points):
            bad.append(f"{it.number}번 배점 {pts.get(it.number)} ≠ 원고 {it.points}")
    total = sum(float(it.points) for it in items)
    if abs(total - full) > 1e-9:
        bad.append(f"배점 합 {total:.1f} ≠ 만점 {full:.1f}")
    return bad


def convert(md: str, *, front: dict[str, str] | None = None, figures: Path | None = None,
            out_dir: Path = Path(".")) -> str:
    """원고 → v2 md. 불변 검사가 어긋나면 ValueError(목록)."""
    items = parse_items(md)
    answers, key_points = parse_key(md)
    missing = sorted(set(it.number for it in items) - set(answers))
    if missing:
        raise ValueError(f"정답 일람에 없는 문항: {missing}")
    odd = {n: (a, answers.get(n)) for n, a in parse_explained(md).items() if answers.get(n) != a}
    if odd:
        raise ValueError(f"해설의 정답이 정답 일람과 다르다: {', '.join(f'{n}번 해설 {a} ≠ 일람 {k}' for n, (a, k) in sorted(odd.items()))}")
    fm = front_matter(md, dict(front or {}))
    out = render_md(items, answers, fm, figures=figures, out_dir=out_dir)
    bad = check_invariance(items, answers, key_points, out, full=float(fm.get("만점", 100)))
    if bad:
        raise ValueError("문항 내용 불변 검사 실패:\n  " + "\n  ".join(bad))
    return out


def _front_args(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for v in values:
        p = Path(v)
        if p.is_file():
            for ln in p.read_text(encoding="utf-8").splitlines():
                if ":" in ln and ln.strip() and not ln.strip().startswith("#"):
                    k, val = ln.split(":", 1)
                    out[k.strip()] = val.strip()
        elif "=" in v:
            k, val = v.split("=", 1)
            out[k.strip()] = val.strip()
        else:
            raise ValueError(f"--front 값은 '키=값' 또는 '키: 값' 줄의 파일이다: {v!r}")
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .lint import errors, lint

    ap = argparse.ArgumentParser(prog="python -m exam_kit.convert",
                                 description="지필 원고(문제지·정답키) → 시험지 md v2 + 문항 내용 불변 검사")
    ap.add_argument("md", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="v2 md 경로(실문항이면 지필평가/ 아래)")
    ap.add_argument("--figures", type=Path, help="인쇄 규격 그림 폴더 — 같은 문항 번호(qNN_)의 *_print.png로 바꾼다")
    ap.add_argument("--front", nargs="*", default=[], help="머리 값: 키=값 … 또는 '키: 값' 줄의 파일(과목코드·출제교사 등)")
    ap.add_argument("--kit", type=Path, help="학교 킷 — 변환 뒤 그 킷의 학교 규칙(rules.json)도 검사한다. 없으면 엔진 규칙만")
    a = ap.parse_args(argv)
    out = a.out.resolve()
    given = _front_args(a.front)
    if a.kit and "양식" not in given:
        from .kit import load_kit as _load

        given["양식"] = _load(a.kit).name
    md = convert(a.md.read_text(encoding="utf-8"), front=given,
                 figures=a.figures.resolve() if a.figures else None, out_dir=out.parent)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    rules = None
    if a.kit:
        from .kit import load_kit

        rules = load_kit(a.kit).rules
    vs = lint(md, md_dir=out.parent, rules=rules)
    n_err = len(errors(vs))
    print(f"wrote {out} — 문항 {len(split_v2(md))} · 불변 검사 통과 · 규칙 검사 오류 {n_err} · 경고 {len(vs) - n_err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
