"""지필 원고 → md v2 변환과 문항 내용 불변 검사 — 합성 원고만."""

from pathlib import Path

import pytest
from PIL import Image

from _kits import kit_dir
from exam_kit.convert import check_invariance, convert, main, parse_items, parse_key, render_md, front_matter

픽스처 = Path(__file__).resolve().parent / "fixtures"
원고 = (픽스처 / "원고_v3형식.md").read_text(encoding="utf-8")
기대 = (픽스처 / "원고_v3형식_v2.md").read_text(encoding="utf-8")
머리값 = {"양식": "예시-원안지", "과목코드": "99", "출제교사": "홍길동", "만점": "20"}


def test_변환은_옮김_규칙대로():
    """머리 `**N.** … (N.N점)` → `## N. [N.N점]`, 〈보기〉 뒤 글·그림·표·코드·목록 글 → :::자료(원고 차례), `- ㄱ.` → :::보기,
    원문자 첫 열 표 → :::답항표, 한 줄 여러 답지 → 한 줄 하나, 정답 일람 → `*`, `**굵게**` 제거, `~~~` → ``` ."""
    assert convert(원고, front=머리값) == 기대
    assert "**" not in 기대 and "[[PAGEBREAK]]" not in 기대 and "유의사항" not in 기대 and "~~~" not in 기대
    assert ':::답항표 머리="출력 순서|반복 횟수|마지막 값"' in 기대 and "*① 3→2→1 | 3 | 1" in 기대
    assert "학년도: 2026" in 기대 and "과목: 정보" in 기대 and "대상: 1학년 _반~_반" in 기대  # 제목에서 · 미정은 자리표시


def test_불변_검사는_글_정답_배점을_잡는다():
    items = parse_items(원고)
    answers, points = parse_key(원고)
    assert check_invariance(items, answers, points, 기대, full=20.0) == []
    바뀐글 = 기대.replace("NOT은 입력을 뒤집는다.", "NOT은 입력을 그대로 둔다.")
    assert [b for b in check_invariance(items, answers, points, 바뀐글, full=20.0) if b.startswith("2번 글이 다르다")]
    빠진줄 = 기대.replace("※ 크기는 반올림했다.\n", "")
    assert [b for b in check_invariance(items, answers, points, 빠진줄, full=20.0) if b.startswith("3번 글이 다르다") and "결과 10줄 · 원고 11줄" in b]
    바뀐정답 = 기대.replace("*② 비트", "② 비트").replace("① 바이트", "*① 바이트")
    assert "5번 정답 ① ≠ 정답 일람 ②" in check_invariance(items, answers, points, 바뀐정답, full=20.0)
    바뀐배점 = 기대.replace("## 3. [4.0점]", "## 3. [4.5점]")
    bad = check_invariance(items, answers, points, 바뀐배점, full=20.0)
    assert "3번 배점 4.5 ≠ 원고 4.0" in bad
    빠진그림 = 기대.replace("![](그림.png){width=5.1cm}\n:::\n\n:::보기", ":::\n\n:::보기")
    assert [b for b in check_invariance(items, answers, points, 빠진그림, full=20.0) if b.startswith("2번 그림 0장")]


def test_어긋나면_변환이_멈춘다():
    with pytest.raises(ValueError, match="배점 합 20.0 ≠ 만점 100.0"):  # 만점을 안 주면 100
        convert(원고, front={"양식": "예시-원안지", "과목코드": "99", "출제교사": "홍길동"})
    with pytest.raises(ValueError, match="정답 일람에 없는 문항"):
        convert(원고.replace("| 문항 | 1 | 2 | 3 | 4 | 5 |", "| 문항 | 1 | 2 | 3 | 4 | 6 |"), front=머리값)
    with pytest.raises(ValueError, match="머리 값이 없다: \\['과목코드'"):
        convert(원고, front={"양식": "예시-원안지", "출제교사": "홍길동", "만점": "20"})
    with pytest.raises(ValueError, match="5번 답지 '①②③④'"):
        convert(원고.replace("⑤ 워드\n", ""), front=머리값)
    with pytest.raises(ValueError, match="문항 앞의 줄"):
        convert(원고.replace("# Ⅱ. 학생 문제지\n", "# Ⅱ. 학생 문제지\n\n떠도는 줄\n"), front=머리값)


