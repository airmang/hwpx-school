"""hwpx 네임스페이스 상수 — skeleton.py·furniture.py가 같이 쓴다.

전에는 여러 파일에 같은 네임스페이스 URI 문자열이 따로 적혀 있었다 — 한 곳으로 모아
값이 갈라질 여지를 없앤다.
"""

from __future__ import annotations

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
# header.xml의 스타일 정의(fontfaces·charPr 등)가 사는 네임스페이스 — hp:와 다른 스키마다.
HH = "http://www.hancom.co.kr/hwpml/2011/head"
