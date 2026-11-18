"""자간 맞춤(Task 28, 설계 D-10) — 끝줄이 짧은 문단의 자간을 줄여 줄 하나를 당긴다.

1학기 제출본 실측(G3 반려 09-27): 본문은 모두 11pt·장평 97이고 줄간격은 스타일 값 그대로다. 손 조정은 자간뿐이다 —
발문 17곳 −1~−17%(대부분 "한 줄을 조금 넘는 발문을 한 줄로"), 5행 답지·〈보기〉 항목·자료 줄 몇 곳 −1~−7%.

대상 문단: 발문 · 답지 줄(5행, 탭 배치형 1·2·3행) · 〈보기〉 항목 · 자료 줄 · 세트 지문. 표 칸(격자표·답항표)·코드 줄은 뺀다.
판정은 실한컴 조판 결과로 한다 — 문서를 한컴에서 열어 저장한 사본의 줄 캐시(hp:linesegarray)에서 문단마다 줄 수와
끝줄 글자를 읽는다(lines_fn). PDF 글리프는 문단 경계를 모른다(한양신명조가 곡선으로 나간다).
언제 당기나(G3 제출본 보정): 끝줄이 짧다 = 끝줄 추정 폭 ÷ 끝줄 가용 폭 ≤ kit.letter_spacing_tail(0.25)이고, 역할 하한
kit.letter_spacing_role_min(발문 −17 · 그 밖 −7) 안에서 줄 하나가 준다. 교사는 발문은 −17까지, 나머지는 −7까지만 당겼다.
얼마나: 줄이 주는 가장 작은(절댓값) s를 이분 탐색으로 — 후보 문단 전부를 한 회차에 함께 잰다(문단의 줄은 서로 무관).
낱말 끌어올림(Task 29): 줄 당김이 아닌 여러 줄 문단에서 끝줄 아닌 줄이 양쪽 정렬로 크게 벌어졌으면(gap_ratio ≥
kit.word_pull_gap 2.0) 줄 수는 그대로 두고 다음 낱말이 앞 줄로 올라오는 가장 작은 s(1씩, 하한 kit.word_pull_min −4).
여유: 찾은 최소값에 kit.letter_spacing_safety(1)를 더한다 — 다시 재어 줄 수·줄 시작이 같을 때만.
파생 charPr = 문단 run의 charPr 복제에서 spacing(7개 언어)만 바꾼 것(charPr에는 hp:switch가 없다). 같은 모양이 있으면
재사용하고, 시도하다 만든 것은 시도마다 걷어 내 최종에는 쓰이는 것만 남는다. 양식의 원래 글자 모양·문단은 바꾸지 않는다.
"""

from __future__ import annotations

import re
import shutil
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from hwpx.document import HwpxDocument
from hwpx.model import Paragraph

from . import equation, q
from .kit import Kit, Metrics, open_seeded, save_stamped, style_ids
from .verify import question_heads

역할 = {"number": "발문", "choice1": "답지", "choice2": "답지", "choice3": "답지", "choice5": "답지",
       "box_guide": "보기", "box": "자료", "normal": "지문"}
_언어 = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")
Key = tuple[int, int]  # (최상위 문단 인덱스, 그 안 문단 차례 — 최상위 자신은 −1)


@dataclass(frozen=True)
class Target:
    key: Key
    number: int  # 문항 번호(세트 지문은 그 세트의 첫 문항)
    role: str    # 발문 · 답지 · 보기 · 자료 · 지문
    text: str


@dataclass(frozen=True)
class Lines:
    """한컴이 조판한 문단 하나 — 줄 수, 끝줄 글자, 끝줄 가용 폭(HWPUNIT), 줄마다 시작 글자 위치(lineseg textpos)."""

    n: int
    tail: str
    avail: int
    text: str
    starts: tuple[int, ...] = ()
    avails: tuple[int, ...] = ()  # 줄마다 가용 폭(lineseg horzsize)
    heights: tuple[int, ...] = ()  # 줄마다 높이(lineseg vertsize) — 수식이 든 줄은 수식 높이까지 늘어난다

    def line(self, i: int) -> str:
        """i번째 줄의 글자(starts로 자른다)."""
        end = self.starts[i + 1] if i + 1 < len(self.starts) else len(self.text)
        return self.text[self.starts[i]:end]

    def extra(self, char_height: int) -> int:
        """줄 높이가 글자 높이를 넘은 만큼의 합(수식이 든 줄) — 줄 높이를 모르면 0."""
        return sum(max(0, h - char_height) for h in self.heights)


@dataclass
class FitResult:
    done: list[tuple[Target, int]] = field(default_factory=list)    # (문단, 자간 %) — 줄 당김과 낱말 끌어올림
    failed: list[tuple[Target, Lines]] = field(default_factory=list)  # 하한까지 줄여도 못 당긴 문단
    rounds: int = 0                                                   # 한컴 측정 횟수(처음 측정 포함)
    words: set = field(default_factory=set)                          # done 가운데 낱말 끌어올림인 문단 키
    minimum: dict = field(default_factory=dict)                      # 키 → 찾은 최소 자간(여유를 빼기 전)


