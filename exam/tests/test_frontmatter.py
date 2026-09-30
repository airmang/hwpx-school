import pytest

from exam_kit.frontmatter import FrontMatter, parse_front_matter

머리 = """---
양식: 예시-원안지
학년도: 2026
학년: 2
학기: 2
차: 2
과목: 인공지능 기초
과목코드: 16
시행: 12.14.(월) 3교시
대상: 2학년 6반~10반
인쇄: 30매 * 4묶음
출제교사: 김출제
---
## 1. [4.0점]
발문
"""


def test_파싱과_분해():
    fm, body = parse_front_matter(머리)
    assert (fm.학년도, fm.학년, fm.학기, fm.차) == (2026, 2, 2, 2)
    assert fm.과목 == "인공지능 기초" and fm.과목코드 == "16" and fm.만점 == 100.0 and fm.논술형 is False
    assert fm.시행_분해() == {"월": "12", "일": "14", "요일": "월", "교시": "3"}
    assert fm.대상_분해() == {"학년": "2", "반_시작": "6", "반_끝": "10"}
    assert fm.인쇄_분해() == {"인쇄매수": "30", "묶음": "4"}
    assert fm.is_draft is False
    assert body.startswith("## 1. [4.0점]")


def test_초안_자리표시():
    fm, _ = parse_front_matter(머리.replace("12.14.(월) 3교시", "12.__.(_) _교시").replace("30매 * 4묶음", "__매 * _묶음"))
    assert fm.시행_분해() == {"월": "12", "일": None, "요일": None, "교시": None}
    assert fm.인쇄_분해() == {"인쇄매수": None, "묶음": None}
    assert fm.is_draft is True


def test_한글_표기도_받는다():
    fm, _ = parse_front_matter(머리.replace("12.14.(월) 3교시", "12월 14일 (월) 3교시"))
    assert fm.시행_분해()["일"] == "14"


@pytest.mark.parametrize("bad", ["시행: 2026.12.14 3교시", "대상: 2학년 6~10반", "인쇄: 30매"])
def test_형식_오류는_실패한다(bad):
    key = bad.split(":")[0]
    text = "\n".join(l if not l.startswith(key + ":") else bad for l in 머리.splitlines())
    with pytest.raises(ValueError):
        parse_front_matter(text)


def test_필수_키_누락():
    with pytest.raises(ValueError, match="출제교사"):
        parse_front_matter("\n".join(l for l in 머리.splitlines() if not l.startswith("출제교사")))


def test_모르는_키():
    with pytest.raises(ValueError, match="학교"):
        parse_front_matter(머리.replace("출제교사: 김출제", "출제교사: 김출제\n학교: 어느고"))


def test_대상_반_미정은_초안():
    """(Task 19) 대상 반을 아직 모르면 `_반~_반` — 초안이고, 반 슬롯은 비워(자리표시) 둔다."""
    md = """---
양식: 예시-원안지
학년도: 2026
학년: 2
학기: 2
차: 2
과목: 합성
과목코드: 16
시행: __.__.(_) _교시
대상: 2학년 _반~_반
인쇄: __매 * _묶음
출제교사: 홍길동
---
"""
    fm, _ = parse_front_matter(md)
    assert fm.is_draft and fm.대상_분해() == {"학년": "2", "반_시작": None, "반_끝": None}


def test_대상_반_한쪽만_미정은_오류():
    md = """---
양식: 예시-원안지
학년도: 2026
학년: 2
학기: 2
차: 2
과목: 합성
과목코드: 16
시행: __.__.(_) _교시
대상: 2학년 3반~_반
인쇄: __매 * _묶음
출제교사: 홍길동
---
"""
    with pytest.raises(ValueError, match="둘 다"):
        parse_front_matter(md)


def test_킷_front_matter가_필수_키를_정한다():
    from exam_kit.frontmatter import parse_front_matter

    학교B = {"required": ["양식", "학년도", "학년", "학기", "차", "과목", "시행", "출제교사"],
            "optional": ["만점", "논술형", "과목코드", "대상", "인쇄"]}
    md = "---\n양식: b\n학년도: 2026\n학년: 2\n학기: 2\n차: 2\n과목: 정보\n시행: 12월 15일 (화) 3교시\n출제교사: 김, 이\n---\n"
    fm, _ = parse_front_matter(md, 학교B)
    assert fm.과목코드 is None and fm.대상 is None and not fm.is_draft and fm.teachers() == ["김", "이"]
    누름틀 = {"required": list(학교B["required"]) + ["과목코드", "대상", "인쇄"], "optional": ["만점", "논술형"]}
    with pytest.raises(ValueError, match="필수 키 누락"):
        parse_front_matter(md, 누름틀)
