"""학교 원안지(지필 시험지) hwpx — 학교 무관 엔진: 킷·규칙 검사·파이프라인. 학교마다 다른 것은 킷(저장소 밖)에.

조판 자체는 python-hwpx-automation의 ``hwpx_automation.office.exam``이 한다.
"""

__version__ = "0.1.0"

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
NS = {"hp": HP, "hh": HH, "hc": HC}


def q(prefix: str, tag: str) -> str:
    """lxml용 정규화 태그 — ``q("hp", "tbl") == "{…/paragraph}tbl"``."""
    return f"{{{NS[prefix]}}}{tag}"
