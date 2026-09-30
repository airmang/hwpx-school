import pytest

from assessment.md import (
    AnswerGrid, AnswerLine, ColumnBreak, DataTable, Figure, Group, Hint, Item, LabeledLines,
    Lines, MdError, Passage, SideBySide, Text, parse_sheet,
)

머리 = "---\nkit: standard\ntitle: 인공지능 기초 수행평가(A)\nscore: 25점/기본점수 10점\ntotal: 3\n---\n"


def test_문항과_배점():
    s = parse_sheet(머리 + "## 용어를 쓰시오 {총 2점}\n:::정답\n(가) 노드\n:::\n## 예시를 쓰시오. {1점}\n:::정답\n언덕\n:::\n")
    a, b = s.items
    assert (a.number, a.prompt, a.points_text, a.points, a.answer) == (1, "용어를 쓰시오", "총 2점", 2, ("(가) 노드",))
    assert (b.number, b.points) == (2, 1)
    assert s.total == 3 and s.score == "25점/기본점수 10점"


def test_배점의_마지막_N점을_쓴다():
    s = parse_sheet(머리 + "## 쓰시오 {각 1점, 총 2점}\n")
    assert s.items[0].points == 2


def test_블록_열한_종():
    본문 = (
        "## 발문 {3점}\n"
        "> (단, 왼쪽부터)\n"
        "이어지는 글\n"
        ":::제시문\n첫 줄\n둘째 줄\n:::\n"
        ":::조건\n조건 1. 하나\n:::\n"
        "| 노드 | 거리 |\n|---|---|\n| S | 16 |\n"
        "![캡션 첫\\n캡션 둘](그림/a.png){width=8cm}\n"
        ":::답칸 (가) | (나)\n"
        ":::표답칸\nBFS\nDFS\n:::\n"
        ":::서술칸 6줄\n"
        ":::서술칸\n최단 경로\n노드 순서\n:::\n"
        ":::단나눔\n"
    )
    b = parse_sheet(머리 + 본문).items[0].blocks
    assert b == (
        Hint("(단, 왼쪽부터)"), Text("이어지는 글"),
        Passage("제시문", ("첫 줄", "둘째 줄")), Passage("조건", ("조건 1. 하나",)),
        DataTable(("노드", "거리"), (("S", "16"),)),
        Figure("그림/a.png", 80.0, ("캡션 첫", "캡션 둘")),
        AnswerLine(("(가)", "(나)")), AnswerGrid(("BFS", "DFS")), Lines(6),
        LabeledLines(("최단 경로", "노드 순서")), ColumnBreak(),
    )


def test_묶음():
    s = parse_sheet(머리 + "::::묶음 1-2 공통 발문\n:::제시문\n글\n:::\n## 가 {1점}\n## 나 {2점}\n::::\n")
    (g,) = s.entries
    assert isinstance(g, Group) and (g.first, g.last, g.prompt) == (1, 2, "공통 발문")
    assert g.blocks == (Passage("제시문", ("글",)),)
    assert [i.number for i in g.items] == [1, 2]
    assert [i.number for i in s.items] == [1, 2]


def test_문항_사이_단나눔은_최상위_항목():
    s = parse_sheet(머리 + "::::묶음 1-1 공통\n## 나 {2점}\n::::\n:::단나눔\n## 다 {1점}\n")
    assert s.entries[1] == ColumnBreak()


@pytest.mark.parametrize("본문, 문구", [
    ("## 배점 없음\n", r"7번째 줄: 문항 줄은"),
    ("글만 있다\n", r"문항 밖에 블록이 있다"),
    (":::모름\n", r"모르는 블록이다: 모름"),
    (":::제시문\n안 닫힘\n", r"블록이 닫히지 않았다"),
    ("## 가 {1점}\n:::정답\n하나\n:::\n:::정답\n둘\n:::\n", r"한 문항에 정답이 둘이다"),
    ("::::묶음 1-2 가\n::::묶음 3-4 나\n", r"묶음 안에 묶음을 열 수 없다"),
    ("::::묶음 1-2 가\n## 가 {1점}\n", r"묶음이 닫히지 않았다"),
    ("## 가 {1점}\n:::서술칸 여섯줄\n", r"서술칸 줄 수는 'N줄' 꼴"),
    ("## 가 {1점}\n| a | b |\n| c |\n", r"표"),
    ("## 가 {1점}\n![](a.jpg){width=8}\n", r"그림 줄"),
    ("## 가 {1점}\n![](a.jpg){align=left}\n", r"8번째 줄: 그림 줄에 모르는 속성이 있다: 'align=left'"),
    ("## 가 {1점}\n![](a.jpg){caption=right}\n", r"8번째 줄: 그림 줄의 caption 값은 left 또는 center 여야 한다"),
])
def test_입력_오류(본문, 문구):
    with pytest.raises(MdError, match=문구):
        parse_sheet(머리 + 본문)


