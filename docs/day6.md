# # Day 6 — CI/CD 심화 + 메트릭 기반 리포트 자동화

## 1) 오늘의 목표
- **pytest 결과·드리프트 상태·OSPF 메트릭**을 통합해 사람이 읽을 수 있는 **자동 리포트**를 생성한다.  
- **GitHub Actions** 내에서 `validate.py` → `pytest` → `collect_routes.py` → `report.py` → `artifact 업로드`의 **완전 자동 파이프라인**을 완성한다.  
- 모든 결과를 **docs/report.md**에 기록하여 “네트워크 헬스 상태(Health Summary)”를 자동으로 시각화하고, **관측 가능성(Observability)**을 한 단계 높인다.

---

## 2) 오늘의 활동 요약
- `report.py`를 확장하여 **OSPF 이웃·경로 수, 테스트 통계, 드리프트 상태**를 상단에 요약 표로 자동 생성하도록 구현  
- `validate.py`의 종료 코드(0/1)를 `DRIFT_STATUS` 환경변수로 CI에 전달  
- GitHub Actions(`.github/workflows/netauto.yml`) 수정:  
  - junit.xml 디렉토리 생성  
  - validate.py 실행 → 결과 export  
  - pytest → collect → report 순으로 실행  
- 로컬 환경에서도 동일한 순서로 실행 테스트 성공:
  ```
  ✅ No drift found across 2 host(s)
  6 passed in 5.54s
  ```
- `docs/report.md` 상단에 자동 요약 메트릭 생성 성공  

---

## 3) 코드와 자세한 설명

### 3-1. 리포트 자동 생성: `python/report.py`
```python
# OSPF·Pytest·Drift 통합 리포트
import os, json, re, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES_PATH = ROOT / "python/out/routes.json"
JUNIT_PATH  = ROOT / "tests/artifacts/junit.xml"
REPORT_MD   = ROOT / "docs/report.md"

def parse_routes(data):
    # OSPF 라우팅 라인('O'로 시작)과 Full 이웃 카운트
    total_routes=total_full=total_neigh=0; nodes={}
    for n,p in sorted(data.items()):
        r, o = p.get("routes",""), p.get("ospf","")
        rcnt = sum(1 for l in r.splitlines() if l.lstrip().startswith("O"))
        full = len(re.findall(r"\bFull\b", o))
        alln = len([l for l in o.splitlines() if l.strip() and "Neighbor ID" not in l])
        nodes[n]={"routes":rcnt,"full":full,"neigh_all":alln}
        total_routes+=rcnt; total_full+=full; total_neigh+=alln
    return nodes,total_routes,total_full,total_neigh

def parse_junit(p):
    if not p.exists(): return dict(tests=0,failures=0,errors=0,skipped=0,passed=0)
    root=ET.fromstring(p.read_text()); suites=root.findall(".//testsuite") or [root]
    tests=fail=err=skip=0
    for s in suites:
        tests+=int(s.attrib.get("tests",0)); fail+=int(s.attrib.get("failures",0))
        err+=int(s.attrib.get("errors",0)); skip+=int(s.attrib.get("skipped",0))
    return dict(tests=tests,failures=fail,errors=err,skipped=skip,passed=max(0,tests-fail-err-skip))

def drift_status():
    v=os.environ.get("DRIFT_STATUS","").strip().lower()
    return "✅ No drift" if v in ("0","ok","true","clean") else ("❌ Drift detected" if v else "Unknown")

data=json.loads(ROUTES_PATH.read_text())
nodes,tr,tf,tn=parse_routes(data)
junit=parse_junit(JUNIT_PATH)
ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
commit=os.environ.get("GITHUB_SHA","")[:7]

summary=f"""## Netauto Health Summary ({ts})

| Metric | Value |
|---|---|
| OSPF Neighbors (Full) | {tf}/{tn} |
| OSPF Routes (Total) | {tr} |
| Pytest Passed/Failed | {junit['passed']}/{junit['failures']+junit['errors']} |
| Pytest Skipped | {junit['skipped']} |
| Drift | {drift_status()} |
| Commit | `{commit}` |

### Node Breakdown
| Node | OSPF Full | OSPF Neigh (all) | OSPF Routes |
|------|-----------|------------------|-------------|
""" + "\n".join([f"| {n} | {m['full']} | {m['neigh_all']} | {m['routes']} |" for n,m in nodes.items()]) + "\n---\n"

REPORT_MD.write_text(summary,encoding="utf-8")
print("wrote",REPORT_MD)
```

**설명**
- OSPF 상태 및 라우팅 정보를 파싱하여 노드별/전체 메트릭 계산  
- `junit.xml`을 파싱해 테스트 결과를 요약  
- `DRIFT_STATUS`를 통해 validate.py 결과를 반영  
- 리포트 상단에 요약 테이블 자동 생성  

---

