# python/api/health.py
# Netauto 프로젝트의 헬스체크 API
# routes.json / junit.xml / report.md 상태를 읽고 네트워크 및 테스트 결과를 JSON으로 반환

from fastapi import FastAPI
from pathlib import Path
from datetime import datetime, timezone
import json, re
import xml.etree.ElementTree as ET

app = FastAPI(title="Netauto Health API")

# --------------------------------------------------
# 경로 설정
# 프로젝트 루트(netauto/) 기준으로 주요 산출물 파일 경로 지정
# --------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "python" / "out" / "routes.json"      # 라우팅 상태 수집 결과
JUNIT  = ROOT / "tests" / "artifacts" / "junit.xml"   # pytest 실행 결과
REPORT = ROOT / "docs" / "report.md"                  # Markdown 리포트

# --------------------------------------------------
# 파일 수정 시각 반환 (UTC ISO8601 형식)
# 없을 경우 None 반환
# --------------------------------------------------
def mtime_iso(p: Path):
    if not p.exists():
        return None
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()

# --------------------------------------------------
# routes.json 파싱
# - FRR(vtysh) 출력에서 OSPF 경로와 Neighbor 상태 요약
# - 라우터별로 route 수, Full 상태 이웃 수, 전체 이웃 수 계산
# --------------------------------------------------
def parse_routes(data: dict) -> dict:
    total_routes = total_full = total_neigh = 0
    nodes = {}

    # 예: "O>* 10.0.2.0/24 ..." → 10.0.2.0/24 추출
    ospf_line = re.compile(r'^\s*O[>\s\*]*\s+(\d+\.\d+\.\d+\.\d+/\d+)\b')

    for n, p in sorted((data or {}).items()):
        routes_text = (p or {}).get("routes", "") or ""
        ospf_text   = (p or {}).get("ospf", "") or ""

        # 'O'로 시작하는 라우트 라인만 추출해 중복 제거
        prefixes = set()
        for line in routes_text.splitlines():
            m = ospf_line.match(line)
            if m:
                prefixes.add(m.group(1))
        rcnt = len(prefixes)

        # OSPF Neighbor 중 Full 상태 라인 수 계산
        full = len(re.findall(r'\bFull\b', ospf_text))

        # Neighbor ID 헤더 제외한 실제 이웃 라인 수 계산
        neigh_lines = [l for l in ospf_text.splitlines() if l.strip() and "Neighbor ID" not in l]
        alln = len(neigh_lines)

        # 라우터별 요약 저장
        nodes[n] = {"routes": rcnt, "full": full, "neigh_all": alln}

        # 전체 합계 계산
        total_routes += rcnt
        total_full   += full
        total_neigh  += alln

    return {
        "nodes": nodes,
        "total_routes": total_routes,
        "total_full": total_full,
        "total_neigh": total_neigh
    }

# --------------------------------------------------
# JUnit XML 파싱
# pytest 결과 파일을 읽어 테스트 요약 반환
# - tests: 전체 테스트 수
# - passed: 통과 수
# - failed: 실패 및 에러 합산
# - skipped: 스킵된 테스트 수
# --------------------------------------------------
def parse_junit() -> dict:
    if not JUNIT.exists():
        return {"tests": 0, "passed": 0, "failed": 0, "skipped": 0}

    root = ET.fromstring(JUNIT.read_text(encoding="utf-8"))

    # 다양한 XML 루트(tag)에 대응 (testsuites, testsuite 등)
    if root.findall(".//testsuite"):
        suites = root.findall(".//testsuite")
    elif root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = list(root)
    else:
        suites = []

    tests = fail = err = skip = 0
    for s in suites:
        tests += int(s.attrib.get("tests", 0))
        fail  += int(s.attrib.get("failures", 0))
        err   += int(s.attrib.get("errors", 0))
        skip  += int(s.attrib.get("skipped", 0))

    passed = max(0, tests - fail - err - skip)
    return {"tests": tests, "passed": passed, "failed": fail + err, "skipped": skip}

# --------------------------------------------------
# /health 엔드포인트
# Netauto 전체 상태를 종합적으로 반환
# --------------------------------------------------
@app.get("/health")
def health():
    """
    반환 내용:
      - status: 전체 상태 ("ok" 또는 "degraded")
      - neighbors: OSPF 이웃 수 및 Full 상태 수
      - routes_total: 전체 OSPF 라우트 수
      - tests: pytest 요약 결과
      - report_present: 리포트 파일 존재 여부
      - nodes: 라우터별 세부 상태
      - mtimes: 주요 파일 수정 시각
    상태 판정 기준:
      - 모든 이웃이 Full 상태이고 테스트 실패 없음 → ok
      - 그 외는 degraded
    """
    # routes.json 로드 (없을 경우 빈 dict)
    if ROUTES.exists():
        try:
            data = json.loads(ROUTES.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}

    # 데이터 파싱
    rsum = parse_routes(data)
    junit = parse_junit()
    report_present = REPORT.exists()

    # 상태 판정
    ok_neighbors = (rsum["total_neigh"] > 0 and rsum["total_full"] == rsum["total_neigh"])
    ok_tests     = (junit["tests"] > 0 and junit["failed"] == 0)
    status       = "ok" if ok_neighbors and ok_tests else "degraded"

    # 주요 파일 수정 시각
    mtimes = {
        "routes_json": mtime_iso(ROUTES),
        "junit_xml":   mtime_iso(JUNIT),
        "report_md":   mtime_iso(REPORT),
    }

    # 최종 반환 JSON
    return {
        "status": status,
        "neighbors": {"full": rsum["total_full"], "total": rsum["total_neigh"]},
        "routes_total": rsum["total_routes"],
        "tests": junit,
        "report_present": report_present,
        "nodes": rsum["nodes"],
        "mtimes": mtimes
    }

