"""작은 수정(exam_kit.patch) — 고친 글만 갈아 끼우고 배치는 그대로. 합성 킷·합성 원고만."""

import re
import shutil
import zipfile
from pathlib import Path

import lxml.etree as ET
import pytest
from exam_kit.kit import load_kit
from exam_kit.patch import NeedsRebuild, apply_patch, check_small
from exam_kit.roundtrip import rebuild
from exam_kit.scan import scan_markdown
from hwpx.document import HwpxDocument

킷 = Path(__file__).resolve().parents[1] / "kits" / "synthetic"
서식 = 킷 / "synthetic_form.hwpx"
픽스처 = Path(__file__).parent / "fixtures"
원고 = (픽스처 / "합성서식_6문항.md").read_text(encoding="utf-8")
첫_발문 = "다음은 탐색 방법에 대한 설명이다."


def _scan(md: str):
    return scan_markdown(md, load_kit(킷).front_matter)


def _top(path: Path) -> list[bytes]:
    root = ET.fromstring(zipfile.ZipFile(path).read("Contents/section0.xml"))
    return [re.sub(rb'\bid="\d+"', b'id="#"', re.sub(rb'instid="\d+"', b"", ET.tostring(p))) for p in root]


# ---- 견주기 --------------------------------------------------------------------------------------


def test_글만_바뀌면_작은_수정이다():
    assert check_small(_scan(원고), _scan(원고.replace(첫_발문, "다음은 여러 탐색 방법에 대한 설명이다.")), {}) == []


@pytest.mark.parametrize("edit, why", [
    (lambda m: m.replace("ㄷ. 휴리스틱은 목표까지의 거리를 어림한다.", "ㄷ. 휴리스틱은 목표까지의 거리를 어림한다.\nㄹ. 합성 항목."), "구성"),
    (lambda m: m.replace(첫_발문, 첫_발문 + "\n\n(가) 합성 조건"), "구성"),
    (lambda m: m.replace("[5.0점]", "[6.0점]", 1), "배점 합"),
    (lambda m: m.replace("학년: 2", "학년: 3", 1), "머리 값"),
    (lambda m: m.replace("## 2. [5.0점]", "## 2. [5.0점] {단나눔}", 1), "나눔 지시"),
])
def test_구조가_바뀌면_다시_조판(edit, why):
    new = edit(원고)
    assert new != 원고
    assert any(why in x for x in check_small(_scan(원고), _scan(new), {}))


def test_배치형_지시는_기존과_같아야_한다():
    new = 원고.replace("## 2. [5.0점]", "## 2. [5.0점] {답항=5행}", 1)
    assert any("배치형" in x for x in check_small(_scan(원고), _scan(new), {"2": "2행"}))
    assert check_small(_scan(원고), _scan(new), {"2": "5행"}) == []


# ---- 갈아 끼우기 -----------------------------------------------------------------------------------


def test_고친_문단만_바뀌고_나머지는_바이트_그대로(tmp_path):
    kit = load_kit(킷)
    old_path = rebuild(원고, kit, 서식, 픽스처, tmp_path / "old.hwpx")
    new = HwpxDocument.open(str(rebuild(원고.replace(첫_발문, "다음은 여러 탐색 방법에 대한 설명이다."), kit, 서식, 픽스처,
                                       tmp_path / "new.hwpx")))
    old = HwpxDocument.open(str(old_path))
    assert apply_patch(old, new, kit) == ["1번 문단 1"]
    old.save_to_path(str(tmp_path / "patched.hwpx"))
    a, b = _top(old_path), _top(tmp_path / "patched.hwpx")
    assert len(a) == len(b) and [i for i, (x, y) in enumerate(zip(a, b)) if x != y] == [1]
    texts = ["".join(t.text or "" for t in p.element.iter("{*}t"))
             for p in HwpxDocument.open(str(tmp_path / "patched.hwpx")).sections[0].paragraphs]
    assert "다음은 여러 탐색 방법에 대한 설명이다." in texts[1]


def test_수식도_갈아_끼운다(tmp_path):
    kit = load_kit(킷)
    md = (픽스처 / "수식_합성.md").read_text(encoding="utf-8")
    old = HwpxDocument.open(str(rebuild(md, kit, 서식, 픽스처, tmp_path / "old.hwpx")))
    new = HwpxDocument.open(str(rebuild(md.replace("$x^2-5x+6=0$", "$x^2-7x+12=0$", 1), kit, 서식, 픽스처, tmp_path / "new.hwpx")))
    assert apply_patch(old, new, kit) == ["1번 문단 1"]
    scripts = [s.text for s in old.sections[0].paragraphs[1].element.iter("{*}script")]
    assert "x ^{2} - 7 x + 12 = 0" in scripts


def test_그림이_바뀌면_다시_조판(tmp_path):
    kit = load_kit(킷)
    root = tmp_path / "원고"
    shutil.copytree(픽스처, root)
    md = (root / "견본_전유형.md").read_text(encoding="utf-8")
    old = HwpxDocument.open(str(rebuild(md, kit, 서식, root, tmp_path / "old.hwpx")))
    from PIL import Image

    with Image.open(root / "그림.png") as im:
        im.rotate(180).save(root / "그림.png")  # 같은 크기, 다른 그림
    new = HwpxDocument.open(str(rebuild(md, kit, 서식, root, tmp_path / "new.hwpx")))
    with pytest.raises(NeedsRebuild, match="그림이 바뀌었다"):
        apply_patch(old, new, kit)


# ---- 실렌더: 명령 전체 ---------------------------------------------------------------------------


def test_작은_수정_실렌더(오라클, tmp_path):
    from exam_kit.build import build
    from exam_kit.patch import patch

    md = tmp_path / "원고.md"
    md.write_text(원고, encoding="utf-8")
    v1 = build(md, 킷, tmp_path / "v1", form_path=서식)
    assert v1.residue("문항지") == 0
    md.write_text(원고.replace(첫_발문, "다음은 여러 탐색 방법에 대한 설명이다."), encoding="utf-8")
    r = patch(md, tmp_path / "v1", 킷, form=서식, out_dir=tmp_path / "v2")
    assert not r.rebuild and r.changed == ["1번 문단 1"] and r.residue("문항지") == 0 and r.residue("답표시본") == 0
    a, b = _top(v1.문항지), _top(r.문항지)
    assert [i for i, (x, y) in enumerate(zip(a, b)) if x != y] == [1]
    md.write_text(원고.replace(첫_발문, "다음은 인공지능이 문제를 풀 때 쓰는 여러 가지 탐색 방법과 그 특징, 장단점을 정리한 합성 "
                                      "설명이다."), encoding="utf-8")
    r = patch(md, tmp_path / "v1", 킷, form=서식, out_dir=tmp_path / "v3")
    assert r.rebuild and r.문항지 is None  # 줄이 늘어 뒤 문항이 움직였다 — 다시 조판
