from hwpx.document import HwpxDocument

from assessment.kit import load_kit
from assessment.memo import add_answer_memo


def test_메모_구조(킷_루트):
    kit = load_kit(킷_루트)
    doc = HwpxDocument.open(kit.skeleton, seed=0)
    p = doc.add_paragraph("1. 쓰시오 ", char_pr_id_ref=kit.char_pr["body"])
    p.add_run("[2점]", char_pr_id_ref=kit.char_pr["body"])
    memo = add_answer_memo(doc, p, "[2점]", ("(가) 노드", "(나) 간선"), kit=kit)

    # 한/글 2024 꼴: 메모 글은 MEMO 누름틀 안, 누름틀은 "[2점]"만 감싼다
    assert [m.text for m in doc.notes.memos] == ["(가) 노드\n(나) 간선"]
    assert memo.attributes["Author"] == "assessment" and memo.attributes["Number"] == "1"
    assert p.text == "1. 쓰시오 [2점]"
    begin = memo.element
    run = begin.getparent().getparent()
    assert "".join(run.itertext()).endswith("[2점]")
    문단 = memo.paragraphs
    assert [q.text for q in 문단] == ["(가) 노드", "(나) 간선"]
    assert {q.style_id_ref for q in 문단} == {str(kit.memo_style)}
    assert {q.para_pr_id_ref for q in 문단} == {str(kit.para_pr["memo"])}
    assert {r.char_pr_id_ref for q in 문단 for r in q.runs} == {str(kit.char_pr["body"])}
    again = HwpxDocument.open(doc.to_bytes())
    assert [m.text for m in again.notes.memos] == ["(가) 노드\n(나) 간선"]
