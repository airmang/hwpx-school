"""수행평가 마크다운 파서 — hwpx 를 모른다. 결과는 문항 트리(Sheet)."""

from __future__ import annotations

import re
from dataclasses import dataclass

FRONT_MATTER_KEYS: tuple[str, ...] = ("kit", "title", "score", "total")
BLOCK_NAMES: tuple[str, ...] = ("제시문", "조건", "안내", "답칸", "표답칸", "서술칸", "나란히", "정답", "단나눔")

_ITEM = re.compile(r"^##\s+(?P<prompt>.+?)\s*\{(?P<points>[^{}]+)\}\s*$")
_POINTS = re.compile(r"(\d+)\s*점")
_GROUP = re.compile(r"^::::묶음\s+(?P<a>\d+)-(?P<b>\d+)\s+(?P<prompt>.+)$")
_FENCE = re.compile(r"^:::(?P<name>[^\s:]+)(?:\s+(?P<args>.*))?$")
_FIGURE = re.compile(r"^!\[(?P<cap>[^\]]*)\]\((?P<path>[^)]+)\)(?:\{(?P<attrs>[^{}]*)\})?\s*$")
_그림_WIDTH = re.compile(r"^width=(\d+(?:\.\d+)?)cm$")
_그림_CAPTION_정렬 = ("left", "center")
_N줄 = re.compile(r"^(\d+)줄$")
_표_구분 = re.compile(r"^\|(\s*:?-+:?\s*\|)+$")


class MdError(ValueError):
    """손으로 쓴 마크다운의 입력 오류 — 문구는 한 문장, 가능하면 줄 번호로 시작."""


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class Hint:
    text: str


@dataclass(frozen=True)
class Passage:
    kind: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class DataTable:
    """자료표. header = 머리 첫 행, sub_header = 머리 둘째 행부터(병합 머리), rows = 몸.
    merges = 병합 사각형 (행0, 열0, 행1, 열1) — 행 번호는 머리 첫 행이 0. 가려진 칸 값은 ""."""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    sub_header: tuple[tuple[str, ...], ...] = ()
    merges: tuple[tuple[int, int, int, int], ...] = ()

    @property
    def head_rows(self) -> tuple[tuple[str, ...], ...]:
        return (self.header, *self.sub_header)


@dataclass(frozen=True)
class Figure:
    path: str
    width_mm: float | None
    caption: tuple[str, ...]
    caption_align: str = "center"


@dataclass(frozen=True)
class SideBySide:
    """`:::나란히` — 그림 2~3개를 한 행에 같은 폭으로."""

    figures: tuple[Figure, ...]


@dataclass(frozen=True)
class AnswerLine:
    labels: tuple[str, ...]


@dataclass(frozen=True)
class AnswerGrid:
    labels: tuple[str, ...]


@dataclass(frozen=True)
class Lines:
    count: int


@dataclass(frozen=True)
class LabeledLines:
    labels: tuple[str, ...]


@dataclass(frozen=True)
class ColumnBreak:
    pass


Block = (Text | Hint | Passage | DataTable | Figure | SideBySide | AnswerLine | AnswerGrid | Lines | LabeledLines
         | ColumnBreak)
# 문항 밖(첫 문항 앞·묶음 닫은 뒤)에도 둘 수 있는 블록. 답칸·서술칸·단서·일반 줄·정답은 문항 안에서만.
TOP_LEVEL_BLOCKS: tuple[type, ...] = (Passage, DataTable, Figure, SideBySide, ColumnBreak)


@dataclass(frozen=True)
class Item:
    number: int
    prompt: str
    points_text: str
    points: int
    blocks: tuple[Block, ...]
    answer: tuple[str, ...] | None
    line: int


@dataclass(frozen=True)
class Group:
    first: int
    last: int
    prompt: str
    blocks: tuple[Block, ...]
    items: tuple[Item, ...]
    line: int


Entry = Item | Group | Passage | DataTable | Figure | SideBySide | ColumnBreak


@dataclass(frozen=True)
class Sheet:
    kit: str
    title: str
    score: str | None
    total: int
    entries: tuple[Entry, ...]

    @property
    def items(self) -> tuple[Item, ...]:
        out: list[Item] = []
        for e in self.entries:
            if isinstance(e, Item):
                out.append(e)
            elif isinstance(e, Group):
                out.extend(e.items)
        return tuple(out)