# ---- 문단 ---------------------------------------------------------------------

# hp:t 안의 한 글자짜리 조각 — 한컴 줄 캐시(textpos)는 이것들을 한 글자로 센다. 형광펜 표지는 글자가 아니다.
# (run.content의 종류 — hp:t 밖, 런 바로 아래 적힌 탭·줄바꿈은 세지 않는다)
_글자_조각 = ("text", "tab", "line_break", "nb_space", "fw_space")


def _수식_폭(eq) -> int:
    """수식(hp:equation 모델)이 줄에서 차지하는 폭 — 상자 폭(hp:sz) + 좌우 바깥 여백(hp:outMargin)."""
    om = eq.out_margins
    return int(eq.width or 0) + (0 if om is None else int(om.left or 0) + int(om.right or 0))


def para_text(p: Paragraph) -> str:
    """문단 자신의 글자(run/t — 탭·줄바꿈·묶음 빈칸·고정폭 빈칸은 한 글자) — 안에 든 표·그림의 글자는 넣지 않는다.
    수식은 줄 캐시처럼 8글자 자리다(equation.line_chars — 첫 글자에 폭을 담는다)."""
    out = []
    for r in p.runs:
        for it in r.content:
            if it.kind == "equation":
                out.append(equation.line_chars(_수식_폭(it.object)))
            elif it.container == "t" and it.kind in _글자_조각:
                out.append(it.text)
    return "".join(out)


def _폭(s: str, m: Metrics) -> int:
    """줄 캐시 글의 추정 폭 — 수식 자리(equation.line_chars)는 담은 폭으로 센다."""
    return sum(w if (w := equation.line_char_width(ch)) is not None else m.char(ch) for ch in s)


def _has_object(p: Paragraph) -> bool:
    """문단 런 바로 아래 표·그림이 있는가(박스·격자표·답항표·그림 문단)."""
    return any(it.kind in ("table", "picture") for r in p.runs for it in r.content)


def inner_paragraphs(doc: HwpxDocument) -> list[list[Paragraph]]:
    """구역 0 최상위 문단마다 그 안의 문단들(표 칸·글상자·캡션·머리말 …, 문서 차례 — paragraph.iter_paragraphs())
    — 키의 둘째 값이 이 차례다."""
    return [[place.paragraph for place in top.iter_paragraphs()] for top in doc.sections[0].paragraphs]


def paragraph_at(doc: HwpxDocument, key: Key, inner: list[list[Paragraph]] | None = None) -> Paragraph:
    """키의 문단 객체 — 최상위 문단, 또는 그 안 문단(키의 둘째 값은 inner_paragraphs 차례)."""
    if key[1] < 0:
        return doc.sections[0].paragraphs[key[0]]
    return (inner_paragraphs(doc) if inner is None else inner)[key[0]][key[1]]


def code_char_prs(doc: HwpxDocument, kit: Kit) -> set[str]:
    """코드 블록 글자 모양 id — 한글 글꼴이 kit.code_font인 charPr(자간 맞춤·양쪽 정렬 대상이 아니다, Task 30)."""
    fid = next((str(i) for i, f in doc.styles.fonts("HANGUL").items() if f.face == kit.code_font), None)
    if fid is None:
        return set()
    return {cid for cid, c in doc.styles.char_properties.items()
            if "fontRef" in c.child_attributes and c.child_attributes["fontRef"].get("hangul") == fid}


def _run_has_text(r) -> bool:
    """런에 공백 아닌 글이 있는가 — 글, 수식 글, 안에 든 개체(표·글상자)의 글, 컨트롤 안 문단(머리말·꼬리말·각주·메모)의 글,
    누름틀 매개변수 글까지(옛 판정이 런의 모든 글 노드를 보던 것과 같게)."""
    if r.text.strip():
        return True
    for it in r.content:
        if it.kind == "equation" and (it.object.script or "").strip():
            return True
        if it.container == "run" and (getattr(it.object, "description", None) or "").strip():
            return True  # 개체 설명 글(hp:shapeComment)
        if it.kind == "ruby" and ((it.object.text or "").strip() or (it.object.ruby_text or "").strip()):
            return True  # 덧말
        cap = getattr(it.object, "caption", None) if it.container == "run" else None
        if cap is not None and any(_run_has_text(rr) for cp in cap.paragraphs for rr in cp.runs):
            return True  # 캡션
        if it.container == "ctrl" and it.object is not None:
            if hasattr(it.object, "paragraphs") and any(cp.nested_text().strip() for cp in it.object.paragraphs):
                return True
            if any((prm.value or "").strip() or (prm.name or "").strip() and False
                   for prm in getattr(it.object, "parameters", ()) or ()):
                return True
        if it.kind == "table":
            if any(_run_has_text(rr) for row in it.object.rows for cell in row.cells for cp in cell.paragraphs
                   for rr in cp.runs):
                return True
        elif it.container == "run" and hasattr(it.object, "iter_paragraphs"):
            if any(pl.paragraph.text.strip() for pl in it.object.iter_paragraphs()):
                return True
    return False


