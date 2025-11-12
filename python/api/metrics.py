from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import APIRouter, Response
from datetime import datetime, timezone
import argparse

from python.utils.parsers import (
    load_health_json,
    parse_junit,
    load_routes_json,
    load_drift_status,
)

# FastAPI 인스턴스가 아니라 APIRouter를 노출해야 health.py가 include_router로 붙일 수 있음
router = APIRouter()

TOPOLOGY = "ospf-mini"  # 필요 시 환경변수로 치환

def _read_commit() -> str:
    head = Path(".git/HEAD")
    if not head.exists():
        return "unknown"
    ref = head.read_text(errors="ignore").strip()
    if ref.startswith("ref:"):
        ref_path = Path(".git") / ref.split(":", 1)[1].strip()
        return ref_path.read_text(errors="ignore").strip()[:12] if ref_path.exists() else "unknown"
    return ref[:12]

def render_metrics() -> str:
    health = load_health_json()
    junit = parse_junit()
    routes = load_routes_json()
    drift = load_drift_status()

    status = health.get("status", "unknown")
    neighbors = health.get("neighbors", {})
    full = int(neighbors.get("full", 0))
    total = int(neighbors.get("total", 0))

    routes_total = int(health.get("routes_total", 0)) or int(routes.get("routes_total", 0))

    # JUnit 우선, health.json은 fallback
    tests_total = int(junit["tests"] if junit["tests"] is not None else health.get("tests", {}).get("tests", 0))
    failed      = int(junit["failures"] if junit["failures"] is not None else health.get("tests", {}).get("failed", 0))
    skipped     = int(junit["skipped"] if junit["skipped"] is not None else health.get("tests", {}).get("skipped", 0))
    passed      = max(tests_total - failed, 0)

    commit = _read_commit()

    lines = []
    # info
    lines.append("# HELP netauto_info Build info label carrier")
    lines.append("# TYPE netauto_info gauge")
    lines.append(f'netauto_info{{commit="{commit}",topo="{TOPOLOGY}"}} 1')

    # status
    lines.append("# HELP netauto_status Overall status (1=ok, 0=else)")
    lines.append("# TYPE netauto_status gauge")
    lines.append(f"netauto_status {1 if status == 'ok' else 0}")

    # neighbors
    lines.append("# HELP netauto_neighbors OSPF neighbors by state")
    lines.append("# TYPE netauto_neighbors gauge")
    lines.append(f'netauto_neighbors{{state="full"}} {full}')
    lines.append(f'netauto_neighbors{{state="total"}} {total}')

    # routes
    lines.append("# HELP netauto_routes_total Total route count")
    lines.append("# TYPE netauto_routes_total gauge")
    lines.append(f"netauto_routes_total {routes_total}")

    # tests
    lines.append("# HELP netauto_tests_count Pytest test counters")
    lines.append("# TYPE netauto_tests_count gauge")
    lines.append(f'netauto_tests_count{{type="total"}} {tests_total}')
    lines.append(f'netauto_tests_count{{type="passed"}} {passed}')
    lines.append(f'netauto_tests_count{{type="failed"}} {failed}')
    lines.append(f'netauto_tests_count{{type="skipped"}} {skipped}')

    # drift
    lines.append("# HELP netauto_drift_config Config drift (1=yes,0=no)")
    lines.append("# TYPE netauto_drift_config gauge")
    lines.append(f"netauto_drift_config {1 if drift else 0}")

    # ---- per-node metrics ----
    nodes = health.get("nodes", {})
    if isinstance(nodes, dict) and nodes:
        lines.append("# HELP netauto_node_routes Routes per node")
        lines.append("# TYPE netauto_node_routes gauge")
        lines.append("# HELP netauto_node_neighbors Neighbors per node and state")
        lines.append("# TYPE netauto_node_neighbors gauge")
        for node, vals in nodes.items():
            try:
                n_routes = int(vals.get("routes", 0))
                n_full = int(vals.get("full", 0))
                n_total = int(vals.get("neigh_all", 0))
            except Exception:
                n_routes, n_full, n_total = 0, 0, 0
            lines.append(f'netauto_node_routes{{node="{node}"}} {n_routes}')
            lines.append(f'netauto_node_neighbors{{node="{node}",state="full"}} {n_full}')
            lines.append(f'netauto_node_neighbors{{node="{node}",state="total"}} {n_total}')

    # timestamp(주석 — Prometheus 무시)
    ts = int(datetime.now(timezone.utc).timestamp())
    lines.append(f"# netauto_timestamp {ts}")

    return "\n".join(lines) + "\n"

@router.get("/metrics")
def metrics():
    return Response(render_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true", help="write docs/metrics.txt")
    args = ap.parse_args()
    if args.snapshot:
        out = Path("docs/metrics.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_metrics(), encoding="utf-8")
        print(f"[ok] wrote {out}")

if __name__ == "__main__":
    main()