def test_front_matter():
    with pytest.raises(MdError, match="모르는 항목이 있다: totl"):
        parse_sheet("---\nkit: a\ntitle: b\ntotl: 3\n---\n")
    with pytest.raises(MdError, match="필수 항목이 없다: total"):
        parse_sheet("---\nkit: a\ntitle: b\n---\n## 가 {1점}\n")
    with pytest.raises(MdError, match="total 은 자연수"):
        parse_sheet("---\nkit: a\ntitle: b\ntotal: 열다섯\n---\n")


def test_그림_속성_순서_상관없이_읽는다():
    """width·caption 을 어떤 순서로 써도 같은 값이어야 한다."""
    앞 = parse_sheet(머리 + "## 가 {1점}\n![캡](a.png){caption=left width=8cm}\n").items[0].blocks[0]
    뒤 = parse_sheet(머리 + "## 가 {1점}\n![캡](a.png){width=8cm caption=left}\n").items[0].blocks[0]
    assert 앞 == 뒤 == Figure("a.png", 80.0, ("캡",), "left")


def test_그림_속성_하나만_써도_된다():
    캡션만 = parse_sheet(머리 + "## 가 {1점}\n![캡](a.png){caption=left}\n").items[0].blocks[0]
    assert 캡션만 == Figure("a.png", None, ("캡",), "left")
    폭만 = parse_sheet(머리 + "## 가 {1점}\n![캡](a.png){width=8cm}\n").items[0].blocks[0]
    assert 폭만 == Figure("a.png", 80.0, ("캡",), "center")


def test_그림_속성_둘_다_생략하면_기본값():
    s = parse_sheet(머리 + "## 가 {1점}\n![캡](a.png)\n").items[0].blocks[0]
    assert s == Figure("a.png", None, ("캡",), "center")


def test_그림_caption_align_기본값은_Figure_직접_생성에도_적용된다():
    """md 바깥에서 `Figure(path, width_mm, caption)` 처럼 위치 인자만 줘도 동작해야 한다."""
    assert Figure("a.png", None, ("캡",)).caption_align == "center"


# --- 병합 머리 표 ------------------------------------------------------------
혼동 = (
    "## 가 {1점}\n"
    "| 답칸 1-① | 예측 | < |\n"
    "| ^ | 예측 양성 | 예측 음성 |\n"
    "|---|---|---|\n"
    "| 실제 양성 |  |  |\n"
    "| 실제 음성 |  |  |\n"
)


def test_병합_머리_표_여러_줄_머리와_병합_사각형():
    (t,) = parse_sheet(머리 + 혼동).items[0].blocks
    assert t.head_rows == (("답칸 1-①", "예측", ""), ("", "예측 양성", "예측 음성"))
    assert t.header == ("답칸 1-①", "예측", "")
    assert t.rows == (("실제 양성", "", ""), ("실제 음성", "", ""))
    # (행0, 열0, 행1, 열1) — 행 번호는 머리 행부터 센다.
    assert t.merges == ((0, 0, 1, 0), (0, 1, 0, 2))


def test_병합_몸_안의_세로_병합과_2x2():
    t = parse_sheet(머리 + "## 가 {1점}\n| a | b | c |\n|---|---|---|\n| A | < | 1 |\n| ^ | ^ | 2 |\n").items[0].blocks[0]
    assert t.merges == ((1, 0, 2, 1),)
    assert t.rows == (("A", "", "1"), ("", "", "2"))


def test_병합_없는_표는_예전과_같다():
    t = parse_sheet(머리 + "## 가 {1점}\n| 노드 | 거리 |\n|---|---|\n| S | 16 |\n").items[0].blocks[0]
    assert t == DataTable(("노드", "거리"), (("S", "16"),))
    assert t.head_rows == (("노드", "거리"),) and t.merges == ()


