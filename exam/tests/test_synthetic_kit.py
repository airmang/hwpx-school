"""학교 킷 없이도 도는 판 — test_compose·test_fit·test_layout 가운데 합성 킷(kits/synthetic)으로 옮기기 전(c66ff81)과 지금
모두 통과하는 시험을 합성 킷으로 다시 돌린다. 옛·새 길이 같은 결과임을 고정한다.

세 모듈은 학교 킷 환경변수(EXAM_KIT_PATH)가 없으면 통째로 건너뛴다(_kits.kit_dir). 여기서는 환경변수를 잠깐 합성 킷으로 두고
세 모듈을 다른 이름으로 읽어 고른 시험만 가져온다. 학교 킷이 있으면 원래 모듈이 돌므로 여기서는 건너뛴다(두 번 돌지 않게).
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_여기 = Path(__file__).resolve().parent
_합성 = _여기.parent / "kits" / "synthetic"
_고른 = {
    "test_compose": ["test_1행은_자동으로_고르지_않는다", "test_격자표", "test_견본_전유형이_모두_조판된다", "test_그림_생성기_폴백과_EXIF_회전",
                     "test_그림_오류는_드러낸다", "test_그림은_줄이지_않고_넓으면_멈춘다", "test_그림은_회색조_사본이_가운데_문단에_앉는다",
                     "test_낱말_단위_접기", "test_답지_5행_한_줄에_하나", "test_답지_다시_쓰기도_물결을_바꾼다", "test_답항표",
                     "test_답항표_균등과_글_길이", "test_답항표_문항의_답항_덮어쓰기는_무시하고_알린다", "test_답항표_문항지_판은_형광펜_없음",
                     "test_답항표_열_수가_머리와_다르면_거부", "test_물결은_조판에서_모두_전각_물결로", "test_밑줄_자식이_없는_charPr는_거부",
                     "test_박스는_견본과_같은_셀_구조로_발문_다음_문단에_앉는다", "test_배치형_덮어쓰기", "test_배치형_보호_묶음과_형광펜",
                     "test_배치형_자동_선택과_줄_구성", "test_보기_안의_표는_거부", "test_새_객체_id는_모든_객체_id_위에서_발급",
                     "test_스캔_오류와_번호_어긋남은_거부", "test_양식_분기가_없으면_양식이_바뀌었다", "test_열_폭",
                     "test_열_폭_넘칠_때는_가장_긴_낱말부터", "test_조판이_만든_paraPr는_모두_쓰인다", "test_줄_수_추정",
                     "test_칸_문단에_칠할_원문자가_없으면_거부", "test_코드_블록_빈_줄은_빈_문단으로_남는다", "test_코드_블록은_고정폭_왼쪽_정렬",
                     "test_형광펜_판본"],
    "test_fit": ["test_가짜_끌어올림은_벌어진_줄_다음_줄이_움직여야", "test_가짜_낱말_끌어올림", "test_가짜_맞춤_가장_작은_자간과_역할_하한",
                 "test_가짜_여유가_줄_시작을_바꾸면_최소값으로", "test_가짜_이미_맞춘_문단은_다시_맞추지_않는다", "test_가짜_측정_글자가_다르면_멈춘다",
                 "test_기준본과_줄_대조", "test_꾸러미_검사", "test_나눔_지시는_묶음_첫_문단에", "test_대상_문단", "test_두_관점_대조_저장_캐시",
                 "test_벌어짐은_탭_줄을_빼고_줄마다", "test_양식_검사는_견본_박스_높이를_킷과_대조한다", "test_자간_charPr_파생·재사용·걷어내기",
                 "test_줄_캐시_읽기", "test_측정은_한_번_더_해_본다"],
    "test_layout": ["test_간격_기본은_distribute", "test_꼬리_자리_판정", "test_단_나눔_균형"],  # 답지 다시 쓰기 시험은 픽스처 이름(배치)이 test_compose와 겹쳐 뺀다
}

if os.environ.get("EXAM_KIT_PATH"):
    pytest.skip("학교 킷이 있다 — 원래 모듈이 돈다", allow_module_level=True)


def _읽기() -> dict:
    """환경변수를 합성 킷으로 두고 세 모듈을 `합성_<이름>`으로 읽는다. 그동안 새로 읽힌 시험 모듈(test_layout 등)은 지워
    pytest가 원래 이름으로 다시 읽을 때 환경변수 없이(건너뛰게) 읽히게 한다."""
    before = set(sys.modules)
    os.environ["EXAM_KIT_PATH"] = str(_합성)
    try:
        mods = {}
        for name in _고른:
            spec = importlib.util.spec_from_file_location(f"합성_{name}", _여기 / f"{name}.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mods[name] = mod
        return mods
    finally:
        del os.environ["EXAM_KIT_PATH"]
        for k in set(sys.modules) - before:
            if k.startswith("test_"):
                del sys.modules[k]


_모듈 = _읽기()


@pytest.fixture(scope="session")
def 양식_hwpx() -> Path:
    return _합성 / "synthetic_form.hwpx"


for _이름, _시험들 in _고른.items():
    _m = _모듈[_이름]
    for _k, _v in vars(_m).items():  # 그 모듈의 픽스처도 함께(견본 따위)
        if hasattr(_v, "_pytestfixturefunction") or type(_v).__name__ == "FixtureFunctionDefinition":
            globals().setdefault(_k, _v)
    for _t in _시험들:
        globals()[f"{_t}__{_이름[5:]}"] = getattr(_m, _t)
