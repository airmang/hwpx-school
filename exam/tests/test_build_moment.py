"""한 빌드의 두 판(문항지·답 표시본)은 같은 순간의 문서 정보를 갖는다 — 저장이 다른 초에 끝나도 M8(same_package)이 통과."""

from datetime import datetime, timezone
from pathlib import Path

import exam_kit.kit as kit_mod
from exam_kit.build import same_package, write_key
from exam_kit.compose import compose
from exam_kit.kit import load_kit, save_stamped
from exam_kit.prepare import finalize_form, prepare_document
from exam_kit.scan import scan_markdown
from exam_kit.slots import fill_slots

킷 = Path(__file__).resolve().parents[1] / "kits" / "synthetic"
서식 = 킷 / "synthetic_form.hwpx"
원고 = Path(__file__).parent / "fixtures" / "합성서식_6문항.md"


def test_답표시본은_문항지와_같은_순간(tmp_path, monkeypatch):
    kit = load_kit(킷)
    s = scan_markdown(원고.read_text(encoding="utf-8"), kit.front_matter)
    doc, prep = prepare_document(서식, kit)
    fill_slots(doc, kit, s.front, question_count=len(s.questions), total_points=30.0)
    prep = prep.refresh(doc)
    res = compose(doc, s, kit, answer_key=False, image_root=원고.parent)
    finalize_form(doc, kit, prep)
    # 저장마다 시계가 흐른다(재현 고정 없이 실제로 돌 때처럼): 문항지 저장과 답 표시본 저장이 다른 초
    때 = iter([datetime(2026, 3, 2, 9, 0, s, tzinfo=timezone.utc) for s in range(10)])
    monkeypatch.setattr(kit_mod, "stamp_moment", lambda: next(때))
    plain, key = tmp_path / "p.hwpx", tmp_path / "k.hwpx"
    save_stamped(doc, plain)
    write_key(plain, key, kit, res.answers)
    assert same_package(plain, key) == []