def _is_code(p: Paragraph, code: set[str]) -> bool:
    runs = [r for r in p.runs if _run_has_text(r)]
    return bool(runs) and all(str(r.char_pr_id_ref) in code for r in runs)


def targets(doc: HwpxDocument, kit: Kit) -> list[Target]:
    """자간 맞춤 대상 문단 — 첫 문항 묶음(세트 머리 포함)부터 마지막 문단(꼬리 닻) 앞까지."""
    from .layout import group_starts  # layout이 이 모듈을 쓴다(순환 import 회피)

    ids = style_ids(doc)
    by_style = {ids[kit.styles[r]][0]: 역할[r] for r in 역할}
    box_roles = {ids[kit.styles[r]][0]: 역할[r] for r in ("box_guide", "box")}
    heads = question_heads(doc)
    if not heads:
        return []
    code = code_char_prs(doc, kit)
    ps = list(doc.sections[0].paragraphs)
    inner = inner_paragraphs(doc)
    starts = group_starts(doc)  # 문항 k의 보호 묶음 = starts[k] ~ 다음 묶음 앞(세트 머리·지문은 그 세트 첫 문항 묶음)
    out: list[Target] = []
    for i in range(starts[0], len(ps) - 1):
        p = ps[i]
        number = bisect_right(starts, i)
        if _has_object(p):  # 〈보기〉·자료 박스: 내용 셀의 박스 스타일 문단만(격자표·답항표 칸은 스타일이 달라 빠진다)
            for j, sub in enumerate(inner[i]):
                role = box_roles.get(str(sub.style_id_ref))
                text = para_text(sub)
                if role and text.strip() and not _has_object(sub) and not _is_code(sub, code):
                    out.append(Target((i, j), number, role, text))
            continue
        role = by_style.get(str(p.style_id_ref))
        text = para_text(p)
        if role and text.strip() and not _is_code(p, code):
            out.append(Target((i, -1), number, role, text))
    return out


# ---- 한컴 측정(줄 캐시) ------------------------------------------------------

def read_lines(hwpx: Path) -> dict[Key, Lines]:
    """한컴이 저장한 hwpx의 줄 캐시(paragraph.line_segments) — 모든 문단(최상위·안쪽)의 Lines. 줄 캐시가 없는 문단은 뺀다."""
    doc = open_seeded(hwpx)
    out: dict[Key, Lines] = {}
    for i, (top, inner) in enumerate(zip(doc.sections[0].paragraphs, inner_paragraphs(doc))):
        for j, p in enumerate([top] + inner):
            segs = p.line_segments
            if not segs:
                continue
            text = para_text(p)
            last = segs[-1]
            out[(i, j - 1)] = Lines(len(segs), text[last.text_position:], last.width, text,
                                    tuple(x.text_position for x in segs), tuple(x.width for x in segs),
                                    tuple(x.height for x in segs))
    return out


def hancom_lines(hwpx: Path, work: Path, *, oracle=None) -> dict[Key, Lines]:
    """hwpx 사본을 한컴에서 열어 저장(줄 캐시를 한컴이 다시 쓴다)한 뒤 읽는다. 원본은 건드리지 않는다.

    사본 이름은 매번 새 무작위 이름이다(재시도 포함) — 한컴에 같은 이름의 문서가 열려 있으면 열기가 실패한다.
    한컴에 넘기기 전에 꾸러미를 검사한다(render.check_package). 한 번 실패하면 새 사본으로 한 번 더 한다.
    """
    import secrets

    from .render import RenderUnavailable, _oracle, check_package, hancom_lock

    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    check_package(hwpx)
    o = _oracle(oracle)
    refresh = getattr(o, "refresh_document", None)
    if refresh is None:  # Windows COM 오라클은 python-hwpx-automation #152부터 저장(refresh_document)을 한다
        raise RenderUnavailable(f"이 렌더 오라클({type(o).__name__})은 한컴 저장(refresh_document)을 못 한다 — "
                                "줄 캐시를 잴 수 없다. python-hwpx-automation을 올린다")
    for _ in range(2):  # 한컴이 막 띄워졌거나 앞 작업이 늦게 끝난 경우 한 번 더
        copy = work / f"줄-{secrets.token_hex(4)}-{Path(hwpx).name}"
        shutil.copyfile(hwpx, copy)
        check_package(copy)
        with hancom_lock():  # 한컴이 사본을 열어 저장하는 동안 — 공용 잠금(render.hancom_lock)
            saved = refresh(str(copy.resolve()))
        if saved:
            return read_lines(copy)
    raise RenderUnavailable(f"한컴 저장(줄 캐시) 실패(2회): {copy}")


