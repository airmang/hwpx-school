"""학습지 마크다운(+한글 펜스) 파서 — hwpx를 알지 못한다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_BLANK = re.compile(r"\[\[(\d+)\]\]")
_ATTR = re.compile(r"(\w+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"']\S*))")
_FIGURE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)(?:\{width=(\d+(?:\.\d+)?)cm\})?\s*$")

# front matter 가 쓸 수 있는 키 전부 — 여기 없는 키(오타 포함)는 거부한다.
_FRONT_MATTER_KEYS: tuple[str, ...] = ("kit", "title", "grade", "keywordPage")

# 펜스 머리의 둥근 따옴표(한글·워드에서 옮기면 흔하다) → 곧은 따옴표. 본문(펜스 몸통)에는
# 적용하지 않는다 — 학생이 답으로 곧이곧대로 옮겨 적는 자리일 수 있다.
_CURLY_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


@dataclass(frozen=True)
class Heading:
    text: str
    textbook: str | None = None


@dataclass(frozen=True)
class Body:
    text: str


@dataclass(frozen=True)
class Prompt:
    text: str


@dataclass(frozen=True)
class Figure:
    path: str
    width_mm: float


@dataclass(frozen=True)
class FigureLine:
    """그림 줄(`![](경로){width=8cm}`) 하나의 날것 해석 — `parse_figure`가 낸다.

    `width=`를 생략하면 `width_mm`은 `None`이다: `parse_figure`는 그 자리에 어떤 기본값을
    쓸지 정하지 않는다(본문 그림 줄은 80mm, `blocks.py`의 칸 안 그림은 칸 폭 — 서로 다른
    기본값 정책을 같은 판별·해석 규칙 위에 얹는다). 기본값이 이미 정해진 구조 노드 `Figure`
    (`width_mm`이 항상 실수)와 이름이 갈리는 이유이기도 하다.
    """

    path: str
    width_mm: float | None


@dataclass(frozen=True)
class Fence:
    name: str
    attrs: dict[str, str] = field(default_factory=dict)
    body: str = ""


Node = Heading | Body | Prompt | Figure | Fence


@dataclass(frozen=True)
class Sheet:
    kit: str
    title: str
    grade: str | None
    keyword_page: bool
    nodes: tuple[Node, ...]


def expand_blanks(text: str) -> str:
    return _BLANK.sub(lambda m: "_" * int(m.group(1)), text)


def parse_figure(text: str) -> FigureLine | None:
    """그림 줄(`![](경로){width=8cm}`) 하나를 읽는다 — 본문 그림 줄과 `blocks.py`의 칸 안
    그림이 같이 쓰는 공개 함수다(정규식 하나로 판별·해석 규칙을 한 곳에 둔다).

    `_FIGURE`가 처음부터 `^!\\[`로 고정돼 있어 "이 줄이 그림 줄을 시도했는가"(판별)와
    "형식이 맞는가"(해석)가 이 함수 하나로 같이 끝난다 — 결과는 둘 다 매치 실패라 `None`
    하나로 같다. "그림 줄이 아니다"(다른 종류의 줄로 조용히 처리)와 "그림 줄인데 형식이
    틀렸다"(거부)를 다른 문구로 알려야 하는 호출자는 `text.startswith("![")`를 따로 봐서
    이 함수의 `None`을 어느 쪽으로 읽을지 스스로 정한다 — 그 문구(줄 번호를 붙이는 `parse_sheet`,
    블록 이름과 칸 글자를 붙이는 `blocks.py`)는 맥락마다 달라 이 함수가 대신 정할 수 없다.
    """
    m = _FIGURE.match(text)
    if m is None:
        return None
    width_mm = float(m.group(2)) * 10 if m.group(2) else None
    return FigureLine(m.group(1), width_mm)


def _parse_attrs(raw: str) -> tuple[dict[str, str], str | None]:
    """`key="값"`/`key='값'`/`key=값` 쌍을 읽는다.

    큰따옴표·작은따옴표 둘 다 값 구분자로 받는다 — 펜스 머리의 둥근 따옴표(“ ” ‘ ’)를
    곧은 따옴표로 바꾼 뒤 이 함수로 넘기므로, 원래 작은 둥근따옴표를 썼던 속성도 여기서
    끊기지 않고 읽혀야 한다. `finditer`가 매치 사이·앞뒤에서 건너뛴 부분(안 닫힌 따옴표·
    오타 등)이 공백이 아니면 그 찌꺼기를 같이 낸다 — 그냥 버리면 안 닫힌 따옴표 같은
    오타가 조용히 무시된 채 지나간다. 호출자가 줄 번호·블록 이름을 붙여 `ValueError`로
    거부한다(이 함수는 컨텍스트를
    모르므로 여기서 직접 던지지 않는다).

    `_ATTR`의 bare-token 대안(마지막 그룹)은 여는 따옴표 문자(`"`/`'`)로 시작하는 토큰을
    일부러 안 받는다 — 안 받으면 그 자리에서 매치 자체가 실패해 위 찌꺼기 경로로 떨어진다.
    이 배제가 없으면 `label="가`처럼 닫는 따옴표 없이 공백도 없는 가(짧은) 값이
    `attrs["label"] == '"가'`(따옴표 문자가 값에 말 그대로 박힌 채)로 "성공적으로" 매치돼
    조용히 오독된다 — 공백이 있는 형제 사례(`label="a b`)는 `\\S+`가 공백에서 멈춰 우연히
    찌꺼기가 남았을 뿐, 근본 원인은 같다.
    """
    attrs: dict[str, str] = {}
    pos = 0
    for m in _ATTR.finditer(raw):
        틈 = raw[pos : m.start()]
        if 틈.strip():
            return attrs, 틈.strip()
        값 = next(g for g in (m.group(2), m.group(3), m.group(4)) if g is not None)
        attrs[m.group(1)] = 값
        pos = m.end()
    나머지 = raw[pos:]
    if 나머지.strip():
        return attrs, 나머지.strip()
    return attrs, None


def _parse_bool(raw: str) -> bool:
    if raw.lower() not in ("true", "false"):
        raise ValueError(f"front matter 의 keywordPage 는 true 또는 false 여야 한다: {raw!r}")
    return raw.lower() == "true"


def _split_front_matter(text: str) -> tuple[dict[str, str], list[str], int]:
    """front matter 를 읽어 `(meta, 본문 줄, 줄_오프셋)`을 낸다.

    `줄_오프셋`은 본문 줄의 0-based 인덱스를 파일 기준 1-based 줄 번호로 바꾸는 값이다
    (`file_line = body_index + 줄_오프셋`) — front matter가 회차마다 줄 수가 달라, 본문
    파싱 중 나는 오류(펜스·그림 줄)가 파일에서 실제로 몇 번째 줄인지 알려주려면 이 오프셋이
    있어야 한다.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("front matter가 없다 — 첫 줄이 '---'여야 한다")
    end = next(
        (i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None
    )
    if end is None:
        raise ValueError("front matter가 닫히지 않았다 — '---' 줄이 하나 더 필요하다")
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            if key not in _FRONT_MATTER_KEYS:
                raise ValueError(
                    f"front matter 에 모르는 항목이 있다: {key} — "
                    f"쓸 수 있는 항목: {', '.join(_FRONT_MATTER_KEYS)}"
                )
            meta[key] = value.strip()
    return meta, lines[end + 1 :], end + 2


def parse_sheet(text: str) -> Sheet:
    meta, lines, 줄_오프셋 = _split_front_matter(text)
    nodes: list[Node] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
        elif stripped.startswith(":::"):
            여는_줄 = i + 줄_오프셋
            머리 = stripped[3:].strip().translate(_CURLY_QUOTES)
            이름, _, 속성raw = 머리.partition(" ")
            if not 이름:
                raise ValueError(
                    f"이름 없는 펜스 — ':::' 뒤에 블록 이름이 와야 한다 (줄 {여는_줄})"
                )
            속성들, 찌꺼기 = _parse_attrs(속성raw)
            if 찌꺼기 is not None:
                raise ValueError(
                    f"{이름} 블록의 속성을 읽을 수 없다: {찌꺼기} (줄 {여는_줄})"
                )
            본문: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                본문.append(expand_blanks(lines[i]))
                i += 1
            if i >= len(lines):
                raise ValueError(f"닫히지 않은 펜스: {이름} (줄 {여는_줄})")
            i += 1
            nodes.append(Fence(이름, 속성들, "\n".join(본문).strip()))
        elif stripped.startswith("## "):
            제목 = stripped[3:].strip()
            교과서 = None
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("교과서:"):
                교과서 = lines[i + 1].split(":", 1)[1].strip()
                i += 1
            nodes.append(Heading(제목, 교과서))
            i += 1
        elif stripped.startswith(">"):
            nodes.append(Prompt(expand_blanks(stripped[1:].strip())))
            i += 1
        elif stripped.startswith("!["):
            줄 = parse_figure(stripped)
            if 줄 is None:
                raise ValueError(
                    f"그림 줄을 읽을 수 없다: {stripped} — 형식: "
                    f"![](경로){{width=8cm}} (줄 {i + 줄_오프셋})"
                )
            # width= 생략 시 80mm(8cm) — 본문 그림 줄의 기본값 정책. parse_figure 자신은
            # 이 기본값을 모른다(칸 안 그림은 칸 폭이 기본이라 서로 다르다 — 위 docstring).
            폭 = 줄.width_mm if 줄.width_mm is not None else 80.0
            nodes.append(Figure(줄.path, 폭))
            i += 1
        else:
            nodes.append(Body(expand_blanks(stripped)))
            i += 1

    빠진 = [키 for 키 in ("kit", "title") if not meta.get(키)]
    if 빠진:
        raise ValueError(f"front matter에 필수 항목이 없다: {', '.join(빠진)}")

    keyword_page_raw = meta.get("keywordPage")
    keyword_page = _parse_bool(keyword_page_raw) if keyword_page_raw is not None else False

    return Sheet(
        kit=meta["kit"],
        title=meta["title"],
        grade=meta.get("grade"),
        keyword_page=keyword_page,
        nodes=tuple(nodes),
    )
