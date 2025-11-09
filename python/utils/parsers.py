from pathlib import Path
import json
import xml.etree.ElementTree as ET

def load_health_json(path="docs/health.json"):
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

def parse_junit(path="tests/artifacts/junit.xml"):
    p = Path(path)
    if not p.exists():
        return {"tests": 0, "failures": 0, "skipped": 0}
    root = ET.fromstring(p.read_text(encoding="utf-8"))
    tests = int(root.attrib.get("tests", 0))
    failures = int(root.attrib.get("failures", 0))
    skipped = int(root.attrib.get("skipped", 0))
    return {"tests": tests, "failures": failures, "skipped": skipped}

def load_routes_json(path="python/routes.json"):
    p = Path(path)
    if not p.exists():
        return {"routes_total": 0}
    data = json.loads(p.read_text(encoding="utf-8"))
    total = 0
    for node in data.values():
        routes = node.get("routes", [])
        total += len(routes)
    return {"routes_total": total}

def load_drift_status(path="DRIFT_STATUS"):
    p = Path(path)
    if not p.exists():
        return 0
    try:
        return int(p.read_text(encoding="utf-8").strip())
    except Exception:
        return 0
