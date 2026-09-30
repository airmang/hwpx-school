"""렌더 측정 루프(Task 26) — 조판·마무리된 문서를 실한컴으로 렌더하고, 재고, 고쳐서 다시 렌더한다.

settle : ⓪ 접힌 답지 줄 — 탭 배치형(1·2·3행) 답지가 칸을 넘어 다음 줄로 접히면 한 단계 느슨한 형으로 다시 쓴다
            (1→2→3→5행, 재렌더, 최대 3회). 눌러 둔 형({답항=N행})은 note만.
         ⓪'' 균형 배치(Task 30) — ⓪' 뒤 렌더에서 문항 묶음 높이를 재어, 쪽수 최소 가운데 단마다 남는 높이가 가장 고른
            단 나눔(동적 계획법)을 박는다. 꼬리 자리·원고 나눔 지시는 제약. 자리가 계획과 다르면 다시 재어 한 번 더.
         ⓪' 자간 맞춤(Task 28, fit.py) — 끝줄이 짧은 발문·답지·〈보기〉·자료·세트 지문의 자간을 줄여 줄 하나를 당긴다.
            한컴 저장 사본의 줄 캐시로 재고(lines_fn), 바뀌었으면 재렌더. 높이가 바뀌므로 분할·꼬리·간격 전에 한 번.
         ① 문항 분할 해소 — 분할된 문항 묶음의 첫 문단에 단 나눔(쪽 경계면 쪽 나눔), 재렌더, 최대 3회.
         ② 꼬리 박스 자리(설계 R-5) — 박스는 닻(마지막 문단)과 함께 흘러 마지막 문항이 끝난 쪽의 오른쪽 단 맨 아래에
            앉는다. 그 자리(박스 높이 + 여유)까지 문항이 오면 한글은 박스를 피하려고 닻을 새 쪽으로 밀어 빈 쪽이 생긴다
            → (나-1) 넘친 단(마지막 쪽 오른쪽 단)의 문항 간격을 kit.question_gap_min(G2: 880 = 반 줄)까지 줄여 본다.
                     넘침이 줄일 수 있는 양보다 크면 렌더 없이 건너뛴다. 단 맨 위 문항(간격 0)은 건드리지 않는다.
            → (나-2) 그 쪽 오른쪽 단의 마지막 문항부터 한 문항씩 다음 쪽으로 넘긴다(최대 3회). 쪽이 늘면 경고(최후 수단).
         ③ 단 맨 위 문항의 위 간격 = 0(제출본과 같다) — 그 묶음에 단/쪽 나눔을 박아 흐름을 고정한 뒤 간격을 뺀다.
         ④ gap="distribute"(기본, G2)면 단마다 남은 세로 공간을 그 단의 문항 머리 간격(첫 문항 제외)에 고르게 나눈다 —
            문항 하나에 더하는 간격은 kit.gap_extra_max까지(Task 30), 넘는 몫은 단 아래에 남긴다
            (마지막 내용 단 제외). ②-2가 문항을 넘겨 보낸 단도 제외 — 빈자리를 단 아래로 모은다(G2 판정, 고정 간격).
         ⑤ 총쪽수 누름틀 = 렌더 쪽수, 최종 렌더, 분할·꼬리 재검사.
         순서: ⓪ → ⓪' → ⓪'' → ① → ③ → ② → ③ → ④ → ⑤. ③을 꼬리(②) 앞에 한 번 해 꼬리 판단이 맨 위 간격(≈18pt)을 뺀 자리를 보게
         하고, ②가 새 쪽으로 넘긴 문항을 위해 뒤에 한 번 더 한다. scan은 문서와 문항 수가 같아야 한다(다르면 ValueError).
문단 보호(keepWithNext·keepLines)가 먼저 분할을 막고, 이 루프는 렌더로만 알 수 있는 것을 고친다.
"""

from __future__ import annotations

import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from hwpx.document import HwpxDocument

from . import q
from .compose import (
    LOOSER,
    case_prev,
    choice_paragraphs,
    derive_para_pr,
    relayout_choices,
    resize_boxes,
)
from .fit import FitResult, Target, fit_spacing, floor_for, hancom_lines, targets
from .geometry import (
    LINE_PT,
    PageLayout,
    body_bottom,
    column_lines,
    group_extents,
    is_head,
    measure,
    splits,
    tail_box_top,
)
from .kit import Kit, style_ids
from .render import RenderResult, render
from .scan import Scan
from .slots import fill_total_pages, read_total_pages
from .verify import question_heads

GAPS = ("fixed", "distribute")
PACKS = ("balanced", "greedy")  # 단 나눔: 최소 쪽수에서 고르게(⓪'') · 앞에서부터 흐르는 대로
DIST_SAFETY = LINE_PT * 0.5 + 1.0  # 글리프 아래끝 ~ 줄 아래끝(160% 줄의 남는 폭) — 나눌 공간에서 뺀다
SQUEEZE_SAFETY = 50                # 간격 줄이기 여유(HWPUNIT) — 계산한 만큼보다 0.5pt 더 줄인다


