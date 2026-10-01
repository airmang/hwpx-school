"""역변환 왕복 불변 검사 — 원안지 → 원고 → 조판(렌더 없이) → 견준다. 역변환의 합격 기준(이슈 #8).

    uv run python -m exam_kit.roundtrip <원안지.hwp|.hwpx> --kit <학교 킷 폴더> --form <서식.hwpx> --work <미추적 폴더>
        [--front 키=값 …]

견주는 것(원본 ↔ 원고로 다시 조판한 답 표시본):
- 원고 수준(역변환 결과의 scan): 문항 수, 문항마다 배점·정답·발문·박스·답지 글(차례 포함, 공백 무시), 세트 지문,
  그림 폭. 원본도 조판본도 같은 역변환으로 읽는다 — 역변환이 고정점이어야 한다.
- 문서 수준(역변환과 무관한 추출): 본문(첫 문항 머리 ~ 꼬리 박스 앞)의 수식(hp:equation)·그림(hp:pic) 개수.

끝 코드 0 = 같다 · 1 = 다르다 · 2 = 역변환이나 조판이 멈췄다. 다른 곳은 자리(문항 번호·종류)만 알리고 글은 쓰지 않는다 —
실제 원안지 말뭉치를 돌려도 결과에 문항 글이 새지 않게(실제 원안지는 로컬에서만, 이슈에는 수치만).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from hwpx.document import HwpxDocument

from . import preserve, q
from .compose import compose, 물결
from .kit import Kit, load_kit
from .prepare import finalize_form, prepare_document
from .reverse import FormProfile, ReverseStop, kit_profile, reverse
from .scan import Scan, scan_markdown
from .slots import fill_slots
from .source import Source, SourceError, open_source
from .verify import _tail_index, question_heads

_그림 = re.compile(r"!\[[^\]]*\]\([^)]*\)(\{[^}]*\})?")


@dataclass
class Counts:
    questions: int
    equations: int
    pictures: int


@dataclass
class Result:
    original: Counts
    rebuilt: Counts
    diffs: list[str] = field(default_factory=list)

    @property
    def same(self) -> bool:
        return not self.diffs


def counts(doc: HwpxDocument, profile: FormProfile) -> Counts:
    """본문(첫 문항 머리 ~ 꼬리 박스 앞)의 문항·수식·그림 수 — 역변환과 무관하게 XML에서 센다."""
    heads = question_heads(doc)  # 책갈피로 표시한 보존 구간의 머리는 이미 빠진다
    ps = list(doc.sections[0].paragraphs)
    tail = _tail_index(doc, profile.tail_marker)
    if heads and not preserve.ranges(doc):  # 원안지: 보존 구간(서술형·논술형 머리 글부터)의 머리를 뺀다 — 역변환과 같은 규칙
        keep = preserve.find_start([p.element for p in ps], heads[0] + 1, tail)
        heads = [h for h in heads if keep is None or h < keep]
    body = [p.element for p in ps[heads[0]:tail]] if heads else []
    return Counts(len(heads), sum(1 for p in body for _ in p.iter(q("hp", "equation"))),
                  sum(1 for p in body for _ in p.iter(q("hp", "pic"))))


def _norm(text: str, pairs) -> str:
    """견줄 글 — 물결 등 킷 글 바꾸기(조판이 하는 것)를 양쪽에 같이, 그림은 파일 이름 빼고 폭만, 공백은 뺀다."""
    text = _그림.sub(lambda m: f"[그림{m.group(1) or ''}]", text)
    return re.sub(r"\s", "", 물결(text, pairs))


def _items(s: Scan, pairs) -> dict[str, tuple]:
    """견줄 항목 — 자리 이름 → 값. 자리 이름이 곧 다른 곳 알림이다(글은 넣지 않는다)."""
    out: dict[str, tuple] = {"문항 수": (len(s.questions),), "세트": tuple(st.rng for st in s.sets)}
    for st in s.sets:
        out[f"세트 {st.rng[0]}~{st.rng[1]} 지문"] = tuple(_norm(x, pairs) for x in st.passage)
        out[f"세트 {st.rng[0]}~{st.rng[1]} 박스"] = tuple((b.kind, tuple(_norm(x, pairs) for x in b.lines)) for b in st.blocks)
    for x in s.questions:
        n = x.number
        out[f"{n}번 배점"] = (x.points,)
        out[f"{n}번 정답"] = tuple(c.mark for c in x.choices if c.correct)
        out[f"{n}번 발문"] = tuple(_norm(t, pairs) for t in x.stem)
        out[f"{n}번 박스·표·그림"] = tuple((b.kind, tuple(_norm(t, pairs) for t in b.lines),
                                         tuple(_norm(h, pairs) for h in b.attrs.get("머리") or ())) for b in x.blocks)
        out[f"{n}번 답지"] = tuple(_norm(f"{c.mark}{c.text}", pairs) for c in x.choices)
    out["보존 블록"] = tuple(tuple(_norm(t, ()) for t in b.lines) for b in s.preserved)  # 미리보기 글 = 원본 구간의 글
    return out


def compare(a: Scan, b: Scan, ca: Counts, cb: Counts, pairs=()) -> list[str]:
    """다른 곳(자리 이름만) — 빈 목록이면 같다."""
    diffs = [f"{k}: {x} ≠ {y}" for k, x, y in (("문항 머리 수", ca.questions, cb.questions),
                                               ("수식 수", ca.equations, cb.equations),
                                               ("그림 수", ca.pictures, cb.pictures)) if x != y]
    ia, ib = _items(a, pairs), _items(b, pairs)
    for k in list(dict.fromkeys([*ia, *ib])):
        if ia.get(k) != ib.get(k):
            diffs.append(k if k not in ("문항 수", "세트") else f"{k}: {ia.get(k)} ≠ {ib.get(k)}")
    return diffs


def rebuild(md: str, kit: Kit, form: Path, image_root: Path, out: Path) -> Path:
    """원고 → 답 표시본 hwpx(렌더 없이 — 조판 계획 그대로). 정답 형광펜이 있어야 정답까지 견줄 수 있다."""
    s = scan_markdown(md, kit.front_matter)
    if s.errors:
        raise ValueError(f"역변환 원고가 원고 문법에 맞지 않는다: L{s.errors[0].line_no} {s.errors[0].reason}")
    doc, prepared = prepare_document(Path(form), kit)
    fill_slots(doc, kit, s.front, question_count=len(s.questions), total_points=sum(x.points or 0.0 for x in s.questions))
    prepared = prepared.refresh(doc)
    compose(doc, s, kit, answer_key=True, image_root=image_root)
    finalize_form(doc, kit, prepared)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save_to_path(str(out))
    return out


def roundtrip(src: Path | Source, kit: Kit, form: Path, work: Path, *, front: dict[str, str] | None = None) -> Result:
    """원안지 → (역변환) 원고 → (조판) 답 표시본 → (역변환) 원고 — 두 원고와 두 문서의 수를 견준다. 산출물은 work에."""
    work = Path(work)
    profile = kit_profile(kit)
    if not isinstance(src, Source):
        src = open_source(Path(src), work / "입력")
    first, second = work / "원고", work / "다시_원고"
    first.mkdir(parents=True, exist_ok=True)
    second.mkdir(parents=True, exist_ok=True)
    md1 = reverse(src, profile, image_dir=first, front=front)
    (first / "원고.md").write_text(md1, encoding="utf-8")
    rebuilt = rebuild(md1, kit, form, first, work / "다시_조판.hwpx")
    md2 = reverse(rebuilt, profile, image_dir=second, front=front)
    (second / "원고.md").write_text(md2, encoding="utf-8")
    pairs = kit.typeset.get("text_replace") or ()
    ca, cb = counts(src.doc, profile), counts(HwpxDocument.open(str(rebuilt)), profile)
    return Result(ca, cb, compare(scan_markdown(md1, kit.front_matter), scan_markdown(md2, kit.front_matter), ca, cb, pairs))


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .reverse import _given

    ap = argparse.ArgumentParser(description="역변환 왕복 불변 검사(원안지 → 원고 → 조판 → 견줌). 끝 코드 0 같다 · 1 다르다 · 2 멈춤")
    ap.add_argument("원안지", help=".hwp 또는 .hwpx")
    ap.add_argument("--kit", required=True)
    ap.add_argument("--form", required=True, help="그 학교 서식 hwpx(다시 조판할 바탕)")
    ap.add_argument("--work", required=True, help="산출물 폴더(git 미추적 자리)")
    ap.add_argument("--front", nargs="*", default=[], metavar="키=값")
    a = ap.parse_args(argv)
    try:
        r = roundtrip(Path(a.원안지), load_kit(Path(a.kit)), Path(a.form), Path(a.work), front=_given(a.front))
    except (ReverseStop, SourceError, ValueError) as e:
        print(f"왕복 멈춤 — {e}")
        return 2
    print(f"원본: 문항 {r.original.questions} · 수식 {r.original.equations} · 그림 {r.original.pictures}")
    print(f"다시 조판: 문항 {r.rebuilt.questions} · 수식 {r.rebuilt.equations} · 그림 {r.rebuilt.pictures}")
    if r.same:
        print("왕복 불변: 같다")
        return 0
    print(f"왕복 불변: 다른 곳 {len(r.diffs)}")
    for d in r.diffs:
        print(f"  - {d}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
