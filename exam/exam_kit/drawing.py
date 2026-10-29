"""원고에 좌표로 적은 도형(`:::도형`) — 한/글 그리기 개체(선·면·곡선)와 얹은 글자로 하나하나 따로 조판한다(10-29 owner).

그림 파일 한 장으로 넣으면 한/글에서 선분·글자를 따로 고칠 수 없다. 좌표로 적으면 엔진이 개체마다 따로 그려, 교사가
한/글에서 선 하나·글자 하나를 집어 옮기거나 지울 수 있고, 비율도 좌표대로 정확하다(수학 교사: GPT로 비율을 못 맞췄다).

    :::도형 width=5cm height=4cm
    점 A 2.5 0.35 위            점 이름·좌표(cm, 틀 왼쪽 위 기준, 아래로 +)·이름 놓을 쪽(없음이면 -)
    면 ABC 옅게                 채운 면 — 옅게·중간·짙게(흑백 인쇄 회색 단계)
    선 AB AC BC                 실선
    점선 BD                     보이지 않는 선·보조선
    길이 BC 8 왼쪽              두 점을 잇는 점선 호 + 숫자(B→C 진행 방향의 왼쪽·오른쪽으로 휜다) — 숫자는 `$…$`도 된다
    직각 H PA                   H에서 P 쪽·A 쪽 두 변에 직각 표시
    ● B                         점 찍기(이름 있는 점 또는 `● x y`)
    곡선 0.5 3 1.2 2 2.5 1.6    좌표를 지나는 매끄러운 곡선(`곡선 점선 …`이면 점선)
    $y^2=3x$ {x=3.2cm y=0.8cm}  자유 글자(그림 위 얹기 문법 그대로)
    :::

점 이름은 대문자 하나 + 선택 프라임(`A`, `A'`) — 글자는 정자(`\\mathrm{A'}`)로 얹는다. 관례(교사 원안지·10-26 답): 숨은 선은 점선,
길이는 점선 호 + 숫자, 점 이름은 문제 수식과 같은 글꼴·크기.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .scan import OVERLAY_RE, Block, Overlay

방향 = {"위": (0, -1), "아래": (0, 1), "왼쪽": (-1, 0), "오른쪽": (1, 0),
        "왼쪽위": (-1, -1), "오른쪽위": (1, -1), "왼쪽아래": (-1, 1), "오른쪽아래": (1, 1)}
채움 = {"옅게": "#E8E8E8", "중간": "#C8C8C8", "짙게": "#9A9A9A"}  # 흑백 인쇄 회색 단계 — 이웃 단계가 뚜렷이 다르게
_이름 = r"[A-Z]'?"
_수 = r"-?\d+(?:\.\d+)?"
_점_RE = re.compile(rf"^점\s+(?P<n>{_이름})\s+(?P<x>{_수})\s+(?P<y>{_수})(?:\s+(?P<d>\S+))?\s*$")
_이음_RE = re.compile(rf"^(?P<kind>선|점선)\s+(?P<pairs>(?:(?:{_이름}){{2}}\s*)+)$")
_면_RE = re.compile(rf"^면\s+(?P<ns>(?:{_이름}){{3,}})(?:\s+(?P<shade>\S+))?\s*$")
_길이_RE = re.compile(rf"^길이\s+(?P<ab>(?:{_이름}){{2}})\s+(?P<label>\$.+\$|\S+)\s+(?P<side>왼쪽|오른쪽)\s*$")
_직각_RE = re.compile(rf"^직각\s+(?P<h>{_이름})\s+(?P<legs>(?:{_이름}){{2}})\s*$")
_점찍기_RE = re.compile(rf"^●\s+(?:(?P<n>{_이름})|(?P<x>{_수})\s+(?P<y>{_수}))\s*$")
_곡선_RE = re.compile(rf"^곡선(?P<dash>\s+점선)?(?P<nums>(?:\s+{_수})+)\s*$")
_CM_RE = re.compile(r"^(\d+(?:\.\d+)?)cm$")


def names(s: str) -> list[str]:
    return re.findall(_이름, s)


@dataclass
class Drawing:
    width_cm: float
    height_cm: float
    points: dict[str, tuple[float, float]] = field(default_factory=dict)
    label_dir: dict[str, str | None] = field(default_factory=dict)
    lines: list[tuple[str, str, bool]] = field(default_factory=list)          # (a, b, 점선?)
    faces: list[tuple[list[str], str]] = field(default_factory=list)          # (점들, 채움 색)
    lengths: list[tuple[str, str, str, str]] = field(default_factory=list)    # (a, b, LaTeX, 왼쪽|오른쪽)
    rights: list[tuple[str, str, str]] = field(default_factory=list)          # (꼭짓점, 변 끝 1, 변 끝 2)
    dots: list = field(default_factory=list)  # (x, y) — 파싱 중에는 이름 있는 점이 ("이름", 이름)
    curves: list[tuple[list[tuple[float, float]], bool]] = field(default_factory=list)
    labels: list[Overlay] = field(default_factory=list)                       # 자유 글자
    bad: list[str] = field(default_factory=list)                              # 귀속 불가 줄·까닭


def parse(block: Block) -> Drawing:
    """`:::도형` 블록 → Drawing. 틀어진 줄은 bad에 (줄, 까닭)으로 — 원고 검사 E029가 알린다."""
    w, h = (_cm(block.attrs.get(k)) for k in ("width", "height"))
    d = Drawing(w or 0.0, h or 0.0)
    if w is None or h is None:
        d.bad.append(f":::도형에 width=…cm height=…cm가 없다 — {block.attrs}")
    pending: list[tuple[str, list[str]]] = []  # 점 정의 뒤에 확인할 이름

    for raw in block.lines:
        s = raw.strip()
        if not s:
            continue
        if m := _점_RE.match(s):
            n, dr = m.group("n"), m.group("d")
            if dr is not None and dr != "-" and dr not in 방향:
                d.bad.append(f"{s} — 이름 놓을 쪽 {dr!r}: {'·'.join(방향)} 또는 -")
                dr = None
            if n in d.points:
                d.bad.append(f"{s} — 점 {n}이 두 번 정의됐다")
            d.points[n] = (float(m.group("x")), float(m.group("y")))
            d.label_dir[n] = None if dr in (None, "-") else dr
        elif m := _이음_RE.match(s):
            ns = names(m.group("pairs").replace(" ", ""))
            for a, b in zip(ns[::2], ns[1::2]):
                d.lines.append((a, b, m.group("kind") == "점선"))
            pending.append((s, ns))
        elif m := _면_RE.match(s):
            shade = m.group("shade") or "옅게"
            if shade not in 채움:
                d.bad.append(f"{s} — 채움 {shade!r}: {'·'.join(채움)}")
                shade = "옅게"
            ns = names(m.group("ns"))
            d.faces.append((ns, 채움[shade]))
            pending.append((s, ns))
        elif m := _길이_RE.match(s):
            a, b = names(m.group("ab"))
            label = m.group("label")
            d.lengths.append((a, b, label[1:-1].strip() if label.startswith("$") else label, m.group("side")))
            pending.append((s, [a, b]))
        elif m := _직각_RE.match(s):
            p, q = names(m.group("legs"))
            d.rights.append((m.group("h"), p, q))
            pending.append((s, [m.group("h"), p, q]))
        elif m := _점찍기_RE.match(s):
            if m.group("n"):
                pending.append((s, [m.group("n")]))
                d.dots.append(("이름", m.group("n")))  # 이름은 아래에서 좌표로
            else:
                d.dots.append((float(m.group("x")), float(m.group("y"))))
        elif m := _곡선_RE.match(s):
            nums = [float(x) for x in m.group("nums").split()]
            if len(nums) % 2 or len(nums) < 6:
                d.bad.append(f"{s} — 곡선은 좌표 셋 이상(x y 짝)")
            else:
                d.curves.append((list(zip(nums[::2], nums[1::2])), bool(m.group("dash"))))
        elif OVERLAY_RE.match(s):
            m = OVERLAY_RE.match(s)
            what = m.group("what")
            d.labels.append(Overlay("점", None, float(m.group("x")), float(m.group("y"))) if what == "●"
                            else Overlay("글자", what[1:-1].strip(), float(m.group("x")), float(m.group("y"))))
        else:
            d.bad.append(f"{s} — 모르는 줄(점·선·점선·면·길이·직각·●·곡선·`$…$ {{x=…cm y=…cm}}`)")
    for s, ns in pending:
        missing = [n for n in ns if n not in d.points]
        if missing:
            d.bad.append(f"{s} — 정의하지 않은 점 {', '.join(missing)}")
    d.dots = [d.points.get(x[1], (0.0, 0.0)) if x and x[0] == "이름" else x for x in d.dots]
    for n, (x, y) in d.points.items():
        if not (0 <= x <= d.width_cm and 0 <= y <= d.height_cm):
            d.bad.append(f"점 {n} ({x}, {y}) — 틀({d.width_cm}×{d.height_cm}cm) 밖이다")
    return d


def _cm(v: str | None) -> float | None:
    m = _CM_RE.match(v or "")
    return float(m.group(1)) if m else None


# ---- 기하(cm, 틀 왼쪽 위 기준, 아래로 +) ---------------------------------------------------------------

def unit(dx: float, dy: float) -> tuple[float, float]:
    r = math.hypot(dx, dy) or 1.0
    return dx / r, dy / r


def length_arc(p: tuple[float, float], q: tuple[float, float], side: str) -> tuple[list[tuple[float, float]], tuple[float, float]]:
    """길이 표시 점선 호 — (지나는 점 셋, 휜 쪽 단위 법선). p→q 진행 방향의 왼쪽(화면에서 반시계 쪽)이 '왼쪽'이다."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    ux, uy = unit(dx, dy)
    nx, ny = (uy, -ux) if side == "왼쪽" else (-uy, ux)  # 화면 좌표(아래로 +)에서 진행 방향 왼쪽 = (uy, -ux)
    bulge = max(0.25, 0.18 * math.hypot(dx, dy))
    mid = ((p[0] + q[0]) / 2 + nx * bulge, (p[1] + q[1]) / 2 + ny * bulge)
    return [p, mid, q], (nx, ny)


