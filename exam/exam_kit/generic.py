"""킷 없는 양식의 역변환 프로필(이슈 #8 일반 규칙) — 등록하지 않은 학교·교과의 원안지도 원고로 되돌린다.

학교 킷이 아는 것(문항 번호 방식·박스 모양·누름틀 자리·꼬리 박스 글)을 일반 규칙으로 찾는다.
- 문항 머리: 자동번호 문단, 또는 최상위 문단 글이 `N.`·`N)`로 시작하는 문단 — N이 1부터 차례대로 이어질 때만(박스 밖 다른
  번호 글에 걸리지 않게).
- 본문: 첫 문항 머리부터. 그 앞(제목·안내·결재 표)은 머리 값을 찾는 데만 쓴다.
- 꼬리: 용지 기준으로 고정한 표가 있는 마지막 문단(꼬리 박스) 앞까지, 없으면 문서 끝까지.
- 박스: 표의 첫 글 줄이 제목(〈보기〉·<보 기>·[조건] 등)이면 그 박스, 제목 없이 글 칸이 하나뿐인 표는 자료, 나머지는 격자표
  (reverse.generic_box). 짝짓기 답항표·코드·그림·수식·보존 구간은 킷 양식과 같은 규칙.
- 머리 값: 첫 문항 앞의 글과 머리말·꼬리말에서 정규식으로(학년도·학년·학기·차·과목·시행·출제교사). 못 찾은 값은
  역변환이 멈추며 `--front 키=값`을 알린다. 양식 이름은 `미등록`(그 학교를 등록하면 킷 이름으로 바꾼다).
일반 규칙으로 찾은 것은 추정이다 — 보고에 그렇게 적는다. 모르는 구조는 킷 양식처럼 자리·까닭을 대고 멈춘다.
"""

from __future__ import annotations

import re

from hwpx.document import HwpxDocument

from .reverse import GENERIC_BOXES, FormProfile
from .verify import _nested_raw, _numbered_para_prs

미등록 = "미등록"
_번호 = re.compile(r"^\s*(\d{1,3})\s*[.．)]\s*\S")
_기본_필수 = ("양식", "학년도", "학년", "학기", "차", "과목", "시행", "출제교사")


#: run.content 조각 중 hp:t 안의 글(글리프·표시는 빼고).
_TEXT_KINDS = ("text", "unknown")


def _flat(paragraphs) -> str:
    """문단들의 글 — 문단 안 표 칸·글상자·캡션 글까지 문서 차례로(``nested_text``), 글리프는 빼고 공백을 하나로 접는다."""
    return re.sub(r"\s+", " ", _nested_raw(paragraphs)).strip()


def _table_paragraphs(table) -> list:
    """표의 문단 — 캡션, 그리고 행·칸 차례(칸 안 표는 칸 문단의 nested_text가 읽는다)."""
    out = list(table.caption.paragraphs) if table.caption is not None else []
    return out + [p for row in table.rows for cell in row.cells for p in cell.paragraphs]


def _own_text(p) -> str:
    """최상위 문단 자신의 글(문단 안 표·그림 칸의 글은 빼고)."""
    return re.sub(r"\s+", " ", "".join(item.text for run in p.runs for item in run.content
                                       if item.container == "t" and item.kind in _TEXT_KINDS)).strip()


def heads(doc: HwpxDocument) -> list[int]:
    """문항 머리 — 자동번호 문단, 또는 차례대로 이어지는 글자 번호(`1.`·`2)` …)로 시작하는 최상위 문단."""
    nums = _numbered_para_prs(doc)
    out, want = [], 1
    for i, p in enumerate(doc.sections[0].paragraphs):
        if str(p.para_pr_id_ref) in nums:
            out.append(i)
            want += 1
            continue
        m = _번호.match(_own_text(p))
        if m and int(m.group(1)) == want:
            out.append(i)
            want += 1
    return out


def tail(doc: HwpxDocument) -> int:
    """본문 끝(꼬리 박스 문단) — ① 용지 기준으로 고정한 표가 있는 마지막 문단, ② 마지막 문항 뒤에서 첫 글이 `※`인 표
    (확인 사항·유의 사항 안내 상자)가 있는 첫 문단, ③ 없으면 문서 끝."""
    ps = list(doc.sections[0].paragraphs)
    for i in range(len(ps) - 1, 0, -1):
        for place in ps[i].iter_objects(kinds="table"):
            pos = place.object.position
            if not pos.treat_as_char and pos.vertical_relative_to == "PAPER":
                return i
    hs = heads(doc)
    for i in range(hs[-1] + 1 if hs else 1, len(ps)):
        if any(_flat(_table_paragraphs(place.object)).startswith("※") for place in ps[i].iter_objects(kinds="table")):
            return i
    return len(ps)


def front(doc: HwpxDocument) -> dict[str, str | None]:
    """첫 문항 앞의 글·머리말·꼬리말에서 찾은 머리 값 — 못 찾으면 None."""
    hs = heads(doc)
    ps = list(doc.sections[0].paragraphs)
    before = " ".join(_flat([p]) for p in ps[:hs[0] if hs else len(ps)])
    first = doc.sections[0]
    hf = " ".join(_flat(story.paragraphs) for story in (*doc.page.headers(section=first), *doc.page.footers(section=first)))
    text = f"{hf} {before}"  # 머리말이 더 믿을 만하다 — 먼저 찾는다

    def find(rx: str) -> str | None:
        m = re.search(rx, text)
        return m.group(1) if m else None

    월, 일 = find(r"(\d{1,2})\s*월\s*\d{1,2}\s*일"), find(r"\d{1,2}\s*월\s*(\d{1,2})\s*일")
    요일, 교시 = find(r"[(（]\s*([월화수목금토일])\s*[)）]"), find(r"(\d)\s*교시")
    return {
        "양식": 미등록,
        # 값이 괄호 안에 든 양식도 있다 — 예 "2026학년도 (1)학년 (2)학기 (1)차 정기시험 (합성과학)과"
        "학년도": find(r"(20\d\d)\s*학년도"),
        "학년": find(r"[(（]?\s*([1-6])\s*[)）]?\s*학년(?!도)"),
        "학기": find(r"[(（]?\s*([12])\s*[)）]?\s*학기"),
        "차": find(r"[(（]?\s*([1-4])\s*[)）]?\s*차"),
        "과목": find(r"과\s*목\s*(?:명)?\s*[:：]\s*([가-힣A-Za-z][가-힣A-Za-z0-9·Ⅰ-Ⅻ]{0,15})")
                or find(r"[(（]\s*([가-힣A-Za-z][가-힣A-Za-z0-9·Ⅰ-Ⅻ ]{0,15}?)\s*[)）]\s*과(?:목)?(?=\s|$)"),
        "시행": f"{월 or '__'}.{일 or '__'}.({요일 or '_'}) {교시 or '_'}교시",
        "출제교사": find(r"출\s*제\s*(?:교\s*사|자)\s*[:：]?\s*([가-힣]{2,4})") or "미상",
    }


def generic_profile() -> FormProfile:
    """킷 없는 양식의 역변환 프로필 — reverse(src, generic_profile())."""
    return FormProfile(미등록, None, None, GENERIC_BOXES, _기본_필수, front,
                       heads=heads, start=lambda hs: hs[0], tail=tail)
