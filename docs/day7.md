# # Day 7 — Health API 구축 + Slack/Pages 통합 자동화

## 1) 오늘의 목표
- 네트워크 상태를 **API로 조회 가능한 형태(Health API)**로 제공  
- `FastAPI` 기반 `/health` 엔드포인트를 구현해 **OSPF, Pytest, Drift 상태를 실시간 제공**  
- GitHub Actions에서 **health.json 자동 생성 및 Pages 게시 → Slack 알림**까지 연동  
- 코드 레벨에서 **운영 환경 수준의 관측 가능성(Observability)** 확보

---

## 2) 오늘의 활동 요약
- `python/api/health.py` 구현  
  - routes.json, junit.xml, report.md를 자동 파싱  
  - 상태 요약(`status`, `neighbors`, `routes_total`, `tests`, `nodes`) 반환  
  - FastAPI 기반 `/health` REST 엔드포인트 제공  
- CI 수정(`.github/workflows/netauto.yml`)  
  - Health JSON을 report와 함께 Pages에 배포  
  - Slack 메시지에 health.json 링크 자동 포함  
- 로컬 테스트 성공  
  ```bash
  pytest -q --junitxml=tests/artifacts/junit.xml
  python python/collect_routes.py
  python python/report.py
  uvicorn python.api.health:app --reload
  ```
  결과:
  ```bash
  curl -s http://127.0.0.1:8080/health | jq .
  {
    "status": "ok",
    "neighbors": {"full": 2, "total": 2},
    "routes_total": 8,
    "tests": {"tests": 6, "passed": 6, "failed": 0, "skipped": 0},
    "report_present": true,
    "nodes": {"clab-netauto-r1": {...}, "clab-netauto-r2": {...}}
  }
  ```

---

## 3) 코드

### 3-1. Health API: `python/api/health.py`
```python
#!/usr/bin/env python3
from fastapi import FastAPI
from pathlib import Path
import json, re
import xml.etree.ElementTree as ET

app = FastAPI(title="Netauto Health API")

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "python" / "out" / "routes.json"
JUNIT  = ROOT / "tests" / "artifacts" / "junit.xml"
REPORT = ROOT / "docs" / "report.md"

# 라우팅 정보 파싱
def parse_routes(data):
    total_routes = total_full = total_neigh = 0
    nodes = {}
    for n, p in sorted((data or {}).items()):
        routes = (p or {}).get("routes", "") or ""
        ospf   = (p or {}).get("ospf", "") or ""
        rcnt = sum(1 for l in routes.splitlines() if l.lstrip().startswith("O"))
        full = len(re.findall(r"\bFull\b", ospf))
        alln = len([l for l in ospf.splitlines() if l.strip() and "Neighbor ID" not in l])
        nodes[n] = {"routes": rcnt, "full": full, "neigh_all": alln}
        total_routes += rcnt; total_full += full; total_neigh += alln
    return {"nodes": nodes, "total_routes": total_routes, "total_full": total_full, "total_neigh": total_neigh}

# 테스트 결과 파싱
def parse_junit():
    if not JUNIT.exists():
        return {"tests": 0, "passed": 0, "failed": 0, "skipped": 0}
    root = ET.fromstring(JUNIT.read_text(encoding="utf-8"))
    suites = root.findall(".//testsuite") or [root]
    tests = fail = err = skip = 0
    for s in suites:
        tests += int(s.attrib.get("tests", 0))
        fail  += int(s.attrib.get("failures", 0))
        err   += int(s.attrib.get("errors", 0))
        skip  += int(s.attrib.get("skipped", 0))
    passed = max(0, tests - fail - err - skip)
    return {"tests": tests, "passed": passed, "failed": fail + err, "skipped": skip}

# /health 엔드포인트
@app.get("/health")
def health():
    data = json.loads(ROUTES.read_text(encoding="utf-8")) if ROUTES.exists() else {}
    rsum = parse_routes(data)
    junit = parse_junit()
    report_present = REPORT.exists()
    ok_neighbors = (rsum["total_neigh"] > 0 and rsum["total_full"] == rsum["total_neigh"])
    ok_tests = (junit["failed"] == 0)
    status = "ok" if ok_neighbors and ok_tests else "degraded"

    return {
        "status": status,
        "neighbors": {"full": rsum["total_full"], "total": rsum["total_neigh"]},
        "routes_total": rsum["total_routes"],
        "tests": junit,
        "report_present": report_present,
        "nodes": rsum["nodes"]
    }
```

