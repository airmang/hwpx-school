"""스켈레톤 지문(kit.json skeleton.sha256) — 킷 설정과 스켈레톤이 짝인지 load_kit이 맞춰 본다(exam의 form.sha256과 같은 뜻)."""

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from worksheet.cli import main
from worksheet.kit import load_kit, skeleton_sha256, stamp_kit

표준킷 = Path(__file__).resolve().parents[1] / "kits" / "standard"
명령 = "python -m worksheet.cli stamp-kit"


def _복사(tmp_path: Path) -> Path:
    root = tmp_path / "킷"
    shutil.copytree(표준킷, root)
    return root


def _스켈레톤_바꾸기(root: Path) -> None:
    """같은 내용에 부품 하나를 더해 바이트만 바꾼다(옛 킷 설정 + 다른 스켈레톤을 흉내 낸다)."""
    sk = root / "skeleton.hwpx"
    with zipfile.ZipFile(sk) as z:
        조각들 = [(i, z.read(i.filename)) for i in z.infolist()]
    with zipfile.ZipFile(sk, "w") as z:
        for i, d in 조각들:
            z.writestr(i, d)
        z.writestr("Contents/바꿈.txt", "다른 스켈레톤")


def _지문_빼기(root: Path) -> None:
    data = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    del data["skeleton"]
    (root / "kit.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_저장소_킷은_지문이_맞는다():
    data = json.loads((표준킷 / "kit.json").read_text(encoding="utf-8"))
    assert data["skeleton"]["sha256"] == skeleton_sha256(표준킷 / "skeleton.hwpx")
    load_kit(표준킷)


def test_스켈레톤이_바뀌면_멈춘다(tmp_path):
    root = _복사(tmp_path)
    _스켈레톤_바꾸기(root)
    with pytest.raises(ValueError, match="스켈레톤과 킷 설정이 짝이 아니다") as e:
        load_kit(root)
    assert 명령 in str(e.value) and "씨앗" in str(e.value)


def test_지문이_없으면_멈춘다(tmp_path):
    root = _복사(tmp_path)
    _지문_빼기(root)
    with pytest.raises(ValueError, match=r"스켈레톤 지문\(skeleton\.sha256\)이 없다") as e:
        load_kit(root)
    assert 명령 in str(e.value)


def test_stamp_뒤에는_읽힌다_그리고_다른_값은_그대로(tmp_path):
    root = _복사(tmp_path)
    _스켈레톤_바꾸기(root)
    전 = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    assert main(["stamp-kit", str(root)]) == 0
    후 = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    assert 후["skeleton"]["sha256"] == skeleton_sha256(root / "skeleton.hwpx") != 전["skeleton"]["sha256"]
    전.pop("skeleton"), 후.pop("skeleton")
    assert 전 == 후 and list(전) == list(후)  # 다른 값·키 차례는 그대로
    load_kit(root)


def test_지문이_없던_킷도_stamp로_적는다(tmp_path):
    root = _복사(tmp_path)
    _지문_빼기(root)
    assert stamp_kit(root) == skeleton_sha256(root / "skeleton.hwpx")
    load_kit(root)
