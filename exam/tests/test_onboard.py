"""학교 등록 ① 해부·킷 초안 — 두 학교 서식으로(없으면 건너뛴다)."""

import json

import pytest

from exam_kit.onboard import TODO, draft_kit, scan, todo_paths


def test_해부_누름틀_양식(양식_hwpx):
    r = scan(양식_hwpx)
    assert "## 누름틀 20개" in r and "## 메모 0개" in r
    assert "number.mode 후보 autonumber" in r and "첫 쪽 나눔 문단 #" in r


def test_해부_학교B(학교B_양식):
    r = scan(학교B_양식)
    assert "## 누름틀 0개" in r and "## 메모 14개" in r and "ellipse 3" in r and "line 7" in r
    assert "number.mode 후보 literal" in r and "논술형/서술형으로 시작하는 문단 #" in r


def test_킷_초안은_사실만_채우고_판단은_TODO(학교B_양식, tmp_path):
    from exam_kit.kit import load_kit

    d = draft_kit(학교B_양식, "시험-원안지")
    assert d["columns"]["width"] == 30049 and d["columns"]["gap"] == 1416  # 글자 자리 양식 킷과 같은 값(사실)
    assert d["tailbox"]["horzOffset"] == 37134
    todo = todo_paths(d)
    assert "styles.number" in todo and "trim.rule" in todo and "metrics.full" in todo
    (tmp_path / "kit.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    with pytest.raises((ValueError, KeyError, TypeError)):  # TODO가 남은 킷은 읽히지 않는다
        load_kit(tmp_path)
    assert TODO == "TODO"
