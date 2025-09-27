import re
import pytest
from conftest import docker_exec, retry

@pytest.mark.smoke
def test_vtysh_available(containers):
    """각 라우터에서 vtysh 동작 확인(환경 체크)"""
    for r in ("r1", "r2"):
        cp = docker_exec(containers[r], "vtysh -c 'show version' || true")
        assert "FRRouting" in cp.stdout, f"vtysh not available on {containers[r]}:\n{cp.stdout}\n{cp.stderr}"

@pytest.mark.smoke
def test_ping_h1_to_h2(containers):
    """엔드투엔드 연결: H1 -> H2 ping 성공"""
    cp = retry(lambda: docker_exec(containers["h1"], "ping -c1 -w3 10.0.2.100"))
    assert cp.returncode == 0, f"Ping failed:\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}"

@pytest.mark.routing
def test_ospf_neighbors_full(containers):
    """각 라우터에서 OSPF 이웃 상태가 Full >= 1"""
    for r in ("r1", "r2"):
        cp = retry(lambda: docker_exec(containers[r], "vtysh -c 'show ip ospf neighbor'"))
        full_count = len(re.findall(r"\bFull\b", cp.stdout))
        assert full_count >= 1, f"OSPF neighbor not Full on {containers[r]}:\n{cp.stdout}"

@pytest.mark.routing
def test_r1_has_ospf_route_to_h2(containers):
    """R1 라우팅 테이블에 10.0.2.0/24 OSPF 경로 및 기대 next-hop 검사"""
    cp = retry(lambda: docker_exec(containers["r1"], "vtysh -c 'show ip route 10.0.2.0/24'"))
    out = cp.stdout
    assert "O>*" in out, f"OSPF route to 10.0.2.0/24 missing on R1:\n{out}"
    assert "via 10.0.12.2" in out, f"Next-hop should be 10.0.12.2 on R1:\n{out}"

@pytest.mark.routing
def test_r2_has_ospf_route_to_h1(containers):
    """R2 라우팅 테이블에 10.0.1.0/24 OSPF 경로 및 기대 next-hop 검사"""
    cp = retry(lambda: docker_exec(containers["r2"], "vtysh -c 'show ip route 10.0.1.0/24'"))
    out = cp.stdout
    assert "O>*" in out, f"OSPF route to 10.0.1.0/24 missing on R2:\n{out}"
    assert "via 10.0.12.1" in out, f"Next-hop should be 10.0.12.1 on R2:\n{out}"

def test_no_drift_against_template(containers):
    """Day3 드리프트 검증을 테스트에 편입 (의도==실제면 통과)"""
    from subprocess import run
    cp = run("python3 python/validate.py", shell=True, text=True, capture_output=True)
    assert cp.returncode == 0, f"Drift detected!\n{cp.stdout}\n{cp.stderr}"
