"""
report.py

수집 결과(JSON)를 사람이 읽기 좋은 Markdown 리포트로 변환.
- 입력: python/out/routes.json  (collect_routes.py가 생성)
- 출력: docs/report.md           (각 노드별 OSPF/Routes를 코드블록으로 기록)


- 코드블록 펜스는 백틱(`)을 사용한다. 내부 내용에 백틱이 섞일 수도 있으므로,
  안전하게 '백틱 6개'를 사용한다. (시작/종료의 개수가 같기만 하면 됨)
"""

import json
import pathlib

# 입력 JSON 파일 경로
SRC = pathlib.Path("python/out/routes.json")

# 출력 디렉토리 및 파일 경로
DST = pathlib.Path("docs")
DST.mkdir(parents=True, exist_ok=True)   # docs 폴더가 없으면 생성
MD = DST / "report.md"

# 코드블록 펜스(백틱 6개). 시작/종료를 같은 문자열로 쓰면 된다.
FENCE = "``````"

# JSON 로드
# 구조 예:
# {
#   "clab-netauto-r1": {"ospf": "...", "routes": "..."},
#   "clab-netauto-r2": {"ospf": "...", "routes": "..."}
# }
data = json.loads(SRC.read_text())

# Markdown 본문을 줄 단위로 쌓아간다.
lines = [
    "# Netauto Report",
    ""  # 상단 제목 뒤 한 줄 공백
]

# dict는 삽입 순서를 유지하지만, 출력 순서를 고정하고 싶다면 sorted(data) 사용 가능
for node, d in data.items():
    # d["ospf"] / d["routes"]는 CLI 원문 출력이므로 양끝 공백/개행을 정리
    ospf_txt = d["ospf"].strip()
    routes_txt = d["routes"].strip()

    lines += [
        f"## {node}",
        "### OSPF Neighbors",
        FENCE,           # 코드블록 시작
        ospf_txt,        # OSPF 이웃 원문
        FENCE,           # 코드블록 종료
        "### Routes",
        FENCE,           # 코드블록 시작
        routes_txt,      # 라우팅 테이블 원문
        FENCE,           # 코드블록 종료
        ""               # 섹션 간 빈 줄
    ]

# 파일로 저장 (줄바꿈으로 합치기)
MD.write_text("\n".join(lines))

print(f"wrote {MD}")

