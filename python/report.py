"""
report.py

수집 결과(JSON)를 사람이 읽기 좋은 Markdown 리포트로 변환.
- 입력: python/out/routes.json  (collect_routes.py가 생성)
- 출력: docs/report.md           (리포트 상단 Summary + 각 노드별 OSPF/Routes 코드블록)

코드블록 펜스는 백틱(`)을 사용한다. 내부 내용에 백틱이 섞일 수도 있으므로,
안전하게 '백틱 6개'를 사용한다. (시작/종료의 개수가 같기만 하면 됨)
"""

import json, pathlib, re

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
data = json.loads(SRC.read_text(encoding="utf-8"))

def count_full(ospf_text: str) -> int:
    return len(re.findall(r"\bFull\b", ospf_text or ""))

def count_ospf_routes(routes_text: str) -> int:
    # 매우 러프한 카운트: 'Known via "ospf"' 라인 수를 센다 (플랫폼/표현 차이 흡수)
    return len(re.findall(r'Known via "ospf"', routes_text or ""))

# ---------- Summary 섹션 ----------
summary_lines = [
    "# Netauto Report",
    "",
    "## Summary",
    "",
    "| Node | OSPF Full Neighbors | OSPF Routes (approx) |",
    "|------|----------------------|----------------------|",
]

# dict는 파이썬 3.7+에서 삽입 순서 유지하지만, 출력 일관성을 위해 정렬 출력
for node in sorted(data.keys()):
    d = data.get(node, {})
    full = count_full(d.get("ospf", ""))
    rcount = count_ospf_routes(d.get("routes", ""))
    summary_lines.append(f"| {node} | {full} | {rcount} |")

summary_lines.append("")

# ---------- 상세 섹션 ----------
detail_lines = []
for node in sorted(data.keys()):
    d = data.get(node, {})
    ospf_txt = (d.get("ospf") or "").strip()
    routes_txt = (d.get("routes") or "").strip()

    detail_lines += [
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
MD.write_text("\n".join(summary_lines + detail_lines), encoding="utf-8")
print(f"wrote {MD}")