# ---- 자간 charPr --------------------------------------------------------------

def _spacing(c) -> int:
    """글자 모양(char_property)의 한글 자간 — 자간 정의가 없으면 0."""
    sp = c.child_attributes.get("spacing")
    return 0 if sp is None else int(sp.get("hangul", "0"))


class Spacer:
    """문단 → 자간 %를 문서에 적용·되돌린다. set()은 매번 원래 상태에서 다시 적용하고, 앞서 만든 charPr는 걷어 낸다."""

    def __init__(self, doc: HwpxDocument):
        self.doc = doc
        self.orig: dict[Key, list[str]] = {}   # 문단 → run charPr id(처음 값)
        self.made = 0                          # 이번 set이 만든 charPr 수(목록 끝에 붙는다)

    def charpr(self, base: str, s: int) -> str:
        """base charPr에서 자간(7개 언어)만 s로 바꾼 charPr id — 같은 모양이 있으면 재사용
        (doc.styles.ensure_run(base_char_pr_id_ref=, letter_spacing=)). 새 정의는 스키마 차례로 쓴다."""
        styles = self.doc.styles
        src = styles.char_property(base)
        if src is None:
            raise ValueError(f"charPr {base}가 없다")
        if "spacing" not in src.child_attributes:
            raise ValueError(f"charPr {base}에 hh:spacing이 없다 — 자간을 바꿀 수 없다")
        before = len(styles.char_properties)
        cid = styles.ensure_run(base_char_pr_id_ref=base, letter_spacing=s)
        if len(styles.char_properties) > before:
            self.made += 1
        return str(cid)

    def _drop_made(self) -> None:
        """이번 set이 만든 charPr를 걷어 낸다 — 런을 원래 id로 되돌린 뒤라 목록 끝의 쓰이지 않는 정의다
        (doc.styles.remove_unused_definitions). 그 앞에 원래 쓰이지 않던 정의가 목록 끝에 붙어 있었으면 그것도 함께 걷힌다
        (한/글도 저장할 때 쓰이지 않는 정의를 지운다 — compose-x)."""
        if self.made:
            self.doc.styles.remove_unused_definitions(["char_properties"])
        self.made = 0

    def set(self, decisions: dict[Key, int]) -> None:
        """decisions 밖 문단은 원래 charPr로, 안의 문단은 run마다 원래 charPr의 자간 s 복제로."""
        inner = inner_paragraphs(self.doc)
        for key, ids in self.orig.items():
            for r, cid in zip(paragraph_at(self.doc, key, inner).runs, ids):
                r.char_pr_id_ref = cid
        self._drop_made()
        for key, s in decisions.items():
            runs = paragraph_at(self.doc, key, inner).runs
            ids = self.orig.setdefault(key, [str(r.char_pr_id_ref) for r in runs])
            if s:
                for r, cid in zip(runs, ids):
                    r.char_pr_id_ref = self.charpr(cid, s)


def current_spacing(doc: HwpxDocument, key: Key) -> int:
    """문단 run들의 자간 가운데 절댓값이 가장 큰 값(부호 그대로) — 이미 맞춘 문단(≠ 0)은 다시 맞추지 않는다."""
    vals = [run.letter_spacing or 0 for run in paragraph_at(doc, key).runs]
    return max(vals, key=abs, default=0)


def drop_line_cache(doc: HwpxDocument, keys) -> None:
    """문단의 줄 캐시(hp:linesegarray)를 지운다 — 한컴이 낡은 캐시를 그대로 쓰지 않고 다시 재게(M-4).
    그 문단을 품은 문단(박스 칸 문단이면 박스 문단)의 캐시도 함께 간다(paragraph.clear_layout_cache)."""
    inner = inner_paragraphs(doc)
    for key in keys:
        paragraph_at(doc, key, inner).clear_layout_cache()


# ---- 맞춤 루프 ----------------------------------------------------------------

def tail_ratio(ln: Lines, m: Metrics) -> float:
    """끝줄 추정 폭 ÷ 끝줄 가용 폭 — 한 줄짜리는 0."""
    return 0.0 if ln.n < 2 or ln.avail <= 0 else _폭(ln.tail.strip(), m) / ln.avail


def floor_for(kit: Kit, role: str) -> int:
    """역할의 자간 하한(음수) — 킷 하한과 역할 하한 가운데 덜 줄이는 쪽."""
    rm = kit.letter_spacing_role_min
    return max(kit.letter_spacing_min, rm.get(role, rm["기타"]))