@dataclass
class Settled:
    render: RenderResult
    layout: list[PageLayout]
    notes: list[str] = field(default_factory=list)  # 경고 — 쪽 추가·간격 줄임·분할 잔존·되돌림(build 보고서가 표시)
    renders: int = 0
    first_pages: int = 0  # 첫 렌더(루프가 손대기 전)에서 본문이 있는 마지막 쪽 — 최종 쪽수가 더 크면 루프가 쪽을 늘렸다.
    # 첫 렌더의 전체 쪽수가 아니다: 오른쪽 단이 꼬리 자리까지 차면 한글이 박스만 앉은 빈 쪽을 덧붙여(Task 26) 쪽수가 이미 는다.
    spacing: list[tuple[Target, int]] = field(default_factory=list)  # 자간 맞춤으로 줄을 당기거나 낱말을 올린 문단과 자간 %
    spacing_words: set = field(default_factory=set)  # spacing 가운데 낱말 끌어올림인 문단 키
    measures: int = 0  # 자간 맞춤의 한컴 측정(저장 사본) 횟수 — 렌더와 따로 센다

    @property
    def pages_added(self) -> bool:
        return self.render.page_count > self.first_pages


# ---- 문서 쪽: 문항 묶음 ------------------------------------------------------

def _keep_next_ids(doc: HwpxDocument) -> set[str]:
    out = set()
    for pp in doc.headers[0].element.iter(q("hh", "paraPr")):
        b = pp.find(q("hh", "breakSetting"))
        if b is not None and b.get("keepWithNext") == "1":
            out.add(pp.get("id"))
    return out


def group_starts(doc: HwpxDocument) -> list[int]:
    """문항마다 보호 묶음 첫 문단의 인덱스 — 머리에서 거꾸로, 앞 문단이 keepWithNext인 동안(세트 머리·자료까지)."""
    ps = list(doc.sections[0].paragraphs)
    keep = _keep_next_ids(doc)
    out, floor = [], 0
    for h in question_heads(doc):
        i = h
        while i - 1 > floor and str(ps[i - 1].element.get("paraPrIDRef")) in keep:
            i -= 1
        out.append(i)
        floor = h
    return out


def set_break(doc: HwpxDocument, index: int, kind: str | None) -> bool:
    """최상위 문단 index에 단 나눔("column")·쪽 나눔("page")·없음(None). 바뀌었으면 True."""
    el = doc.sections[0].paragraphs[index].element
    want = ("1" if kind == "column" else "0", "1" if kind == "page" else "0")
    if (el.get("columnBreak"), el.get("pageBreak")) == want:
        return False
    el.set("columnBreak", want[0])
    el.set("pageBreak", want[1])
    doc.sections[0].mark_dirty()
    return True


def choice_layouts(doc: HwpxDocument, kit: Kit) -> dict[int, tuple[str, int]]:
    """탭 배치형 문항 → (형, 답지 줄 수). 5행·답항표 문항은 없다(한 줄에 답지 하나라 탭 칸이 없다)."""
    ids = style_ids(doc)
    kinds = {ids[kit.styles[r]][0]: f"{r[-1]}행" for r in ("choice1", "choice2", "choice3")}
    ps = list(doc.sections[0].paragraphs)
    out = {}
    for k in range(len(question_heads(doc))):
        rows = [str(ps[i].element.get("styleIDRef")) for i in choice_paragraphs(doc, kit, k + 1)]
        if rows and rows[0] in kinds:
            out[k] = (kinds[rows[0]], len(rows))
    return out


# 답지 줄 첫 글리프 dx 범위는 킷 render.choice_dx(예: 답항 왼여백 1000 = 10pt면 9.5~11.5 — 원문자와 접힌 줄이 모두 여기).
# 〈보기〉 항목 줄(ㄱ. dx 12.4)은 밖이고, 답지 줄끼리는 줄 피치(17.6pt)로 붙어 있어 박스와 답지 사이 틈에서 끊긴다.


SLOT_TOL = 1.2  # 원문자 x0 = 칸 시작 + 0.55pt(Task 25 렌더 실측 ±0.5)
# choice_dx 윗끝 11.5는 실측 최대 11.3에 빠듯하다. 첫 원문자가 그보다 오른쪽에 찍혀 접힘 세기에서 빠져도, 칸 검사가
# 첫 칸(시작 10.55 ± 1.2)에 글자가 없다고 잡는다 — 둘이 함께 윗끝의 빈틈을 덮는다.


