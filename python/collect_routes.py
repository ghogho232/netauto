"""
collect_routes.py

컨테이너 기반 FRR 라우터들에서 라우팅/OSPF 상태를 수집해
python/out/routes.json 파일에 저장하는 스크립트.

- 각 컨테이너에 대해:
  * 'show ip route' (전체 라우팅 테이블)
  * 'show ip ospf neighbor' (OSPF 이웃 상태)
- 수집 결과 예:
  {
    "clab-netauto-r1": {"routes": "...원문...", "ospf": "...원문..."},
    "clab-netauto-r2": {"routes": "...",       "ospf": "..."}
  }
"""

import json
import subprocess
import pathlib

# 수집 대상 컨테이너 이름들.
# containerlab로 만든 라우터 컨테이너 이름과 동일해야 한다.
# 필요 시 인벤토리/백업 파일에서 자동 추출하는 방식으로 개선 가능.
CONTAINERS = ["clab-netauto-r1", "clab-netauto-r2"]

# 출력 디렉토리 Path 객체. 존재하지 않으면 생성한다.
OUT = pathlib.Path("python/out")
OUT.mkdir(parents=True, exist_ok=True)

def sh(cmd: str) -> str:
    """
    쉘 명령을 실행하고 stdout을 문자열로 반환한다.
    - shell=True: 문자열 기반 셸 명령 사용
    - text=True: 바이트가 아닌 문자열로 결과 반환
    - capture_output=True: stdout/stderr를 캡처(여기선 stdout만 사용)
    주의: 외부 입력을 그대로 cmd에 넣지 말 것(셸 인젝션 위험).
    """
    result = subprocess.run(
        cmd,
        shell=True,
        text=True,
        capture_output=True
    )
    # 여기서는 간단히 stdout만 반환.
    # 필요 시 result.returncode / result.stderr 검사 로깅 가능.
    return result.stdout

# 최종적으로 JSON으로 직렬화할 누적 딕셔너리
data = {}

# 각 컨테이너에 대해 라우팅/OSPF 상태를 수집
for c in CONTAINERS:
    # 전체 라우팅 테이블 수집 (OSPF만 원하면 show ip route ospf 로 변경)
    routes = sh(f"docker exec {c} vtysh -c 'show ip route'")
    # OSPF 이웃 상태 수집
    ospf   = sh(f"docker exec {c} vtysh -c 'show ip ospf neighbor'")

    # 컨테이너 이름을 키로 하여 원문 텍스트를 저장
    data[c] = {
        "routes": routes,  # 라우팅 테이블 원문
        "ospf": ospf       # OSPF 이웃 테이블 원문
    }

# 수집 결과를 pretty JSON으로 저장 (들여쓰기 2칸)
with open(OUT / "routes.json", "w") as f:
    json.dump(data, f, indent=2)

# 사용자 피드백용 메시지
print("saved python/out/routes.json")