def line_gaps(ln: Lines, m: Metrics) -> list[float]:
    """끝줄을 뺀 줄마다 '공백 하나에 남는 폭 ÷ 공백 폭'(양쪽 정렬로 벌어진 정도, 추정 글자 폭). 공백이 없거나 탭이 든
    줄(탭 배치형 답지 — 벌어짐이 아니라 칸이다)은 0."""
    out = []
    for i in range(len(ln.starts) - 1):
        raw = ln.line(i)
        body = raw.strip()
        spaces = body.count(" ")
        out.append(0.0 if not spaces or "\t" in raw or i >= len(ln.avails)
                   else (ln.avails[i] - _폭(body.strip(), m)) / spaces / m.space)
    return out


def gap_ratio(ln: Lines, m: Metrics) -> float:
    """가장 벌어진 줄의 벌어짐(line_gaps의 최댓값) — 한 줄짜리는 0."""
    return max(line_gaps(ln, m), default=0.0)


WORD_ROLES = ("발문", "답지", "보기", "자료")


@dataclass
class _Search:
    kind: str       # "줄"(줄 하나 당김, 이분 탐색) · "낱말"(줄 수 그대로 낱말 끌어올림, 1씩)
    floor: int      # 가 볼 가장 큰 |s|
    bad: int = 0    # 목적을 못 이룬 가장 큰 |s|
    good: int = 0   # 목적을 이룬 가장 작은 |s|(0 = 아직 없음)
    seen: Lines | None = None  # good에서 잰 줄
    line: int = 0   # 낱말: 가장 벌어진 줄 i — 줄 i+1의 시작이 뒤로 가야 끌어올림이다

    def next(self) -> int | None:
        if self.kind == "줄":
            hi = self.good or self.floor + 1
            return None if hi - self.bad <= 1 else (self.bad + hi) // 2
        return None if self.good or self.bad >= self.floor else self.bad + 1


def fit_spacing(doc: HwpxDocument, kit: Kit, save: Callable[[], Path], lines_fn: Callable[[Path, int], dict]) -> FitResult:
    """대상 문단의 자간을 맞춰 문서에 남긴다 — 두 가지 목적(설계 §6.6).

    ① 줄 당김: 끝줄이 짧은 문단(끝줄 비율 ≤ letter_spacing_tail)의 줄 하나를 당기는 가장 작은 |s| — 역할 하한 안(이분 탐색).
    ② 낱말 끌어올림: ①이 아닌 여러 줄 문단 가운데 줄이 양쪽 정렬로 벌어진 것(gap_ratio ≥ word_pull_gap)은, 줄 수를 그대로
       두고 다음 줄 첫 낱말이 앞 줄로 올라오는(줄 시작이 바뀌는) 가장 작은 |s| — word_pull_min 안(1씩). 줄 수가 바뀌면 버린다.
    찾은 최소값에 여유 1을 더한다(letter_spacing_safety, 역할 하한 안) — 한 번 더 재어 줄 수·줄 시작이 최소값 때와 같을
    때만 남기고, 다르면 최소값으로 둔다. save() = 저장 경로, lines_fn(경로, 회차) = 한컴 조판 결과의 Lines.
    이미 자간이 있는 문단은 건드리지 않는다. 대상 문단의 줄 캐시는 먼저 지운다(M-4).
    """
    res = FitResult()
    ts = [t for t in targets(doc, kit) if current_spacing(doc, t.key) == 0]
    if not ts:
        return res
    drop_line_cache(doc, [t.key for t in ts])
    base = _measure(lines_fn, save(), 1, ts)
    res.rounds = 1
    by = {t.key: t for t in ts}
    runs: dict[Key, _Search] = {}
    for t in ts:
        b = base[t.key]
        if b.n < 2:
            continue
        if tail_ratio(b, kit.metrics) <= kit.letter_spacing_tail:
            runs[t.key] = _Search("줄", abs(floor_for(kit, t.role)))
        elif t.role in WORD_ROLES and kit.word_pull_min and gap_ratio(b, kit.metrics) >= kit.word_pull_gap:
            gaps = line_gaps(b, kit.metrics)
            runs[t.key] = _Search("낱말", abs(kit.word_pull_min), line=gaps.index(max(gaps)))
    sp = Spacer(doc)
    ok: dict[Key, int] = {}
    while True:
        trial = {k: v for k, r in runs.items() if (v := r.next()) is not None}
        if not trial:
            break
        sp.set({k: -v for k, v in trial.items()} | {k: -v for k, v in ok.items()})
        res.rounds += 1
        m = _measure(lines_fn, save(), res.rounds, [by[k] for k in trial])
        for k, v in trial.items():
            r, b, got = runs[k], base[k], m[k]
            if r.kind == "줄":
                hit = got.n < b.n
            else:
                i = r.line + 1
                hit = got.n == b.n and got.starts[i] > b.starts[i]  # 벌어진 줄 다음 줄의 첫 낱말이 올라왔다
                if got.n != b.n:
                    r.bad = r.floor  # 줄 수가 바뀌었다 — 끌어올림이 아니다, 그만둔다
            if hit:
                r.good, r.seen = v, got
            elif got.n == b.n or r.kind == "줄":
                r.bad = max(r.bad, v)
            if r.next() is None and r.good and r.good <= r.floor:
                ok[k] = r.good
    res.minimum = dict(ok)
    safe = {k: min(v + kit.letter_spacing_safety, runs[k].floor) for k, v in ok.items()}
    if any(safe[k] != ok[k] for k in ok):  # 여유 확인 — 줄 수·줄 시작이 최소값 때와 같아야 남긴다
        sp.set({k: -v for k, v in safe.items()})
        res.rounds += 1
        m = _measure(lines_fn, save(), res.rounds, [by[k] for k in ok])
        for k in ok:
            if (m[k].n, m[k].starts) == (runs[k].seen.n, runs[k].seen.starts):
                ok[k] = safe[k]
    sp.set({k: -v for k, v in ok.items()})
    save()
    res.done = sorted(((by[k], -v) for k, v in ok.items()), key=lambda x: x[0].key)
    res.words = {k for k in ok if runs[k].kind == "낱말"}
    res.failed = sorted(((by[k], base[k]) for k, r in runs.items()
                         if r.kind == "줄" and k not in ok and floor_for(kit, by[k].role) == kit.letter_spacing_min),
                        key=lambda x: x[0].key)
    return res


