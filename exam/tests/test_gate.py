"""엔진 회귀 게이트(exam_kit.gate) — paraPr는 내용으로, 문단 id·그림 instid는 정규화해 견준다."""

import zipfile
from pathlib import Path

from exam_kit.gate import compare, main

HH = 'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"'
HP = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'


def _header(paras: list[tuple[str, str]], style_ref: str) -> str:
    pps = "".join(f'<hh:paraPr id="{i}"><hh:align horizontal="{a}"/></hh:paraPr>' for i, a in paras)
    return (f'<hh:head {HH}><hh:refList><hh:paraProperties itemCnt="{len(paras)}">{pps}</hh:paraProperties>'
            f'<hh:styles itemCnt="1"><hh:style id="0" paraPrIDRef="{style_ref}"/></hh:styles></hh:refList></hh:head>')


def _section(ref: str, pid: str = "1", instid: str = "5", text: str = "가") -> str:
    return (f'<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" {HP}>'
            f'<hp:p id="{pid}" paraPrIDRef="{ref}"><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>'
            f'<hp:p id="{pid}1" paraPrIDRef="0"><hp:run><hp:pic instid="{instid}"/></hp:run></hp:p></hs:sec>')


def _hwpx(path: Path, header: str, section: str) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/header.xml", header)
        z.writestr("Contents/section0.xml", section)
    return path


def test_같은_내용의_paraPr_재사용은_같다(tmp_path):
    # 기준은 paraPr 2가 1과 내용이 같은 중복이고 본문이 2를 쓴다. 새 것은 중복 없이 1을 쓴다(재사용) — 문단 id·instid도 다르다
    a = _hwpx(tmp_path / "a.hwpx", _header([("0", "LEFT"), ("1", "CENTER"), ("2", "CENTER")], "2"), _section("2"))
    b = _hwpx(tmp_path / "b.hwpx", _header([("0", "LEFT"), ("1", "CENTER")], "1"), _section("1", pid="9", instid="77"))
    assert compare(a, b) == []


def test_paraPr_내용이_다르면_다르다(tmp_path):
    a = _hwpx(tmp_path / "a.hwpx", _header([("0", "LEFT"), ("1", "CENTER")], "1"), _section("1"))
    b = _hwpx(tmp_path / "b.hwpx", _header([("0", "LEFT"), ("1", "RIGHT")], "1"), _section("1"))
    assert any("paraPr 내용이 다르다" in d for d in compare(a, b))


def test_본문이_다르면_다르다(tmp_path):
    h = _header([("0", "LEFT"), ("1", "CENTER")], "1")
    a = _hwpx(tmp_path / "a.hwpx", h, _section("1"))
    assert compare(a, _hwpx(tmp_path / "b.hwpx", h, _section("1", text="나"))) == ["Contents/section0.xml"]
    assert compare(a, _hwpx(tmp_path / "c.hwpx", h, _section("0"))) == ["Contents/section0.xml"]  # 같은 글, 다른 문단 모양


def test_CLI(tmp_path, capsys):
    base, new = tmp_path / "기준", tmp_path / "새"
    base.mkdir()
    new.mkdir()
    h = _header([("0", "LEFT")], "0")
    _hwpx(base / "x.hwpx", h, _section("0"))
    _hwpx(new / "x.hwpx", h, _section("0", pid="3"))
    assert main([str(base), str(new)]) == 0
    _hwpx(new / "x.hwpx", h, _section("0", text="다"))
    assert main([str(base), str(new)]) == 1
    assert "다르다" in capsys.readouterr().out
