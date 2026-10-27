"""원고의 인라인 수식 `$…$`(LaTeX) — 한/글 수식(hp:equation)으로 조판한다. 1차는 인라인 수식만이다.

- 표기: `$…$` 안이 LaTeX다. 달러 글자는 `\\$`로 쓴다. `$$…$$`(한 줄 가운데 블록 수식)는 아직 조판하지 않는다.
- 변환: python-hwpx `hwpx.experimental.latex_to_eqedit`(LaTeX → 한/글 수식 문자열). 바꿀 수 없는 LaTeX는 조용히 넘기지 않고
  오류다(원고 규칙 E025). experimental 표면이라 계약이 바뀔 수 있다 — 엔진 테스트가 동작을 고정한다.
- 크기: `estimate_equation_size`(수식 구조로 잰 상자, python-hwpx 6.6.0). 조판은 문단 래퍼 `add_equation`이 같은 측정으로
  hp:sz를 적는다. 줄에서 수식이 차지하는 폭 = 상자 폭 + 좌우 바깥 여백(add_equation의 hp:outMargin).
- 가린 글(mask): 수식 하나를 사용자 영역 글자 하나(U+F0000 + 차례)로 바꾼 글이다. 밑줄 `__…__`·낱말 나누기·폭 추정이
  수식 안의 글자를 건드리지 않게 한다. 달러 글자(`\\$`)는 가린 글에서 `$`다.
- 한/글 줄 캐시(hp:lineseg textpos)는 수식 하나를 8글자 자리로 센다(한/글 컨트롤과 같다, 합성 식 저장본 실측).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from hwpx.equation import EquationConversionError
from hwpx.experimental import estimate_equation_size, latex_to_eqedit

바깥_여백 = 56  # add_equation이 적는 hp:outMargin left·right(HWPUNIT)
TEXTPOS = 8     # 한/글 줄 캐시에서 수식 하나가 차지하는 글자 자리
_자리0, _자리_끝 = 0xF0000, 0xFFFFE  # 가린 글의 수식 자리(보충 사용자 영역 A)
_줄_폭0 = 0x100000                  # 줄 캐시 글의 수식 첫 글자(보충 사용자 영역 B) — 폭을 담는다
_폭_없음 = "​"


class MathError(ValueError):
    """원고 수식 표기 오류 — 닫히지 않은 `$`, 빈 수식, 블록 수식 `$$`, 한/글 수식으로 바꿀 수 없는 LaTeX."""


@dataclass(frozen=True)
class Math:
    latex: str   # `$…$` 안(앞뒤 공백 없이)
    script: str  # 한/글 수식 문자열(hp:script)

    @property
    def source(self) -> str:
        return f"${self.latex}$"


# 한/글 수식의 글꼴 명령 rm + 대문자(점 이름). 한/글은 `rmA`·`rm A` 둘 다 정자 A로 찍는다(교사 원안지 실물). python-hwpx 6.8.0은
# 두 꼴을 다르게 다룬다 — 폭 어림은 붙은 꼴을 한 낱말(r·m·A)로 읽어 세 배쯤 넓게 잡고(`rmA` 2431 vs 한/글 825 HWPUNIT: 그림
# 위 점 이름이 0.30cm 밀렸다, 10-26 렌더), LaTeX 되돌림은 rm을 옮기지 않아 띄운 꼴은 `rm A` → 다시 한/글 수식 `"rm" A`(글자
# rm이 찍힌다)가 된다. 그래서 문서에는 띄운 꼴(spaced — 폭이 맞는다), 원고 LaTeX에는 붙은 꼴(glued — 그대로 왕복한다)을 쓴다.
# 상류가 rm을 \mathrm으로 옮기면 걷는다.
_붙은_rm = re.compile(r"(?<![A-Za-z])rm(?=[A-Z])")
_띄운_rm = re.compile(r"(?<![A-Za-z])rm\s+(?=[A-Z])")


def spaced(script: str) -> str:
    """한/글 수식 문자열의 붙은 글꼴 명령을 띄운다(`rmA` → `rm A`) — 한/글 렌더는 같고 폭 어림이 맞는다."""
    return _붙은_rm.sub("rm ", script)


def glued(script: str) -> str:
    """띄운 글꼴 명령을 붙인다(`rm A` → `rmA`) — 원고 LaTeX로 되돌릴 때. 되돌린 `rmA`는 다시 `rmA`로 바뀐다(왕복)."""
    return _띄운_rm.sub("rm", script)


# LaTeX 원문에 남은 한/글 글꼴 명령 낱말 — python-hwpx(6.8.0·6.9.0)의 eqedit_to_latex는 한/글 수식의 rm·it·bold를 LaTeX로
# 옮기지 않고 낱말로 두고, latex_to_eqedit는 그 낱말을 글로 보고 따옴표를 쳐(`"it"`) 한/글이 글자 it를 찍는다 — 기하 원안지를
# 다시 조판하니 벡터 식이 `AB = ita`로 찍혔다(10-26 렌더). 상류가 고치기 전까지 조용히 깨진 수식을 내지 않고 멈춘다.
# 글 인자(\text{…}·\mathrm{…} 등) 안은 글이라 보지 않고, 점 이름 `rmA`(뒤에 글자가 붙은 꼴)는 한/글이 정자 A로 읽어 걸지 않는다.
_글_인자 = re.compile(r"\\(?:text|textrm|mathrm|mathbf|operatorname)\s*\{[^{}]*\}")
_글꼴_낱말 = re.compile(r"(?<![\\A-Za-z])(rm|it|bold)(?![A-Za-z])")


@lru_cache(maxsize=4096)
def to_script(latex: str) -> str:
    """LaTeX → 한/글 수식 문자열. 바꿀 수 없으면 MathError(변환기 까닭을 붙인다). 글꼴 명령 낱말(rm·it·bold)이 글 인자 밖에
    남아 있으면 글자로 찍히니 MathError — 정자는 `\\mathrm{…}`(점 이름은 `rmA`도 된다), 기울임은 명령 없이, 굵게는 `\\mathbf{…}`."""
    m = _글꼴_낱말.search(_글_인자.sub("", latex))
    if m:
        raise MathError(f"한/글 글꼴 명령 `{m.group(1)}`이 낱말로 남아 수식에 글자 {m.group(1)}로 찍힌다 ${latex}$ — 정자는 "
                        "`\\mathrm{…}`(점 이름은 `rmA`도 된다), 기울임은 명령 없이, 굵게는 `\\mathbf{…}`로 쓴다(한/글 원안지를 "
                        "되돌린 수식이면 상류 python-hwpx 글꼴 명령 되돌림 문제)")
    try:
        return spaced(latex_to_eqedit(latex))
    except EquationConversionError as e:  # UnsupportedLatexError도 이 갈래다
        raise MathError(f"한/글 수식으로 바꿀 수 없다 ${latex}$ — {e}") from e


def _close(text: str, k: int) -> int:
    """k부터 닫는 `$`(바로 앞이 `\\`가 아닌) 자리 — 없으면 −1."""
    while True:
        j = text.find("$", k)
        if j < 0 or text[j - 1] != "\\":
            return j
        k = j + 1


def _pieces(text: str, *, strict: bool) -> list[tuple[str, bool]]:
    """text → [(글 조각(원문 그대로, `\\$` 포함), False) | (`$…$` 안, True)].

    strict면 표기 오류에 MathError. 아니면 멈추지 않는다 — `$$`는 글로, 닫히지 않은 `$` 뒤는 모두 글로 본다.
    """
    out: list[tuple[str, bool]] = []
    i = start = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and text.startswith("$", i + 1):
            i += 2
            continue
        if ch != "$":
            i += 1
            continue
        if text.startswith("$", i + 1):
            if strict:
                raise MathError(f"블록 수식 `$$…$$`은 아직 조판하지 않는다 — 인라인 `$…$`으로 쓴다: {text[i:i + 24]!r}")
            i += 2
            continue
        j = _close(text, i + 1)
        if j < 0:
            if strict:
                raise MathError(f"닫히지 않은 `$` — 달러 글자는 `\\$`로 쓴다: {text[i:i + 24]!r}")
            break
        if i > start:
            out.append((text[start:i], False))
        out.append((text[i + 1:j], True))
        i = start = j + 1
    if start < n:
        out.append((text[start:], False))
    return out


def 자리(k: int) -> str:
    """가린 글에서 k번째 수식의 자리 글자."""
    return chr(_자리0 + k)


def 자리_번호(ch: str) -> int | None:
    """가린 글의 글자가 수식 자리면 그 차례, 아니면 None."""
    o = ord(ch) - _자리0
    return o if 0 <= o < _자리_끝 - _자리0 else None


# 수식 바로 뒤에 한글(조사 등)이 붙으면 수식 끝에 한/글 수식의 1/4 칸(`)을 둔다 — 교사 원안지 실측(10-27): 발문에서 수식
# 바로 뒤가 한글인 95곳 중 92곳이 `로 끝났고(`2`인`·`…=1`의`), 뒤가 공백·쉼표인 곳과 답지·그림 위 글자에는 없었다.
# 원고에는 쓰지 않는다 — 조판이 붙이고 역변환이 걷는다(reverse._수식_원고).
뒤_띄움 = "`"
_한글 = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")


@lru_cache(maxsize=8192)
def mask(text: str) -> tuple[str, tuple[Math, ...]]:
    """원고 글 → (가린 글, 수식들). 표기 오류·바꿀 수 없는 LaTeX는 MathError. 수식 바로 뒤가 한글이면 그 수식의 한/글
    수식 문자열 끝에 뒤_띄움(`)을 붙인다."""
    out: list[str] = []
    maths: list[Math] = []
    pieces = _pieces(text, strict=True)
    for i, (s, is_math) in enumerate(pieces):
        if is_math:
            latex = s.strip()
            if not latex:
                raise MathError(f"빈 수식 `${s}$`")
            if len(maths) >= _자리_끝 - _자리0:
                raise MathError("한 문단의 수식이 너무 많다")
            after = pieces[i + 1] if i + 1 < len(pieces) else None
            tick = after is not None and not after[1] and bool(_한글.match(after[0]))
            maths.append(Math(latex, to_script(latex) + (뒤_띄움 if tick else "")))
            out.append(자리(len(maths) - 1))
        else:
            if any(자리_번호(ch) is not None for ch in s):
                raise MathError("원고 글에 보충 사용자 영역 글자(U+F0000~)가 있다 — 수식 자리와 겹친다")
            out.append(s.replace("\\$", "$"))
    return "".join(out), tuple(maths)


def unmask(masked: str, maths: tuple[Math, ...]) -> str:
    """mask의 거꾸로 — 수식 자리는 `$…$`로, 달러 글자는 `\\$`로."""
    out = []
    for ch in masked:
        k = 자리_번호(ch)
        out.append(maths[k].source if k is not None else ("\\$" if ch == "$" else ch))
    return "".join(out)


def pieces(masked: str, maths: tuple[Math, ...]) -> list[str | Math]:
    """가린 글 조각 → [글 | Math] 차례대로(빈 글은 뺀다)."""
    out: list[str | Math] = []
    buf: list[str] = []
    for ch in masked:
        k = 자리_번호(ch)
        if k is None:
            buf.append(ch)
            continue
        if buf:
            out.append("".join(buf))
            buf = []
        out.append(maths[k])
    if buf:
        out.append("".join(buf))
    return out


def without_math(text: str) -> str:
    """수식 `$…$`을 자리 글자(U+FFFC) 하나로 바꾼 글 — 원고 규칙 정규식이 수식 안의 `(1)`·`**` 같은 글자에 걸리지 않게.
    표기 오류가 있어도 멈추지 않는다(E025가 따로 알린다)."""
    return "".join("￼" if is_math else s for s, is_math in _pieces(text, strict=False))


def outside(text: str, fn: Callable[[str], str]) -> str:
    """수식 `$…$` 밖의 글에만 fn을 — 수식은 그대로 둔다. 표기 오류가 있어도 멈추지 않는다(닫히지 않은 `$` 뒤는 글)."""
    return "".join(f"${s}$" if is_math else fn(s) for s, is_math in _pieces(text, strict=False))


def split_pipes(text: str) -> list[str]:
    """`a|$|x|$|b` → ['a', '$|x|$', 'b'] — `str.split("|")`과 같되 수식 안의 `|`(절댓값 등)로는 나누지 않는다."""
    cells: list[str] = []
    cur: list[str] = []
    for s, is_math in _pieces(text, strict=False):
        if is_math:
            cur.append(f"${s}$")
            continue
        head, *rest = s.split("|")
        cur.append(head)
        for part in rest:
            cells.append("".join(cur))
            cur = [part]
    cells.append("".join(cur))
    return cells


def split_cells(row: str) -> list[str]:
    """md 표 줄 `| a | $|x|$ |` → ['a', '$|x|$'] — 수식 안의 `|`로는 칸을 나누지 않는다."""
    return [c.strip() for c in split_pipes(row.strip().strip("|"))]


@lru_cache(maxsize=4096)
def box(script: str, base_unit: int) -> tuple[int, int]:
    """수식 상자 (폭, 높이) HWPUNIT — add_equation이 hp:sz에 적는 것과 같은 측정."""
    return estimate_equation_size(script, base_unit=base_unit)


def width(m: Math, base_unit: int) -> int:
    """줄에서 수식이 차지하는 폭 = 상자 폭 + 좌우 바깥 여백."""
    return box(m.script, base_unit)[0] + 2 * 바깥_여백


def height(m: Math, base_unit: int) -> int:
    return box(m.script, base_unit)[1]


def line_chars(width_: int) -> str:
    """한/글 줄 캐시 글(fit.para_text)에서 수식 하나 — 8글자 자리. 첫 글자에 폭(HWPUNIT)을 담고(U+100000 + 폭)
    나머지 일곱은 폭 없는 글자(U+200B)다. 줄 끝 폭 추정(fit)이 line_char_width로 읽는다."""
    return chr(_줄_폭0 + max(0, min(width_, 0xFFFD))) + _폭_없음 * (TEXTPOS - 1)


def line_char_width(ch: str) -> int | None:
    """line_chars 글자의 폭 — 수식 첫 글자면 담은 폭, 폭 없는 글자면 0, 그 밖의 글자면 None."""
    if ch == _폭_없음:
        return 0
    o = ord(ch) - _줄_폭0
    return o if 0 <= o <= 0xFFFD else None


def readable(text: str) -> str:
    """줄 캐시 글 → 사람이 읽는 글 — 수식 자리(line_chars 여덟 글자)를 `[수식]`으로(보고서 알림용)."""
    out = []
    for ch in text:
        w = line_char_width(ch)
        if w is None:
            out.append(ch)
        elif ch != _폭_없음:
            out.append("[수식]")
    return "".join(out)


def line_key(text: str) -> str:
    """줄 캐시 글을 견줄 때 — 수식 첫 글자(폭)를 한 글자로 모은다(다시 저장한 한/글이 상자 폭을 바꿔도 같은 글)."""
    return "".join("￼" if line_char_width(ch) not in (None, 0) else ch for ch in text)