def test_인쇄_규격_그림으로_바꾼다(tmp_path):
    """--figures: 같은 문항 번호(qNN_)의 *_print.png, 폭 = 원래 크기(px ÷ 300dpi), 경로는 출력 md 기준."""
    figs = tmp_path / "그림_인쇄규격"
    figs.mkdir()
    Image.new("L", (1181, 400), 255).save(figs / "합성_q01_순서도_print.png")
    Image.new("L", (600, 300), 255).save(figs / "합성_q02_회로_print.png")
    out_dir = tmp_path / "원고"
    md = convert(원고, front=머리값, figures=figs, out_dir=out_dir)
    assert "![](../그림_인쇄규격/합성_q01_순서도_print.png){width=10.0cm}" in md
    assert "![](../그림_인쇄규격/합성_q02_회로_print.png){width=5.1cm}" in md
    (figs / "합성_q02_회로_print.png").unlink()
    with pytest.raises(ValueError, match="2번 그림: .*'q02_…_print.png'가 0개"):
        convert(원고, front=머리값, figures=figs, out_dir=out_dir)


def test_CLI(tmp_path, capsys):
    src = tmp_path / "원고.md"
    src.write_text(원고, encoding="utf-8")
    (tmp_path / "그림.png").write_bytes((픽스처 / "그림.png").read_bytes())
    front = tmp_path / "front.txt"
    front.write_text("과목코드: 99\n출제교사: 홍길동\n", encoding="utf-8")
    out = tmp_path / "v2.md"
    assert main([str(src), "--out", str(out), "--front", str(front), "만점=20", "양식=예시-원안지"]) == 0
    assert out.read_text(encoding="utf-8") == 기대
    assert "불변 검사 통과 · 규칙 검사 오류 0" in capsys.readouterr().out


def test_머리는_제목과_주어진_값에서():
    fm = front_matter(원고, {"양식": "예시-원안지", "과목코드": "99", "출제교사": "홍길동", "시행": "4.20.(월) 2교시"})
    assert (fm["학년도"], fm["학기"], fm["학년"], fm["차"], fm["과목"], fm["시행"]) == ("2026", "1", "1", "1", "정보", "4.20.(월) 2교시")
    with pytest.raises(ValueError, match="모르는 머리 키"):
        front_matter(원고, {"양식": "예시-원안지", "과목코드": "99", "출제교사": "홍길동", "교시": "3"})
    items = parse_items(원고)
    assert [len(it.choices) for it in items] == [5] * 5 and items[0].table_head == ["출력 순서", "반복 횟수", "마지막 값"]
    assert render_md(items, parse_key(원고)[0], front_matter(원고, 머리값)) == 기대


# ---- Task 32 fix: 차례까지 보는 불변 검사 · 접힌 줄·자리 벗어난 줄은 멈춘다 ----------------------------


def test_접힌_답지는_멈춘다():
    """(C-1) 답지가 두 줄로 접히면 둘째 줄이 자료로 새어 답지 위로 옮겨졌다 — 이어 붙이지 않고 멈춘다."""
    접힘 = 원고.replace("③ 입력 값은 네 개이다.", "③ 입력 값은\n네 개이다.")
    with pytest.raises(ValueError, match="4번 ③ 다음 줄이 이어진 줄이다 — 원고에서 한 줄로"):
        convert(접힘, front=머리값)


def test_접힌_보기_항목은_멈춘다():
    """(C-2) 〈보기〉 항목이 두 줄로 접히면 둘째 줄이 자료로 새었다."""
    접힘 = 원고.replace("- ㄴ. OR는 두 입력이 모두 0일 때만 1이다.", "- ㄴ. OR는 두 입력이\n모두 0일 때만 1이다.")
    with pytest.raises(ValueError, match="2번 〈보기〉 ㄴ. 다음 줄이 이어진 줄이다"):
        convert(접힘, front=머리값)


