import re

import pytest

from worksheet.md import (
    Body, Fence, Figure, FigureLine, Heading, Prompt, expand_blanks, parse_figure, parse_sheet,
)

샘플 = """---
kit: 시험킷
title: 탐색을 활용한 문제해결
grade: 2학년
keywordPage: false
---

## 탐색 알고리즘 종류
교과서: 33-35P

■ 정렬: 자료를 정해진 [[8]]에 따라 [[8]]대로 늘어놓는 일

> 아래 그림의 트리 구조에서 초기 상태 A에서 출발하여 목표 상태 G까지 탐색한다.

:::비교표 cols="맹목적 탐색|휴리스틱 탐색" rows="정의|탐색 방법|종류"
:::

:::답칸 label="DFS 탐색 순서" lines=1
:::

![](그림/트리.png){width=8cm}

## 맹목적 탐색
"""


def test_front_matter를_읽는다():
    sheet = parse_sheet(샘플)
    assert sheet.kit == "시험킷"
    assert sheet.title == "탐색을 활용한 문제해결"
    assert sheet.grade == "2학년"
    assert sheet.keyword_page is False


def test_노드를_문서_순서대로_낸다():
    종류 = [type(n).__name__ for n in parse_sheet(샘플).nodes]
    assert 종류 == ["Heading", "Body", "Prompt", "Fence", "Fence", "Figure", "Heading"]


def test_제목과_교과서쪽을_묶는다():
    nodes = parse_sheet(샘플).nodes
    assert nodes[0] == Heading(text="탐색 알고리즘 종류", textbook="33-35P")
    assert nodes[6] == Heading(text="맹목적 탐색", textbook=None)


def test_빈칸을_밑줄로_편다():
    assert expand_blanks("상황을 [[8]]하고") == "상황을 " + "_" * 8 + "하고"
    assert expand_blanks("[[3]]과 [[20]]") == "___과 " + "_" * 20
    assert parse_sheet(샘플).nodes[1] == Body(
        text="■ 정렬: 자료를 정해진 ________에 따라 ________대로 늘어놓는 일"
    )


def test_발문은_꺾쇠를_뗀다():
    assert parse_sheet(샘플).nodes[2] == Prompt(
        text="아래 그림의 트리 구조에서 초기 상태 A에서 출발하여 목표 상태 G까지 탐색한다."
    )


def test_펜스_속성을_읽는다():
    nodes = parse_sheet(샘플).nodes
    assert nodes[3] == Fence(
        name="비교표",
        attrs={"cols": "맹목적 탐색|휴리스틱 탐색", "rows": "정의|탐색 방법|종류"},
        body="",
    )
    assert nodes[4] == Fence(name="답칸", attrs={"label": "DFS 탐색 순서", "lines": "1"}, body="")


def test_그림은_cm를_mm로_바꾼다():
    assert parse_sheet(샘플).nodes[5] == Figure(path="그림/트리.png", width_mm=80.0)


def test_펜스_본문을_보존한다():
    본문 = parse_sheet(
        "---\nkit: k\ntitle: t\ngrade: 2학년\n---\n\n:::라벨설명\n[1] 인간의 지능\n: 설명 [[8]]\n:::\n"
    ).nodes[0]
    assert 본문.name == "라벨설명"
    assert 본문.body == "[1] 인간의 지능\n: 설명 ________"


def test_닫히지_않은_펜스는_거부한다():
    with pytest.raises(ValueError, match="닫히지 않은 펜스"):
        parse_sheet("---\nkit: k\ntitle: t\ngrade: 2학년\n---\n\n:::답칸 label=\"x\"\n")


def test_front_matter가_닫히지_않으면_거부한다():
    with pytest.raises(ValueError, match="front matter가 닫히지 않았다"):
        parse_sheet("---\nkit: k\ntitle: t\n\n## 섹션\n")


@pytest.mark.parametrize(
    "머리, 빠진", [("kit: k\n", "title"), ("title: t\n", "kit"), ("", "kit, title")]
)
def test_front_matter_필수항목이_없으면_거부한다(머리, 빠진):
    with pytest.raises(ValueError, match=f"필수 항목이 없다: {빠진}"):
        parse_sheet(f"---\n{머리}grade: 2학년\n---\n\n## 섹션\n")


# --- grade 는 죽은 입력이 아니다 — front matter 에 없으면 None -------------------------


def test_grade가_없으면_None이다():
    sheet = parse_sheet("---\nkit: k\ntitle: t\n---\n\n## 섹션\n")
    assert sheet.grade is None


# --- 입력 경계 — front matter 오타 키·keywordPage 값 -----------------------------------


def test_front_matter_모르는_키를_잡는다():
    with pytest.raises(
        ValueError,
        match="front matter 에 모르는 항목이 있다: keywordpage — "
        "쓸 수 있는 항목: kit, title, grade, keywordPage",
    ):
        parse_sheet("---\nkit: k\ntitle: t\nkeywordpage: true\n---\n\n## 섹션\n")


