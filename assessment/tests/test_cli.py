import json
import subprocess
import sys
from pathlib import Path

from test_hwpx import MD, _png

그림_초과_MD = """---
kit: standard
title: 그림 시험
total: 2
---

## 그림 문제 {2점}
![](a.png){width=20cm}
:::정답
답
:::
"""


def _cli(*args, cwd):
    return subprocess.run([sys.executable, "-m", "assessment.cli", *args], capture_output=True, text=True, cwd=cwd)


def test_compose_와_check(킷_루트, tmp_path):
    md = tmp_path / "a.md"
    md.write_text(MD, encoding="utf-8")
    r = _cli("compose", str(md), "--kit", str(킷_루트), "-o", str(tmp_path / "a.hwpx"), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    보고 = json.loads(r.stdout)
    assert 보고["items"] == 2 and 보고["student"].endswith("a_학생용.hwpx")
    r = _cli("check", str(md), "--kit", str(킷_루트), "--out", str(tmp_path / "a.hwpx"), cwd=tmp_path)
    assert r.returncode == 0 and json.loads(r.stdout)["문제"] == []


def test_검사_문제는_종료코드_1(킷_루트, tmp_path):
    md = tmp_path / "b.md"
    md.write_text(MD.replace("total: 4", "total: 9"), encoding="utf-8")
    r = _cli("compose", str(md), "--kit", str(킷_루트), "-o", str(tmp_path / "b.hwpx"), cwd=tmp_path)
    assert r.returncode == 1 and "배점 합계" in json.loads(r.stdout)["문제"][0]


def test_입력_오류는_종료코드_2(킷_루트, tmp_path):
    md = tmp_path / "c.md"
    md.write_text("제목 없음\n", encoding="utf-8")
    r = _cli("compose", str(md), "--kit", str(킷_루트), "-o", str(tmp_path / "c.hwpx"), cwd=tmp_path)
    assert r.returncode == 2 and r.stderr.startswith("오류: front matter가 없다")


def test_check_out_확장자_오류는_종료코드_2(킷_루트, tmp_path):
    md = tmp_path / "d.md"
    md.write_text(MD, encoding="utf-8")
    r = _cli("check", str(md), "--kit", str(킷_루트), "--out", str(tmp_path / "d.docx"), cwd=tmp_path)
    assert r.returncode == 2 and r.stderr.startswith("오류: 출력은 .hwpx 여야 한다")


def test_check_산출물_없으면_종료코드_2(킷_루트, tmp_path):
    md = tmp_path / "e.md"
    md.write_text(MD, encoding="utf-8")
    r = _cli("check", str(md), "--kit", str(킷_루트), "--out", str(tmp_path / "e.hwpx"), cwd=tmp_path)
    assert r.returncode == 2 and r.stderr.startswith("오류: 산출물이 없다")


def test_compose_출력_폴더가_없으면_만든다(킷_루트, tmp_path):
    md = tmp_path / "f.md"
    md.write_text(MD, encoding="utf-8")
    out = tmp_path / "새_수행평가" / "자료" / "f.hwpx"
    r = _cli("compose", str(md), "--kit", str(킷_루트), "-o", str(out), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    보고 = json.loads(r.stdout)
    assert Path(보고["student"]).exists() and Path(보고["answers"]).exists()


def test_그림_폭_초과는_compose_종료코드_2(킷_루트, tmp_path):
    """Minor-5: 그림 폭 초과는 check_sheet 가 못 잡는 입력 오류 — 검사 문제(JSON, 1)가 아니라 오류 한 줄(2)이어야 한다."""
    (tmp_path / "a.png").write_bytes(_png(10, 10))
    md = tmp_path / "g.md"
    md.write_text(그림_초과_MD, encoding="utf-8")
    r = _cli("compose", str(md), "--kit", str(킷_루트), "-o", str(tmp_path / "g.hwpx"), cwd=tmp_path)
    assert r.returncode == 2 and r.stderr.startswith("오류: 그림 폭이 칸 안쪽보다 넓다")
    assert not list(tmp_path.glob("*.hwpx"))


def test_단나눔_InputError는_cli_종료코드_2(킷_루트, tmp_path, monkeypatch, capsys):
    """§8: HwpxWriter.save() 의 단나눔 InputError 가 cli 에서도 오류 한 줄 + 종료코드 2로 나온다."""
    from assessment.blocks import InputError
    from assessment.cli import main as cli_main

    md = tmp_path / "j.md"
    md.write_text(MD, encoding="utf-8")

    def _단나눔_실패(*a, **kw):
        raise InputError(":::단나눔 뒤에 아무 내용이 없다 — 마지막 단나눔을 지운다")

    monkeypatch.setattr("assessment.cli.compose", _단나눔_실패)
    코드 = cli_main(["compose", str(md), "--kit", str(킷_루트), "-o", str(tmp_path / "j.hwpx")])
    캡처 = capsys.readouterr()
    assert 코드 == 2 and 캡처.err.startswith("오류: :::단나눔 뒤에 아무 내용이 없다")


def test_compose_os_replace_실패는_종료코드_2(킷_루트, tmp_path, monkeypatch, capsys):
    """§8: 마지막 os.replace 가 OSError 를 내면 raw traceback 이 아니라 한 줄 오류 + 종료코드 2."""
    from assessment import compose as compose_mod
    from assessment.cli import main as cli_main

    md = tmp_path / "i.md"
    md.write_text(MD, encoding="utf-8")
    out = tmp_path / "i.hwpx"

    def _항상_실패(src, dst):
        raise OSError("디스크가 꽉 찼다")

    monkeypatch.setattr(compose_mod.os, "replace", _항상_실패)
    코드 = cli_main(["compose", str(md), "--kit", str(킷_루트), "-o", str(out)])
    캡처 = capsys.readouterr()
    assert 코드 == 2
    assert 캡처.err.startswith("오류: 파일을 쓰지 못했다:")


def test_그림_폭_초과는_check_out없이도_종료코드_2(킷_루트, tmp_path):
    """Minor-5: --out 없는 check 도 compose 전에 미리 잡아야 한다(계획을 한 번 돌려본다)."""
    (tmp_path / "a.png").write_bytes(_png(10, 10))
    md = tmp_path / "g.md"
    md.write_text(그림_초과_MD, encoding="utf-8")
    r = _cli("check", str(md), "--kit", str(킷_루트), cwd=tmp_path)
    assert r.returncode == 2 and r.stderr.startswith("오류: 그림 폭이 칸 안쪽보다 넓다")