def test_목록_표지_없는_보기_항목과_자리_벗어난_줄():
    """(I-1) 〈보기〉 안의 `ㄷ. …`(목록 표지 없음)은 항목이다. 〈보기〉 밖의 `ㄱ.`, 항목 뒤 자료, 답지 뒤 줄은 멈춘다."""
    맨항목 = 원고.replace("- ㄷ. NOT은 입력을 뒤집는다.", "\nㄷ. NOT은 입력을 뒤집는다.")
    assert convert(맨항목, front=머리값) == 기대
    with pytest.raises(ValueError, match="5번 〈보기〉 표지 밖의 항목"):
        convert(원고.replace("컴퓨터가 정보를 저장하는 가장 작은 단위는? (4.0점)\n",
                           "컴퓨터가 정보를 저장하는 가장 작은 단위는? (4.0점)\n\nㄱ. 떠도는 항목\n"), front=머리값)
    with pytest.raises(ValueError, match="2번 〈보기〉 항목 뒤에 자료가 있다"):
        convert(원고.replace("- ㄷ. NOT은 입력을 뒤집는다.\n", "- ㄷ. NOT은 입력을 뒤집는다.\n\n| 가 | 나 |\n|---|---|\n| 1 | 2 |\n"), front=머리값)
    with pytest.raises(ValueError, match="5번 답지 뒤에 줄이 있다"):
        convert(원고.replace("⑤ 워드\n", "⑤ 워드\n\n※ 답지 뒤 설명\n"), front=머리값)


def test_답지의_굵게는_벗기고_규칙_검사가_잡는다():
    """(I-2) 답지의 `**`는 벗긴다(조판기는 별표를 그대로 찍는다). 원고 md에 남은 `**`는 E024."""
    from exam_kit.lint import lint

    assert convert(원고.replace("② 비트", "② **비트**"), front=머리값) == 기대
    head = 기대.split("\n## 1.")[0]
    md = head + "\n## 1. [20.0점]\n발문?\n\n:::보기\nㄱ. **굵은** 항목\n:::\n\n① a\n*② **b**\n③ c\n④ d\n⑤ e\n"
    assert [v.code for v in lint(md)].count("E024") == 1
    code = head + "\n## 1. [20.0점]\n발문?\n\n```\nx = 2**3\n```\n\n① a\n*② b\n③ c\n④ d\n⑤ e\n"
    assert "E024" not in [v.code for v in lint(code)]  # 코드 블록 안의 **는 글자 그대로


def test_그림_두_장_문항은_인쇄_규격_교체를_멈춘다(tmp_path):
    """(I-3) --figures는 문항당 한 장(qNN_ 파일 하나) — 두 장이면 같은 파일로 둘 다 바꾸지 않고 멈춘다."""
    figs = tmp_path / "그림"
    figs.mkdir()
    Image.new("L", (1181, 400), 255).save(figs / "합성_q02_회로_print.png")
    두장 = 원고.replace("〈보기〉\n\n![](그림.png){width=5.1cm}\n\n- ㄱ.", "〈보기〉\n\n![](그림.png){width=5.1cm}\n\n![](그림.png){width=5.1cm}\n\n- ㄱ.")
    with pytest.raises(ValueError, match="2번 그림이 2장"):
        convert(두장, front=머리값, figures=figs, out_dir=tmp_path)
    assert "![](그림.png){width=5.1cm}\n![](그림.png){width=5.1cm}" in convert(두장, front=머리값)  # --figures 없으면 그대로


def test_불변_검사는_차례를_본다():
    """(1) 줄 모음이 같아도 차례가 바뀌면(자료 줄이 답지 사이로 옮겨지는 등) 잡는다."""
    items = parse_items(원고)
    answers, points = parse_key(원고)
    옮김 = 기대.replace("입력 값은 3, 4, 5이다.\n출력은 정수로 한다.", "출력은 정수로 한다.\n입력 값은 3, 4, 5이다.")
    assert [b for b in check_invariance(items, answers, points, 옮김, full=20.0) if b.startswith("4번 글이 다르다")]
    assert check_invariance(items, answers, {k: v.rstrip("0").rstrip(".") for k, v in points.items()}, 기대, full=20.0) == []  # 4 = 4.0


def test_해설의_정답을_정답_일람과_대조한다():
    """(5) 해설 줄 `N. **③**`이 있으면 정답 일람과 같아야 한다."""
    with pytest.raises(ValueError, match="1번 해설 ② ≠ 일람 ①"):
        convert(원고.replace("1. **①** 합성 해설.", "1. **②** 합성 해설."), front=머리값)


