import os, time, subprocess, pathlib, pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_PREFIX = "clab-netauto"
PREFIX = os.getenv("NETAUTO_PREFIX", DEFAULT_PREFIX)

def run(cmd: str, timeout: int = 25):
    return subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout)

def docker_exec(container: str, inner: str, timeout: int = 25):
    return run(f"docker exec {container} sh -lc \"{inner}\"", timeout=timeout)

def retry(fn, tries=5, delay=2):
    last = None
    for _ in range(tries):
        last = fn()
        if last.returncode == 0:
            return last
        time.sleep(delay)
    return last

@pytest.fixture(scope="session")
def containers():
    return {
        "r1": f"{PREFIX}-r1",
        "r2": f"{PREFIX}-r2",
        "h1": f"{PREFIX}-h1",
        "h2": f"{PREFIX}-h2",
    }

@pytest.fixture(scope="session")
def artifacts_dir():
    d = ROOT / "tests" / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d

def pytest_runtest_makereport(item, call):
    if call.when == "call" and call.excinfo is not None:
        try:
            subprocess.run("python3 python/collect_routes.py", shell=True, cwd=ROOT)
            subprocess.run("python3 python/report.py", shell=True, cwd=ROOT)
        except Exception:
            pass