def _measure(lines_fn, path: Path, n: int, ts: list[Target]) -> dict[Key, Lines]:
    m = lines_fn(path, n)
    for t in ts:  # 한컴 사본의 문단이 문서의 문단과 같은지 — 키가 어긋나면 다른 문단의 자간을 바꾼다
        got = m.get(t.key)
        if got is None or re.sub(r"\s", "", equation.line_key(got.text)) != re.sub(r"\s", "", equation.line_key(t.text)):
            raise ValueError(f"한컴 측정 {n}회차: {t.number}번 {t.role} 문단 {t.key}의 줄 캐시가 없거나 글자가 다르다")
    return m


def summary(done: list[tuple[Target, int]], words=frozenset()) -> dict[int, str]:
    """문항 → 적용한 자간 요약(보고서 배치 표) — 예: '발문 −11 · 답지 −3 · 보기 −2(낱말)'. words = 낱말 끌어올림 문단 키."""
    out: dict[int, list[str]] = {}
    for t, s in done:
        out.setdefault(t.number, []).append(f"{t.role} {s:+d}".replace("-", "−") + ("(낱말)" if t.key in words else ""))
    return {k: " · ".join(v) for k, v in out.items()}


# ---- 기준본과 문단별 줄 수 대조(G3 합격 기준) --------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s", "", equation.line_key(text)).replace("~", "∼")


def norm_starts(ln: Lines) -> tuple[int, ...]:
    """줄 시작을 '앞의 공백 아닌 글자 수'로 — 원고의 공백 정리(역변환)와 무관하게 두 판을 대조한다."""
    return tuple(len(re.sub(r"\s", "", ln.text[:x])) for x in ln.starts)


def line_diff(ts: list[Target], ours: dict[Key, Lines], ref: dict[Key, Lines]) -> list[tuple[Target, Lines, Lines | None]]:
    """대상 문단마다 (문단, 우리 줄, 기준본 줄). 기준본 문단은 글자(공백 무시)가 같은 문단을 문서 차례로 앞에서부터
    찾는다 — 없으면 None(글이 다르거나 배치형이 달라 줄 문단이 다르다)."""
    ref_seq = [(k, _norm(v.text)) for k, v in sorted(ref.items())]
    out, j = [], 0
    for t in ts:
        want = _norm(t.text)
        hit = next((i for i in range(j, len(ref_seq)) if ref_seq[i][1] == want), None)
        if hit is not None:
            j = hit + 1
        out.append((t, ours[t.key], None if hit is None else ref[ref_seq[hit][0]]))
    return out


def same_lines(a: Lines, b: Lines | None) -> bool:
    """줄 수와 줄 시작(공백 아닌 글자 위치)이 같다 — G3 합격 기준(Task 29)."""
    return b is not None and a.n == b.n and norm_starts(a) == norm_starts(b)


@dataclass(frozen=True)
class Traits:
    """대조 까닭을 가르는 문단 속성 — 왼여백·내어쓰기(case), 글이 공백으로 시작하나, run 자간 값들."""

    left: int
    intent: int
    lead_space: bool
    spacing: tuple[int, ...]

    def positions(self, half: int) -> tuple[int, int]:
        """(첫 줄 글 시작 x, 둘째 줄부터 시작 x) HWPUNIT — 앞 공백은 반각 한 칸(half, 킷 metrics)으로 친다.
        내어쓰기(음수)는 둘째 줄부터 들어간다."""
        first = self.left + (half if self.lead_space else 0) + max(self.intent, 0)
        return first, self.left - min(self.intent, 0)