def wrapped_choices(doc: HwpxDocument, pdf: Path, kit: Kit) -> list[tuple[int, str]]:
    """렌더에서 답지가 칸을 넘은 탭 배치형 문항 (k, 형). 두 가지를 본다.

    - 접힘: 문항 끝에서 거꾸로 이어진 '답지 자리' 줄(dx가 kit.render.choice_dx 안)이 배치형 줄 수보다 많다. 문항 구역 = 그 머리
      줄부터 다음에 단 왼끝(dx < 2)에서 시작하는 줄(다음 머리·세트 머리) 앞까지. 접힌 줄은 같은 왼여백에서 시작한다.
    - 칸 어긋남: 답지 줄마다 k번째 칸 시작(+0.55pt)에 글자가 없다 — 앞 답지가 칸을 넘어 탭이 다음 탭 자리로 밀렸다.
    텍스트 층 본문 글자(ㄱ·ㄴ·ㄷ)도 줄에 넣는다 — 접힌 줄이 `ㄹ`뿐이면 곡선 글리프가 없다(Task 25 강제 넘침 렌더).
    """
    from .compose import Samples, _Composer, 배치형

    lines = column_lines(pdf, kit, text=True)
    heads = [i for i, ln in enumerate(lines) if is_head(ln)]
    lo, hi = kit.render["choice_dx"]
    c = _Composer(doc, kit, Samples(None, None, None), answer_key=False)
    out = []
    for k, (kind, rows) in choice_layouts(doc, kit).items():
        if k >= len(heads):
            break
        start = heads[k]
        end = next((j for j in range(start + 1, len(lines)) if lines[j].dx < 2.0), len(lines))
        n, j = 0, end - 1
        while j > start and lo <= lines[j].dx <= hi and (
                n == 0 or lines[j].page != lines[j + 1].page or lines[j].col != lines[j + 1].col
                or lines[j + 1].y0 - lines[j].y0 < LINE_PT * 1.3):
            n, j = n + 1, j - 1
        if n > rows:
            out.append((k, kind))
            continue
        role, per_row = 배치형[kind]
        starts = c.slots(role, max(per_row))
        for ln, cnt in zip(lines[end - rows:end], per_row):
            xs = [g.x0 - (ln.boxes[0].x0 - ln.dx) for g in ln.boxes]  # 단 왼끝 기준
            if any(not any(abs(x - (starts[i] / 100 + 0.55)) < SLOT_TOL for x in xs) for i in range(cnt)):
                out.append((k, kind))
                break
    return out


# ---- 렌더 쪽: 문항 자리 ------------------------------------------------------

def head_places(layout: list[PageLayout]) -> list[tuple[int, int]]:
    """읽는 차례의 문항 머리 자리 (쪽, 단)."""
    return [(c.page, c.col) for p in layout for c in p.columns for _ in c.heads]


def _by_col(places: list[tuple[int, int]]) -> dict[tuple[int, int], list[int]]:
    out: dict[tuple[int, int], list[int]] = {}
    for k, pl in enumerate(places):
        out.setdefault(pl, []).append(k)
    return out


def _last_content(layout: list[PageLayout]) -> PageLayout:
    content = [p for p in layout if not p.blank]
    if not content:
        raise ValueError("렌더에 본문 내용이 없다")
    return content[-1]


def _limit(kit: Kit) -> float:
    return tail_box_top(kit) - kit.tailbox["room"] / 100.0


def tail_problem(layout: list[PageLayout], kit: Kit) -> str | None:
    """꼬리 박스가 제자리면 None, 문항을 옮겨 풀 문제(빈 쪽·침범)면 까닭. 박스를 못 찾으면 ValueError.

    문항 이동은 빈 쪽과 침범에만 쓴다 — 박스가 안 보이는 것은 배치 문제가 아니라 양식·측정 문제다.
    """
    last = layout[-1]
    if last.blank:
        return f"{last.page}쪽이 빈 쪽이다(꼬리 박스만 앉았다)"
    if last.tail_box is None:
        raise ValueError(f"마지막 쪽({last.page}쪽)에서 꼬리 박스를 찾지 못했다 — 양식·geometry.tail_box_rect를 본다")
    right = last.columns[-1]
    if right.bottom is not None and right.bottom > _limit(kit):
        return f"오른쪽 단 내용이 {right.bottom:.1f}pt까지 와 꼬리 박스 자리({_limit(kit):.1f}pt 위)를 침범한다"
    return None


