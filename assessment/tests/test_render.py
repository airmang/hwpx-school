import pytest

from assessment.compose import compose
from assessment.render import render_hancom
from test_hwpx import MD


@pytest.mark.hancom
def test_실한컴_두_파일_렌더(킷_루트, tmp_path):
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    r = compose(tmp_path / "a.md", 킷_루트, tmp_path / "a.hwpx")
    for path in (r.student, r.answers):
        결과 = render_hancom(path, tmp_path / f"{path.stem}.png")
        assert 결과.pages >= 1 and all(p.exists() for p in 결과.pngs)