def _split_front_matter(text: str) -> tuple[dict[str, str], list[str], int]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise MdError("front matter가 없다 — 첫 줄이 '---'여야 한다")
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            break
    else:
        raise MdError("front matter가 닫히지 않았다 — '---' 줄이 하나 더 필요하다")
    meta: dict[str, str] = {}
    for n, raw in enumerate(lines[1:end], start=2):
        if not raw.strip():
            continue
        key, sep, value = raw.partition(":")
        if not sep:
            raise MdError(f"{n}번째 줄: front matter 는 '키: 값' 꼴이어야 한다: {raw.strip()!r}")
        key = key.strip()
        if key not in FRONT_MATTER_KEYS:
            raise MdError(f"front matter 에 모르는 항목이 있다: {key} — 쓸 수 있는 항목: {', '.join(FRONT_MATTER_KEYS)}")
        meta[key] = value.strip()
    return meta, lines[end + 1:], end + 2


class _Builder:
    def __init__(self) -> None:
        self.entries: list[Entry] = []
        self.group: dict | None = None
        self.item: dict | None = None
        self.number = 0

    def _close_item(self) -> None:
        if self.item is None:
            return
        it = self.item
        done = Item(it["number"], it["prompt"], it["points_text"], it["points"], tuple(it["blocks"]), it["answer"], it["line"])
        (self.group["items"] if self.group is not None else self.entries).append(done)
        self.item = None

    def open_item(self, prompt: str, points_text: str, line: int) -> None:
        self._close_item()
        pts = _POINTS.findall(points_text)
        if not pts:
            raise MdError(f"{line}번째 줄: 배점에 'N점'이 없다: {{{points_text}}}")
        self.number += 1
        self.item = {"number": self.number, "prompt": prompt, "points_text": points_text.strip(),
                     "points": int(pts[-1]), "blocks": [], "answer": None, "line": line}

    def open_group(self, a: int, b: int, prompt: str, line: int) -> None:
        if self.group is not None:
            raise MdError(f"{line}번째 줄: 묶음 안에 묶음을 열 수 없다 — 앞 묶음을 '::::' 로 닫는다")
        self._close_item()
        self.group = {"first": a, "last": b, "prompt": prompt, "blocks": [], "items": [], "line": line}

    def close_group(self, line: int) -> None:
        if self.group is None:
            raise MdError(f"{line}번째 줄: 닫을 묶음이 없다")
        self._close_item()
        g, self.group = self.group, None
        self.entries.append(Group(g["first"], g["last"], g["prompt"], tuple(g["blocks"]), tuple(g["items"]), g["line"]))

    def add(self, block: Block, line: int) -> None:
        if self.item is not None:
            self.item["blocks"].append(block)
        elif self.group is not None:
            self.group["blocks"].append(block)
        elif isinstance(block, TOP_LEVEL_BLOCKS):
            self.entries.append(block)
        else:
            raise MdError(
                f"{line}번째 줄: 문항 밖에 블록이 있다 — 답칸·서술칸·단서·일반 줄은 '## 발문 {{배점}}' 줄 아래에 둔다"
                "(문항 밖에는 안내·제시문·조건·그림·표·나란히만)"
            )

    def set_answer(self, lines: list[str], line: int) -> None:
        if self.item is None:
            raise MdError(f"{line}번째 줄: :::정답 은 문항 안에만 둔다")
        if self.item["answer"] is not None:
            raise MdError(f"{line}번째 줄: 한 문항에 정답이 둘이다")
        self.item["answer"] = tuple(lines)

    def finish(self) -> tuple[Entry, ...]:
        if self.group is not None:
            raise MdError(f"{self.group['line']}번째 줄: 묶음이 닫히지 않았다 — '::::' 줄이 필요하다")
        self._close_item()
        return tuple(self.entries)


def _cells(row: str) -> tuple[str, ...]:
    return tuple(c.strip() for c in row.strip().strip("|").split("|"))


