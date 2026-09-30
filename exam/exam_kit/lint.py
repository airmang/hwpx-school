"""원고 md의 [기계] 검사. E = 오류(조판 거부), W = 경고(보고만).

두 층이다.
- 엔진 규칙: 원고 문법·구조(번호 차례·정답 1개·답지 ①~⑤·답항표·그림·세트·나눔 지시·별표). 늘 돈다.
- 학교 규칙: 학교 문항 제작 연수자료의 [기계] 규칙. 킷 rules.json에 적힌 코드만 켜지고, 설정(정규식·한도)도 거기서 온다.
  킷이 없거나 rules.json이 없으면 엔진 규칙만 돈다.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .scan import Scan, scan_markdown

원문자 = "①②③④⑤"


@dataclass(frozen=True)
class Violation:
    code: str
    level: str
    line_no: int
    msg: str


def _v(code: str, line_no: int, msg: str) -> Violation:
    return Violation(code, code[0], line_no, msg)


def rule_E001(s: Scan) -> list[Violation]:
    return [_v("E001", e.line_no, f"{e.reason}: {e.text!r}") for e in s.errors]


def rule_E002(s: Scan) -> list[Violation]:
    nums = [q.number for q in s.questions]
    want = [str(i) for i in range(1, len(nums) + 1)]
    return [] if nums == want else [_v("E002", s.questions[0].line_no if s.questions else 1, f"문항 번호 {nums} ≠ {want}")]


def rule_E003(s: Scan) -> list[Violation]:
    return [_v("E003", q.line_no, f"{q.number}번 배점 없음") for q in s.questions if q.points_raw is None]


def rule_W003(s: Scan, cfg: dict) -> list[Violation]:
    return [_v("W003", q.line_no, f"{q.number}번 배점 {q.points_raw} — 소수 1자리 [N.N점] 권장")
            for q in s.questions if q.points_raw is not None and q.points_raw.startswith("(")]


def rule_E004(s: Scan) -> list[Violation]:
    total = sum(q.points or 0.0 for q in s.questions)
    if abs(total - s.front.만점) > 1e-9:
        return [_v("E004", 1, f"배점 합 {total:.1f} ≠ 만점 {s.front.만점:.1f}")]
    return []


def rule_E005(s: Scan) -> list[Violation]:
    return [_v("E005", q.line_no, f"{q.number}번 정답 표기 {sum(c.correct for c in q.choices)}개")
            for q in s.questions if sum(c.correct for c in q.choices) != 1]


def rule_E006(s: Scan) -> list[Violation]:
    return [_v("E006", q.line_no, f"{q.number}번 답지 {''.join(c.mark for c in q.choices)!r}")
            for q in s.questions if "".join(c.mark for c in q.choices) != 원문자]


def rule_E007(s: Scan, cfg: dict) -> list[Violation]:
    marks = [c.mark for q in s.questions for c in q.choices if c.correct]
    if len(marks) < cfg["min_answers"]:
        return []
    cnt = Counter(marks)
    out = []
    limit = math.ceil(len(marks) / cfg["divisor"])
    for m, n in cnt.items():
        if n > limit:
            out.append(_v("E007", 1, f"정답 {m} {n}개 — {limit}개 초과(편중)"))
    if len(cnt) == 5 and len(set(cnt.values())) == 1:
        out.append(_v("W007", 1, f"정답 번호별 개수가 전부 {marks.count(marks[0])}개로 같다"))
    return out


def rule_E008(s: Scan, cfg: dict) -> list[Violation]:
    out = []
    for q in s.questions:
        ranks = [cfg["order"][b.kind] for b in q.blocks]
        if ranks != sorted(ranks):
            out.append(_v("E008", q.line_no, f"{q.number}번 블록 순서 {[b.kind for b in q.blocks]} — {cfg['message']}"))
    return out


def rule_E009(s: Scan) -> list[Violation]:
    out = []
    for q in s.questions:
        for b in q.blocks:
            if b.kind != "답항표":
                continue
            head = b.attrs.get("머리")
            if not head:
                out.append(_v("E009", b.line_no, f"{q.number}번 답항표에 머리 속성이 없다"))
                continue
            rows = [c.text.split("|") for c in q.choices]
            if len(rows) != 5 or any(len(r) != len(head) for r in rows):
                out.append(_v("E009", b.line_no, f"{q.number}번 답항표 행 {len(rows)} / 열 {[len(r) for r in rows]} ≠ {len(head)}"))
    return out


def _images(s: Scan):
    """(문항 번호, 줄 번호, 경로, 폭 cm) — 그림 블록과 자료 박스 안 그림 줄 모두(세트 블록 포함)."""
    from .scan import IMG_RE

    for owner, blocks in [(q.number, q.blocks) for q in s.questions] + [(f"[{a}∼{b}]", st.blocks) for st in s.sets
                                                                        for a, b in [st.rng]]:
        for b in blocks:
            if b.kind == "그림" and b.attrs.get("src"):
                yield owner, b.line_no, b.attrs["src"], b.attrs.get("width_cm")
            elif b.kind in ("자료", "그림"):
                for ln in b.lines:
                    m = IMG_RE.match(ln.strip())
                    if m:
                        yield owner, b.line_no, m.group("src"), float(m.group("w")) if m.group("w") else None


def rule_E010(s: Scan, md_dir: Path | None) -> list[Violation]:
    if md_dir is None:
        return []
    return [_v("E010", line, f"{n}번 그림 없음: {src}") for n, line, src, _ in _images(s) if not (md_dir / src).exists()]


def rule_W022(s: Scan, md_dir: Path | None) -> list[Violation]:
    """그림 규격(Task 30): 원고 폭이 원래 크기(원본 px ÷ 300dpi)보다 작으면 줄여 넣는 것 — 그림 속 글자가 작아진다(W022).
    1.02배보다 크면 300dpi 아래로 늘려 넣는 것 — 흐려진다(W023).
    그림은 쓸 폭에 맞는 크기로 다시 만든다(단·박스 안 폭을 넘으면 조판이 오류로 멈춘다)."""
    from PIL import Image

    from .compose import natural_width_cm

    if md_dir is None:
        return []
    out = []
    for n, line, src, cm in _images(s):
        path = md_dir / src
        if cm is None or not path.is_file():
            continue
        with Image.open(path) as im:
            im_width = im.width
        natural = natural_width_cm(im_width)
        if cm < natural * 0.98:
            out.append(_v("W022", line, f"{n}번 그림 {src} 폭 {cm}cm < 원래 크기 {natural:.1f}cm — 줄여 넣는다"))
        elif cm > natural * 1.02:
            out.append(_v("W023", line, f"{n}번 그림 {src} 폭 {cm}cm > 원래 크기 {natural:.1f}cm — 늘려 넣는다"
                                        f"({round(im_width * 2.54 / cm)}dpi) — 흐려질 수 있다"))
    return out


def rule_E011(s: Scan) -> list[Violation]:
    out = []
    for st in s.sets:
        members = [q for q in s.questions if q.set_rng == st.rng]
        want = [str(i) for i in range(int(st.rng[0]), int(st.rng[1]) + 1)]
        if len(members) < 2 or [q.number for q in members] != want:
            out.append(_v("E011", st.line_no, f"세트 {st.rng} 문항 {[q.number for q in members]} ≠ {want}"))
    return out


_물결 = re.compile(r"\[\d+~\d+\]")


def rule_E012(s: Scan, cfg: dict) -> list[Violation]:
    out = []
    for q in s.questions:
        for ln in q.stem:
            if _물결.search(ln):
                out.append(_v("E012", q.line_no, f"{q.number}번 '[a~b]' — 물결은 ∼(U+223C)"))
    return out


def lint(md: str, *, md_dir: Path | None = None, rules: dict | None = None) -> list[Violation]:
    """rules = 킷 rules.json 내용({"source", "rules": {코드: 설정}}) — 없으면 엔진 규칙만."""
    s = scan_markdown(md)
    out: list[Violation] = []
    for r in ENGINE_RULES:
        out.extend(r(s))
    for code, cfg in ((rules or {}).get("rules") or {}).items():
        if code not in SCHOOL_RULES:
            raise ValueError(f"rules.json: 모르는 규칙 {code} — 지원: {sorted(SCHOOL_RULES)}")
        out.extend(SCHOOL_RULES[code](s, cfg))
    out.extend(rule_E010(s, md_dir))
    out.extend(rule_W022(s, md_dir))
    return sorted(out, key=lambda v: (v.line_no, v.code))


def errors(vs: list[Violation]) -> list[Violation]:
    return [v for v in vs if v.level == "E"]


# 학교 규칙의 정규식은 그 학교 킷의 rules.json에 있다(값과 그 까닭은 각 규칙의 note).
# E014 금칙: 관형형("적합한")까지 잡고 반의 접두 "부-"는 뺀다. E017 "다음 그림/표": 뒤에 다른 음절이 곧장 이어지면
# ("표현"·"그림책") 별개 낱말이라 공백·문장부호·끝·조사 뒤에서만 잡는다.


def _직접발문(q) -> str:
    return q.stem[-1] if q.stem else ""


def rule_E013(s: Scan, cfg: dict) -> list[Violation]:
    항목, 금지 = re.compile(cfg["item"]), re.compile(cfg["forbidden"])
    out = []
    for q in s.questions:
        for b in q.blocks:
            if b.kind != "보기":
                continue
            for ln in b.lines:
                if not 항목.match(ln.strip()) or 금지.search(ln):
                    out.append(_v("E013", b.line_no, f"{q.number}번 〈보기〉 항목 기호: {ln.strip()[:20]!r} — {cfg['message']}"))
    return out


# 범위: 발문 전체(stem 전 줄) — 간접 발문의 도입부에도 금칙 어휘가 나올 수 있다.
def rule_E014(s: Scan, cfg: dict) -> list[Violation]:
    금칙 = [(re.compile(p), label) for p, label in cfg["words"]]
    out = []
    for q in s.questions:
        stem = " ".join(q.stem)
        for pat, label in 금칙:
            if pat.search(stem):
                out.append(_v("E014", q.line_no, f"{q.number}번 금칙 어휘 {label!r}"))
    return out


# 범위: 직접 발문만(stem 마지막 줄) — "가장"은 실제 선택 기준을 묻는 마지막 문장에서만 문제된다.
def rule_E015(s: Scan, cfg: dict) -> list[Violation]:
    부정, 낱말 = re.compile(cfg["negation"]), cfg["word"]
    return [_v("E015", q.line_no, f"{q.number}번 부정 발문에 {낱말!r}") for q in s.questions
            if 부정.search(_직접발문(q)) and 낱말 in _직접발문(q)]


# 범위: 발문 전체(stem 전 줄) — 굵게·밑줄 표기 규칙은 간접 발문에도 적용된다.
def rule_E016(s: Scan, cfg: dict) -> list[Violation]:
    부정 = re.compile(cfg["negation"])
    밑줄부정 = re.compile(r"__[^_]*" + cfg["negation"] + r"[^_]*__")
    out = []
    for q in s.questions:
        stem = " ".join(q.stem)
        if "**" in stem:
            out.append(_v("E016", q.line_no, f"{q.number}번 발문에 굵게(**) — 밑줄만 쓴다"))
        if 부정.search(stem) and not 밑줄부정.search(stem):
            out.append(_v("E016", q.line_no, f"{q.number}번 부정어에 __밑줄__ 없음"))
    return out


# 범위: 발문 전체(stem 전 줄) — "다음 그림/표/…" 오용은 간접 발문 도입부에서도 나온다.
def rule_E017(s: Scan, cfg: dict) -> list[Violation]:
    pat = re.compile(cfg["pattern"])
    return [_v("E017", q.line_no, f"{q.number}번 {m.group(0)!r} — {cfg['message']}") for q in s.questions
            for m in [pat.search(" ".join(q.stem))] if m]


# 범위: 발문 전체(stem 전 줄) — "위 글"도 간접 발문에 흔히 나온다.
def rule_E018(s: Scan, cfg: dict) -> list[Violation]:
    pat = re.compile(cfg["pattern"])
    return [_v("E018", q.line_no, f"{q.number}번 {cfg['message']}") for q in s.questions if pat.search(" ".join(q.stem))]


def rule_W019(s: Scan, cfg: dict) -> list[Violation]:
    out = []
    for q in s.questions:
        if any(b.kind == "답항표" for b in q.blocks):
            continue
        texts = [c.text for c in q.choices]
        lens = [len(t) for t in texts]
        기호순 = all(re.match(r"^[ㄱㄴㄷㄹㅁ(]", t) for t in texts) and texts == sorted(texts)
        if lens != sorted(lens) and lens != sorted(lens, reverse=True) and not 기호순:
            out.append(_v("W019", q.line_no, f"{q.number}번 답지가 길이순·기호순이 아님 — 논리순인지 확인"))
    return out


# 범위: 직접 발문만(stem 마지막 줄) — 물음표로 끝나야 하는 것은 실제로 묻는 마지막 문장이다.
def rule_W020(s: Scan, cfg: dict) -> list[Violation]:
    끝 = cfg["end"]
    return [_v("W020", q.line_no, f"{q.number}번 발문이 {끝!r}로 끝나지 않음") for q in s.questions
            if not _직접발문(q).rstrip().endswith(끝)]


# 나눔 지시({단나눔}·{쪽나눔}, Task 29)는 문항 묶음을 새 단·새 쪽에서 시작하게 한다 — 첫 문항은 관리박스 바로 아래라 뜻이 없다.
def rule_E021(s: Scan) -> list[Violation]:
    return [_v("E021", q.line_no, f"{q.number}번 나눔 지시 — 첫 문항은 관리박스 바로 아래에서 시작한다")
            for q in s.questions[:1] if q.brk]


def _글_줄(lines) -> list[str]:
    """블록 줄 가운데 글 줄 — 코드 블록(``` 사이) 줄은 뺀다(코드는 글자 그대로라 `**`가 뜻일 수 있다)."""
    out, code = [], False
    for ln in lines:
        if ln.strip().startswith("```"):
            code = not code
            continue
        if not code:
            out.append(ln)
    return out


# 범위: 발문 밖의 문항 글 전부(답지·〈보기〉·자료·세트 지문) — 조판기는 `**`를 굵게로 읽지 않아 별표가 그대로 찍힌다(Task 32 I-2).
# 발문의 `**`는 E016이 본다.
def rule_E024(s: Scan) -> list[Violation]:
    out = []
    for q in s.questions:
        where = [(c.line_no, c.text) for c in q.choices]
        where += [(b.line_no, ln) for b in q.blocks if b.kind in ("자료", "보기", "조건", "주", "답항표") for ln in _글_줄(b.lines)]
        if any("**" in t for _, t in where):
            line = next(n for n, t in where if "**" in t)
            out.append(_v("E024", line, f"{q.number}번 답지·박스 글에 굵게(**) — 조판에서 별표가 그대로 찍힌다"))
    for st in s.sets:
        texts = list(st.passage) + [ln for b in st.blocks if b.kind in ("자료", "보기") for ln in _글_줄(b.lines)]
        if any("**" in t for t in texts):
            out.append(_v("E024", st.line_no, f"세트 {st.rng[0]}~{st.rng[1]} 지문·박스 글에 굵게(**)"))
    return out


ENGINE_RULES = [rule_E001, rule_E002, rule_E003, rule_E004, rule_E005, rule_E006, rule_E009, rule_E011, rule_E021, rule_E024]
SCHOOL_RULES = {"W003": rule_W003, "E007": rule_E007, "E008": rule_E008, "E012": rule_E012, "E013": rule_E013,
                "E014": rule_E014, "E015": rule_E015, "E016": rule_E016, "E017": rule_E017, "E018": rule_E018,
                "W019": rule_W019, "W020": rule_W020}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="시험 md 규칙 검사")
    ap.add_argument("md")
    ap.add_argument("--kit", help="학교 킷 — 그 킷의 rules.json(학교 규칙)도 돈다. 없으면 엔진 규칙만")
    args = ap.parse_args(argv)
    path = Path(args.md)
    rules = None
    if args.kit:
        from .kit import load_kit

        rules = load_kit(Path(args.kit)).rules
    vs = lint(path.read_text(encoding="utf-8"), md_dir=path.parent, rules=rules)
    for v in vs:
        print(f"{v.code} L{v.line_no} {v.msg}", file=sys.stdout)
    n_err = len(errors(vs))
    print(f"오류 {n_err} · 경고 {len(vs) - n_err}")
    return 1 if n_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
