"""

- 입력:
  - python/out/routes.json  (텍스트 기반: {"node": {"routes": "...", "ospf": "..."}})
  - tests/artifacts/junit.xml (있으면 요약 반영, 없으면 0으로 처리)
  - 환경변수 DRIFT_STATUS (0/ok/true/clean => No drift)

- 출력:
  - docs/report.md
    - 상단: Netauto Health Summary (요약 표 + 노드별 요약 표)
    - 구분선 --- 이후: 노드별 OSPF/Routes 원문 코드블록(6-backticks)
    - 같은 파일 재실행 시 상단 요약만 갈아끼움(---를 경계로)
"""
import os, json, re, datetime, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
ROUTES_PATH = ROOT / "python" / "out" / "routes.json"
JUNIT_PATH  = ROOT / "tests" / "artifacts" / "junit.xml"
DOCS_DIR    = ROOT / "docs"
REPORT_MD   = DOCS_DIR / "report.md"

FENCE = "``````"
SUMMARY_MARK = "## Netauto Health Summary ("
SEPARATOR = "\n---\n"

def load_routes_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

def parse_ospf_routes_count(routes_text: str) -> int:
    """
    FRR 'show ip route' 텍스트에서 OSPF 라인만 카운트.
    - 좌측 공백 제거 후 'O'로 시작하는 라인 (O, O>*, O   등)
    - 'Codes:'나 'A - Babel' 같은 범례/설명 라인은 제외
    """
    if not routes_text:
        return 0
    cnt = 0
    for raw in routes_text.splitlines():
        line = raw.lstrip()
        if not line:
            continue
        if line.startswith("Codes:"):
            continue
        # 'X - YYY' 형태 범례 라인 배제
        if re.match(r"^[A-Z]\s*-\s", line):
            continue
        if line.startswith("O"):
            cnt += 1
    return cnt

def parse_ospf_neighbors(ospf_text: str) -> tuple[int, int]:
    """
    FRR 'show ip ospf neighbor' 테이블에서
    - 헤더 제외, 빈 줄 제외
    - 한 줄 = 한 이웃으로 간주
    - 'Full' 포함 여부로 Full 카운트
    """
    if not ospf_text:
        return 0, 0
    total = full = 0
    for raw in ospf_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "Neighbor ID" in line and "State" in line:
            continue
        # 데이터 라인
        parts = line.split()
        if len(parts) < 4:
            continue
        total += 1
        if re.search(r"\bFull\b", line, flags=re.I):
            full += 1
    return total, full

def aggregate_metrics(data: dict):
    node = {}
    total_routes = total_neigh = total_full = 0
    for n, payload in sorted(data.items()):
        routes_txt = (payload or {}).get("routes", "") or ""
        ospf_txt   = (payload or {}).get("ospf", "") or ""
        r_cnt = parse_ospf_routes_count(routes_txt)
        neigh_all, full = parse_ospf_neighbors(ospf_txt)
        node[n] = {"routes": r_cnt, "neigh_all": neigh_all, "full": full}
        total_routes += r_cnt
        total_neigh  += neigh_all
        total_full   += full
    return node, total_routes, total_neigh, total_full

def parse_junit(p: Path):
    if not p.exists():
        return dict(tests=0, failures=0, errors=0, skipped=0, passed=0)
    txt = p.read_text(encoding="utf-8")
    root = ET.fromstring(txt)
    suites = []
    if root.tag == "testsuites":
        suites = list(root)
    elif root.tag == "testsuite":
        suites = [root]
    else:
        suites = root.findall(".//testsuite")
    tests = failures = errors = skipped = 0
    for ts in suites:
        tests   += int(ts.attrib.get("tests", 0))
        failures+= int(ts.attrib.get("failures", 0))
        errors  += int(ts.attrib.get("errors", 0))
        skipped += int(ts.attrib.get("skipped", 0))
    passed = max(0, tests - failures - errors - skipped)
    return dict(tests=tests, failures=failures, errors=errors, skipped=skipped, passed=passed)

def drift_status_from_env() -> str:
    v = os.environ.get("DRIFT_STATUS", "").strip().lower()
    if v == "":
        return "Unknown"
    return "✅ No drift" if v in ("0", "ok", "true", "clean") else "❌ Drift detected"

def build_summary_md(node_metrics: dict, t_routes: int, t_neigh: int, t_full: int, junit: dict) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    commit = os.environ.get("GITHUB_SHA", "")[:7]
    lines = []
    lines.append(f"{SUMMARY_MARK}{ts})\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| OSPF Neighbors (Full) | {t_full}/{t_neigh} |")
    lines.append(f"| OSPF Routes (Total) | {t_routes} |")
    lines.append(f"| Pytest Passed/Failed | {junit['passed']}/{junit['failures'] + junit['errors']} |")
    lines.append(f"| Pytest Skipped | {junit['skipped']} |")
    lines.append(f"| Drift | {drift_status_from_env()} |")
    lines.append(f"| Commit | `{commit}` |")
    lines.append("\n### Node Breakdown")
    lines.append("| Node | OSPF Full | OSPF Neigh (all) | OSPF Routes |")
    lines.append("|------|-----------|------------------|-------------|")
    for n in sorted(node_metrics):
        m = node_metrics[n]
        lines.append(f"| {n} | {m['full']} | {m['neigh_all']} | {m['routes']} |")
    return "\n".join(lines) + SEPARATOR

def build_detail_md(data: dict) -> str:
    lines = []
    for n in sorted(data.keys()):
        d = data.get(n, {}) or {}
        ospf_txt = (d.get("ospf") or "").strip()
        routes_txt = (d.get("routes") or "").strip()
        lines += [
            f"## {n}",
            "### OSPF Neighbors",
            FENCE, ospf_txt, FENCE,
            "### Routes",
            FENCE, routes_txt, FENCE,
            ""
        ]
    return "\n".join(lines)

def merge_summary_into_existing(summary_md: str, existing: str) -> str:
    """
    기존 report.md가 Summary 블록으로 시작하면 그 블록을 교체,
    아니면 summary를 맨 위에 삽입. Summary 끝은 SEPARATOR(---)로 구분.
    """
    if existing.startswith(SUMMARY_MARK):
        if SEPARATOR in existing:
            _, after = existing.split(SEPARATOR, 1)
            return summary_md + after
        else:
            return summary_md
    else:
        return summary_md + existing

def main():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    data = load_routes_json(ROUTES_PATH)

    node_metrics, t_routes, t_neigh, t_full = aggregate_metrics(data)
    junit = parse_junit(JUNIT_PATH)

    summary_md = build_summary_md(node_metrics, t_routes, t_neigh, t_full, junit)

    # 상세 섹션은 기존 파일이 없거나 상세가 비어 있으면 새로 생성
    if REPORT_MD.exists():
        existing = REPORT_MD.read_text(encoding="utf-8")
        # 기존 내용에 상세 섹션이 이미 있다면 유지하고 상단만 교체
        new_text = merge_summary_into_existing(summary_md, existing)
    else:
        detail_md = build_detail_md(data)
        new_text = summary_md + detail_md

    REPORT_MD.write_text(new_text, encoding="utf-8")
    print("wrote", REPORT_MD)

if __name__ == "__main__":
    main()