def pack_columns(h: list[float], gap: float, top, limit: float, tail_limit: float, brk: dict[int, str]) -> list[int] | None:
    """묶음 높이 h(차례대로)를 단 0, 1, 2 …(짝수 = 왼쪽 단)에 나눠 담는다 — 묶음 k의 단 번호 목록, 안 되면 None.

    단 j에 들어가는가: top(j) + 높이 합 + (개수 − 1) × gap ≤ limit(마지막 묶음이 오른쪽 단이면 tail_limit — 꼬리 자리).
    고르는 기준: (넘치는 단 수, 마지막 쪽 번호, 그 쪽들의 모든 단 남는 높이 제곱합) 사전식 최소 — 넘침이 먼저, 그다음 쪽수,
    그다음 고르게. 마지막 단도 세고, 마지막 쪽 오른쪽 단이 비면 그 단(꼬리 자리까지)도 통째로 남는 높이로 센다 — 앞 단에
    몰아 담고 뒤를 비우는 배치보다 모든 단에 고르게 나누는 배치를 고른다("3개 들어갈 만하면 3개, 아니면 2개").
    brk[k] = "column"이면 묶음 k는 단 맨 위, "page"면 새 쪽 왼쪽 단 맨 위(앞 쪽 오른쪽 단이 비어도 된다).
    한 단보다 높은 묶음은 혼자 한 단에 둔다(분할 해소는 뒤 단계).
    """
    n = len(h)
    if n == 0:
        return []
    # best(k, j) = 묶음 k부터를 단 j부터 담는 가장 좋은 배치. 뒤(큰 k, 큰 j)에서 앞으로 표를 채운다(재귀 없음).
    # 단 번호는 묶음마다 많아야 두 칸(단 하나 + 쪽나눔으로 비는 오른쪽 단)에 빈 단 넘김 하나 — 3n + 3이면 넉넉하다.
    J = 3 * n + 3
    memo: dict[tuple[int, int], tuple | None] = {}

    def get(k: int, j: int):
        return memo.get((k, j)) if j <= J else None

    def best(k: int, j: int):
        out = None
        if not (brk.get(k) == "page" and j % 2 and k > 0):
            used = 0.0
            for e in range(k + 1, n + 1):
                if e - 1 > k and (e - 1) in brk:  # 지시가 있는 묶음은 단 맨 위여야 한다
                    break
                used += h[e - 1] + (gap if e - 1 > k else 0.0)
                last = e == n
                cap = (tail_limit if (last and j % 2) else limit) - top(j)
                if used > cap and e - 1 > k:
                    break
                over = 1 if used > cap else 0  # 혼자서도 넘치는 단(분할)은 무엇보다 피한다
                if last:  # 마지막 단도 남는 높이를 센다 — 왼쪽 단에서 끝나면 비는 오른쪽 단(꼬리 자리)도 통째로
                    slack = max(cap - used, 0.0)
                    cost = slack * slack
                    if j % 2 == 0:
                        right = tail_limit - top(j + 1)
                        cost += right * right
                    cand = (over, j // 2 + 1, cost, [j] * (e - k))
                else:
                    forced = brk.get(e) == "page" and (j + 1) % 2  # 쪽나눔 지시로 오른쪽 단 j + 1이 빈다
                    nj = j + 1 + (1 if forced else 0)
                    rest = get(e, nj)
                    if rest is None:
                        if used > cap:
                            break
                        continue
                    slack = max(cap - used, 0.0)
                    cost = slack * slack + rest[2]
                    if forced:  # 지시로 비는 단도 스스로 비운 단(아래)처럼 통째로 남는 높이로 센다
                        empty = limit - top(j + 1)
                        cost += empty * empty
                    cand = (over + rest[0], rest[1], cost, [j] * (e - k) + rest[3])
                if out is None or cand[:3] < out[:3]:
                    out = cand
                if used > cap:  # 혼자서도 넘치는 묶음 — 더 넣지 않는다
                    break
        if j % 2:  # 오른쪽 단을 비우고 새 쪽으로(꼬리 자리가 모자랄 때 — place_tail의 넘김과 같다). 빈 단은 통째로 남는 높이
            rest = get(k, j + 1)
            if rest is not None:
                empty = limit - top(j)
                cand = (rest[0], rest[1], empty * empty + rest[2], rest[3])
                if out is None or cand[:3] < out[:3]:
                    out = cand
        return out

    for k in range(n - 1, -1, -1):
        for j in range(J, -1, -1):
            memo[(k, j)] = best(k, j)
    got = memo[(0, 0)]
    return None if got is None else got[3]


class _Loop:
    def __init__(self, doc: HwpxDocument, kit: Kit, hwpx: Path, out_dir: Path, render_fn, scan: Scan | None = None,
                 lines_fn=None):
        self.doc, self.kit, self.hwpx, self.out_dir, self.render_fn = doc, kit, Path(hwpx), Path(out_dir), render_fn
        self.scan = scan
        self.lines_fn = lines_fn
        self.fitted = FitResult()
        self.pinned: list = []  # 원고 나눔 지시 문단(pin_directed)
        self.balanced: list | None = None  # 균형 배치가 박은 자리(쪽, 단)
        self.hwpx.parent.mkdir(parents=True, exist_ok=True)
        self.n = 0
        self.notes: list[str] = []
        self.kept_wraps: dict[int, int] = {}  # 접혔지만 그대로 둔 문항(눌러 둔 형·scan 없음) → 그 note의 notes 자리 — note는 한 번
        self.moved_from: set[tuple[int, int]] = set()  # 꼬리 자리 때문에 문항을 다음 쪽으로 넘겨 보낸 단(쪽, 단) — 나눔 제외

    # ⓪ 접힌 답지
    def fix_wraps(self, rr, lay, rounds: int):
        answer_key = next(self.doc.sections[0].element.iter(q("hp", "markpenBegin")), None) is not None
        for _ in range(rounds):
            changed = False
            for k, kind in wrapped_choices(self.doc, rr.pdf, self.kit):
                qn = self.scan.questions[k] if self.scan is not None else None
                if qn is None or qn.override:
                    if k not in self.kept_wraps:
                        why = f"눌러 둔 형({{답항={qn.override}}})이라 그대로 둔다" if qn is not None else "원고(scan)가 없어 다시 쓸 수 없다"
                        self.kept_wraps[k] = len(self.notes)  # note 자리 — 뒤에 풀리면 이 note를 고친다(M-6)
                        self.notes.append(f"{k + 1}번 답지가 {kind}에서 칸을 넘었다(접힘·칸 어긋남) — {why}")
                    continue
                looser = LOOSER[kind]
                relayout_choices(self.doc, self.kit, qn, looser, answer_key=answer_key)
                self.notes.append(f"{k + 1}번 답지가 {kind}에서 칸을 넘어(접힘·칸 어긋남) {looser}으로 바꿨다(렌더 확인)")
                changed = True
            if not changed:
                return rr, lay
            rr, lay = self.render()
        return rr, lay

    # ⓪' 자간 맞춤
    def fit(self, rr, lay):
        def save() -> Path:
            self.doc.save_to_path(str(self.hwpx))
            return self.hwpx

        work = self.out_dir / "자간"
        res = fit_spacing(self.doc, self.kit, save, lambda p, n: self.lines_fn(p, work / f"m{n}"))
        self.fitted = res
        resized = 0
        if any(t.role in ("보기", "자료") for t in targets(self.doc, self.kit)):
            # 박스 셀 높이를 실제 줄 수로(한글은 셀을 줄이지 않는다 — 자간으로 당긴 항목 아래가 빈다, Task 29)
            res.rounds += 1
            resized = resize_boxes(self.doc, self.kit, self.lines_fn(save(), work / f"m{res.rounds}"))
        for n in range(1, res.rounds):  # 측정 사본은 마지막 것만 남긴다(M-7)
            shutil.rmtree(work / f"m{n}", ignore_errors=True)
        for t, ln in res.failed:
            self.notes.append(f"{t.number}번 {t.role} 끝줄이 짧은데 자간 {floor_for(self.kit, t.role)}%까지 줄여도 "
                              f"줄이 줄지 않았다(끝줄 {ln.tail.strip()!r}) — 그대로 둔다")
        if not res.done and not resized:
            return rr, lay
        return self.render()

    def pin_directed(self) -> None:
        """원고 나눔 지시({단나눔}·{쪽나눔})로 조판이 넣은 나눔 — 루프 시작 때 문항 묶음 첫 문단에 이미 있는 나눔. 루프는
        이 문단의 나눔을 바꾸거나 지우지 않는다(_brk). 문단 요소로 기억한다 — 답지를 다시 쓰면 인덱스가 밀린다."""
        ps = self.ps
        self.pinned = [ps[i].element for i in group_starts(self.doc)
                       if "1" in (ps[i].element.get("columnBreak"), ps[i].element.get("pageBreak"))]

    def is_pinned(self, index: int) -> bool:
        el = self.ps[index].element
        return any(el is p for p in self.pinned)

    def _brk(self, index: int, kind: str | None) -> bool:
        """set_break — 지시된 나눔 문단이면 손대지 않고 False."""
        return False if self.is_pinned(index) else set_break(self.doc, index, kind)

    @property
    def ps(self) -> list:
        return list(self.doc.sections[0].paragraphs)

    def render(self) -> tuple[RenderResult, list[PageLayout]]:
        self.n += 1
        self.doc.save_to_path(str(self.hwpx))
        rr = self.render_fn(self.hwpx, self.out_dir / f"r{self.n}")
        lay = measure(rr.pdf, self.kit)
        heads = head_places(lay)
        m = len(question_heads(self.doc))
        if len(heads) != m:
            raise ValueError(f"렌더 {self.n}회차: 렌더에서 찾은 문항 머리 {len(heads)}개 ≠ 문서의 문항 {m}개 — 머리 판정(geometry.is_head)을 본다")
        return rr, lay

    def _set_prev(self, index: int, base: str, prev: int) -> bool:
        el = self.ps[index].element
        pid = derive_para_pr(self.doc.headers[0], base, prev=prev)
        if el.get("paraPrIDRef") == pid:
            return False
        el.set("paraPrIDRef", pid)
        return True

    def _restore(self, original: dict[int, str]) -> None:
        ps = self.ps
        for i, pid in original.items():
            ps[i].element.set("paraPrIDRef", pid)
        self.doc.sections[0].mark_dirty()  # 저장은 dirty 절만 쓴다 — 빠뜨리면 되돌림이 파일에 안 닿는다

    # ⓪'' 균형 배치
    def plan_columns(self, rr, lay) -> list[int] | None:
        """렌더에서 잰 묶음 높이로 단 나눔을 고른다 — 묶음 k가 앉을 단 번호(0 = 1쪽 왼쪽, 1 = 1쪽 오른쪽, 2 = 2쪽 왼쪽 …).

        차례는 그대로다. 쪽수가 가장 적은 배치 가운데, 마지막 단을 뺀 단마다 남는 높이의 제곱합이 가장 작은 것(동적 계획법).
        단에 들어가는가 = 단 윗끝 + 높이 합 + 사이 간격 ≤ 단 한계(본문 하단 − DIST_SAFETY, 마지막 쪽 오른쪽 단은 꼬리 자리 한계).
        원고 나눔 지시({단나눔}은 새 단, {쪽나눔}은 새 쪽 왼쪽 단)는 제약이다. 한 단보다 높은 묶음은 혼자 한 단(분할은 ①이 본다).
        """
        starts = group_starts(self.doc)
        heads = question_heads(self.doc)
        n = len(starts)
        if n < 2:
            return None
        set_first = {k for k in range(n) if starts[k] != heads[k]}
        ext = group_extents(rr.pdf, self.kit, set_first)
        if len(ext) != n:
            self.notes.append(f"균형 배치: 렌더에서 잰 묶음 {len(ext)}개 ≠ 문항 {n}개 — 건너뛴다")
            return None
        h = [e.height for e in ext]
        gaps = [b.top[2] - a.segments[-1][3] for a, b in zip(ext, ext[1:])
                if len(a.segments) == 1 and a.segments[-1][:2] == b.top[:2]]
        gap = sorted(gaps)[len(gaps) // 2] if gaps else self.kit.question_gap / 100.0 + LINE_PT - 11.0
        ps = self.ps
        brk = {}
        for k, i in enumerate(starts):
            el = ps[i].element
            if any(el is p for p in self.pinned):
                brk[k] = "page" if el.get("pageBreak") == "1" else "column"
        first_top = ext[0].top[2]
        page_top = {c.page: c.top for p in lay for c in p.columns}
        # 단 맨 위 묶음의 윗끝 = 본문 상단 + 글리프 여백 + 위 간격(이 렌더에서는 아직 있다 — ③이 뒤에 뺀다, 그만큼 여유)
        lead = 2.0 + self.kit.question_gap / 100.0
        other_top = page_top.get(2, page_top.get(1)) + lead
        limit, tail_limit = body_bottom(self.kit) - DIST_SAFETY, _limit(self.kit)

        def top(j: int) -> float:
            if j == 0:
                return first_top
            p = j // 2 + 1
            return (page_top[p] + lead) if p in page_top and p > 1 else (page_top[1] + lead if p == 1 else other_top)

        return pack_columns(h, gap, top, limit, tail_limit, brk)

    def apply_columns(self, plan: list[int]) -> bool:
        """계획의 단 나눔을 박는다 — 단의 첫 묶음은 단(오른쪽 단)·쪽(왼쪽 단) 나눔, 나머지는 나눔 없음(지시는 그대로)."""
        starts = group_starts(self.doc)
        changed = False
        for k, i in enumerate(starts):
            if k == 0:
                continue
            kind = None if plan[k] == plan[k - 1] else ("page" if plan[k] % 2 == 0 else "column")
            changed |= self._brk(i, kind)
        if changed:
            self.doc.sections[0].mark_dirty()
        return changed

    def balance(self, rr, lay, rounds: int = 2):
        """⓪'' 균형 배치(Task 30) — plan_columns를 박고 재렌더. 자리가 계획과 다르면(높이 추정 오차) 새 렌더로 다시 한 번.
        두 번 다 다르면 박은 나눔을 거두고(지시 나눔은 그대로) 원래 흐름으로 되돌린다 — 틀린 계획을 남기지 않는다."""
        before = {i: (self.ps[i].element.get("columnBreak"), self.ps[i].element.get("pageBreak")) for i in group_starts(self.doc)}
        for n in range(rounds):
            plan = self.plan_columns(rr, lay)
            if plan is None:
                if n == 0:  # 잴 수 없거나 담을 수 없다 — 아직 박은 것이 없다
                    return rr, lay
                break  # 앞 회차에 박은 나눔이 있다 — 되돌린다
            want = [(j // 2 + 1, j % 2 + 1) for j in plan]
            if head_places(lay) == want:
                return rr, lay
            if not self.apply_columns(plan):
                if n == 0:  # 박을 것이 없다 — 지금 나눔 그대로(추정만 틀렸다), 되돌릴 것도 없다
                    return rr, lay
                break  # 같은 계획을 이미 박았는데 자리가 또 다르다 — 두 번째 어긋남으로 보고 되돌린다
            rr, lay = self.render()
            if head_places(lay) == want:
                self.balanced = want
                return rr, lay
        for i, (col, page) in before.items():  # 되돌림
            if not self.is_pinned(i):
                set_break(self.doc, i, "column" if col == "1" else "page" if page == "1" else None)
        self.notes.append("균형 배치: 계획한 단 나눔과 렌더 자리가 두 번 다 달라 원래 흐름으로 되돌렸다")
        return self.render()

    # ① 분할
    def resolve_splits(self, rr, lay, rounds: int):
        for _ in range(rounds):
            sp = splits(rr.pdf, self.kit)
            if not sp:
                return rr, lay
            starts, places = group_starts(self.doc), head_places(lay)
            moved = False
            for p, c, _dx in sp:
                ks = [k for k, pl in enumerate(places) if pl < (p, c)]
                if not ks:
                    continue
                k = ks[-1]
                col = lay[places[k][0] - 1].columns[places[k][1] - 1]
                if places.index(places[k]) == k and col.first_is_head:  # 이미 단 맨 위에서 시작하는 묶음
                    self.notes.append(f"{k + 1}번 문항이 한 단보다 길어 나뉜다({p}쪽 {c}단) — 나눔으로 풀 수 없다")
                    continue
                moved |= self._brk(starts[k], "page" if c == 1 else "column")
            if not moved:
                return rr, lay
            rr, lay = self.render()
        left = splits(rr.pdf, self.kit)
        if left:
            self.notes.append(f"문항 분할 {len(left)}곳이 {rounds}회 뒤에도 남았다: {left}")
        return rr, lay

    # ②-1 넘친 단 간격 줄이기
    def squeeze(self, rr, lay):
        """마지막 쪽 오른쪽 단의 문항 간격(단 맨 위 제외)을 하한까지 줄여 꼬리 자리를 만든다 — 되면 렌더, 안 되면 None.

        그 단만 줄인다: 단 맨 위 문항마다 나눔이 박혀 있어(③이 꼬리보다 먼저) 왼쪽 단을 줄여도 오른쪽 단 문항이 당겨지지
        않는다. 넘침이 줄일 수 있는 양(간격 − 하한의 합)보다 크면 렌더하지 않고 note만 남긴다.
        """
        g, gmin = self.kit.question_gap, self.kit.question_gap_min
        if gmin >= g:
            return None
        last = _last_content(lay)
        right = last.columns[-1]
        if right.bottom is None:
            return None
        starts, places = group_starts(self.doc), head_places(lay)
        right_ks = _by_col(places).get((last.page, right.col), [])
        if len(right_ks) < 2:
            return None
        header, ps = self.doc.headers[0], self.ps
        need = (right.bottom - _limit(self.kit)) * 100
        room = sum(max(0, case_prev(header, ps[starts[k]].element.get("paraPrIDRef")) - gmin) for k in right_ks[1:])
        if need + SQUEEZE_SAFETY > room:
            self.notes.append(f"꼬리 박스 자리: {last.page}쪽 오른쪽 단이 {need / 100:.1f}pt 넘쳐 간격 줄이기(하한 {gmin}, "
                              f"줄일 수 있는 양 {room / 100:.1f}pt)로는 모자라 줄이지 않았다")
            return None
        new = max(gmin, g - math.ceil(need / (len(right_ks) - 1)) - SQUEEZE_SAFETY)
        original: dict[int, str] = {}
        for k in right_ks[1:]:
            i = starts[k]
            base = ps[i].element.get("paraPrIDRef")
            if case_prev(header, base) > new:
                original[i] = base
                self._set_prev(i, base, new)
        if not original:
            return None
        self.doc.sections[0].mark_dirty()
        rr2, lay2 = self.render()
        if tail_problem(lay2, self.kit) is None:
            self.notes.append(f"꼬리 박스 자리를 만들려고 {last.page}쪽 오른쪽 단 문항 간격을 {g} → {new}로 줄였다(하한 {gmin})")
            return rr2, lay2
        self._restore(original)
        return None

    # ②-2 꼬리 박스
    def place_tail(self, rr, lay, rounds: int):
        if tail_problem(lay, self.kit) is None:
            return rr, lay
        got = self.squeeze(rr, lay)
        if got is not None:
            return got
        pages_before = _last_content(lay).page
        moved: list[int] = []
        for _ in range(rounds):
            why = tail_problem(lay, self.kit)
            if why is None:
                break
            last = _last_content(lay)
            places = head_places(lay)
            ks = [k for k, pl in enumerate(places) if pl == (last.page, len(last.columns))]
            if not ks:
                ks = [k for k, pl in enumerate(places) if pl <= (last.page, len(last.columns))][-1:]
            if not ks or ks[-1] == 0:
                self.notes.append(f"꼬리 박스 자리를 만들 수 없다: {why}")
                break
            k = ks[-1]
            self.moved_from.add(places[k])
            if self.is_pinned(group_starts(self.doc)[k]):
                self.notes.append(f"꼬리 박스 자리: {k + 1}번에 원고 나눔 지시가 있어 옮기지 않는다 — {why}")
                break
            self._brk(group_starts(self.doc)[k], "page")
            if k + 1 not in moved:
                moved.append(k + 1)
            rr, lay = self.render()
        else:
            why = tail_problem(lay, self.kit)
            if why is not None:
                self.notes.append(f"꼬리 박스 자리를 {rounds}회 안에 만들지 못했다: {why}")
        if moved:
            after = len(lay)
            self.notes.append(f"꼬리 박스 자리가 없어 {', '.join(f'{k}번' for k in moved)}을 다음 쪽으로 넘겼다 — "
                              f"쪽 {pages_before} → {after}" + (" (쪽 추가: 최후 수단)" if after > pages_before else ""))
        return rr, lay

    # ③ 단 맨 위 간격 0
    def zero_tops(self, rr, lay):
        starts, places = group_starts(self.doc), head_places(lay)
        split_cols = {(p, c) for p, c, _ in splits(rr.pdf, self.kit)}
        ps = self.ps
        changed = False
        for (p, c), ks in _by_col(places).items():
            if (p, c) == (1, 1) or (p, c) in split_cols or ks[0] == 0:
                continue
            i = starts[ks[0]]
            changed |= self._brk(i, "page" if c == 1 else "column")  # 흐름 고정 — 간격을 빼도 문항이 앞 단으로 안 당겨진다
            changed |= self._set_prev(i, ps[i].element.get("paraPrIDRef"), 0)
        if not changed:
            return rr, lay
        self.doc.sections[0].mark_dirty()
        rr2, lay2 = self.render()
        if head_places(lay2) != places:
            self.notes.append("단 맨 위 간격을 뺐더니 문항 배치가 바뀌었다(나눔 고정이 안 먹었다)")
        return rr2, lay2

    # ④ 간격 나눔
    def distribute(self, rr, lay, rounds: int):
        ps = self.ps
        header = self.doc.headers[0]
        starts, places = group_starts(self.doc), head_places(lay)
        split_cols = {(p, c) for p, c, _ in splits(rr.pdf, self.kit)}
        by_col = _by_col(places)
        tail_col = (len(lay), 2)  # 꼬리 박스가 앉는 단 — 마지막 쪽 오른쪽 단
        for (p, c), ks in by_col.items():  # 흐름 고정(zero_tops가 이미 박았으면 그대로)
            if (p, c) != (1, 1) and (p, c) not in split_cols and ks[0] > 0:
                self._brk(starts[ks[0]], "page" if c == 1 else "column")
        original = {starts[k]: ps[starts[k]].element.get("paraPrIDRef") for k in range(len(starts))}
        safety = DIST_SAFETY
        for _ in range(rounds):
            for (p, c), ks in by_col.items():
                if (p, c) in self.moved_from or len(ks) < 2:  # 한 문항 단·꼬리 때문에 넘겨 보낸 단은 위에 붙인 채로
                    continue
                col = lay[p - 1].columns[c - 1]
                # 단 아래 맞춤(Task 31): 마지막 문항 끝이 단 한계에 닿게 — 꼬리 단은 꼬리 박스 위 여유(_limit)까지
                floor = _limit(self.kit) if (p, c) == tail_col else body_bottom(self.kit)
                slack = floor - col.bottom - safety
                if slack <= 0:
                    continue
                extra = int(slack * 100 / (len(ks) - 1))
                if self.kit.gap_extra_max is not None:  # 간격 상한(Task 30) — 넘는 몫은 단 아래에 남긴다
                    extra = min(extra, self.kit.gap_extra_max)
                for k in ks[1:]:
                    i = starts[k]
                    self._set_prev(i, original[i], case_prev(header, original[i]) + extra)
            self.doc.sections[0].mark_dirty()
            rr2, lay2 = self.render()
            if (head_places(lay2) == places and len(lay2) == len(lay) and tail_problem(lay2, self.kit) is None
                    and not splits(rr2.pdf, self.kit)):  # 나눈 간격으로 문항이 단을 넘어 나뉘면 되돌린다
                return rr2, lay2
            self._restore(original)  # 넘쳤다 — 되돌리고 한 줄 더 남겨 다시
            safety += LINE_PT
        self.notes.append(f"간격 나눔이 {rounds}회 안에 배치를 지키지 못해 고정 간격으로 되돌렸다")
        return self.render()


def settle(doc: HwpxDocument, kit: Kit, hwpx: Path, out_dir: Path, *, gap: str = "distribute",
           render_fn=render, rounds: int = 3, scan: Scan | None = None, fit: bool = True, lines_fn=None,
           balance: bool = True) -> Settled:
    """finalize_form을 거친 문서를 렌더 루프로 굳혀 hwpx에 저장한다 — 총쪽수 누름틀까지 채운 최종 렌더를 돌려준다.

    scan(조판에 쓴 원고)이 있으면 접힌 답지를 느슨한 형으로 다시 쓴다. 없으면 접힘을 note로만 남긴다.
    fit이면 자간 맞춤(⓪'). lines_fn(hwpx, 작업 폴더) → 줄 캐시(fit.Lines) — 기본은 한컴 저장 사본(fit.hancom_lines).
    """
    if gap not in GAPS:
        raise ValueError(f"gap은 {GAPS} 가운데 하나: {gap!r}")
    if scan is not None and len(scan.questions) != len(question_heads(doc)):
        raise ValueError(f"원고(scan) 문항 {len(scan.questions)}개 ≠ 문서 문항 {len(question_heads(doc))}개 — 다른 원고다")
    loop = _Loop(doc, kit, hwpx, out_dir, render_fn, scan, lines_fn or hancom_lines)
    loop.pin_directed()
    rr, lay = loop.render()
    first_pages = _last_content(lay).page
    rr, lay = loop.fix_wraps(rr, lay, rounds)
    if fit:
        rr, lay = loop.fit(rr, lay)  # 답지를 다시 쓴 뒤에(다시 쓰면 자간이 사라진다), 높이를 쓰는 단계들 앞에
    if balance:
        rr, lay = loop.balance(rr, lay)  # 자간 맞춤으로 높이가 굳은 뒤, 분할·꼬리·간격 전에
    rr, lay = loop.resolve_splits(rr, lay, rounds)
    rr, lay = loop.zero_tops(rr, lay)   # 꼬리 판단 전에: 단 맨 위 간격(≈18pt)을 뺀 자리까지 보고 넘길지 정한다
    rr, lay = loop.place_tail(rr, lay, rounds)
    rr, lay = loop.zero_tops(rr, lay)   # 꼬리 때문에 새 쪽으로 넘긴 문항도 맨 위 간격 0
    if gap == "distribute":
        rr, lay = loop.distribute(rr, lay, rounds)
    if read_total_pages(doc, kit) != str(rr.page_count):
        pages = rr.page_count
        fill_total_pages(doc, kit, pages)
        rr, lay = loop.render()
        if rr.page_count != pages:
            loop.notes.append(f"총쪽수를 {pages}로 채웠더니 렌더 쪽수가 {rr.page_count}로 바뀌었다")
    left = splits(rr.pdf, kit)  # 최종 렌더 재검사
    if left:
        loop.notes.append(f"최종 렌더에 문항 분할이 남았다: {left}")
    why = tail_problem(lay, kit)
    if why is not None:
        loop.notes.append(f"최종 렌더의 꼬리 박스가 제자리가 아니다: {why}")
    wrapped = {k for k, _ in wrapped_choices(doc, rr.pdf, kit)}
    still = sorted(k + 1 for k in wrapped - loop.kept_wraps.keys())
    if still:
        loop.notes.append(f"최종 렌더에 접힌 답지 줄이 남았다: {still}번")
    for k, at in loop.kept_wraps.items():  # ⓪에서 그대로 둔 접힘이 뒤 단계(자간 맞춤 등) 뒤에 풀렸다 — 그 note를 고친다(M-6)
        if k not in wrapped:
            loop.notes[at] += " → 최종 렌더에서는 풀렸다(자간 맞춤 뒤)"
    return Settled(render=rr, layout=lay, notes=loop.notes, renders=loop.n, first_pages=first_pages,
                   spacing=loop.fitted.done, spacing_words=loop.fitted.words, measures=loop.fitted.rounds)
