"""킷 교체 감시 — kit.json 의 번호를 바꾸면 산출물의 번호도 바뀌어야 한다(코드에 박힌 값 탐지)."""
import json
import shutil
import zipfile
import xml.etree.ElementTree as ET

from assessment.compose import compose
from assessment.ns import HP
from test_hwpx import MD


def test_borderFill_바꾸면_따라간다(킷_루트, tmp_path):
    root = tmp_path / "킷"
    shutil.copytree(킷_루트, root)
    d = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    # 스켈레톤 header 에 실재하는 다른 번호로 서로 맞바꾼다(존재 검사 통과용).
    bf = d["styles"]["borderFill"]
    bf["underline"], bf["rule"] = bf["rule"], bf["underline"]
    (root / "kit.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    r = compose(tmp_path / "a.md", root, tmp_path / "a.hwpx")
    뿌리 = ET.fromstring(zipfile.ZipFile(r.student).read("Contents/section0.xml"))
    답칸 = [tc for tc in 뿌리.iter(f"{{{HP}}}tc") if "".join(tc.itertext()).strip() == "(가)"]
    assert 답칸 and 답칸[0].get("borderFillIDRef") == str(bf["underline"])


def test_charPr_바꾸면_따라간다(킷_루트, tmp_path):
    root = tmp_path / "킷"
    shutil.copytree(킷_루트, root)
    d = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    d["styles"]["charPr"]["hint"] = d["styles"]["charPr"]["body"]
    (root / "kit.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    r = compose(tmp_path / "a.md", root, tmp_path / "a.hwpx")
    뿌리 = ET.fromstring(zipfile.ZipFile(r.student).read("Contents/section0.xml"))
    단서 = [p for p in 뿌리.findall(f"{{{HP}}}p") if "".join(p.itertext()).startswith("(단,")]
    assert {r.get("charPrIDRef") for r in 단서[0].iter(f"{{{HP}}}run")} == {str(d["styles"]["charPr"]["body"])}


def test_표_바깥_여백_바꾸면_따라간다(킷_루트, tmp_path):
    root = tmp_path / "킷"
    shutil.copytree(킷_루트, root)
    d = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    d["furniture"]["tableOutMargin"] = 77
    (root / "kit.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    r = compose(tmp_path / "a.md", root, tmp_path / "a.hwpx")
    뿌리 = ET.fromstring(zipfile.ZipFile(r.student).read("Contents/section0.xml"))
    assert {t.find(f"{{{HP}}}outMargin").get("top") for t in 뿌리.iter(f"{{{HP}}}tbl")} == {"77"}


def _답칸_행(뿌리):
    for tr in 뿌리.iter(f"{{{HP}}}tr"):
        칸들 = list(tr.iter(f"{{{HP}}}tc"))
        if any("".join(c.itertext()) == "(가)" for c in 칸들):
            return 칸들
    raise AssertionError("답칸 행이 없다")


def test_borderFill_none_바꾸면_틈_칸이_따라간다(킷_루트, tmp_path):
    root = tmp_path / "킷"
    shutil.copytree(킷_루트, root)
    d = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    bf = d["styles"]["borderFill"]
    bf["none"], bf["rule"] = bf["rule"], bf["none"]
    (root / "kit.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    r = compose(tmp_path / "a.md", root, tmp_path / "a.hwpx")
    행 = _답칸_행(ET.fromstring(zipfile.ZipFile(r.student).read("Contents/section0.xml")))
    assert len(행) == 3 and 행[1].get("borderFillIDRef") == str(bf["none"])


def test_charPr_answer_label_바꾸면_라벨이_따라간다(킷_루트, tmp_path):
    root = tmp_path / "킷"
    shutil.copytree(킷_루트, root)
    d = json.loads((root / "kit.json").read_text(encoding="utf-8"))
    d["styles"]["charPr"]["answer_label"] = d["styles"]["charPr"]["hint"]
    (root / "kit.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "a.md").write_text(MD, encoding="utf-8")
    r = compose(tmp_path / "a.md", root, tmp_path / "a.hwpx")
    행 = _답칸_행(ET.fromstring(zipfile.ZipFile(r.student).read("Contents/section0.xml")))
    라벨 = [c for c in 행 if "".join(c.itertext()) in ("(가)", "(나)")]
    assert 라벨 and {run.get("charPrIDRef") for c in 라벨 for run in c.iter(f"{{{HP}}}run")} == {str(d["styles"]["charPr"]["hint"])}
