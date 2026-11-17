"""학교 킷 없이도 도는 판 — 학교 킷 전용 시험 모듈(test_compose·test_fit·test_layout·test_build·test_convert·test_geometry·
test_kit·test_lint·test_prepare·test_render·test_reverse) 가운데 합성 킷(kits/synthetic)으로 옛 판(c66ff81)과 지금 모두 통과하는
시험을 합성 킷으로 다시 돌린다. 옛·새 길이 같은 결과임을 고정한다.

그 모듈들은 학교 킷 환경변수(EXAM_KIT_PATH)가 없으면 통째로 건너뛴다(_kits.kit_dir). 여기서는 환경변수를 잠깐 합성 킷으로 두고
모듈을 다른 이름으로 읽어 고른 시험만 가져온다. 시험 몸에서 kit_dir()을 부르는 것도 있어 고른 시험이 도는 동안에도 합성 킷을
가리킨다. 학교 킷이 있으면 원래 모듈이 돌므로 여기서는 건너뛴다(두 번 돌지 않게). 한/글이 필요한 시험은 넣지 않는다(오라클이
없으면 건너뛴다).
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
    "test_layout": ["test_간격_기본은_distribute", "test_꼬리_자리_판정", "test_단_나눔_균형"],  # 답지 다시 쓰기 시험(2개)은 픽스처 이름(배치)이 test_compose와 겹쳐 뺀다
    "test_build": ["test_git_밖이면_모른다", "test_lint_warn이면_경고로_두고_조판한다", "test_규칙_오류를_넘기고_조판했으면_맨_앞에_알린다", "test_규칙_오류면_조판하지_않는다",
                   "test_단_나눔_pack은_settle의_balance로", "test_두_판_꾸러미_대조", "test_두_판_배치_대조",
                   "test_두_판_배치_대조는_Windows_형광펜_밀림만_봐준다", "test_보고서_단계_줄은_stage로", "test_보고서는_확인_필요와_쪽_추가를_드러낸다",
                   "test_보고서의_파일_열기_명령은_OS에_맞다", "test_빈_형광펜은_정답이_아니다", "test_옛_산출물_정리는_다른_원고를_건드리지_않는다",
                   "test_옛_산출물_정리는_대괄호를_glob으로_읽지_않는다", "test_쪽_추가는_글귀가_아니라_쪽수로", "test_출력_폴더가_git_무시_대상이_아니면_알린다",
                   "test_형광펜_더하기는_조판_형광펜과_같은_자리", "test_형광펜_자리가_없으면_멈춘다"],
    "test_convert": ["test_CLI", "test_ᄆ_밖의_보기_항목_기호는_멈춘다", "test_그림_두_장_문항은_인쇄_규격_교체를_멈춘다", "test_답지의_굵게는_벗기고_규칙_검사가_잡는다",
                     "test_두_줄_발문은_이어서_옮긴다", "test_머리는_제목과_주어진_값에서", "test_목록_표지_없는_보기_항목과_자리_벗어난_줄",
                     "test_박스_뒤_본문_줄은_발문_이음_줄이다", "test_변환은_옮김_규칙대로", "test_보기_뒤_참고_줄은_보기_아래_본문_줄로", "test_불변_검사는_글_정답_배점을_잡는다",
                     "test_불변_검사는_차례를_본다", "test_어긋나면_변환이_멈춘다", "test_인쇄_규격_그림으로_바꾼다", "test_접힌_답지는_멈춘다", "test_접힌_보기_항목은_멈춘다",
                     "test_참고_줄은_스캔_규칙_조판까지", "test_참고_줄은_역변환에서도_보기_아래로", "test_해설의_정답을_정답_일람과_대조한다"],
    "test_geometry": ["test_Windows_한컴_PDF가_아니면_Type3_글자를_더하지_않는다", "test_Windows_한컴_PDF의_형광펜_사각형만_뺀다", "test_박스_찾기",
                      "test_박스와_격자표_가르기_빈_틀_버리기", "test_잉크_상자는_글자_폭_상자_안의_잉크에_붙는다"],
    "test_kit": ["test_schema가_다르면_멈춘다", "test_verify_kit_양식", "test_양식_sha가_kit과_같다", "test_킷_버전은_README_이력_맨_위와_같다"],
    "test_lint": ["test_CLI", "test_E001_문법", "test_E002_번호_연속", "test_E004_배점_합", "test_E005_정답_수", "test_E006_답지_다섯",
                  "test_E009_답항표", "test_E010_그림_존재", "test_E011_세트", "test_E014_반의_접두_제외", "test_E017_명사_경계_오탐_없음",
                  "test_E021_첫_문항_나눔_지시", "test_W022_그림을_줄여_넣으면_경고", "test_W023_그림을_늘려_넣으면_경고", "test_모르는_학교_규칙_코드는_멈춘다",
                  "test_엔진_규칙과_학교_규칙은_겹치지_않는다", "test_픽스처는_오류_0"],
    "test_prepare": ["test_sha_검사", "test_사이드카", "test_양식_변조_감지"],
    "test_render": ["test_side_by_side_쪽_수가_다르면_없는_쪽은_빈_칸", "test_기한을_넘기면_HancomBusy", "test_다른_쪽이_쥐면_기다렸다_들어간다",
                    "test_렌더_실패하면_한컴을_띄우고_한_번_재시도", "test_렌더와_줄_캐시_저장은_잠금_안에서", "test_오라클은_닿는_실한컴을_고른다",
                    "test_윈도우에서는_한컴을_띄우지_않는다", "test_잠금_경로는_upstream_공용_잠금", "test_저장을_못_하는_오라클이면_줄_캐시를_재지_않는다",
                    "test_한컴_띄우기는_멈춘_호출에_막히지_않는다"],
    "test_reverse": ["test_bin_items", "test_classify_table_3x3_제목행_병합_격자는_자료가_아니다", "test_classify_table_격자표",
                     "test_classify_table_그림_표가_든_격자표는_오류", "test_classify_table_병합_칸_격자표는_오류", "test_cli_출력_폴더를_만든다",
                     "test_detect_matching", "test_main_scan_오류면_0이_아니다", "test_matching_머리_변형",
                     "test_paragraph_text_글_없는_컨트롤은_건너뛴다", "test_paragraph_text_글을_싣는_컨트롤은_오류",
                     "test_paragraph_text_노랑_형광펜이_낱말에_있으면_오류", "test_paragraph_text_모르는_요소는_오류",
                     "test_paragraph_text_밑줄_run_앞뒤_공백은_밑줄_밖으로", "test_paragraph_text_변경_추적은_오류", "test_paragraph_text_탭_밑줄_형광펜",
                     "test_paragraph_text_형광펜_뒤_공백·run_경계를_건넌다", "test_paragraph_text_흰_형광펜은_정답이_아니다",
                     "test_picture_line_원래_폭_cm", "test_reverse_body_BinData_없으면_오류", "test_reverse_body_답지_뒤_본문은_오류",
                     "test_reverse_body_답지가_다섯이_아니면_오류", "test_reverse_body_머리_없는_열맞춤_답지는_오류",
                     "test_reverse_body_짝짓기_열맞춤_실패는_오류", "test_reverse_body_첫_문항_앞_내용은_오류", "test_split_choices",
                     "test_split_choices_답지_속_원문자는_자르지_않는다"],
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


@pytest.fixture(autouse=True)
def _합성_킷_환경(monkeypatch):
    """고른 시험이 도는 동안 kit_dir()·킷_루트가 합성 킷을 가리키게. 실한컴 오라클은 '없음'으로 둔다(한/글을 띄우지 않는다 —
    오라클을 고르는 시험은 스스로 available을 바꿔 끼운다)."""
    from hwpx_automation.office.rendering import oracle as O

    monkeypatch.setenv("EXAM_KIT_PATH", str(_합성))
    for 오라클 in (O.WindowsComOracle, O.MacHancomOracle):
        monkeypatch.setattr(오라클, "available", lambda self: False)


for _이름, _시험들 in _고른.items():
    _m = _모듈[_이름]
    for _k, _v in vars(_m).items():  # 그 모듈의 픽스처도 함께(견본 따위)
        if hasattr(_v, "_pytestfixturefunction") or type(_v).__name__ == "FixtureFunctionDefinition":
            globals().setdefault(_k, _v)
    for _t in _시험들:
        globals()[f"{_t}__{_이름[5:]}"] = getattr(_m, _t)