def read_traits(hwpx: Path) -> dict[Key, Traits]:
    """hwpx의 모든 문단(최상위·안쪽)의 Traits — 키는 read_lines와 같다. 여백은 문단 모양의 case 분기(한/글 2016+가 읽는 것)."""
    doc = open_seeded(hwpx)
    styles = doc.styles
    out: dict[Key, Traits] = {}
    for i, (top, inner) in enumerate(zip(doc.sections[0].paragraphs, inner_paragraphs(doc))):
        for j, p in enumerate([top] + inner):
            pp = styles.paragraph_property(p.para_pr_id_ref) if p.para_pr_id_ref is not None else None
            sw = None if pp is None else pp.version_switch
            m = None if sw is None or sw.case is None else sw.case.margin
            runs = [c for r in p.runs if _run_has_text(r)
                    and (c := styles.char_property(r.char_pr_id_ref)) is not None]
            out[(i, j - 1)] = Traits(int((m.left if m else None) or 0), int((m.intent if m else None) or 0),
                                     para_text(p).startswith(" "), tuple(_spacing(c) for c in runs))
    return out


BOX_CAUSE = "제출본 박스별 기하 차이(ㄱ 자리·내어쓰기)"
FORM_BOX = "제출본 박스만 양식 스타일(앞 공백·내어쓰기 −2500)"


def mismatch_cause(t: Target, ours: Lines, ref: Lines | None, mine: Traits, theirs: Traits | None, *, m: Metrics) -> str:
    """줄 대조 불일치의 까닭 — 두 파일의 문단 속성으로 가른다. 가르지 못하면 '설명 없음'(합격 기준: 0건).

    〈보기〉 항목은 어긋난 첫 줄 시작 k를 본다: k = 1이면 첫 줄 폭(글 시작 x), k ≥ 2이면 둘째 줄부터의 폭(내어쓰기 x)이
    두 판에서 달라야 설명이 된다(첫 줄 x는 둘째 줄 시작만, 내어쓰기 x는 셋째 줄부터만 바꾼다).
    """
    if ref is None or theirs is None:
        return "설명 없음 — 기준본에 같은 글의 문단이 없다"
    if t.role == "보기" and ours.n == ref.n:
        a, b = norm_starts(ours), norm_starts(ref)
        k = next((i for i in range(len(a)) if a[i] != b[i]), None)
        if k is None:
            return "설명 없음 — 줄 시작이 같다"
        (mf, mc), (tf, tc) = mine.positions(m.half), theirs.positions(m.half)
        if (k == 1 and mf != tf) or (k >= 2 and mc != tc):
            label = FORM_BOX if theirs.lead_space and theirs.intent == -2500 else BOX_CAUSE
            what = f"첫 줄 x {tf}(엔진 {mf})" if k == 1 else f"내어쓰기 x {tc}(엔진 {mc})"
            return f"{label}: {what}"
        return "설명 없음 — 〈보기〉 항목의 글 자리·내어쓰기가 같은데 줄바꿈이 다르다"
    hand = [v for v in theirs.spacing if v]
    if hand and len(hand) < len(theirs.spacing) and ours.n == ref.n:
        return f"제출본 손 자간이 문단 일부 run에만({min(hand)}) — 줄 수는 같고 낱말 자리만 옮겨졌다"
    if ours.n < ref.n and any(mine.spacing) and not any(theirs.spacing):
        return "엔진은 짧은 끝줄을 당겼고 제출본은 그대로(같은 모양의 다른 문단은 교사도 당겼다) — 문서화된 예외"
    return "설명 없음"


CACHE_CAUSE = "제출본 저장 줄 캐시(출제 PC 배치)"


