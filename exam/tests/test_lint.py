from pathlib import Path

import pytest

from _kits import kit_dir
from exam_kit.kit import load_kit
from exam_kit.lint import ENGINE_RULES, SCHOOL_RULES, errors, lint

픽스처 = Path(__file__).parent / "fixtures" / "견본_전유형.md"
머리 = 픽스처.read_text(encoding="utf-8").split("\n## 1.")[0] + "\n"
_5 = "① a\n*② b\n③ c\n④ d\n⑤ e\n"


def _q(n: int, points: str = "[10.0점]", stem: str = "발문?", body: str = "", choices: str = _5, head_extra: str = "") -> str:
    return f"## {n}. {points}{head_extra}\n{stem}\n{body}{choices}\n"


def _md(*qs: str) -> str:
    return 머리 + "".join(qs)


_규칙 = load_kit(kit_dir()).rules


def _codes(md: str, **kw) -> set[str]:
    return {v.code for v in lint(md, rules=_규칙, **kw)}


def test_픽스처는_오류_0():
    vs = lint(픽스처.read_text(encoding="utf-8"), md_dir=픽스처.parent, rules=_규칙)
    assert errors(vs) == [], [f"{v.code} L{v.line_no} {v.msg}" for v in errors(vs)]


def test_E001_문법():
    assert "E001" in _codes(_md("본문 먼저\n" + _q(1)))


def test_E002_번호_연속():
    assert "E002" in _codes(_md(_q(1, "[50.0점]"), _q(3, "[50.0점]")))


def test_E003_배점_표기():
    assert "E003" in _codes(_md(_q(1, "[100점]")))
    assert "E003" in _codes(_md(_q(1, "[100.00점]")))
    assert "W003" in _codes(_md(_q(1, "(100점)")))


def test_E004_배점_합():
    assert "E004" in _codes(_md(_q(1, "[60.0점]"), _q(2, "[30.0점]")))
    assert "E004" not in _codes(_md(_q(1, "[60.0점]"), _q(2, "[40.0점]")))


def test_E005_정답_수():
    assert "E005" in _codes(_md(_q(1, "[100.0점]", choices="① a\n② b\n③ c\n④ d\n⑤ e\n")))
    assert "E005" in _codes(_md(_q(1, "[100.0점]", choices="*① a\n*② b\n③ c\n④ d\n⑤ e\n")))


def test_E006_답지_다섯():
    assert "E006" in _codes(_md(_q(1, "[100.0점]", choices="*① a\n② b\n③ c\n④ d\n")))
    assert "E006" in _codes(_md(_q(1, "[100.0점]", choices="*② b\n① a\n③ c\n④ d\n⑤ e\n")))


def test_E007_정답_편중():
    qs = [_q(i, "[10.0점]", choices=_5) for i in range(1, 11)]  # 전부 ② → 편중
    assert "E007" in _codes(_md(*qs))
    same = [_q(i, "[10.0점]", choices=_5.replace("*②", "②").replace(f"{m} ", f"*{m} ", 1)) for i, m in zip(range(1, 11), "①②③④⑤①②③④⑤")]
    assert "W007" in _codes(_md(*same))


def test_E008_블록_순서():
    body = ":::보기\nㄱ. x\n:::\n:::자료\n글\n:::\n"
    assert "E008" in _codes(_md(_q(1, "[100.0점]", body=body)))


def test_E009_답항표():
    body = ':::답항표 머리="ㄱ|ㄴ"\n① a | b\n*② a | b\n③ a | b\n④ a | b | c\n⑤ a | b\n:::\n'
    assert "E009" in _codes(_md(_q(1, "[100.0점]", body=body, choices="")))
    body = ':::답항표\n① a | b\n*② a | b\n③ a | b\n④ a | b\n⑤ a | b\n:::\n'
    assert "E009" in _codes(_md(_q(1, "[100.0점]", body=body, choices="")))


def test_E010_그림_존재(tmp_path):
    md = _md(_q(1, "[100.0점]", body="![](없음.png){width=5cm}\n"))
    assert "E010" in _codes(md, md_dir=tmp_path)


def test_E011_세트():
    md = _md("## 1~2. 세트\n지문\n### 1. [100.0점]\n발문?\n" + _5)
    assert "E011" in _codes(md)


def test_E012_물결():
    assert "E012" in _codes(_md(_q(1, "[100.0점]", stem="[1~2] 다음 글을 읽고 답하시오?")))


def test_E013_보기_기호():
    assert "E013" in _codes(_md(_q(1, "[100.0점]", body=":::보기\n(1) x\n:::\n")))
    assert "E013" in _codes(_md(_q(1, "[100.0점]", body=":::보기\n- x\n:::\n")))
    assert "E013" not in _codes(_md(_q(1, "[100.0점]", body=":::보기\nㄱ. x\n∘ y\n:::\n")))


@pytest.mark.parametrize("stem", ["설명으로 적합한 것은?", "관계가 가장 거리가 먼 것은?", "가깝지 않은 것은?"])
def test_E014_금칙_어휘(stem):
    assert "E014" in _codes(_md(_q(1, "[100.0점]", stem=stem)))


@pytest.mark.parametrize("stem", ["부적합한 것은?", "부적당한 것은?"])
def test_E014_반의_접두_제외(stem):
    assert "E014" not in _codes(_md(_q(1, "[100.0점]", stem=stem)))


def test_E015_부정_가장():
    assert "E015" in _codes(_md(_q(1, "[100.0점]", stem="가장 적절하지 __않은__ 것은?")))