def test_두_줄_발문은_이어서_옮긴다():
    """(M-1) 발문이 두 줄이면(배점이 첫 줄 끝에 있어도) 한 줄로 잇고 불변 검사도 이어서 본다."""
    두줄 = 원고.replace("**5.** 컴퓨터가 정보를 저장하는 가장 작은 단위는? (4.0점)",
                     "**5.** 컴퓨터가 정보를 저장하는 (4.0점)\n가장 작은 단위는?")
    md = convert(두줄, front=머리값)
    assert "## 5. [4.0점]\n컴퓨터가 정보를 저장하는 가장 작은 단위는?\n" in md


def test_ㅁ_밖의_보기_항목_기호는_멈춘다():
    """(M-2) ㅂ. 같은 기호는 이어진 줄이 아니라 지원하지 않는 항목 기호로 알린다."""
    ㅂ항목 = 원고.replace("- ㄷ. NOT은 입력을 뒤집는다.", "- ㄷ. NOT은 입력을 뒤집는다.\n- ㅂ. 여섯째 항목이다.")
    with pytest.raises(ValueError, match="2번 〈보기〉 항목 기호 ㅂ은 지원하지 않는다\\(ㄱ~ㅁ\\)"):
        convert(ㅂ항목, front=머리값)


# ---- 〈보기〉 뒤 참고 줄(09-29 결정) ------------------------------------------------------------


참고 = 원고.replace("- ㄷ. NOT은 입력을 뒤집는다.\n", "- ㄷ. NOT은 입력을 뒤집는다.\n※ 단, 입력은 0 또는 1이다.\n")


def test_보기_뒤_참고_줄은_보기_아래_본문_줄로():
    """※ 참고 줄은 :::보기 바로 아래(답지 앞) 본문 줄 — 불변 검사는 차례까지(항목 뒤·답지 앞) 그대로 본다."""
    md = convert(참고, front=머리값)
    assert "ㄷ. NOT은 입력을 뒤집는다.\n:::\n※ 단, 입력은 0 또는 1이다.\n\n① ㄱ\n" in md
    빈줄뒤 = 원고.replace("- ㄷ. NOT은 입력을 뒤집는다.\n", "- ㄷ. NOT은 입력을 뒤집는다.\n\n단, 입력은 0 또는 1이다.\n")
    assert "\n:::\n단, 입력은 0 또는 1이다.\n\n① ㄱ" in convert(빈줄뒤, front=머리값)  # 빈 줄 뒤 글 줄도 참고 줄
    items, (answers, points) = parse_items(참고), parse_key(참고)
    옮김 = md.replace(":::\n※ 단, 입력은 0 또는 1이다.\n", ":::\n").replace("\n:::보기\n", "\n※ 단, 입력은 0 또는 1이다.\n:::보기\n")
    assert [b for b in check_invariance(items, answers, points, 옮김, full=20.0) if b.startswith("2번 글이 다르다")]
    with pytest.raises(ValueError, match="2번 〈보기〉 항목이 참고 줄 뒤에 있다"):
        convert(참고.replace("※ 단, 입력은 0 또는 1이다.\n", "※ 단, 입력은 0 또는 1이다.\n- ㄹ. 넷째 항목이다.\n"), front=머리값)


