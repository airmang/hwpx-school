"""md 머리(front-matter) → FrontMatter. 슬롯의 원천이며 `__`/`_`는 미확정 자리표시다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 아는 키 전부. 어느 키가 필수인지는 킷 front_matter가 정한다(누름틀 결재란 양식은 과목코드·대상·인쇄까지 필수일 수 있고, 없는 양식은 기본만).
필수 = ("양식", "학년도", "학년", "학기", "차", "과목", "과목코드", "시행", "대상", "인쇄", "출제교사")
선택 = ("만점", "논술형")
# 조판 지시 — 양식 칸에 들어가지 않으므로 킷 front_matter와 상관없이 늘 받는다.
조판 = ("답항",)
답항_시작 = ("2행부터", "1행부터")  # 답지 배치형 자동 선택을 어느 형부터 하나(기본 2행부터 — G3 판정 09-27)
기본_필수 = ("양식", "학년도", "학년", "학기", "차", "과목", "시행", "출제교사")  # 킷 없이 읽을 때(lint 등)
_시행 = re.compile(r"^(\d{1,2}|__)(?:월|\.)\s*(\d{1,2}|__)(?:일|\.)\s*\((월|화|수|목|금|토|일|_)\)\s*(\d{1,2}|_)교시$")
_대상 = re.compile(r"^(\d)학년\s*(\d{1,2}|_)반\s*[~∼]\s*(\d{1,2}|_)반$")  # 반 미정은 `_`(초안, Task 19)
_인쇄 = re.compile(r"^(\d+|__)매\s*\*\s*(\d+|_)묶음$")


def _opt(s: str) -> str | None:
    return None if set(s) <= {"_"} else s


@dataclass(frozen=True)
class FrontMatter:
    양식: str
    학년도: int
    학년: int
    학기: int
    차: int
    과목: str
    과목코드: str | None
    시행: str
    대상: str | None
    인쇄: str | None
    출제교사: str
    만점: float = 100.0
    논술형: bool = False
    답항: str = "2행부터"  # 답지 배치형 자동 선택의 시작(답항_시작) — 문항의 {답항=N행}이 우선
    raw: dict = field(default_factory=dict)

    def 시행_분해(self) -> dict[str, str | None]:
        m = _시행.match(self.시행)
        return dict(zip(("월", "일", "요일", "교시"), (_opt(x) for x in m.groups())))

    def 대상_분해(self) -> dict[str, str | None]:
        if self.대상 is None:
            return {"학년": None, "반_시작": None, "반_끝": None}
        m = _대상.match(self.대상)
        학년, a, b = m.groups()
        return {"학년": 학년, "반_시작": _opt(a), "반_끝": _opt(b)}

    def 인쇄_분해(self) -> dict[str, str | None]:
        if self.인쇄 is None:
            return {"인쇄매수": None, "묶음": None}
        m = _인쇄.match(self.인쇄)
        return dict(zip(("인쇄매수", "묶음"), (_opt(x) for x in m.groups())))

    @property
    def is_draft(self) -> bool:
        """원고에 쓴 머리 값 가운데 자리표시(`__`·`_`)가 남은 것이 있다 — 쓰지 않은 선택 키(학교 B의 대상·인쇄)는 뺀다."""
        parts = [self.시행_분해()] + ([self.대상_분해()] if self.대상 is not None else []) + (
            [self.인쇄_분해()] if self.인쇄 is not None else [])
        return any(v is None for d in parts for v in d.values())

    def teachers(self) -> list[str]:
        """출제교사 여러 명은 쉼표로 — 쓴 차례 그대로(학교 B: 편집자를 맨 앞에)."""
        return [x.strip() for x in self.출제교사.split(",") if x.strip()]


def parse_front_matter(md: str, schema: dict | None = None) -> tuple[FrontMatter, str]:
    """schema = 킷 front_matter {"required": [...], "optional": [...]} — 없으면 기본_필수만 필수, 나머지 아는 키는 선택."""
    required = tuple(schema["required"]) if schema else 기본_필수
    allowed = (set(schema["required"]) | set(schema["optional"]) if schema else set(필수) | set(선택)) | set(조판)
    lines = md.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("front-matter가 없다: 첫 줄은 '---'")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("front-matter를 닫는 '---'가 없다") from None
    d: dict[str, str] = {}
    for ln in lines[1:end]:
        if not ln.strip():
            continue
        if ":" not in ln:
            raise ValueError(f"front-matter 줄 형식 오류: {ln!r}")
        k, v = ln.split(":", 1)
        d[k.strip()] = v.strip()
    unknown = set(d) - allowed
    if unknown:
        raise ValueError(f"모르는 키: {sorted(unknown)}")
    missing = [k for k in required if k not in d]
    if missing:
        raise ValueError(f"필수 키 누락: {missing}")
    if d.get("답항", "2행부터") not in 답항_시작:
        raise ValueError(f"답항 형식 오류: {d['답항']!r} — {' 또는 '.join(답항_시작)}")
    for key, rx in (("시행", _시행), ("대상", _대상), ("인쇄", _인쇄)):
        if key in d and not rx.match(d[key]):
            raise ValueError(f"{key} 형식 오류: {d[key]!r}")
    반 = _대상.match(d["대상"]).groups()[1:] if "대상" in d else ()
    if ("_" in 반) and set(반) != {"_"}:  # 반 범위의 한쪽만 정한 것은 오타일 가능성이 크다 — 둘 다 정하거나 둘 다 `_`
        raise ValueError(f"대상 반은 둘 다 정하거나 둘 다 미정(`_반~_반`)이어야 한다: {d['대상']!r}")
    fm = FrontMatter(
        양식=d["양식"], 학년도=int(d["학년도"]), 학년=int(d["학년"]), 학기=int(d["학기"]), 차=int(d["차"]),
        과목=d["과목"], 과목코드=d.get("과목코드"), 시행=d["시행"], 대상=d.get("대상"), 인쇄=d.get("인쇄"),
        출제교사=d["출제교사"],
        만점=float(d.get("만점", "100")), 논술형=d.get("논술형", "false").lower() in ("true", "예", "1"),
        답항=d.get("답항", "2행부터"), raw=d,
    )
    return fm, "\n".join(lines[end + 1:])
