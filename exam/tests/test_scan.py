from pathlib import Path

from exam_kit.frontmatter import parse_front_matter
from exam_kit.scan import scan_markdown

픽스처 = Path(__file__).parent / "fixtures" / "견본_전유형.md"
머리 = 픽스처.read_text(encoding="utf-8").split("\n## 1.")[0] + "\n"


def _scan(body: str):
    return scan_markdown(머리 + body)


def test_픽스처_전체():
    s = scan_markdown(픽스처.read_text(encoding="utf-8"))
    assert s.errors == ()
    assert [q.number for q in s.questions] == [str(i) for i in range(1, 11)]
    assert abs(sum(q.points for q in s.questions) - 100.0) < 1e-9
    assert [q.choices[[c.correct for c in q.choices].index(True)].mark for q in s.questions] == list("②④①⑤③②④①④③")
    assert s.questions[1].blocks[0].kind == "보기" and len(s.questions[1].blocks[0].lines) == 4
    assert s.questions[3].blocks[0].kind == "표" and len(s.questions[3].blocks[0].lines) == 4
    assert s.questions[4].blocks[0].kind == "그림" and s.questions[4].blocks[0].attrs == {"src": "그림.png", "width_cm": 6.0}
    assert s.questions[5].blocks[1].kind == "답항표" and s.questions[5].blocks[1].attrs["머리"] == ["(가)", "(나)", "(다)"]
    assert s.questions[5].choices[1].text == "지도 | 강화 | 비지도" and s.questions[5].choices[1].correct
    assert s.sets[0].rng == ("7", "8") and s.sets[0].blocks[0].kind == "자료"
    assert s.questions[6].set_rng == ("7", "8") and s.questions[8].override == "3행"
    assert s.questions[9].blocks[0].kind == "자료" and s.questions[9].blocks[0].lines[0].startswith("| 모델")


def test_문항_머리_변형():
    s = _scan("## 1. (4점)\n발문?\n① a\n*② b\n③ c\n④ d\n⑤ e\n")
    assert s.questions[0].points == 4.0 and s.questions[0].points_raw == "(4점)"
    s = _scan("## 1.\n발문?\n① a\n*② b\n③ c\n④ d\n⑤ e\n")
    assert s.questions[0].points is None


def test_오류_수집():
    s = _scan("발문이 먼저\n## 1. [4.0점]\n발문?\n:::보기\nㄱ. x\n① a\n")
    reasons = [e.reason for e in s.errors]
    assert any("문항 앞" in r for r in reasons)
    assert any("펜스" in r for r in reasons)
    앞_오류 = next(e for e in s.errors if "문항 앞" in e.reason)
    펜스_오류 = next(e for e in s.errors if "펜스" in e.reason)
    assert 앞_오류.line_no == 15  # 픽스처 머리(13줄 front-matter + 빈 줄) 뒤 body 1번째 줄
    assert 펜스_오류.line_no == 20  # 닫히지 않은 펜스 — 마지막 줄(① a)에서 검출
    s = _scan("## 1. [4.0점]\n발문?\n:::엉뚱\n:::\n")
    assert any("펜스 이름" in e.reason for e in s.errors)
    s = _scan("### 1. [4.0점]\n발문?\n")
    assert any("세트 밖" in e.reason for e in s.errors)
    s = _scan("## 1. [4.0점]\n발문?\n① a\n② b\n덧붙임\n")
    assert any("답지 뒤" in e.reason for e in s.errors)


def test_문항_앞_표_오류():
    s = _scan("| a | b |\n|---|---|\n| 1 | 2 |\n## 1. [4.0점]\n발문?\n① a\n*② b\n③ c\n④ d\n⑤ e\n")
    표_오류 = [e for e in s.errors if "표" in e.reason]
    assert len(표_오류) == 1
    assert 표_오류[0].line_no == 15  # 표의 첫 줄(원문 기준)
    assert 표_오류[0].text == "| a | b |"
    assert 표_오류[0].reason == "문항 앞에 표가 있다"


def test_답항표_빈줄_줄번호():
    s = _scan("## 1. [4.0점]\n발문?\n:::답항표\n① a\n\n*② b\n:::\n")
    assert s.errors == ()
    assert s.questions[0].choices[0].line_no == 18
    assert s.questions[0].choices[1].line_no == 20  # 빈 줄(19)을 건너뛴 원문 줄 번호


def test_나눔_지시():
    """{단나눔}·{쪽나눔}(Task 29) — {답항=N행}과 순서 무관하게 같이 쓴다. 모르는 지시·겹친 지시는 오류."""
    q5 = "발문?\n① a\n*② b\n③ c\n④ d\n⑤ e\n"
    s = _scan(f"## 1. [4.0점]\n{q5}\n## 2. [4.0점] {{단나눔}} {{답항=2행}}\n{q5}\n## 3. [4.0점]{{답항=5행}}{{쪽나눔}}\n{q5}\n"
              f"## 4~5. 세트\n지문.\n\n### 4. [4.0점] {{쪽나눔}}\n{q5}\n### 5. [4.0점]\n{q5}")
    assert s.errors == ()
    assert [(q.override, q.brk) for q in s.questions] == [(None, None), ("2행", "column"), ("5행", "page"),
                                                          (None, "page"), (None, None)]
    bad = _scan(f"## 1. [4.0점] {{줄나눔}}\n{q5}\n## 2. [4.0점] {{단나눔}}{{쪽나눔}}\n{q5}")
    assert ["줄나눔" in e.reason for e in bad.errors] == [True, False] and "쪽나눔" in bad.errors[1].reason


def test_코드_블록():
    """(Task 30) ``` 펜스 — 문항 블록(앞 공백·빈 줄 그대로, 다른 문법으로 안 읽는다)과 :::자료 안(여닫는 줄째로 싣는다)."""
    body = ("## 1. [4.0점]\n발문?\n\n```text\nx = 1\n  y  =  2\n\n① 이건 답지가 아니다\n```\n\n"
            ":::자료\n설명\n```\na    1\n\nb    2\n```\n:::\n\n① a\n*② b\n③ c\n④ d\n⑤ e\n")
    s = _scan(body)
    assert s.errors == ()
    code, jaryo = s.questions[0].blocks
    assert code.kind == "코드" and code.lines == ("x = 1", "  y  =  2", "", "① 이건 답지가 아니다") and code.attrs["lang"] == "text"
    assert jaryo.kind == "자료" and jaryo.lines == ("설명", "```", "a    1", "", "b    2", "```")
    assert len(s.questions[0].choices) == 5
    assert [e.reason for e in _scan("## 1. [4.0점]\n발문?\n```\nx\n").errors] == ["닫히지 않은 코드 블록"]