def test_keywordPage_값이_true_false가_아니면_거부한다():
    with pytest.raises(
        ValueError, match="keywordPage 는 true 또는 false 여야 한다: 'yes'"
    ):
        parse_sheet("---\nkit: k\ntitle: t\nkeywordPage: yes\n---\n\n## 섹션\n")


def test_keywordPage는_대소문자를_가리지_않는다():
    sheet = parse_sheet("---\nkit: k\ntitle: t\nkeywordPage: TRUE\n---\n\n## 섹션\n")
    assert sheet.keyword_page is True


# --- 이름 없는 펜스 · 닫히지 않은 펜스의 줄 번호 ---------------------------------------


def test_이름_없는_펜스를_줄_번호와_함께_거부한다():
    with pytest.raises(
        ValueError,
        match=r"이름 없는 펜스 — ':::' 뒤에 블록 이름이 와야 한다 \(줄 8\)",
    ):
        parse_sheet("---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n:::\n:::\n")


def test_짝_없는_닫는_줄도_이름_없는_펜스로_거부한다():
    """닫는 줄만 홀로 있으면 파서는 그 줄을 '이름 없는 여는 줄'로 본다(짝이 없다)."""
    with pytest.raises(ValueError, match="이름 없는 펜스"):
        parse_sheet(
            "---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n:::답칸 label=\"x\" lines=1\n내용\n:::\n:::\n"
        )


def test_닫히지_않은_펜스는_여는_줄_번호를_알려준다():
    with pytest.raises(ValueError, match=r"닫히지 않은 펜스: 답칸 \(줄 8\)"):
        parse_sheet("---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n:::답칸 label=\"x\"\n")


# --- 펜스 머리의 둥근 따옴표 -----------------------------------------------------------


def test_둥근_따옴표는_곧은_따옴표로_바뀐_뒤_읽힌다():
    sheet = parse_sheet(
        "---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n"
        ':::답칸 label="DFS 탐색 순서" lines=1\n:::\n'.replace('"DFS 탐색 순서"', "“DFS 탐색 순서”")
    )
    fence = sheet.nodes[1]  # nodes[0]은 '## 섹션' Heading
    assert fence.attrs["label"] == "DFS 탐색 순서"  # 둥근 따옴표 탓에 “DFS 로 잘리지 않는다


def test_둥근_홑따옴표도_바뀐다():
    sheet = parse_sheet(
        "---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n"
        ":::강조박스 title=‘튜링 테스트’\n내용\n:::\n"
    )
    fence = sheet.nodes[1]  # nodes[0]은 '## 섹션' Heading
    assert fence.attrs["title"] == "튜링 테스트"


# --- 속성 문자열의 찌꺼기 --------------------------------------------------------------


def test_속성_찌꺼기가_있으면_줄_번호와_함께_거부한다():
    with pytest.raises(
        ValueError,
        match=r"답칸 블록의 속성을 읽을 수 없다: extra_junk \(줄 8\)",
    ):
        parse_sheet(
            '---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n:::답칸 label="가" extra_junk\n:::\n'
        )


def test_안_닫힌_따옴표도_속성_찌꺼기로_거부한다():
    with pytest.raises(ValueError, match=r"답칸 블록의 속성을 읽을 수 없다:.*\(줄 8\)"):
        parse_sheet('---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n:::답칸 label="a b\n:::\n')


# --- 안 닫힌 따옴표는 공백 유무와 무관하게 거부된다 ------------------------------------------
# `_ATTR`의 bare-token 대안(\S+)은 여는 따옴표 문자도 "그냥 문자"로 매치할 수 있다 — 값 뒤에
# 공백이 없으면(label="가 처럼 한 단어) attrs={'label': '"가'}로 "성공적으로" 매치돼 오류가
# 안 난다. 공백 있는 형제 사례(label="a b, 위 테스트)는 \S+가 공백에서 멈추므로 이 경로를
# 안 타지만, 근본 원인은 같다 — 그래서 둘 다 확인한다.


@pytest.mark.parametrize(
    "속성raw",
    [
        'label="가',          # 안 닫힌 따옴표, 공백 없음(한 글자 값)
        'label="abc',         # 안 닫힌 따옴표, 공백 없음(영문 여러 글자 값)
        'lines=1 label="x',   # 앞에 정상 속성이 있어도 뒤의 안 닫힌 따옴표를 잡는다
        'label="a b',         # 통제 — 공백 있는 경우(이 경로는 원래도 거부된다)
    ],
)
def test_안_닫힌_따옴표는_공백_유무와_무관하게_거부한다(속성raw):
    with pytest.raises(ValueError, match=r"답칸 블록의 속성을 읽을 수 없다:.*\(줄 8\)"):
        parse_sheet(f'---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n:::답칸 {속성raw}\n:::\n')