def test_참고_줄은_스캔_규칙_조판까지(양식_hwpx):
    """v2 참고 줄 → scan Block('주') → lint 통과 → compose: 〈보기〉 박스 바로 아래 바탕글 문단(발문 글자 모양, 왼여백 = 발문 이음 자리)."""
    from exam_kit.compose import 발문_이음_왼여백, compose
    from exam_kit.kit import load_kit, style_ids
    from exam_kit.lint import errors, lint
    from exam_kit.prepare import prepare_document
    from exam_kit.scan import scan_markdown

    md = convert(참고, front=머리값)
    s = scan_markdown(md)
    assert s.errors == () and [b.kind for b in s.questions[1].blocks] == ["자료", "보기", "주"]
    assert errors(lint(md, md_dir=픽스처)) == []
    kit = load_kit(kit_dir())
    doc, _ = prepare_document(양식_hwpx, kit)
    compose(doc, s, kit, answer_key=False, image_root=픽스처)
    ids = style_ids(doc)
    ps = [p.element for p in doc.sections[0].paragraphs]
    i = next(k for k, p in enumerate(ps) if "".join(p.itertext()).startswith("※ 단, 입력은"))
    assert any(t.tag.endswith("tbl") for t in ps[i - 1].iter()) and "".join(ps[i + 1].itertext()).startswith("①")  # 박스 바로 아래, 답지 앞
    note = ps[i]
    assert note.get("styleIDRef") == str(ids[kit.styles["normal"]][0])
    assert note.find(".//{*}run").get("charPrIDRef") == str(ids[kit.styles["number"]][2])
    pp = doc.headers[0].element.find(f".//{{*}}paraPr[@id='{note.get('paraPrIDRef')}']")
    assert pp.find(".//{*}case//{*}left").get("value") == str(발문_이음_왼여백)


def test_박스_뒤_본문_줄은_발문_이음_줄이다():
    """(10-01 결정) :::자료·그림·표 뒤의 본문 줄도 〈보기〉 참고 줄처럼 발문 이음 줄(Block '주') — 발문에 몰래 붙지 않고,
    블록 바로 아래·답지 앞 자리 그대로."""
    from exam_kit.scan import scan_markdown

    md = 기대.replace("※ 크기는 반올림했다.\n:::\n", "※ 크기는 반올림했다.\n:::\n이어지는 줄\n")
    s = scan_markdown(md)
    assert s.errors == ()
    q = next(x for x in s.questions if any(b.lines == ("이어지는 줄",) for b in x.blocks))
    i = next(k for k, b in enumerate(q.blocks) if b.lines == ("이어지는 줄",))
    assert q.blocks[i].kind == "주" and q.blocks[i - 1].kind == "자료"
    assert "이어지는 줄" not in " ".join(q.stem)


def test_참고_줄은_역변환에서도_보기_아래로(양식_hwpx, tmp_path):
    """조판본 → 역변환 md: 참고 줄이 :::보기 바로 아래 본문 줄로 돌아오고, 다시 스캔하면 Block('주')."""
    from exam_kit.compose import compose
    from exam_kit.kit import load_kit
    from exam_kit.prepare import finalize_form, prepare_document
    from exam_kit.reverse import reverse
    from exam_kit.scan import scan_markdown
    from exam_kit.slots import fill_slots

    # 역변환은 제출본 모양(공백으로 맞춘 짝짓기 답지)을 읽는다 — 조판기의 답항표는 읽지 않아, 〈보기〉 문항 하나로 본다
    head = 기대.split("\n## 1.")[0].replace("만점: 20", "만점: 4").replace("__.__.(_) _교시", "4.20.(월) 2교시")
    md = head.replace("_반~_반", "1반~5반").replace("__매 * _묶음", "30매 * 4묶음") + (
        "\n## 1. [4.0점]\n논리 회로에 대한 설명으로 옳은 것만을 모두 고른 것은?\n\n:::보기\n"
        "ㄱ. AND는 두 입력이 모두 1일 때만 1이다.\nㄴ. NOT은 입력을 뒤집는다.\n:::\n※ 단, 입력은 0 또는 1이다.\n\n"
        "① ㄱ\n② ㄴ\n*③ ㄱ, ㄴ\n④ 없음\n⑤ 모두\n")
    s = scan_markdown(md)
    kit = load_kit(kit_dir())
    doc, prepared = prepare_document(양식_hwpx, kit)
    fill_slots(doc, kit, s.front, question_count=len(s.questions), total_points=sum(q.points for q in s.questions))
    prepared = prepared.refresh(doc)
    compose(doc, s, kit, answer_key=False, image_root=픽스처)
    finalize_form(doc, kit, prepared)
    doc.save_to_path(str(tmp_path / "x.hwpx"))
    back = reverse(tmp_path / "x.hwpx", kit, image_dir=tmp_path)
    assert "ㄴ. NOT은 입력을 뒤집는다.\n:::\n※ 단, 입력은 0 또는 1이다.\n" in back
    assert [b.kind for b in scan_markdown(back).questions[0].blocks] == ["보기", "주"]
