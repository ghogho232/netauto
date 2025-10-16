# Day 5 — CI/CD 자동화 및 라이트 모드 테스트 환경 구축

## 1) 오늘의 목표

- 로컬에서 수동으로 수행하던 **pytest·드리프트 검증 프로세스**를 GitHub Actions로 자동화한다.
- Containerlab 없는 환경에서도 동작하도록 **라이트 모드(CI_LIGHT)** 를 추가해, 빌드 실패를 방지한다.
- 코드 변경 시마다 **자동 검증 → 결과 리포트 업로드**까지 수행하는 CI/CD 기반 운영 체계를 구축한다.

---

## 2) 오늘의 활동 요약

- `.github/workflows/netauto.yml` 작성 → **GitHub Actions 파이프라인** 정의
- `pytest.ini` 추가 → 사용자 정의 마커(`smoke`, `routing`) 등록
- `test_connectivity.py` 수정 → 라이트 모드(CI_LIGHT) 시 네트워크 의존 테스트 **자동 스킵**
- CI 환경변수 `CI_LIGHT=1` 설정 → Docker 없는 CI 환경에서도 pytest 통과
- 커밋 → Push → Actions 자동 실행 → JUnit XML 결과 확인

---

## 3) 코드와 자세한 설명

### 3-1. GitHub Actions 워크플로우: `.github/workflows/netauto.yml`

```yaml
name: Netauto CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    env:
      CI_LIGHT: "1"           # Docker/Containerlab 없는 환경에서도 스킵 모드 실행
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          python -m venv .venv
          . .venv/bin/activate
          pip install -r requirements.txt
      - name: Run pytest
        run: |
          . .venv/bin/activate
          pytest -v --junitxml=tests/artifacts/junit.xml
      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: netauto-artifacts
          path: |
            docs/report.md
            python/out/routes.json
            tests/artifacts/junit.xml
```

**설명**
- 푸시 또는 PR마다 CI 실행
- Python 3.11 환경 세팅 → pytest 실행 → 산출물(`report.md`, `routes.json`) 업로드
- `CI_LIGHT` 환경 변수 덕분에 **Docker 명령이 없어도 실패하지 않음**

---

### 3-2. Pytest 마커 등록: `pytest.ini`

```ini
[pytest]
markers =
    smoke: 기본 연결 확인 테스트
    routing: 라우팅/OSPF 검증 테스트
```

**설명**
- `Unknown pytest.mark.smoke` 경고 제거
- 테스트 그룹 분류 가능 (필요 시 `pytest -m smoke` 등으로 선택 실행)

---

### 3-3. 테스트 코드 수정: `tests/test_connectivity.py`

```python
import os, re, pytest
from conftest import docker_exec, retry

CI_LIGHT = os.getenv("CI_LIGHT") == "1"
skip_if_light = pytest.mark.skipif(CI_LIGHT, reason="CI light mode: no lab/docker available")

@pytest.mark.smoke
@skip_if_light
def test_vtysh_available(containers):
    ...

@pytest.mark.smoke
@skip_if_light
def test_ping_h1_to_h2(containers):
    ...

@pytest.mark.routing
@skip_if_light
def test_ospf_neighbors_full(containers):
    ...

@pytest.mark.routing
@skip_if_light
def test_r1_has_ospf_route_to_h2(containers):
    ...

@pytest.mark.routing
@skip_if_light
def test_r2_has_ospf_route_to_h1(containers):
    ...

def test_no_drift_against_template(containers):
    from subprocess import run
    cp = run("python3 python/validate.py", shell=True, text=True, capture_output=True)
    assert cp.returncode == 0, f"Drift detected!\n{cp.stdout}\n{cp.stderr}"
```

**설명**
- `@skip_if_light` → 라이트 모드에서는 vtysh/ping/OSPF 테스트 스킵
- **실행 유지 테스트**: `test_no_drift_against_template`  
  → 템플릿과 백업 비교만 실행되어 **드리프트 검증 통과**

---

## 4) 실행 결과

Actions 실행 결과 (JUnit XML):

```xml
<testsuite name="pytest" errors="0" failures="0" skipped="5" tests="6">
  <skipped message="CI light mode: no lab/docker available" />
</testsuite>
```

- 총 6개 테스트 중 5개 스킵, 1개 성공(`test_no_drift_against_template`)
- `failures="0"`, `errors="0"` → **CI 성공**
- Docker 컨테이너가 없어도 pytest 정상 종료

**해석**
> “GitHub Actions 환경에서는 라이트 모드로 드리프트 검증만 수행하고,  
> 로컬 환경에서는 풀 테스트(vtysh/ping/OSPF)까지 수행”

---

## 5) 오늘 배운 것

- **CI/CD 개념**: 코드 변경 → 자동 테스트 → 결과 피드백의 자동화 루프
- **GitHub Actions 활용**: Python 설치, pytest 실행, 아티팩트 업로드 자동화
- **라이트 모드 전략**: CI 환경에 맞게 테스트 스킵/통과를 유연하게 조정
- **Pytest 마커 구조화**: 테스트의 성격별 그룹화로 유지보수성 향상
- **Observability 연계**: CI 단계에서도 drift 검증을 통해 구성 일관성 확인

---

## 6) 실행 런북 (Runbook)

```bash
# 1) 로컬 풀 테스트 실행 (Containerlab이 실행 중일 때)
pytest -v

# 2) 라이트 모드 테스트 (CI 환경과 동일하게)
CI_LIGHT=1 pytest -v

# 3) GitHub에 커밋 및 푸시 → Actions 자동 실행
git add .
git commit -m "ci: add GitHub Actions + light mode skip"
git push origin main
```

**결과 해석**
- GitHub Actions → ✅ 녹색 체크 표시 (Success)
- Artifacts 탭 → `report.md`, `routes.json`, `junit.xml` 다운로드 가능

---

## 7) 보충하면 좋을 것

- **Full 모드 CI 추가**: self-hosted runner에서 Containerlab 구동 → 실제 네트워크 테스트
- **Slack/Webhook 알림**: 실패 시 즉시 알림 전송
- **정적 검사 추가**: YAML/Jinja 템플릿 Lint, `yamllint`/`jinjalint` 통합
- **CI/CD 확장**: PR 자동 검증 + main 브랜치 머지 시 자동 보고서 생성
- **Makefile 통합**: `make test-light`, `make test-full`, `make drift` 등 단축 명령 추가