@pytest.mark.parametrize("표, 문구", [
    ("| < | a |\n|---|---|\n| 1 | 2 |\n", r"8번째 줄: .*첫 칸"),
    ("| ^ | a |\n|---|---|\n| 1 | 2 |\n", r"8번째 줄: .*첫 칸"),
    ("| a | < |\n| ^ | b |\n|---|---|\n| 1 | 2 |\n", r"8번째 줄: .*직사각형"),
    ("| a | b |\n|---|---|\n| ^ | 2 |\n", r"10번째 줄: .*머리.*몸"),
    ("| a | b |\n|---|---|\n| < | 2 |\n", r"10번째 줄: .*왼쪽"),
    ("| a | b |\n| c | d |\n|---|---|\n| 1 | 2 |\n|---|---|\n| 3 | 4 |\n", r"12번째 줄: .*구분 행은 하나"),
    ("| a | b |\n|---|---|\n", r"8번째 줄: 표는"),
])
def test_병합_표_거부(표, 문구):
    with pytest.raises(MdError, match=문구):
        parse_sheet(머리 + "## 가 {1점}\n" + 표)


# --- 나란히 그림·문항 밖 블록 --------------------------------------------------
def test_나란히_그림_둘_셋():
    둘 = parse_sheet(머리 + "## 가 {1점}\n:::나란히\n![캡A](a.png)\n\n![캡B](b.png){caption=left width=4cm}\n:::\n").items[0].blocks
    assert 둘 == (SideBySide((Figure("a.png", None, ("캡A",)), Figure("b.png", 40.0, ("캡B",), "left"))),)
    셋 = parse_sheet(머리 + "## 가 {1점}\n:::나란히\n![](a.png)\n![](b.png)\n![](c.png)\n:::\n").items[0].blocks[0]
    assert [f.path for f in 셋.figures] == ["a.png", "b.png", "c.png"]


@pytest.mark.parametrize("본문, 문구", [
    ("## 가 {1점}\n:::나란히\n![](a.png)\n:::\n", r"8번째 줄: :::나란히 에는 그림 줄을 2~3개 쓴다 — 지금 1개"),
    ("## 가 {1점}\n:::나란히\n" + "![](a.png)\n" * 4 + ":::\n", r"8번째 줄: :::나란히 에는 그림 줄을 2~3개 쓴다 — 지금 4개"),
    ("## 가 {1점}\n:::나란히\n![](a.png)\n글 줄\n:::\n", r"10번째 줄: :::나란히 안에는 그림 줄만 쓴다"),
    ("## 가 {1점}\n:::나란히\n![](a.png)\n![](b.png){align=x}\n:::\n", r"10번째 줄: 그림 줄에 모르는 속성이 있다"),
    ("## 가 {1점}\n:::나란히 셋\n![](a.png)\n:::\n", r"머리 줄에는 아무것도 더 쓰지 않는다"),
])
def test_나란히_입력_오류(본문, 문구):
    with pytest.raises(MdError, match=문구):
        parse_sheet(머리 + 본문)


def test_문항_밖_블록은_최상위_항목():
    s = parse_sheet(머리 + (
        ":::안내\n시험 시간 50분\n:::\n"
        ":::제시문\n공통 글\n:::\n"
        ":::조건\n조건 1\n:::\n"
        "![캡](a.png)\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n"
        ":::나란히\n![](a.png)\n![](b.png)\n:::\n"
        "## 가 {1점}\n"
        "::::묶음 2-2 공통\n## 나 {1점}\n::::\n"
        ":::안내\n여기부터 2부\n:::\n"
        ":::단나눔\n"
        "## 다 {1점}\n"
    ))
    kinds = [type(e).__name__ for e in s.entries]
    assert kinds == ["Passage", "Passage", "Passage", "Figure", "DataTable", "SideBySide", "Item", "Group", "Passage", "ColumnBreak", "Item"]
    assert s.entries[0] == Passage("안내", ("시험 시간 50분",))
    assert s.entries[8] == Passage("안내", ("여기부터 2부",))
    assert [i.number for i in s.items] == [1, 2, 3]


def test_안내는_문항_안에서도_쓴다():
    s = parse_sheet(머리 + "## 가 {1점}\n:::안내\n알림\n:::\n")
    assert s.items[0].blocks == (Passage("안내", ("알림",)),)


@pytest.mark.parametrize("본문", [
    ":::답칸 (가)\n", ":::표답칸\nA\n:::\n", ":::서술칸 3줄\n", ":::서술칸\n라벨\n:::\n",
    "> (단, 조건)\n", "일반 글\n",
])
def test_문항_밖에_둘_수_없는_블록(본문):
    with pytest.raises(MdError, match=r"7번째 줄: 문항 밖에 블록이 있다"):
        parse_sheet(머리 + 본문)


def test_문항_밖_정답은_거부():
    with pytest.raises(MdError, match=r"7번째 줄: :::정답 은 문항 안에만 둔다"):
        parse_sheet(머리 + ":::정답\n답\n:::\n")
