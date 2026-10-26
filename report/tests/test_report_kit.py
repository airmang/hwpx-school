from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

import pytest

import report_kit

ROOT = Path(__file__).resolve().parents[1]
STANDARD = ROOT / "kits" / "standard"
SAMPLE = ROOT / "kits" / "standard" / "예시_계획.json"


def _section(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read("Contents/section0.xml").decode("utf-8")


def test_standard_kit_matches_its_template(tmp_path: Path) -> None:
    fresh = report_kit.register(STANDARD / "견본.hwpx", tmp_path / "standard")

    assert fresh["skeletonOpenSafe"] is True
    assert fresh["roles"] == report_kit.roles(STANDARD)
    assert set(fresh["roles"]) == {"표제", "날짜", "쪽나눔", "띠", "1단계", "2단계", "3단계", "참고"}


def test_sample_plan_builds_without_leftover_placeholders(tmp_path: Path) -> None:
    plan = json.loads(SAMPLE.read_text(encoding="utf-8"))
    out = tmp_path / "out.hwpx"

    result = report_kit.make(plan, STANDARD, out)

    assert result["ok"], result["errors"]
    assert result["styleCoverage"]["missing"] == []
    section = _section(out)
    assert "{{" not in section
    assert ">Ⅰ<" in section and ">Ⅱ<" in section
    assert "□ 추진 근거" in section


def test_unknown_role_is_refused(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="no role"):
        report_kit.make({"blocks": [{"role": "4단계", "text": "x"}]}, STANDARD, tmp_path / "x.hwpx")


@pytest.mark.hancom
def test_sample_renders_in_hancom(tmp_path: Path) -> None:
    from hwpx_automation.office.rendering.mac_session import MacHancomSession

    out = tmp_path / "out.hwpx"
    report_kit.make(json.loads(SAMPLE.read_text(encoding="utf-8")), STANDARD, out)
    session = MacHancomSession(timeout_seconds=150)
    try:
        assert session.render_pdf(out, out.with_suffix(".pdf")) is not None
    finally:
        session.close()