def _표(rows: list[str], n: int) -> DataTable:
    """표 줄 모음 → DataTable. `|---|` 위 행 전부가 머리, 아래가 몸. `<` 왼쪽 칸과, `^` 위 칸과 병합."""
    구분 = [k for k, r in enumerate(rows) if _표_구분.match(r)]
    if not 구분 or 구분[0] == 0 or 구분[0] == len(rows) - 1:
        raise MdError(f"{n}번째 줄: 표는 머리 행(1줄 이상)·'|---|' 구분 행·몸 행 하나 이상으로 쓴다")
    h = 구분[0]
    if len(구분) > 1:
        raise MdError(f"{n + 구분[1]}번째 줄: 표의 '|---|' 구분 행은 하나만 쓴다")
    격자 = [list(_cells(r)) for k, r in enumerate(rows) if k != h]
    줄 = [n + k for k in range(len(rows)) if k != h]  # 격자 행 → 원본 줄 번호
    폭 = len(격자[0])
    for r, 행 in enumerate(격자):
        if len(행) != 폭:
            raise MdError(f"{줄[r]}번째 줄: 표의 모든 행은 첫 행과 칸 수가 같아야 한다({폭}칸)")
    주인: dict[tuple[int, int], tuple[int, int]] = {}
    for r, 행 in enumerate(격자):
        for c, 값 in enumerate(행):
            if 값 not in ("<", "^"):
                주인[r, c] = (r, c)
                continue
            if (r, c) == (0, 0):
                raise MdError(f"{줄[r]}번째 줄: 표의 첫 칸에는 '{값}' 를 쓸 수 없다 — 병합할 칸이 없다")
            if 값 == "<":
                if c == 0:
                    raise MdError(f"{줄[r]}번째 줄: 첫 열의 '<' 는 병합할 왼쪽 칸이 없다")
                주인[r, c] = 주인[r, c - 1]
            else:
                if r == 0:
                    raise MdError(f"{줄[r]}번째 줄: 첫 행의 '^' 는 병합할 위 칸이 없다")
                if r == h:
                    raise MdError(f"{줄[r]}번째 줄: '^' 가 머리와 몸 경계를 가로질러 병합한다 — 머리 칸과 몸 칸은 병합하지 않는다")
                주인[r, c] = 주인[r - 1, c]
            행[c] = ""
    영역: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for 칸, 앵커 in 주인.items():
        영역.setdefault(앵커, []).append(칸)
    merges: list[tuple[int, int, int, int]] = []
    for (r0, c0), 칸들 in sorted(영역.items()):
        if len(칸들) == 1:
            continue
        r1, c1 = max(r for r, _ in 칸들), max(c for _, c in 칸들)
        if len(칸들) != (r1 - r0 + 1) * (c1 - c0 + 1):
            raise MdError(f"{줄[r0]}번째 줄: 표의 병합 영역이 직사각형이 아니다 — '{격자[r0][c0]}' 칸에 붙은 '<'·'^' 를 확인한다")
        merges.append((r0, c0, r1, c1))
    머리 = tuple(tuple(r) for r in 격자[:h])
    return DataTable(머리[0], tuple(tuple(r) for r in 격자[h:]), 머리[1:], tuple(merges))


def _single_fence(name: str, args: str, n: int) -> Block:
    if name == "단나눔":
        if args:
            raise MdError(f"{n}번째 줄: :::단나눔 뒤에는 아무것도 쓰지 않는다")
        return ColumnBreak()
    if name == "답칸":
        labels = tuple(a.strip() for a in args.split("|") if a.strip())
        if not labels:
            raise MdError(f"{n}번째 줄: :::답칸 뒤에 라벨을 '|' 로 나눠 쓴다 — 예: :::답칸 (가) | (나)")
        return AnswerLine(labels)
    m = _N줄.match(args)  # name == "서술칸"
    if not m or int(m.group(1)) < 1:
        raise MdError(f"{n}번째 줄: 서술칸 줄 수는 'N줄' 꼴이어야 한다: {args!r}")
    return Lines(int(m.group(1)))


def _그림_속성(raw: str, n: int) -> tuple[float | None, str]:
    """`{width=8cm caption=left}` — 공백으로 나눈 토큰을 순서·조합 상관없이 읽는다(둘 다 생략 가능)."""
    width_mm: float | None = None
    caption_align = "center"
    for tok in raw.split():
        if m := _그림_WIDTH.match(tok):
            width_mm = float(m.group(1)) * 10
        elif tok.startswith("caption="):
            값 = tok.split("=", 1)[1]
            if 값 not in _그림_CAPTION_정렬:
                raise MdError(f"{n}번째 줄: 그림 줄의 caption 값은 left 또는 center 여야 한다: {tok!r}")
            caption_align = 값
        else:
            raise MdError(f"{n}번째 줄: 그림 줄에 모르는 속성이 있다: {tok!r}")
    return width_mm, caption_align


