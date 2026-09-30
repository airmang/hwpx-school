from lxml import etree

from assessment.kit import load_kit
from assessment.memo import append_memo_run
from assessment.ns import HP


def test_메모_구조(킷_루트):
    kit = load_kit(킷_루트)
    run = etree.Element(f"{{{HP}}}run", {"charPrIDRef": "11"})
    append_memo_run(run, "[2점]", ("(가) 노드", "(나) 간선"), number=3, kit=kit)
    ctrl1, t, ctrl2 = list(run)
    fb = ctrl1.find(f"{{{HP}}}fieldBegin")
    fe = ctrl2.find(f"{{{HP}}}fieldEnd")
    assert fb.get("type") == "MEMO" and fe.get("beginIDRef") == fb.get("id") == "1000000003"
    assert fe.get("fieldid") == fb.get("fieldid")
    assert t.text == "[2점]"
    문단 = fb.findall(f"{{{HP}}}subList/{{{HP}}}p")
    assert ["".join(p.itertext()) for p in 문단] == ["(가) 노드", "(나) 간선"]
    assert {p.get("styleIDRef") for p in 문단} == {str(kit.memo_style)}
    assert {p.get("paraPrIDRef") for p in 문단} == {str(kit.para_pr["memo"])}