def fresh_layout(hwpx: Path, work: Path, *, oracle=None) -> dict[Key, Lines]:
    """기준본 사본에서 줄 캐시를 모두 지우고 이 PC 한컴으로 새로 조판한 줄 — 저장된 캐시는 출제 PC의 조판이라, 캐시가
    없는 엔진 산출물(인쇄 PC가 새로 조판한다)과 견주는 공정한 기준은 새 조판이다(Task 29 판정)."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    bare = work / f"캐시없음-{Path(hwpx).name}"
    doc = open_seeded(hwpx)
    for place in doc.text.iter_paragraphs():  # 본문·칸·머리말·꼬리말 … 모든 문단(바탕쪽은 구역 XML 밖)
        if place.where != "master_page":
            place.paragraph.clear_layout_cache()
    save_stamped(doc, bare)
    return hancom_lines(bare, work, oracle=oracle)


def diff_rows(doc: HwpxDocument, kit: Kit, ours: dict[Key, Lines], mine: dict[Key, Traits],
              ref: dict[Key, Lines], theirs: dict[Key, Traits], fresh: dict[Key, Lines] | None = None) -> list[tuple]:
    """대상 문단마다 (문단, 우리 줄, 기준본 줄, 까닭 또는 ''). fresh가 있으면(저장 캐시 관점) 새 조판과는 같은데 캐시와
    다른 문단을 CACHE_CAUSE로 적는다."""
    by_text: dict[str, list[Key]] = {}  # 글 → 기준본 키(문서 차례) — line_diff와 같은 차례로 짝을 찾는다
    for k, v in sorted(ref.items()):
        by_text.setdefault(_norm(v.text), []).append(k)
    used: dict[str, int] = {}
    out = []
    ts = targets(doc, kit)
    rows = line_diff(ts, ours, ref)
    fresh_ref = [r for _, _, r in line_diff(ts, ours, fresh)] if fresh is not None else [None] * len(rows)
    for (t, o, r), f in zip(rows, fresh_ref):
        rk = None
        if r is not None:
            n = _norm(t.text)
            rk = by_text[n][min(used.get(n, 0), len(by_text[n]) - 1)]
            used[n] = used.get(n, 0) + 1
        cause = ""
        if not same_lines(o, r):
            if fresh is not None and same_lines(o, f):
                cause = f"{CACHE_CAUSE} — 이 PC에서 새로 조판하면 엔진과 같다"
            else:
                cause = mismatch_cause(t, o, r, mine[t.key], None if rk is None else theirs[rk], m=kit.metrics)
        out.append((t, o, r, cause))
    return out


def _print_table(title: str, doc: HwpxDocument, rows: list[tuple]) -> tuple[int, int]:
    print(f"## {title}\n")
    print("| 문항 | 역할 | 엔진 줄 시작 | 기준본 줄 시작 | 자간 | 불일치 까닭 |")
    print("|---|---|---|---|---|---|")
    causes: dict[str, int] = {}
    for t, o, r, cause in rows:
        s = current_spacing(doc, t.key)
        if cause:
            head = cause.split(":")[0].split(" — ")[0]
            causes[head] = causes.get(head, 0) + 1
        label = f"{t.role} {t.text.strip()[:1]}" if t.role in ("보기", "답지") else t.role  # 기호만(ㄱ·①) — 글은 내지 않는다
        print(f"| {t.number} | {label} | {list(norm_starts(o))} | {'—' if r is None else list(norm_starts(r))} | "
              f"{s if s else ''} | {cause} |")
    bad = sum(causes.values())
    unexplained = sum(v for k, v in causes.items() if k.startswith("설명 없음"))
    print(f"\n문단 {len(rows)} · 여러 줄 {sum(1 for _, o, _, _ in rows if o.n > 1)} · 불일치 {bad} · 설명 없음 {unexplained}")
    for k, v in sorted(causes.items(), key=lambda x: -x[1]):
        print(f"- {k}: {v}")
    print()
    return bad, unexplained


def main(argv: list[str] | None = None) -> int:
    """문항지 hwpx와 기준본 hwpx의 문단별 줄 수·줄 시작 대조와 까닭 — 두 관점을 늘 함께 낸다.

    ① 합격 기준: 기준본을 이 PC 한컴으로 새로 조판한 줄(fresh_layout). ② 기준본에 저장된 줄 캐시(출제 PC의 조판) —
    ①과 같은데 ②와 다른 문단은 CACHE_CAUSE. 문항지는 사본을 한컴에서 저장해 줄 캐시를 만든다(실한컴 2회).
    출력은 표준 출력뿐이다(글자는 내지 않는다 — 수만). 끝 코드: ①의 설명 없음이 0이면 0."""
    import argparse
    import tempfile

    from .kit import load_kit

    ap = argparse.ArgumentParser(prog="python -m exam_kit.fit",
                                 description="문단별 줄 수·줄 시작 대조와 불일치 까닭(합격: 새 조판 기준 설명 없음 0)")
    ap.add_argument("ours", type=Path)
    ap.add_argument("ref", type=Path)
    ap.add_argument("--kit", type=Path, required=True)
    a = ap.parse_args(argv)
    kit = load_kit(a.kit)
    doc = open_seeded(a.ours)
    with tempfile.TemporaryDirectory(prefix="줄대조-", dir=a.ours.resolve().parent) as work:
        ours = hancom_lines(a.ours, Path(work) / "엔진")
        fresh = fresh_layout(a.ref, Path(work) / "기준본")
    mine, theirs, cached = read_traits(a.ours), read_traits(a.ref), read_lines(a.ref)
    _, unexplained = _print_table("① 합격 기준 — 기준본을 이 PC 한컴으로 새로 조판(줄 캐시 없음)", doc,
                                  diff_rows(doc, kit, ours, mine, fresh, theirs))
    _print_table("② 기준본 저장 줄 캐시(출제 PC 조판, 한컴이 파일을 열 때 그대로 쓴다)", doc,
                 diff_rows(doc, kit, ours, mine, cached, theirs, fresh))
    return 0 if unexplained == 0 else 2


if __name__ == "__main__":
    import sys

    sys.exit(main())
