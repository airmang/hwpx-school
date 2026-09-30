"""킷 기술서(kit.json) — 로드·실재 검사. 양식은 저작물(git 미추적), kit.json이 그 위의 저작물."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from hwpx.document import HwpxDocument


# 킷은 두 파일이다.
#   kit.json    — 양식 층: 서식 파일이 정한 것(용지·단·스타일·누름틀·관리박스·꼬리 박스·견본 높이·코드 글꼴)
#   habits.json — 교사 습관 층: 한 교사(검수 교사)가 손으로 맞춘 값(간격·자간 맞춤·낱말 끌어올림)
#   rules.json  — 학교 규칙 층: 학교 문항 제작 연수자료의 [기계] 규칙(lint.SCHOOL_RULES 코드별 설정). 없으면 엔진 규칙만
# 학교 킷에 habits.json이 없으면 엔진 기본(defaults/habits.json = 첫 등록 학교 1학기 제출본 실측)을 쓰고, 보고서에 출처를 적는다.
# 코드에는 기본값을 두지 않는다 — 빠진 키는 어느 파일의 무슨 키인지 적어 오류로 세운다(fail-loud).
SCHEMA = 2
KIT_KEYS = frozenset({"kit", "schema", "version", "form", "page", "columns", "styles", "slots", "slots_removed",
                      "placeholders", "teacher_cell", "notice_box_height", "box_min_height", "code_font", "tailbox",
                      "admin", "guidance_text", "sample_text", "trim", "sample_region", "remove", "leftover_prefix",
                      "boxes", "set_marker",
                      "typeset", "metrics", "front_matter", "text_slots", "number", "render"})
GLYPH_SOURCES = ("curves", "text")  # 렌더 판정의 글리프: 본문이 PDF에서 곡선으로 나가는 글꼴 | 텍스트 층 글자
NUMBER_MODES = ("autonumber", "literal")  # 문항 번호: 스타일 자동번호가 그린다 | 조판기가 견본 번호 글자 모양으로 쓴다
BOX_KINDS = ("보기", "자료")  # 원고 문법의 박스 펜스(:::보기·:::자료) — 킷 boxes가 둘 다 기술해야 한다
TRIM_RULES = ("first_page_break", "text_prefix")  # 지울 구역(논술형 샘플~꼬리 앞)의 시작 — 첫 쪽 나눔 문단 | 글이 prefix로 시작하는 첫 문단
SAMPLE_REGIONS = ("role_styles", "admin_to_tail")  # 조판기가 바꿀 샘플 구역 — 역할 스타일 문단 첫~끝 | 관리박스 뒤 ~ 꼬리 박스 앞 전부
KIT_OPTIONAL = frozenset({"note", "text_slots_note"})
HABIT_KEYS = frozenset({"question_gap", "question_gap_min", "gap_extra_max", "letter_spacing_min", "letter_spacing_tail",
                        "letter_spacing_role_min", "letter_spacing_safety", "word_pull_min", "word_pull_gap",
                        "gap_mode", "pack", "bogi_hanging_indent", "grid"})
HABIT_OPTIONAL = frozenset({"source", "note"})
DEFAULT_HABITS = Path(__file__).resolve().parent / "defaults" / "habits.json"


@dataclass(frozen=True)
class Metrics:
    """양식 본문 글자·줄 치수(HWPUNIT) — 조판의 줄 수·칸 폭 추정. 값은 킷 metrics(실한컴 렌더로 잰다)."""

    full: int                 # 전각(한글 등) 글자 폭
    half: int                 # 반각(ASCII) 글자 폭
    space: int                # 공백 폭
    upper: int                # 로마자 대문자 폭
    char_height: int          # 글자 높이
    line_pitch: dict          # {줄간격 %(int): 한 줄 피치}
    box_extra: int            # 박스 내용 셀 높이 = (n − 1) × 피치 + box_extra
    mark_col: int             # 답항표 첫 열(원문자) 폭

    def char(self, ch: str) -> int:
        if ch == " ":
            return self.space
        if "A" <= ch <= "Z":
            return self.upper
        return self.half if ord(ch) < 0x80 else self.full

    def text(self, s: str) -> int:
        return sum(map(self.char, s))


def _metrics(d: dict) -> Metrics:
    return Metrics(full=d["full"], half=d["half"], space=d["space"], upper=d["upper"], char_height=d["char_height"],
                   line_pitch={int(k): v for k, v in d["line_pitch"].items()}, box_extra=d["box_extra"],
                   mark_col=d["mark_col"])


@dataclass(frozen=True)
class Kit:
    root: Path
    name: str
    form_sha256: str
    page: dict
    columns: dict
    styles: dict[str, str]
    slots: dict[str, str]
    slots_removed: list[str]
    placeholders: dict[str, str | None]
    teacher_cell: dict | None       # 누름틀 양식의 출제교사 칸 — 글자 자리 슬롯 양식은 None
    notice_box_height: int | None   # 정리 뒤 유의 박스 높이(제출본 실측값이 있을 때) — None이면 건드리지 않는다
    tailbox: dict
    box_min_height: int | None      # 〈보기〉·자료 내용 행 최소 높이 = 양식 견본 내용 셀 높이(_check_form이 양식과 대조)
    code_font: str                  # 코드 블록 고정폭 글꼴(Task 30) — 양식 fontface에 있으면 그것, 없으면 덧붙인다
    admin: dict                     # 관리박스 정리: paragraph·delete_tables_with·notice_table_with·notice_delete_paras_with·notice_replace
    guidance_text: tuple[str, ...]  # 서식 안내 문구 — 산출물에 남으면 실패(M7d)
    sample_text: tuple[str, ...]    # 서식 샘플 문항 문구 — 산출물에 남으면 실패(M7d)
    trim: dict                      # 지울 구역(논술형 샘플~꼬리 앞)의 시작: {"rule": TRIM_RULES, "prefix": text_prefix일 때}
    sample_region: str              # 샘플 구역 규칙(SAMPLE_REGIONS)
    remove: dict                    # 양식 준비에서 통째로 지울 것: {"memos": bool, "drawings": bool}
    leftover_prefix: str            # 마지막 문항과 꼬리 사이에서 지울 안내 줄의 머리
    boxes: dict                     # 견본 박스 {"보기"|"자료": title·title_match·shape·cells·content_cell·rails·style}
    set_marker: dict                # 세트 표지 견본 run: pattern(정규식)·char_height·bold
    typeset: dict                   # 조판 관례: score_suffix·set_head(format 문자열)·text_replace·grayscale_pictures
    metrics: Metrics                # 본문 글자·줄 치수
    front_matter: dict              # 원고 머리 키: {"required": [...], "optional": [...]}
    text_slots: list                # 글자 자리 슬롯(누름틀 없는 양식): [{name, where, find, fill, (each, join, read)}]
    render: dict                    # 렌더 판정 입력: glyphs(GLYPH_SOURCES)·text_fonts(텍스트 층 본문 글꼴)·choice_dx(답지 줄 dx 범위 pt)
    number: dict                    # 문항 번호: {"mode": NUMBER_MODES, literal이면 "format"({n}), "sample_pattern"(견본 번호 run)}
    # ---- 교사 습관 층(habits.json) ----
    question_gap: int               # 문항 머리 앞 간격(HWPUNIT, case 분기) — 예: 1760 = 11pt×160% 한 줄
    question_gap_min: int           # 꼬리 박스 자리를 만들려고 넘친 단 간격을 줄일 하한(= question_gap이면 줄이지 않음)
    gap_extra_max: int | None       # distribute가 문항 하나에 더하는 간격 상한(HWPUNIT) — None이면 상한 없음(Task 31)
    letter_spacing_min: int         # 자간 맞춤 하한(%)
    letter_spacing_tail: float      # 자간 맞춤 후보 = 끝줄 추정 폭 ÷ 끝줄 가용 폭이 이 값 이하
    letter_spacing_role_min: dict   # 역할별 하한 {"발문": …, "기타": …}
    letter_spacing_safety: int      # 찾은 최소 자간에 더 줄 여유(%)
    word_pull_min: int              # 낱말 끌어올림 하한(%) — 0이면 끈다
    word_pull_gap: float            # 끌어올림 후보 = 벌어진 줄의 공백당 남는 폭 ÷ 공백 폭이 이 값 이상
    gap_mode: str                   # 문항 간격 기본 방식(layout.GAPS) — build --gap이 없을 때
    pack: str                       # 단 나눔 기본 방식(layout.PACKS) — build --pack이 없을 때
    bogi_hanging_indent: int        # 〈보기〉 항목 내어쓰기(case) — 제출본 교사 박스 다수 기하(Task 29)
    grid: dict                      # 격자표: in_margin·out_margin(칸 안·바깥 여백)·min_col(열 최소 폭)
    habits_source: str              # 습관값 출처(보고서에 적는다) — "킷" 또는 기본 파일의 source
    rules: dict | None              # 학교 규칙(rules.json 내용) — 없으면 None(엔진 규칙만)

    @property
    def forbidden_text(self) -> tuple[str, ...]:
        """산출물 본문에 남으면 안 되는 서식 안내·샘플 문구."""
        return self.guidance_text + self.sample_text

    def slot_ids(self) -> dict[str, str]:
        removed = set(self.slots_removed)
        return {k: v for k, v in self.slots.items() if k not in removed}


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path: Path, required: frozenset, optional: frozenset) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    missing, unknown = sorted(required - d.keys()), sorted(d.keys() - required - optional)
    if missing or unknown:
        raise ValueError(f"킷 파일 {path}: " + " · ".join(
            ([f"빠진 키 {missing}"] if missing else []) + ([f"모르는 키 {unknown}"] if unknown else [])))
    return d


def load_kit(root: Path) -> Kit:
    root = Path(root)
    d = _read(root / "kit.json", KIT_KEYS, KIT_OPTIONAL)
    if d["schema"] != SCHEMA:
        raise ValueError(f"킷 파일 {root / 'kit.json'}: schema {d['schema']} — 이 엔진은 {SCHEMA}만 읽는다")
    if d["trim"]["rule"] not in TRIM_RULES or (d["trim"]["rule"] == "text_prefix" and not d["trim"].get("prefix")):
        raise ValueError(f"킷 파일 {root / 'kit.json'}: trim {d['trim']!r} — 지원: {TRIM_RULES}(text_prefix는 prefix 필요)")
    if d["sample_region"] not in SAMPLE_REGIONS:
        raise ValueError(f"킷 파일 {root / 'kit.json'}: sample_region {d['sample_region']!r} — 지원: {SAMPLE_REGIONS}")
    if d["render"]["glyphs"] not in GLYPH_SOURCES:
        raise ValueError(f"킷 파일 {root / 'kit.json'}: render.glyphs {d['render']['glyphs']!r} — 지원: {GLYPH_SOURCES}")
    if d["number"]["mode"] not in NUMBER_MODES:
        raise ValueError(f"킷 파일 {root / 'kit.json'}: number.mode {d['number']['mode']!r} — 지원: {NUMBER_MODES}")
    missing_boxes = [k for k in BOX_KINDS if k not in d["boxes"]]
    if missing_boxes:
        raise ValueError(f"킷 파일 {root / 'kit.json'}: boxes에 {missing_boxes} 없음")
    own = root / "habits.json"
    h = _read(own if own.exists() else DEFAULT_HABITS, HABIT_KEYS, HABIT_OPTIONAL)
    source = "킷(habits.json)" if own.exists() else f"엔진 기본 — {h.get('source', DEFAULT_HABITS.name)}"
    rules = json.loads((root / "rules.json").read_text(encoding="utf-8")) if (root / "rules.json").exists() else None
    return Kit(
        root=root, name=d["kit"], form_sha256=d["form"]["sha256"], page=d["page"], columns=d["columns"],
        styles=d["styles"], slots=d["slots"], slots_removed=d["slots_removed"], placeholders=d["placeholders"],
        teacher_cell=d["teacher_cell"], notice_box_height=d["notice_box_height"], tailbox=d["tailbox"],
        box_min_height=d["box_min_height"], code_font=d["code_font"], admin=d["admin"],
        guidance_text=tuple(d["guidance_text"]), sample_text=tuple(d["sample_text"]), trim=d["trim"],
        sample_region=d["sample_region"], remove=d["remove"],
        leftover_prefix=d["leftover_prefix"], boxes=d["boxes"], set_marker=d["set_marker"],
        typeset=d["typeset"], metrics=_metrics(d["metrics"]), front_matter=d["front_matter"],
        text_slots=d["text_slots"], number=d["number"], render=d["render"],
        question_gap=h["question_gap"], question_gap_min=h["question_gap_min"], gap_extra_max=h["gap_extra_max"],
        letter_spacing_min=h["letter_spacing_min"], letter_spacing_tail=h["letter_spacing_tail"],
        letter_spacing_role_min=h["letter_spacing_role_min"], letter_spacing_safety=h["letter_spacing_safety"],
        word_pull_min=h["word_pull_min"], word_pull_gap=h["word_pull_gap"], gap_mode=h["gap_mode"], pack=h["pack"],
        bogi_hanging_indent=h["bogi_hanging_indent"], grid=h["grid"], habits_source=source,
        rules=rules,
    )


def style_ids(doc: HwpxDocument) -> dict[str, tuple[str, str | None, str | None]]:
    """스타일 이름 → (style id, paraPr id, charPr id). upstream profile.py와 같은 조회."""
    out: dict[str, tuple[str, str | None, str | None]] = {}
    for s in doc.styles.values():
        if not s.name:
            continue
        sid = str(s.id if s.id is not None else s.raw_id)
        pp = None if s.para_pr_id_ref is None else str(s.para_pr_id_ref)
        cp = None if s.char_pr_id_ref is None else str(s.char_pr_id_ref)
        out.setdefault(s.name, (sid, pp, cp))
    return out


def verify_kit(kit: Kit, *, form_path: Path) -> list[str]:
    """양식이 kit.json과 맞는지: sha256 일치 + `prepare._check_form`의 구조 검사."""
    from .prepare import _check_form  # 순환 import 회피(prepare.py가 kit.py를 가져다 쓴다)

    문제: list[str] = []
    if sha256(form_path) != kit.form_sha256:
        문제.append(f"양식 sha256 불일치: {form_path}")
    try:
        _check_form(HwpxDocument.open(str(form_path)), kit)
    except ValueError as e:
        문제.append(str(e))
    return 문제