def test_E016_부정_밑줄():
    assert "E016" in _codes(_md(_q(1, "[100.0점]", stem="적절하지 않은 것은?")))
    assert "E016" in _codes(_md(_q(1, "[100.0점]", stem="적절하지 **않은** 것은?")))
    assert "E016" not in _codes(_md(_q(1, "[100.0점]", stem="적절하지 __않은__ 것은?")))


@pytest.mark.parametrize("stem", ["다음 〈보기〉에서 고른 것은?", "다음 그림에서 옳은 것은?", "다음 표에 대한 설명은?"])
def test_E017_다음_오용(stem):
    assert "E017" in _codes(_md(_q(1, "[100.0점]", stem=stem)))


@pytest.mark.parametrize("stem", ["다음 표현 중 옳은 것은?", "다음 표준에 맞는 것은?", "다음 그림책의 설명은?"])
def test_E017_명사_경계_오탐_없음(stem):
    assert "E017" not in _codes(_md(_q(1, "[100.0점]", stem=stem)))


@pytest.mark.parametrize("stem", ["다음 표에서 옳은 것은?", "다음 그림은 무엇인가?", "다음 〈보기〉에서"])
def test_E017_명사_경계_정탐_유지(stem):
    assert "E017" in _codes(_md(_q(1, "[100.0점]", stem=stem)))


def test_E018_윗글():
    assert "E018" in _codes(_md(_q(1, "[100.0점]", stem="위 글의 주제는?")))
    assert "E018" not in _codes(_md(_q(1, "[100.0점]", stem="윗글의 주제는?")))


def test_W019_답지_순서():
    ch = "① 아주 긴 답지입니다\n*② 짧다\n③ 중간 길이\n④ 아주아주 더 긴 답지입니다\n⑤ 중\n"
    assert "W019" in _codes(_md(_q(1, "[100.0점]", choices=ch)))
    assert "W019" not in _codes(_md(_q(1, "[100.0점]", choices="① ㄱ\n*② ㄴ\n③ ㄱ, ㄷ\n④ ㄴ, ㄷ\n⑤ ㄱ, ㄴ, ㄷ\n")))


def test_W020_물음표():
    assert "W020" in _codes(_md(_q(1, "[100.0점]", stem="다음을 고르시오.")))


def test_CLI(tmp_path, capsys):
    from exam_kit.lint import main

    bad = tmp_path / "bad.md"
    bad.write_text(_md(_q(1, "[100점]")), encoding="utf-8")
    assert main([str(bad)]) == 1
    assert "E003" in capsys.readouterr().out
    good = tmp_path / "good.md"
    good.write_text(픽스처.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "그림.png").write_bytes((픽스처.parent / "그림.png").read_bytes())
    assert main([str(good)]) == 0


def test_E021_첫_문항_나눔_지시():
    assert "E021" in _codes(_md(_q(1, head_extra=" {단나눔}"), _q(2)))
    assert "E021" not in _codes(_md(_q(1), _q(2, head_extra=" {쪽나눔}")))


def test_W022_그림을_줄여_넣으면_경고(tmp_path):
    """(Task 30) 원래 크기 = 원본 px ÷ 300dpi. 600px = 5.08cm — 4cm로 넣으면(축소) W022, 5.1cm면 없다. 자료 박스 안 그림도 본다."""
    from PIL import Image

    Image.new("L", (600, 300), 255).save(tmp_path / "a.png")
    작게 = _md(_q(1, body="![](a.png){width=4cm}\n\n"), _q(2, body=":::자료\n![](a.png){width=4cm}\n:::\n\n"))
    vs = [v for v in lint(작게, md_dir=tmp_path) if v.code == "W022"]
    assert len(vs) == 2 and "5.1cm" in vs[0].msg
    assert "W022" not in _codes(_md(_q(1, body="![](a.png){width=5.1cm}\n\n")), md_dir=tmp_path)
    assert "E010" in _codes(_md(_q(1, body=":::자료\n![](없음.png){width=4cm}\n:::\n\n")), md_dir=tmp_path)


def test_W023_그림을_늘려_넣으면_경고(tmp_path):
    """(m-3) 원고 폭이 원래 크기 × 1.02보다 크면 300dpi 아래로 늘려 넣는 것 — 흐려진다. 600px = 5.08cm."""
    from PIL import Image

    Image.new("L", (600, 300), 255).save(tmp_path / "a.png")
    vs = [v for v in lint(_md(_q(1, body="![](a.png){width=6cm}\n\n")), md_dir=tmp_path) if v.code == "W023"]
    assert len(vs) == 1 and "5.1cm" in vs[0].msg and "dpi" in vs[0].msg
    assert not {"W022", "W023"} & set(_codes(_md(_q(1, body="![](a.png){width=5.1cm}\n\n")), md_dir=tmp_path))


# ---- 학교 규칙 층(범용화 R3) -------------------------------------------------------

def test_학교_규칙은_rules_json이_켠다():
    나쁜 = _md(_q(1, "[100.0점]", stem="위 글에서 가장 적합한 것은"))
    assert {"E014", "E018", "W020"} <= _codes(나쁜)
    엔진만 = {v.code for v in lint(나쁜)}
    assert not (엔진만 & set(SCHOOL_RULES))
    assert set(_규칙["rules"]) == set(SCHOOL_RULES)  # 이 누름틀 양식 킷은 학교 규칙을 모두 켠다


def test_모르는_학교_규칙_코드는_멈춘다():
    with pytest.raises(ValueError, match="모르는 규칙 E999"):
        lint(_md(_q(1, "[100.0점]")), rules={"rules": {"E999": {}}})


def test_엔진_규칙과_학교_규칙은_겹치지_않는다():
    엔진 = {r.__name__.removeprefix("rule_") for r in ENGINE_RULES}
    assert not 엔진 & set(SCHOOL_RULES)