@pytest.mark.parametrize(
    "속성raw, 키, 기대값",
    [
        ('label="가 나"', "label", "가 나"),  # 정상적으로 닫힌 큰따옴표(공백 포함)는 그대로 받는다
        ("label=가", "label", "가"),          # 따옴표 없는 바른 값도 여전히 받는다
        ('cols="가=나"', "cols", "가=나"),     # 따옴표 안의 '='는 값의 일부다(키 구분자와 안 헷갈린다)
        ('rows="a|b"', "rows", "a|b"),        # 따옴표 안의 '|'도 값의 일부다
    ],
)
def test_제대로_닫힌_값은_거부되지_않는다(속성raw, 키, 기대값):
    """bare-token이 여는 따옴표를 거부하는 규칙이 정상 입력까지 과잉 차단하지 않는지
    확인하는 통제군."""
    sheet = parse_sheet(f'---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n:::답칸 {속성raw}\n:::\n')
    fence = sheet.nodes[1]  # nodes[0]은 '## 섹션' Heading
    assert fence.attrs[키] == 기대값


# --- 그림 줄 형식 오류 -----------------------------------------------------------------


def test_그림_width에_공백이_있으면_거부한다():
    줄 = "![](그림/a.png){width=4 cm}"
    with pytest.raises(
        ValueError,
        match=re.escape(f"그림 줄을 읽을 수 없다: {줄} — 형식: ![](경로){{width=8cm}}")
        + r" \(줄 8\)",
    ):
        parse_sheet(f"---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n{줄}\n")


def test_그림_width에_점이_두개면_영문_오류_대신_한국어_문구로_거부한다():
    """`[\\d.]+`로 읽으면 '1.2.3'을 통째로 먹여 `float()`가 영문 ValueError로 죽는다."""
    줄 = "![](그림/a.png){width=1.2.3cm}"
    with pytest.raises(
        ValueError,
        match=re.escape(f"그림 줄을 읽을 수 없다: {줄} — 형식: ![](경로){{width=8cm}}")
        + r" \(줄 8\)",
    ):
        parse_sheet(f"---\nkit: k\ntitle: t\n---\n\n## 섹션\n\n{줄}\n")


# --- parse_figure — 본문 그림 줄과 blocks.py의 칸 안 그림이 같이 쓰는 공개 함수 ------------------
# parse_sheet(위)는 이 함수의 결과에 자신의 기본값(width= 생략 시 80mm)을 얹을 뿐이다 —
# 아래 테스트들은 parse_sheet를 거치지 않고 이 함수 자체의 판별·해석 규칙만 본다.


def test_parse_figure는_그림_줄이_아니면_None이다():
    """`!`로 시작하지 않는 줄은 그림 줄을 시도한 것도 아니다 — 보통 글자로 본다."""
    assert parse_figure("그냥 글자") is None
    assert parse_figure("") is None


def test_parse_figure는_형식에_안_맞아도_None이다():
    """`!`로 시작하는데 형식이 틀린 줄도 None — "그림 줄이 아니다"와 같은 값이다. 어느
    쪽인지 갈라 다른 문구로 거부하는 일은 호출자(parse_sheet·blocks.py) 몫이다(정규식이
    `^!\\[`로 시작해 애초에 결과가 갈리지 않는다)."""
    assert parse_figure("![](그림/a.png){width=4 cm}") is None
    assert parse_figure("![나쁜 형식") is None


def test_parse_figure는_width_생략시_None을_낸다():
    """기본값(80mm)을 고르지 않는다 — 그 정책은 호출자(parse_sheet)가 얹는다."""
    assert parse_figure("![](그림/a.png)") == FigureLine(path="그림/a.png", width_mm=None)


def test_parse_figure는_width_있으면_mm로_바꾼다():
    assert parse_figure("![](그림/a.png){width=4cm}") == FigureLine(path="그림/a.png", width_mm=40.0)
    assert parse_figure("![](그림/a.png){width=4.5cm}") == FigureLine(path="그림/a.png", width_mm=45.0)


def test_parse_sheet의_그림_기본값_80mm은_parse_figure_위에_얹은_정책이다():
    """parse_sheet(기존 동작, 불변)가 parse_figure의 None(생략) 위에 80mm을 얹는다는 것을
    양쪽에서 확인한다 — 회귀 시 어느 쪽이 깨졌는지 갈라 보여준다."""
    assert parse_figure("![](그림/트리.png)") == FigureLine(path="그림/트리.png", width_mm=None)
    sheet = parse_sheet("---\nkit: k\ntitle: t\n---\n\n![](그림/트리.png)\n")
    assert sheet.nodes[0] == Figure(path="그림/트리.png", width_mm=80.0)
