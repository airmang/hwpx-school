from exam_kit._png import png  # noqa: F401  # 픽스처에서 같은 이름으로 쓴다


def 텍스트(el) -> str:
    return "".join(el.itertext())


def 최상위_문단(doc) -> list:
    return list(doc.sections[0].paragraphs)