**설명**
- FastAPI로 `/health` 엔드포인트 생성  
- routes.json, junit.xml, report.md 존재 여부 확인  
- status는 이웃·테스트 정상 여부에 따라 `ok` 또는 `degraded` 결정  
- 네트워크 상태를 JSON 형태로 실시간 반환  

---

### 3-2. CI/CD 연계 (GitHub Actions)
- `report.md`와 함께 `health.json` 자동 생성 후 Pages 배포  
- Slack 알림 메시지에 “Health JSON 링크” 포함  
- 다음 코드 추가:
```yaml
# health.json 생성 (FastAPI 호출 없이 직접 모듈 실행)
python - <<'PY'
import json, pathlib
from python.api.health import health
data = health()
pathlib.Path("docs/health.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
```

---

## 4) 어려웠던 점 → 어떻게 극복했나

**문제 1: health.json에 테스트 결과가 반영되지 않음**  
- **증상:** pytest 결과가 항상 0으로 출력됨  
- **원인:** junit.xml 경로를 잘못 지정해 Health API가 빈 데이터를 읽음  
- **해결:** 절대경로(`tests/artifacts/junit.xml`)로 수정 후 정상 반영

**문제 2: status가 항상 degraded로 표시됨**  
- **증상:** 실제 OSPF가 Full이어도 degraded 반환  
- **해결:** 조건식 수정 → `total_full == total_neigh`일 때만 ok

**문제 3: FastAPI 실행 중 경로 인식 오류**  
- **증상:** uvicorn 실행 시 `FileNotFoundError: routes.json`  
- **해결:** `ROOT = Path(__file__).resolve().parents[2]` 로 절대경로 지정

---

## 5) 실행 런북 (Runbook)
> 전제: Containerlab 실행 중, FastAPI 설치 완료

```bash
# 1) 상태 수집
python python/collect_routes.py

# 2) 리포트 생성
python python/report.py

# 3) Health API 로컬 실행
uvicorn python.api.health:app --reload

# 4) 상태 확인
curl -s http://127.0.0.1:8080/health | jq .
```

**결과 해석**
- `"status": "ok"` → 테스트 및 이웃 모두 정상  
- `"status": "degraded"` → 일부 OSPF 혹은 테스트 실패  
- `"routes_total"` → 네트워크 경로 수 (OSPF 학습 결과 반영)  
- `"tests"` → Pytest 결과 통계  

---

## 6) 오늘 공부한 것
- **FastAPI 기반 헬스 체크 설계 원리**  
  - REST API로 시스템 상태를 노출하는 표준 패턴 이해  
- **CI/CD 파이프라인 내 API 통합**  
  - FastAPI 결과를 JSON으로 추출해 GitHub Actions에서 활용  
- **Observability 확장**  
  - Slack/Pages/Health API로 가시성 강화  
- **경로/이웃/테스트 메트릭 통합 설계**  
  - 실시간 네트워크 품질 지표를 코드 단에서 집계  
- **DevOps 친화적 구조 설계**  
  - 코드 변경 → 자동 테스트 → 자동 리포트 → 자동 알림 완성  

---

## 7) 보충하면 좋을 것
- **health.json에 timestamp·commit 해시 추가** → 변경 추적 강화  
- **FastAPI에 `/metrics` 추가** → Prometheus 호환 출력  
- **Slack 알림 시 status별 색상 지정 고도화**    
- **BGP/정책검증 모듈 추가** → 멀티 프로토콜 지원 확장  

---

 **정리**
> Day 7의 핵심 성과는  
> **“Health API 기반의 네트워크 관측 자동화 완성”**  
> CI/CD와 FastAPI, Slack, Pages가 유기적으로 연결되어  
> 실시간 상태 모니터링과 자동 리포트 생성이 가능한 구조를 구축하였다.

