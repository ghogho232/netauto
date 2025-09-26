import subprocess


def sh(cmd):
return subprocess.run(cmd, shell=True, capture_output=True)


def test_h1_to_h2_ping():
# 사전: h1/h2 IP/게이트웨이 설정은 Makefile의 make hostcfg에서 처리
res = sh("docker exec netauto-h1 ping -c1 -W2 10.0.2.100")
assert res.returncode == 0, res.stderr
