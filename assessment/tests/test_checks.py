import struct
import zlib

from assessment.checks import check_answers, check_sheet, check_student, png_size
from assessment.md import parse_sheet

머리 = "---\nkit: standard\ntitle: t\ntotal: {total}\n---\n"


def _png(w=4, h=2) -> bytes:
    def c(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + c(b"IDAT", zlib.compress(raw)) + c(b"IEND", b"")


def test_깨끗하면_빈_목록(tmp_path):
    s = parse_sheet(머리.format(total=2) + "## 가 {2점}\n:::정답\n답\n:::\n")
    assert check_sheet(s, base_dir=tmp_path) == []


def test_배점_합계(tmp_path):
    s = parse_sheet(머리.format(total=5) + "## 가 {2점}\n:::정답\n답\n:::\n")
    assert check_sheet(s, base_dir=tmp_path) == ["배점 합계가 total 과 다르다: 문항 합 2점 ≠ total 5점"]


def test_정답_누락(tmp_path):
    s = parse_sheet(머리.format(total=1) + "## 가 {1점}\n")
    assert check_sheet(s, base_dir=tmp_path) == ["1번 문항에 :::정답 이 없다(6번째 줄)"]


def test_묶음_범위(tmp_path):
    s = parse_sheet(머리.format(total=1) + "::::묶음 2-3 공통\n## 가 {1점}\n:::정답\n답\n:::\n::::\n")
    assert check_sheet(s, base_dir=tmp_path) == ["묶음 번호 [2-3] 가 실제 문항 번호 [1-1] 와 다르다(6번째 줄)"]


def test_빈_묶음(tmp_path):
    s = parse_sheet(머리.format(total=0) + "::::묶음 1-1 공통\n::::\n")
    assert check_sheet(s, base_dir=tmp_path) == ["[1-1] 묶음에 문항이 없다(6번째 줄)"]


def test_그림_파일(tmp_path):
    (tmp_path / "ok.png").write_bytes(_png())
    (tmp_path / "가짜.png").write_bytes(b"not png")
    s = parse_sheet(머리.format(total=1) + "## 가 {1점}\n![](ok.png)\n![](없음.png)\n![](가짜.png)\n:::정답\n답\n:::\n")
    assert check_sheet(s, base_dir=tmp_path) == [
        "1번 문항의 그림 파일이 없다: 없음.png",
        "1번 문항의 그림이 PNG 가 아니다: 가짜.png",
    ]


def test_png_size():
    assert png_size(_png(4, 2)) == (4, 2)


def test_학생용_누출_검사(킷_루트, tmp_path):
    from assessment.compose import compose
    from test_hwpx import MD
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    r = compose(tmp_path / "a.md", 킷_루트, tmp_path / "a.hwpx")
    s = parse_sheet(MD)
    assert check_student(r.student, s) == []
    assert check_answers(r.answers, s) == []
    # 정답용을 학생용 자리에 넣으면 걸린다
    문제 = check_student(r.answers, s)
    assert "학생용에 메모가 2개 있다 — 0개여야 한다" in 문제
    assert any("학생용에 1번 정답 줄과 같은 글이 있다" in m for m in 문제)


def test_문항_밖_그림과_나란히_그림도_검사(tmp_path):
    (tmp_path / "ok.png").write_bytes(_png())
    s = parse_sheet(머리.format(total=1) + (
        "![](없음1.png)\n"
        ":::나란히\n![](ok.png)\n![](없음2.png)\n:::\n"
        "## 가 {1점}\n:::나란히\n![](ok.png)\n![](없음3.png)\n:::\n:::정답\n답\n:::\n"
        "::::묶음 2-2 공통\n:::나란히\n![](ok.png)\n![](없음4.png)\n:::\n::::\n"
    ))
    assert check_sheet(s, base_dir=tmp_path) == [
        "[2-2] 묶음에 문항이 없다(19번째 줄)",
        "문항 밖의 그림 파일이 없다: 없음1.png",
        "문항 밖의 그림 파일이 없다: 없음2.png",
        "[2-2] 묶음의 그림 파일이 없다: 없음4.png",
        "1번 문항의 그림 파일이 없다: 없음3.png",
    ]
