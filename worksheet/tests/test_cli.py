"""CLI 오류 문형: 교사 입력 오류는 트레이스백이 아니라 stderr 한 줄 + 종료코드 2다.

`검사(check)` 서브커맨드가 [기계] 검사 문제를 내는(종료코드 1) 경로와는 다르다 — 여기서
보는 건 md·kit.json 자체가 읽을 수 없을 때(`ValueError`/`OSError`)의 CLI 경계다.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from hwpx.document import HwpxDocument

from worksheet.cli import main as cli_main
from worksheet.compose import compose
from worksheet.ns import HP

_표준_스켈레톤 = Path(__file__).resolve().parents[1] / "kits" / "standard" / "skeleton.hwpx"


def _q(tag: str) -> str:
    return f"{{{HP}}}{tag}"


기본_MD = """---
kit: 시험킷
title: 제목
---

## 섹션

:::답칸 label="가" lines=1
:::
"""


def test_없는_원본으로_extract_kit을_하면_코드_2고_대상_디렉터리가_안_생긴다(tmp_path, capsys):
    source = tmp_path / "없는원본.hwpx"
    dest = tmp_path / "새킷"

    코드 = cli_main(["extract-kit", str(source), str(dest)])
    err = capsys.readouterr().err

    assert 코드 == 2
    assert "오류: 원본 hwpx 가 없다" in err
    assert "Traceback" not in err
    assert not dest.exists()


def test_안전하지_않은_원본으로_extract_kit을_하면_코드_2고_skeleton이_안_생긴다(tmp_path, capsys):
    """extract_skeleton이 ValueError(구조 거부)로 실패해도 CLI 경계는 그대로 작동해야 한다:
    오류 한 줄 + 코드 2, 그리고 dest 아래 skeleton.hwpx가 생기면 안 된다(원자적 쓰기가 CLI
    경로에서도 실제로 지켜지는지 — extract_skeleton 단위 테스트와는 별개로 cli_main을
    끝까지 통과시켜 본다)."""
    안전하지_않은_원본 = tmp_path / "안전하지않은원본.hwpx"
    doc = HwpxDocument.open(_표준_스켈레톤)
    section = doc.sections[0]
    첫_run = section.element.findall(_q("p"))[0].findall(_q("run"))[0]
    ctrl = 첫_run.find(_q("ctrl"))
    글자 = ctrl.makeelement(_q("t"), {})
    글자.text = "유출될_머리말"
    ctrl.append(글자)
    section.mark_dirty()
    doc.save_to_path(안전하지_않은_원본)

    dest = tmp_path / "새킷"
    코드 = cli_main(["extract-kit", str(안전하지_않은_원본), str(dest)])
    err = capsys.readouterr().err

    assert 코드 == 2
    assert "오류: 스켈레톤을 안전하게 만들지 못했다" in err
    assert "Traceback" not in err
    assert not (dest / "skeleton.hwpx").exists()


def test_cols_없는_비교표로_compose하면_코드_2고_트레이스백이_없다(킷_루트, tmp_path, capsys):
    md = tmp_path / "s.md"
    md.write_text(
        기본_MD.replace(':::답칸 label="가" lines=1', ':::비교표 rows="가"'),
        encoding="utf-8",
    )
    out = tmp_path / "s.hwpx"

    코드 = cli_main(["compose", str(md), "--kit", str(킷_루트), "-o", str(out)])
    err = capsys.readouterr().err

    assert 코드 == 2
    assert "오류: 조판할 수 없다" in err
    assert "Traceback" not in err
    assert not out.exists()


def test_필수_키_빠진_킷으로_compose하면_코드_2다(킷_루트, tmp_path, capsys):
    빠진킷 = tmp_path / "빠진킷"
    shutil.copytree(킷_루트, 빠진킷)
    데이터 = json.loads((빠진킷 / "kit.json").read_text(encoding="utf-8"))
    del 데이터["furniture"]["labelWidth"]
    (빠진킷 / "kit.json").write_text(json.dumps(데이터, ensure_ascii=False), encoding="utf-8")

    md = tmp_path / "s.md"
    md.write_text(기본_MD, encoding="utf-8")
    out = tmp_path / "s.hwpx"

    코드 = cli_main(["compose", str(md), "--kit", str(빠진킷), "-o", str(out)])
    err = capsys.readouterr().err

    assert 코드 == 2
    assert "오류: kit.json 에 필수 키가 없다" in err
    assert "Traceback" not in err


def test_검사_문제는_예외가_아니라_여전히_코드_1이다(킷_루트, tmp_path, capsys):
    """CLI는 예외(ValueError/OSError)만 코드 2로 바꾼다 — [기계] 검사가 낸 문제 목록(빈
    슬롯 등)은 예외가 아니므로 코드 1이어야 한다. 표준 킷(슬롯이 다 비어 있다)에 대고
    검사해 이 구별을 확인한다."""
    표준_킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"
    md = tmp_path / "s.md"
    md.write_text(기본_MD, encoding="utf-8")
    out = tmp_path / "s.hwpx"
    compose(md, 킷_루트, out)  # 산출물 자체는 슬롯이 다 찬 킷_루트로 정상 조판한다

    코드 = cli_main(["check", str(md), "--kit", str(표준_킷), "--hwpx", str(out)])
    보고 = json.loads(capsys.readouterr().out)

    assert 코드 == 1
    assert any("빈 슬롯" in m for m in 보고["문제"])


# --- check --out 도 compose 와 같은 방어를 받는다 ----------------------------------------
# _docx_인가가 ".docx 아니면 무조건 hwpx"로 판정하면 확장자를 모르는 --out이 hwpx 분기로
# 강제 라우팅돼 raw zipfile.BadZipFile 트레이스백이 샌다. output_format()을 _check_cmd
# 첫머리에서 불러 compose와 같은 한 줄 오류·코드 2로 거부하는지 확인한다.


@pytest.mark.parametrize("이름, 표기", [("학습지", "(없음)"), ("학습지.pdf", ".pdf")])
def test_check_는_확장자를_알_수_없는_out을_종료코드_2로_거부한다(이름, 표기, 킷_루트, tmp_path, capsys):
    md = tmp_path / "s.md"
    md.write_text(기본_MD, encoding="utf-8")

    코드 = cli_main(["check", str(md), "--kit", str(킷_루트), "--out", str(tmp_path / 이름)])
    err = capsys.readouterr().err

    assert 코드 == 2
    assert f"오류: 출력 형식을 알 수 없다: {표기} — .hwpx 또는 .docx" in err
    assert "Traceback" not in err