def _그림_줄(line: str, n: int) -> Figure:
    m = _FIGURE.match(line)
    if m is None:
        raise MdError(f"{n}번째 줄: 그림 줄은 '![캡션](경로.png){{width=8cm caption=left}}' 꼴이어야 한다: {line!r}")
    cap = tuple(c.strip() for c in m["cap"].split("\\n") if c.strip())
    width_mm, caption_align = _그림_속성(m["attrs"] or "", n)
    return Figure(m["path"], width_mm, cap, caption_align)


def _나란히(content: list[tuple[int, str]], n: int) -> SideBySide:
    for k, c in content:
        if not c.startswith("!["):
            raise MdError(f"{k}번째 줄: :::나란히 안에는 그림 줄만 쓴다: {c!r}")
    if not 2 <= len(content) <= 3:
        raise MdError(f"{n}번째 줄: :::나란히 에는 그림 줄을 2~3개 쓴다 — 지금 {len(content)}개")
    return SideBySide(tuple(_그림_줄(c, k) for k, c in content))


def parse_sheet(text: str) -> Sheet:
    meta, body, offset = _split_front_matter(text)
    missing = [k for k in ("kit", "title", "total") if not meta.get(k)]
    if missing:
        raise MdError(f"front matter에 필수 항목이 없다: {', '.join(missing)}")
    if not meta["total"].isdigit():
        raise MdError(f"front matter 의 total 은 자연수여야 한다: {meta['total']!r}")
    b = _Builder()
    i = 0
    while i < len(body):
        n, line = offset + i, body[i].strip()
        i += 1
        if not line:
            continue
        if line == "::::":
            b.close_group(n)
            continue
        if m := _GROUP.match(line):
            b.open_group(int(m["a"]), int(m["b"]), m["prompt"].strip(), n)
            continue
        if line.startswith("::::"):
            raise MdError(f"{n}번째 줄: 묶음은 '::::묶음 a-b 공통 발문' 꼴이어야 한다")
        if m := _ITEM.match(line):
            b.open_item(m["prompt"].strip(), m["points"], n)
            continue
        if line.startswith("#"):
            raise MdError(f"{n}번째 줄: 문항 줄은 '## 발문 {{배점}}' 꼴이어야 한다: {line!r}")
        if line == ":::":
            raise MdError(f"{n}번째 줄: 닫을 블록이 없는 ':::' 이다")
        if m := _FENCE.match(line):
            name, args = m["name"], (m["args"] or "").strip()
            if name not in BLOCK_NAMES:
                raise MdError(f"{n}번째 줄: 모르는 블록이다: {name} — 쓸 수 있는 블록: {', '.join(BLOCK_NAMES)}")
            if name in ("단나눔", "답칸") or (name == "서술칸" and args):
                b.add(_single_fence(name, args, n), n)
                continue
            if args:
                raise MdError(f"{n}번째 줄: :::{name} 머리 줄에는 아무것도 더 쓰지 않는다")
            줄들: list[tuple[int, str]] = []
            while i < len(body) and body[i].strip() != ":::":
                if body[i].strip():
                    줄들.append((offset + i, body[i].strip()))
                i += 1
            if i == len(body):
                raise MdError(f"{n}번째 줄: :::{name} 블록이 닫히지 않았다 — ':::' 줄이 필요하다")
            i += 1
            content = [c for _, c in 줄들]
            if not content:
                raise MdError(f"{n}번째 줄: :::{name} 블록이 비었다")
            if name == "정답":
                b.set_answer(content, n)
            elif name == "나란히":
                b.add(_나란히(줄들, n), n)
            elif name in ("제시문", "조건", "안내"):
                b.add(Passage(name, tuple(content)), n)
            elif name == "표답칸":
                b.add(AnswerGrid(tuple(content)), n)
            else:  # 서술칸(라벨)
                b.add(LabeledLines(tuple(content)), n)
            continue
        if line.startswith("> "):
            b.add(Hint(line[2:].strip()), n)
        elif line.startswith("!["):
            b.add(_그림_줄(line, n), n)
        elif line.startswith("|"):
            rows = [line]
            while i < len(body) and body[i].strip().startswith("|"):
                rows.append(body[i].strip())
                i += 1
            b.add(_표(rows, n), n)
        else:
            b.add(Text(line), n)
    return Sheet(meta["kit"], meta["title"], meta.get("score") or None, int(meta["total"]), b.finish())
