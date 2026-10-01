"""md v2 스캐너 — 검사 전용 IR. 조판 IR은 upstream(office/exam)이 만든다."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .equation import split_pipes
from .frontmatter import FrontMatter, parse_front_matter

_배점 = r"(?:\[(?P<p1>\d+\.\d)점\]|\((?P<p2>\d+)점\)|\[[^\]]*\])?"
_덮 = r"(?P<opts>(?:\s*\{[^{}]*\})*)"  # 문항 지시: {답항=N행} · {단나눔} · {쪽나눔}(Task 29) — _지시가 푼다
_지시_답항 = re.compile(r"^답항=(1행|2행|3행|5행)$")
나눔_지시 = {"단나눔": "column", "쪽나눔": "page"}
Q_RE = re.compile(r"^##\s+(?P<n>\d+)\.\s*" + _배점 + _덮 + r"\s*$")
SET_RE = re.compile(r"^##\s+(?P<a>\d+)\s*[~∼]\s*(?P<b>\d+)\.\s*세트\s*$")
MEMBER_RE = re.compile(r"^###\s+(?P<n>\d+)\.\s*" + _배점 + _덮 + r"\s*$")
CHOICE_RE = re.compile(r"^(?P<star>\*?)(?P<mark>[①②③④⑤])\s*(?P<t>.*)$")
FENCE_OPEN_RE = re.compile(r"^:::(?P<name>\S+)(?:\s+(?P<attrs>.*))?$")
FENCE_CLOSE_RE = re.compile(r"^:::\s*$")
CODE_FENCE_RE = re.compile(r"^```(?P<lang>\S*)\s*$")  # 코드 블록(Task 30) — 문항·세트 블록으로, 또는 :::자료 안에서
IMG_RE = re.compile(r"^!\[\]\((?P<src>[^)]+)\)(?:\{width=(?P<w>[\d.]+)cm\})?\s*$")
TABLE_ROW_RE = re.compile(r"^\|.*\|\s*$")
_ATTR_RE = re.compile(r'(\w+)=(?:"([^"]*)"|(\S+))')
펜스_이름 = ("자료", "보기", "조건", "답항표", "그림")  # 조건: 〈조건〉 박스(학교 B 결정표 29) — 킷에 견본이 있어야 조판된다


@dataclass(frozen=True)
class Choice:
    mark: str
    text: str
    correct: bool
    line_no: int


@dataclass(frozen=True)
class Block:
    kind: str
    lines: tuple[str, ...]
    attrs: dict
    line_no: int


@dataclass(frozen=True)
class Question:
    number: str
    points: float | None
    points_raw: str | None
    override: str | None
    stem: tuple[str, ...]
    blocks: tuple[Block, ...]
    choices: tuple[Choice, ...]
    line_no: int
    set_rng: tuple[str, str] | None = None
    brk: str | None = None  # 나눔 지시 — "column"({단나눔}) · "page"({쪽나눔}): 이 문항 묶음이 새 단·새 쪽에서 시작한다


@dataclass(frozen=True)
class QuestionSet:
    rng: tuple[str, str]
    passage: tuple[str, ...]
    blocks: tuple[Block, ...]
    line_no: int


@dataclass(frozen=True)
class ScanError:
    line_no: int
    text: str
    reason: str


@dataclass(frozen=True)
class Scan:
    front: FrontMatter
    questions: tuple[Question, ...]
    sets: tuple[QuestionSet, ...]
    errors: tuple[ScanError, ...]


def _attrs(s: str | None) -> dict:
    out: dict = {}
    for k, v1, v2 in _ATTR_RE.findall(s or ""):
        v = v1 if v1 != "" else v2
        out[k] = split_pipes(v) if k == "머리" else v  # 수식 `$…$` 안의 `|`로는 나누지 않는다
    return out


class _Buf:
    def __init__(self, number: str, m: re.Match, line_no: int, set_rng=None):
        self.number = number
        p1, p2 = m.group("p1"), m.group("p2")
        self.points = float(p1) if p1 else (float(p2) if p2 else None)
        self.points_raw = f"[{p1}점]" if p1 else (f"({p2}점)" if p2 else None)
        self.override, self.brk, self.bad = None, None, []
        for opt in re.findall(r"\{([^{}]*)\}", m.group("opts") or ""):
            opt = opt.strip()
            ov = _지시_답항.match(opt)
            if ov and self.override is None:
                self.override = ov.group(1)
            elif opt in 나눔_지시 and self.brk is None:
                self.brk = 나눔_지시[opt]
            else:
                self.bad.append(opt)
        self.line_no = line_no
        self.set_rng = set_rng
        self.stem: list[str] = []
        self.blocks: list[Block] = []
        self.choices: list[Choice] = []

    def freeze(self) -> Question:
        return Question(self.number, self.points, self.points_raw, self.override, tuple(self.stem),
                        tuple(self.blocks), tuple(self.choices), self.line_no, self.set_rng, self.brk)


def scan_markdown(md: str, front_schema: dict | None = None) -> Scan:
    """front_schema = 킷 front_matter(필수·선택 키) — 없으면 기본 필수만."""
    front, body = parse_front_matter(md, front_schema)
    lines = body.splitlines()
    offset = len(md.splitlines()) - len(lines)  # front-matter가 차지한 줄 수 → 오류 줄 번호는 원문 기준
    errors: list[ScanError] = []
    questions: list[Question] = []
    sets: list[QuestionSet] = []
    cur: _Buf | None = None
    set_open: dict | None = None  # {"rng","passage","blocks","line_no"}
    fence: dict | None = None    # {"kind","attrs","lines","line_no"}
    table: list[str] | None = None
    table_line = 0

    def err(i: int, text: str, reason: str) -> None:
        errors.append(ScanError(i + offset + 1, text, reason))

    def target_blocks() -> list[Block] | None:
        if cur is not None:
            return cur.blocks
        if set_open is not None:
            return set_open["blocks"]
        return None

    def flush_table() -> None:
        nonlocal table
        if table:
            tb = target_blocks()
            if tb is not None:
                tb.append(Block("표", tuple(table), {}, table_line))
            else:
                errors.append(ScanError(table_line, table[0], "문항 앞에 표가 있다"))
        table = None

    def flush_q() -> None:
        nonlocal cur
        if cur is not None:
            questions.append(cur.freeze())
            cur = None

    def flush_set() -> None:
        nonlocal set_open
        if set_open is not None:
            sets.append(QuestionSet(set_open["rng"], tuple(set_open["passage"]), tuple(set_open["blocks"]), set_open["line_no"]))
            set_open = None

    code: dict | None = None  # 문항·세트 블록인 ``` 코드 블록 {"lines","lang","line_no"}
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if code is not None:  # 코드 안의 줄은 그대로(앞 공백·빈 줄 포함) — 다른 문법으로 읽지 않는다
            if CODE_FENCE_RE.match(line.strip()) and not line.strip()[3:]:
                tb = target_blocks()
                if tb is not None:
                    tb.append(Block("코드", tuple(code["lines"]), {"lang": code["lang"]}, code["line_no"]))
                code = None
            else:
                code["lines"].append(line)
            continue
        if fence is not None:
            if fence.get("in_code"):  # :::자료 안의 ``` — 빈 줄까지 그대로 싣는다(여는·닫는 줄도 싣어 compose가 가른다)
                fence["lines"].append(line)
                fence["line_nos"].append(i + offset + 1)
                if line.strip() == "```":
                    fence["in_code"] = False
                continue
            if CODE_FENCE_RE.match(line.strip()):
                fence["lines"].append(line)
                fence["line_nos"].append(i + offset + 1)
                fence["in_code"] = True
                continue
            if FENCE_CLOSE_RE.match(line):
                kind = fence["kind"]
                if kind == "답항표":
                    for ln, lno in zip(fence["lines"], fence["line_nos"]):
                        m = CHOICE_RE.match(ln.strip())
                        if m and cur is not None:
                            cur.choices.append(Choice(m.group("mark"), m.group("t").strip(), m.group("star") == "*", lno))
                tb = target_blocks()
                if tb is not None:
                    tb.append(Block(kind, tuple(fence["lines"]), fence["attrs"], fence["line_no"]))
                fence = None
            elif line.strip():
                fence["lines"].append(line)
                fence["line_nos"].append(i + offset + 1)
            continue
        m = CODE_FENCE_RE.match(line.strip())
        if m:
            flush_table()
            if cur is None and set_open is None:
                err(i, line, "문항 앞에 코드 블록이 있다")
            code = {"lines": [], "lang": m.group("lang"), "line_no": i + offset + 1}
            continue
        if not line.strip():
            flush_table()
            continue
        if TABLE_ROW_RE.match(line):
            if table is None:
                table, table_line = [], i + offset + 1
            table.append(line)
            continue
        flush_table()
        m = SET_RE.match(line)
        if m:
            flush_q(); flush_set()
            set_open = {"rng": (m.group("a"), m.group("b")), "passage": [], "blocks": [], "line_no": i + offset + 1}
            continue
        m = MEMBER_RE.match(line)
        if m:
            if set_open is None:
                err(i, line, "'### N.' 문항이 세트 밖에 있다")
                continue
            flush_q()
            cur = _Buf(m.group("n"), m, i + offset + 1, set_open["rng"])
            for opt in cur.bad:
                err(i, line, f"모르는 문항 지시 {{{opt}}}(겹친 지시 포함) — {{답항=N행}} · {{단나눔}} · {{쪽나눔}}")
            continue
        m = Q_RE.match(line)
        if m:
            flush_q(); flush_set()
            cur = _Buf(m.group("n"), m, i + offset + 1)
            for opt in cur.bad:
                err(i, line, f"모르는 문항 지시 {{{opt}}}(겹친 지시 포함) — {{답항=N행}} · {{단나눔}} · {{쪽나눔}}")
            continue
        m = FENCE_OPEN_RE.match(line)
        if m:
            name = m.group("name")
            if name not in 펜스_이름:
                err(i, line, f"모르는 펜스 이름: {name}")
            if cur is None and set_open is None:
                err(i, line, "문항 앞에 펜스가 있다")
            fence = {"kind": name, "attrs": _attrs(m.group("attrs")), "lines": [], "line_nos": [], "line_no": i + offset + 1}
            continue
        m = IMG_RE.match(line)
        if m:
            tb = target_blocks()
            if tb is None:
                err(i, line, "문항 앞에 그림이 있다")
            else:
                tb.append(Block("그림", (line,), {"src": m.group("src"), "width_cm": float(m.group("w")) if m.group("w") else None}, i + offset + 1))
            continue
        m = CHOICE_RE.match(line)
        if m:
            if cur is None:
                err(i, line, "문항 밖의 답지")
            else:
                cur.choices.append(Choice(m.group("mark"), m.group("t").strip(), m.group("star") == "*", i + offset + 1))
            continue
        if cur is not None:
            if cur.choices:
                err(i, line, "답지 뒤에 본문 줄이 있다")
            elif cur.blocks and cur.blocks[-1].kind in ("보기", "주"):
                # 〈보기〉 뒤 참고 줄(09-29 결정, "※ 단, …") — 〈보기〉 박스 바로 아래·답지 앞의 본문 문단. 줄마다 한 문단
                last = cur.blocks[-1]
                if last.kind == "주":
                    cur.blocks[-1] = Block("주", last.lines + (line.strip(),), {}, last.line_no)
                else:
                    cur.blocks.append(Block("주", (line.strip(),), {}, i + offset + 1))
            elif cur.blocks:
                err(i, line, "박스·표·그림 뒤의 본문 줄 — 발문은 박스 앞에 쓴다(〈보기〉 바로 뒤의 참고 줄만 된다)")
            else:
                cur.stem.append(line.strip())
        elif set_open is not None:
            set_open["passage"].append(line.strip())
        else:
            err(i, line, "문항 앞에 본문이 있다")
    if fence is not None:
        err(len(lines) - 1, "", f"닫히지 않은 펜스: {fence['kind']}")
    if code is not None:
        err(code["line_no"] - offset - 1, "```", "닫히지 않은 코드 블록")
    flush_table(); flush_q(); flush_set()
    return Scan(front, tuple(questions), tuple(sets), tuple(errors))