def right_mark(h: tuple[float, float], a: tuple[float, float], b: tuple[float, float], size: float = 0.25):
    """직각 표시 두 변 — 꼭짓점 h에서 a·b 쪽으로 size만큼 간 두 점과 그 합으로 만든 작은 사각형의 바깥 두 변."""
    ux, uy = unit(a[0] - h[0], a[1] - h[1])
    vx, vy = unit(b[0] - h[0], b[1] - h[1])
    p1 = (h[0] + ux * size, h[1] + uy * size)
    p2 = (h[0] + vx * size, h[1] + vy * size)
    c = (h[0] + (ux + vx) * size, h[1] + (uy + vy) * size)
    return [(p1, c), (c, p2)]


def segments(d: Drawing) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """겹침 검사에 쓸 그린 선분들(선·점선·면 테두리·곡선 꺾은선 근사)."""
    out = [(d.points[a], d.points[b]) for a, b, _ in d.lines if a in d.points and b in d.points]
    for ns, _ in d.faces:
        ps = [d.points[n] for n in ns if n in d.points]
        out += list(zip(ps, ps[1:] + ps[:1]))
    for ps, _ in d.curves:
        out += list(zip(ps, ps[1:]))
    return out


def hits_box(seg, box) -> bool:
    """선분이 상자(x0, y0, x1, y1)와 만나는가 — Liang–Barsky."""
    (x1, y1), (x2, y2) = seg
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, qv in ((-dx, x1 - box[0]), (dx, box[2] - x1), (-dy, y1 - box[1]), (dy, box[3] - y1)):
        if p == 0:
            if qv < 0:
                return False
            continue
        t = qv / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True
