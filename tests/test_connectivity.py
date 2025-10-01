import os
import re
import pytest
from conftest import docker_exec, retry

CI_LIGHT = os.getenv("CI_LIGHT") == "1"

# 라이트 모드에서는 네트워크 실사 항목만 스킵 (vtysh/ping/OSPF/route)
skip_if_light = pytest.mark.skipif(CI_LIGHT, reason="CI light mode: no lab/docker available")

@pytest.mark.smoke
@skip_if_light
def test_vtysh_available(containers):
    for r in ("r1", "r2"):
        cp = docker_exec(containers[r], "vtysh -c 'show version' || true")
        assert "FRRouting" in cp.stdout, f"vtysh not available on {containers[r]}:\n{cp.stdout}\n{cp.stderr}"

@pytest.mark.smoke
@skip_if_light
def test_ping_h1_to_h2(containers):
    cp = retry(lambda: docker_exec(containers["h1"], "ping -c1 -w3 10.0.2.100"))
    assert cp.returncode == 0, f"Ping failed:\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}"

@pytest.mark.routing
@skip_if_light
def test_ospf_neighbors_full(containers):
    for r in ("r1", "r2"):
        cp = retry(lambda: docker_exec(containers[r], "vtysh -c 'show ip ospf neighbor'"))
        full_count = len(re.findall(r"\bFull\b", cp.stdout))
        assert full_count >= 1, f"OSPF neighbor not Full on {containers[r]}:\n{cp.stdout}"

@pytest.mark.routing
@skip_if_light
def test_r1_has_ospf_route_to_h2(containers):
    """R1 라우팅 테이블에 10.0.2.0/24 OSPF 경로 및 기대 next-hop 검사"""
    cp = retry(lambda: docker_exec(containers["r1"], "vtysh -c 'show ip route 10.0.2.0/24'"))
    out = cp.stdout
    # FRR 버전에 따라 요약표시는 O>* 이지만, prefix 조회는 아래 형태
    assert 'Known via "ospf"' in out, f"Not learned via OSPF on R1:\n{out}"
    assert re.search(r"^\s*\*\s*10\.0\.12\.2\b", out, re.M), f"Next-hop should be 10.0.12.2 on R1:\n{out}"

@pytest.mark.routing
@skip_if_light
def test_r2_has_ospf_route_to_h1(containers):
    """R2 라우팅 테이블에 10.0.1.0/24 OSPF 경로 및 기대 next-hop 검사"""
    cp = retry(lambda: docker_exec(containers["r2"], "vtysh -c 'show ip route 10.0.1.0/24'"))
    out = cp.stdout
    assert 'Known via "ospf"' in out, f"Not learned via OSPF on R2:\n{out}"
    assert re.search(r"^\s*\*\s*10\.0\.12\.1\b", out, re.M), f"Next-hop should be 10.0.12.1 on R2:\n{out}"

def test_no_drift_against_template(containers):
    from subprocess import run
    cp = run("python3 python/validate.py", shell=True, text=True, capture_output=True)
    assert cp.returncode == 0, f"Drift detected!\n{cp.stdout}\n{cp.stderr}"