### 3-2. CI 연계: `.github/workflows/netauto.yml`
```yaml
      - name: Prepare junit output dir
        run: mkdir -p tests/artifacts

      - name: Run drift check (validate.py)
        id: drift
        env:
          CI_LIGHT: "1"
          NETAUTO_PREFIX: "clab-netauto"
        run: |
          . .venv/bin/activate
          set +e
          python python/validate.py
          CODE=$?
          echo "exit_code=$CODE" >> $GITHUB_OUTPUT
          exit 0

      - name: Export DRIFT_STATUS for report
        run: echo "DRIFT_STATUS=${{ steps.drift.outputs.exit_code }}" >> $GITHUB_ENV

      - name: Run tests + report
        run: |
          . .venv/bin/activate
          pytest -q --junitxml=tests/artifacts/junit.xml
          python python/collect_routes.py || true
          python python/report.py || true
```

**설명**
- validate.py 실행 결과(0/1)를 CI 환경변수로 저장  
- pytest 결과(`junit.xml`)와 수집 결과(`routes.json`)를 기반으로 report.py가 리포트 생성  
- CI 실행 시마다 최신 헬스 상태 리포트를 자동 갱신  

---

## 4) 어려웠던 점 → 어떻게 극복했나

**문제 1: pytest 결과가 리포트에 반영되지 않음**  
- **증상:** `docs/report.md` 상단의 Pytest 통계가 항상 0/0으로 표시됨.  
  원인은 `tests/artifacts/junit.xml` 파일이 CI에서 생성되지 않아서, report.py가 데이터를 읽지 못함.  
- **해결:** GitHub Actions 실행 전 `tests/artifacts` 디렉토리를 **사전에 생성**하도록 단계 추가.  
  그 결과 pytest 결과가 정상적으로 `junit.xml`에 기록되고 리포트에 반영됨.

**문제 2: Drift 상태가 항상 Unknown으로 표시**  
- **증상:** validate.py의 결과가 report.py에 전달되지 않아 리포트에서 항상 `Drift = Unknown` 표시.  
- **해결:** GitHub Actions 내에서 validate.py 종료 코드를 `DRIFT_STATUS` 환경변수로 **전달하도록 수정.**  
  report.py는 이 값을 읽어 0이면 ✅ No drift, 1이면 ❌ Drift detected 로 자동 표시되도록 개선.

**문제 3: FRR 출력 파싱 오탐**  
- **증상:** `show ip route` 출력의 ‘Codes:’ 나 ‘A - Babel’ 같은 범례까지 OSPF 경로로 잘못 카운트됨.  
- **해결:** 정규식을 개선해 범례·공백 라인 및 비OSPF 라인을 필터링하여 정확한 경로 수만 집계하도록 수정.

**문제 4: utcnow 경고(Deprecation Warning)**  
- **증상:** `datetime.datetime.utcnow()` 가 비권장 API로 경고 발생.  
- **해결:** `datetime.now(timezone.utc)` 형식으로 교체하여 timezone-aware UTC 표기 방식으로 수정.  

---

## 5) 실행 런북 (Runbook)
> 전제: Containerlab 환경 실행 중, pytest 설치 완료, backups 존재

```bash
# 1) pytest 실행
pytest -q --junitxml=tests/artifacts/junit.xml || true

# 2) 드리프트 검사
python python/validate.py; export DRIFT_STATUS=$?

# 3) 리포트 생성
python python/report.py
# → docs/report.md 생성/갱신

# 4) CI 실행 시 (자동)
# validate.py → pytest → collect_routes.py → report.py → artifacts 업로드
```

**결과 해석**
- `docs/report.md` 상단 표에서 다음 항목 확인:
  - OSPF Neighbors (Full): 이웃이 모두 Full인지
  - Pytest Passed/Failed: 테스트 통과율
  - Drift: ✅이면 템플릿과 실제 설정 일치
  - Commit: 어떤 커밋 시점의 결과인지

---

## 6) 오늘 공부한 것
- **CI/CD와 Observability 통합**  
  - 단순 테스트 자동화를 넘어 **운영 리포트 자동화** 구현  
- **상태 집계 파이프라인 설계**  
  - raw CLI → JSON → Markdown으로 이어지는 데이터 흐름 이해  
- **GitHub Actions 환경변수 흐름 제어**  
  - validate.py 종료 코드 → report.py 환경변수 전달  
- **정규식 기반 텍스트 파싱 기법**  
  - FRRouting 출력에서 의미 있는 라인만 추출  
- **시간·커밋 기반 버전 관리 리포트**  
  - ts + SHA로 실행 시점과 버전 추적 가능  

---

## 7) 보충하면 좋을 것 (다음 단계 제안)
- **리포트 아카이브**: docs/history/report-YYYYMMDD.md 형태로 날짜별 저장  
- **Slack / Webhook 알림**: Drift 발생 시 자동 알림  
- **GitHub Pages 게시**: docs/ 디렉토리를 Pages로 자동 배포  
- **FastAPI 헬스 엔드포인트**: `/health` API로 리포트 요약 제공  
- **BGP·정책 확장**: 라우팅 프로토콜 확장 및 정책 템플릿 검증 추가  

---
