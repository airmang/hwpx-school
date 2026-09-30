import json
import random
import shutil
import struct
import zipfile
import zlib
from pathlib import Path

import pytest
from hwpx.document import HwpxDocument

from _helpers import _png

루트 = Path(__file__).resolve().parents[1]
표준킷 = 루트 / "kits" / "standard"
시험_슬롯 = {"school": "시험고등학교", "teacher": "김교사T", "subject": "정보", "grade": "2학년"}


@pytest.fixture(scope="session")
def 킷_루트(tmp_path_factory) -> Path:
    """표준 킷을 복사해 슬롯만 채운 시험용 킷 — 공개 테스트는 비공개 자산 없이 돈다."""
    root = tmp_path_factory.mktemp("kits") / "시험킷"
    shutil.copytree(표준킷, root)
    데이터 = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    데이터["kit"] = "시험킷"
    데이터["slots"] = dict(시험_슬롯)
    (root / "kit.json").write_text(
        json.dumps(데이터, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return root


def _더러운_미리보기_png(width: int = 60, height: int = 60) -> bytes:
    """무작위 픽셀 PNG — 단색 PNG는 zlib가 몇백 바이트로 뭉개 버려 1024B 문턱을 못 넘는다."""
    rnd = random.Random(20260921)

    def row(_y: int) -> bytes:
        return bytes([0]) + bytes(rnd.randrange(256) for _ in range(width * 3))

    raw = b"".join(row(y) for y in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    )


@pytest.fixture(scope="session")
def 원본_hwpx(tmp_path_factory) -> Path:
    """비공개 실제 원본 대신, 테스트가 직접 만드는 '더러운 원본' — 공개 테스트는 비공개
    자산 없이 돈다.

    kits/standard/skeleton.hwpx 를 열어 본문 문단·표·그림을 채우고 작성자 흔적(전부 합성
    금칙어)을 심어 저장한다. extract_skeleton()이 이걸 세척했을 때 진짜로 씻겼는지를
    tests/test_skeleton.py가 본다.
    """
    dest = tmp_path_factory.mktemp("원본") / "더러운원본.hwpx"
    doc = HwpxDocument.open(표준킷 / "skeleton.hwpx")

    doc.add_paragraph("더러운 원본 문단 1")
    doc.add_paragraph("더러운 원본 문단 2")
    표 = doc.add_table(2, 2, width=50460)
    표.set_cell_text(0, 0, "표 안 내용")
    doc.add_picture(_png(20, 20), "png", width_mm=10, height_mm=10)

    doc.package.set_document_metadata(creator="금칙작성자", title="금칙제목")
    doc.package.write("Preview/PrvText.txt", "금칙학교 김금칙T")
    doc.package.set_part("Preview/PrvImage.png", _더러운_미리보기_png())

    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save_to_path(dest)

    # 픽스처가 실제로 더러운지 먼저 확인한다 — 안 그러면 세척 테스트가 공허해진다.
    z = zipfile.ZipFile(dest)
    assert sum(1 for n in z.namelist() if n.startswith("BinData/")) >= 1
    assert "금칙작성자" in z.read("Contents/content.hpf").decode("utf-8", "ignore")
    assert "금칙학교" in z.read("Preview/PrvText.txt").decode("utf-8", "ignore")
    assert len(z.read("Preview/PrvImage.png")) > 1024

    return dest
