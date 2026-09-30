"""양식 hwpx의 BinData 그림 → 재현/그림/imageN.png (양식 재현용, 로컬 전용).

양식은 사용자 자산이라 재현/그림/ 은 git 무시다. 엔진은 PNG 만 받고 자르기(imgClip)·비율 왜곡을 하지 않으므로,
원본 `hp:pic` 이 **화면에 보여 주는 모양**을 PNG 로 굳힌다:
  ① imgClip 으로 자른다(imgDim 단위 → 픽셀) ② 원본 표시 크기(curSz)의 가로세로비로 높이를 맞춘다
  ③ BMP 는 PNG 로 바꾼다. 원본 표시 폭(cm, 1cm = 2834.6 HWPUNIT)을 함께 찍는다 — md 의 {width=…cm} 값.
실행: uv run --python 3.13 python scripts/뽑기_원본그림.py <양식.hwpx>
"""
import io
import sys
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HC = "http://www.hancom.co.kr/hwpml/2011/core"
HWPUNIT_PER_CM = 7200 / 2.54

if len(sys.argv) != 2:
    raise SystemExit(__doc__)
원본 = Path(sys.argv[1])
대상 = Path(__file__).resolve().parents[1] / "재현" / "그림"
대상.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(원본) as z:
    파일 = {Path(n).stem: n for n in z.namelist() if n.startswith("BinData/")}
    구역 = etree.fromstring(z.read("Contents/section0.xml"))
    for pic in 구역.iter(f"{{{HP}}}pic"):
        아이디 = pic.find(f"{{{HC}}}img").get("binaryItemIDRef")
        im = Image.open(io.BytesIO(z.read(파일[아이디]))).convert("RGB")
        clip, dim, cur = (pic.find(f"{{{HP}}}{t}") for t in ("imgClip", "imgDim", "curSz"))
        배율_x = int(dim.get("dimwidth")) / im.width
        배율_y = int(dim.get("dimheight")) / im.height
        상자 = (round(int(clip.get("left")) / 배율_x), round(int(clip.get("top")) / 배율_y),
               round(int(clip.get("right")) / 배율_x), round(int(clip.get("bottom")) / 배율_y))
        im = im.crop(상자)
        표시_w, 표시_h = int(cur.get("width")), int(cur.get("height"))
        높이 = round(im.width * 표시_h / 표시_w)
        if abs(높이 - im.height) > 1:
            im = im.resize((im.width, 높이), Image.LANCZOS)
        출력 = 대상 / f"{아이디}.png"
        im.save(출력, "PNG")
        print(f"{파일[아이디]} → {출력} 자름{상자} {im.width}x{im.height}px "
              f"표시 {표시_w}x{표시_h} HWPUNIT = 폭 {표시_w / HWPUNIT_PER_CM:.3f}cm")
