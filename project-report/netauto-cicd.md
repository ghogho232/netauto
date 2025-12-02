# Netauto 프로젝트 CI/CD 및 GitHub Actions

## 목차
- [1. 개요](#1-개요)
  - [1.1 GitHub Actions 워크플로 개요](#11-github-actions-워크플로-개요)
- [2. `netauto.yml` 워크플로 상세 구조](#2-netautoyml-워크플로-상세-구조)
  - [2.1 Netauto GitHub Actions 전체 구조 요약](#21-netauto-github-actions-전체-구조-요약)
  - [2.2 트리거 조건(on)](#22-트리거-조건on)
  - [2.3 전체 Job 구성](#23-전체-job-구성-개요)
- [3. `light` Job - 기본 CI 및 리포트 생성](#3-light-job---기본-ci-및-리포트-생성)
  - [3.1 개요](#31-개요)
  - [3.2 실행 환경 및 출력 정의](#32-실행-환경-및-출력-정의)
  - [3.3 상세 단계별 설명](#33-상세-단계별-설명)

- [4. `publish` Job - GitHub Pages 배포](#4-publish-job---github-pages-배포)
  - [4.1 의존 관계 및 권한](#41-의존-관계-및-권한)
  - [4.2 단계별 설명](#42-단계별-설명)
- [5. `notify` Job - Slack 알림 (Light 결과)](#5-notify-job---slack-알림-light-결과)
  - [5.1 역할](#51-역할)
  - [5.2 JUnit 요약 파싱](#52-junit-요약-파싱)
  - [5.3 Slack 메시지 구성](#53-slack-메시지-구성)
- [6. `lint` Job - Prometheus Rules 정적 검사](#6-lint-job---prometheus-rules-정적-검사)
  - [6.1 역할](#61-역할)
  - [6.2 수행 내용](#62-수행-내용)
- [7. `full` Job - Containerlab 기반 E2E CI](#7-full-job---containerlab-기반-e2e-ci)
  - [7.1 역할](#71-역할)
  - [7.2 수행 내용](#72-수행-내용)
  - [7.3 Ansible 결합](#73-ansible-결합)
  - [7.4 E2E 테스트와 드리프트](#74-e2e-테스트와-드리프트)
- [8. `notify_full` Job - FULL 결과 Slack 알림](#8-notify_full-job---full-결과-slack-알림)
  - [8.1 역할](#81-역할)
  - [8.2 주요 정보](#82-주요-정보)
- [9. `validate-observability` - 관측 스택 전용 검증 워크플로](#9-validate-observabilityyml---관측-스택-전용-검증-워크플로)
  - [9.1 트리거 조건](#91-트리거-조건)
  - [9.2 수행 내용](#92-수행-내용)
- [10. 전체 아키텍처 요약](#10-전체-아키텍처-요약)
- [11. 결론](#11-결론)


## 1. 개요

이 문서는 Netauto 프로젝트에서 설계, 구현한 **GitHub Actions 기반 CI/CD 파이프라인**의 구조와 동작 원리를 체계적으로 정리한다

아래의 네가지 요소를 중심으로 설명한다
- 네트워크 자동화(Ansible, Containerlab)와 소프트웨어 테스트(Pytest)를 어떻게 CI에 통합했는지
- Prometheus / Grafana / Alertmanager / Slack / GitHub Pages 등 **관측, 알림 체계**를 어떻게 연계했는지
- `netauto.yml`, `validate-observability.yml` 두 워크플로가 어떤 역할을 분담하는지
- 향후 확장이나 개선 시 고려해야 할 설계 포인트


---
## 전체 아키텍처

```text
                       +--------------------------+
                       |          GitHub          |
                       |  (Repo / Actions / Pages)|
                       +--------------------------+
                                    |
                +-------------------+-------------------+
                |                                       |
                v                                       v
        +----------------+                     +-------------------------+
        |  netauto.yml   |                     | validate-observability  |
        |   (Main CI)    |                     |    (Observability CI)   |
        +----------------+                     +-------------------------+
                 |                                         |
      +----------+-----------+                             |
      |          |           |                             |
      v          v           v                             v
+-----------+ +--------+  +---------+         +---------------------------+
|  light    | | publish|  | notify  |         |  checks (observability)   |
| (no lab)  | +--------+  +---+-----+         +---------------------------+
+-----------+     |           |                             |
      |           |           |                             |
      |           |           |          +--------------------------------------+
      |           |           |          |                                      |
      v           |           v          v                                      v
+--------------+  |     +-----------+  +----------------+   +-----------------------+
|  artifacts   |  |     |  Slack    |  | Prometheus     |   |  Prometheus Rules     |
| (junit.xml,  |  |     | (Light)   |  | config lint    |   | check (alert_rules)   |
|  report.md,  |  |     +-----------+  | (promtool cfg) |   +-----------------------+
|  routes.json)|  |                    +----------------+
+--------------+  |                          |
      |           |                          v
      |           v                    +------------------------+
      |    +--------------------+      | Grafana dashboard JSON |
      |    | GitHub Pages       |      | lint (jq netauto-health|
      |    |  - index.html      |      | .json)                 |
      |    |  - docs/report.md  |      +------------------------+
      |    +--------------------+                 |
      |                                           v
      |                                   +--------------------------+
      |                                   | Metrics API contract     |
      |                                   | check (metrics.py        |
      |                                   |  --snapshot, grep check) |
      |                                   +--------------------------+
      |
      v
+--------------+
|    full      |
| (E2E lab:    |
|  containerlab|
|  + Ansible   |
|  + pytest)   |
+------+-------+
       |
       v
+----------------+
|  notify_full   |
|    (Slack)     |
+----------------+

```
### 1.1 GitHub Actions 워크플로 개요

Netauto 프로젝트의 `.github/workflows` 디렉터리 구조는 다음과 같다

```text
.github/
└── workflows
    ├── netauto.yml
    └── validate-observability.yml
```

두 파일의 역할은 다음과 같이 분리된다

- `netauto.yml`  
  - 프로젝트 전체에 대한 메인 CI/CD 파이프라인
  - **Light / Full 모드**를 모두 포함
  - GitHub Pages 배포, Slack 알림, promtool lint 등을 하나의 워크플로에서 수행

- `validate-observability.yml`  
  - 관측 관련 리소스(prometheus, grafana, metrics API)가 변경되었을 때 동작
  - Prometheus 설정/룰 lint, Grafana JSON lint, metrics 스냅샷 계약(Contract) 검증 담당

이를 다이어그램으로 표현하면 아래와 같다

```text
CI / CD 전체 개요

+---------------------------------------------------+
|                  GitHub Actions                   |
|                                                   |
|  +----------------------+   +-------------------+ |
|  |    netauto.yml       |   | validate-obs...   | |
|  | (메인 파이프라인)     |   | (관측 리소스 전용) |  |
|  +----------------------+   +-------------------+ |
|                                                   |
+---------------------------------------------------+
```

---

## 2. `netauto.yml` 워크플로 상세 구조

### 2.1 Netauto GitHub Actions 전체 구조 요약

### Job 파이프라인 도식
![github action flow](https://github.com/ghogho232/netauto/blob/main/images/cicd1_githubaction.png)

```text

.github/workflows/netauto.yml
│
├── 트리거(on:)
│   ├── push(main)
│   ├── pull_request
│   └── workflow_dispatch(LIGHT/FULL)
│
└── jobs:
    ├── light (기본 CI, containerlab 없이 수행)
    ├── publish (GitHub Pages 배포)
    ├── notify (Slack 알림)
    ├── lint (Prometheus promtool)
    ├── full (containerlab E2E 테스트)
    └── notify_full (FULL 결과 Slack 알림)
```
### 2.2 트리거 조건(on)

```yaml
name: netauto

on:
  pull_request:
  push:
    branches: [ main ]
  workflow_dispatch:
    inputs:
      mode:
        description: "CI mode (LIGHT or FULL)"
        required: false
        default: "LIGHT"
        type: choice
        options:
          - LIGHT
          - FULL
```

### 주요 포인트

1. **pull_request**  
   - PR이 생성되거나 업데이트될 때마다 CI가 동작
   - 기본적으로 `light` Job을 통해 코드 변경이 기존 테스트, 템플릿, 스크립트와 충돌하지 않는지 검증

2. **push (main 브랜치)**  
   - main 브랜치에 커밋이 push되면 CI가 자동 실행
   - 이때는 프로젝트의 기준이 되는 브랜치이므로 필요에 따라 `full` Job까지 동작해 **실제 Containerlab E2E**까지 수행

3. **workflow_dispatch (수동 실행)**  
   - GitHub Actions 화면에서 직접 `Run workflow` 버튼을 눌러 실행 가능
   - `mode` 입력 값에 따라 **LIGHT / FULL** 모드를 선택할 수 있어 지금 바로 FULL 테스트를 돌려보고싶을 때 사용 가능

이 트리거 설계는
- PR 단계에서는 빠르게 피드백을 주고  
- main 브랜치에서는 좀 더 무거운 FULL 검증을 수행하며  
- 필요할 때 수동으로 `FULL job`을 강제 실행할 수 있는 **유연한 CI**를 가능하게 함

---

### 2.3 전체 Job 구성 개요

`netauto.yml` 안에는 다음과 같은 Job들을 정의했다

1. `light` : 기본 CI (드리프트 검사 + pytest + 리포트 생성)
2. `publish` : GitHub Pages로 report.md를 배포
3. `notify` : Light 결과를 Slack으로 알림
4. `lint` : Prometheus alert rules를 promtool로 검증
5. `full` : Containerlab 기반 E2E 테스트 포함 FULL CI
6. `notify_full` : Full 결과를 Slack으로 알림


---

## 3. `light` Job - 기본 CI 및 리포트 생성
![light job](https://github.com/ghogho232/netauto/blob/main/images/cicd6_light_log.png)

### 3.1 개요

`light` Job은 Netauto CI의 **핵심 기반**이다  
Containerlab 등 실제 랩 환경 없이 **코드, 스크립트, 템플릿 레벨**에서 다음을 검증한다

- Python 코드가 설치 가능한지(의존성 충족 여부)
- `validate.py`가 의도대로 실행되는지
- `pytest` 기반 테스트가 성공하는지
- `collect_routes.py`, `report.py`가 정상 실행되어 산출물을 생성하는지
- 이 모든 결과를 GitHub Actions Artifact로 잘 업로드하는지

**네트워크 장비 없이도 프로젝트의 논리, 구성이 문제가 없는지**를 확인하는 단계

### 3.2 실행 환경 및 출력 정의

```yaml
light:
  name: CI Light (no lab)
  runs-on: ubuntu-22.04
  outputs:
    drift_status: ${{ steps.drift.outputs.exit_code }}
```

- `runs-on: ubuntu-22.04`  
  - 통일된 리눅스 환경에서 CI를 실행해 환경 편차를 줄임
- `outputs.drift_status`  
  - 이후 `notify` Job에서 drift 결과를 사용하기 위해 step output을 Job output으로 변경

### 3.3 상세 단계별 설명

### 3.3.1 코드 체크아웃

```yaml
- uses: actions/checkout@v4
```

- GitHub Actions 기본 단계
- 저장소 전체를 runner에 가져옴

### 3.3.2 Python 환경 구성

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: "3.12"
```

- Python 3.12 환경을 설치
- 프로젝트가 기대하는 최신 런타임으로 통일

### 3.3.3 의존성 설치

```yaml
python -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

- 독립된 가상 환경을 생성해서 다른 Job과 충돌 없이 패키지 관리
- `requirements.txt` 에 명시된 패키지(fastapi, pytest, jinja2, requests 등) 설치

### 3.3.4 JUnit 출력 디렉터리 준비

```yaml
mkdir -p tests/artifacts
```

- pytest가 `--junitxml` 결과를 기록할 디렉터리 생성
- 경로를 고정해 나중에 Slack, Pages Job에서 공통으로 참조할 수 있게 함

### 3.3.5 드리프트 검사 (validate.py)

```yaml
- name: Run drift check (validate.py)
  env:
    CI_LIGHT: "1"
    NETAUTO_PREFIX: "clab-netauto"
  id: drift
  run: |
    . .venv/bin/activate
    set +e
    python python/validate.py
    CODE=$?
    echo "exit_code=$CODE" >> $GITHUB_OUTPUT
    exit 0
```

- 실제 장비가 없는 Light 모드에서는 `CI_LIGHT=1` 을 통해 스크립트가 안전한 모드로 동작하도록 함
- 스크립트의 종료 코드(CODE)를 Job output으로 노출하지만 CI 자체는 **즉시 실패시키지 않음**
  - `exit 0` 으로 마무리하여 이후 단계(테스트, 리포트 생성)를 계속 진행하게 함
  - 대신 이 결과는 보고, 알림용으로 활용

### 3.3.6 DRIFT_STATUS 환경 변수 전달

```yaml
- name: Export DRIFT_STATUS for report
  run: echo "DRIFT_STATUS=${{ steps.drift.outputs.exit_code }}" >> $GITHUB_ENV
```

- 이후 Python 스크립트 또는 Job 내에서 `os.environ["DRIFT_STATUS"]`같은 방식으로 참조 가능하게 함
- report.py에서 drift 상태를 리포트에 반영할 수 있게함

### 3.3.7 pytest 실행 + 상태 수집 + 리포트 생성

```yaml
- name: Run drift + unit-safe tests (light mode)
  env:
    CI_LIGHT: "1"
    NETAUTO_PREFIX: "clab-netauto"
  run: |
    . .venv/bin/activate
    set +e
    pytest -q --junitxml=tests/artifacts/junit.xml
    TEST_RC=$?
    python python/collect_routes.py || true
    python python/report.py || true
    exit $TEST_RC
```

## 이 단계는 Light Job에서 **가장 중요한 부분**이다

1. pytest로 테스트 실행 + 결과를 junit.xml에 저장
2. collect_routes.py 실행 (실제 라우팅 상태 snapshot 수집)
3. report.py 실행 (docs/report.md 생성)
4. pytest 결과코드(TEST_RC)를 최종 종료 코드로 사용

### 설계 포인트

- **드리프트 유무는 CI 실패 사유가 아님**  
  - 환경 변화, 랩 상태에 따라 drift가 발생해도 기본적으로 pytest를 신뢰함
- **테스트 실패는 CI 실패 사유**  
  - 네트워크 연결, OSPF neighbor, 라우팅 테이블 등이 기대와 다르면 워크플로를 실패로 표시

### 3.3.8 아티팩트 업로드

```yaml
- name: Upload artifacts
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: netauto-artifacts-light
    path: |
      tests/artifacts/**
      docs/report.md
      python/out/**
```

- `if: always()` 로 설정하여 테스트가 실패했더라도 산출물을 반드시 업로드
- 이후 Job (`publish`, `notify`)에서 동일 artifact 이름으로 다운로드해 활용

### 3.3.9 결과물
### artifacts/junit.xml
![test_junit](https://github.com/ghogho232/netauto/blob/main/images/cicd5_light_test_junit.png)
### report.md
![report](https://github.com/ghogho232/netauto/blob/main/images/cicd2_light_report.png)
### python/out/route.json
![route](https://github.com/ghogho232/netauto/blob/main/images/cicd3_light_route_json.png)

---

## 4. `publish` Job - GitHub Pages 배포

### 4.1 의존 관계 및 권한

```yaml
publish:
  needs: light
  permissions:
    pages: write
    id-token: write
    contents: read
```

- 반드시 Light Job 이후에 실행되는 구조 (`needs: light`)
- Pages 배포에 필요한 권한을 명시적으로 선언

### 4.2 단계별 설명

1. **아티팩트 다운로드**  
   - `netauto-artifacts-light` 를 `site/` 디렉터리로 전개
2. **파일 구조 확인**  
   - `find` 명령으로 구조 출력 -> 디버깅 용이
3. **report.md 존재 검증**  
   - 없으면 CI 실패 처리 -> GitHub Pages가 깨진 링크를 노출하지 않도록 방지
4. **index.html 생성**  
   - 루트에서 docs/report.md로 링크를 제공
5. **Configure Pages 및 deploy**  
   - `actions/configure-pages` 와 `upload-pages-artifact`, `deploy-pages` 를 조합해 자동 배포
6. **최종 URL 출력**  
   - `https://{OWNER}.github.io/{REPO}/` 형식으로 완성 URL을 콘솔에 남김

이 Job으로 Netauto는 **테스트 결과를 GitHub Pages로 자동 공개**하는 CI + 자동 문서 배포 구조를 완성

![publish_log](https://github.com/ghogho232/netauto/blob/main/images/cicd7_publish_log.png)

![publish_report](https://github.com/ghogho232/netauto/blob/main/images/cicd8_publish_report.png)

이 주소에서 확인 가능
https://ghogho232.github.io/netauto/docs/report.md

---

## 5. `notify` Job - Slack 알림 (Light 결과)

### 5.1 역할

`notify` Job은 Light Job의 결과를 Slack으로 전달하는 역할 

- 테스트 요약 (총 테스트, 통과, 실패, 스킵)
- Drift 상태 (0: 정상, 그 외: 이상)

### 5.2 JUnit 요약 파싱

```bash
python - <<'PY'
import xml.etree.ElementTree as ET, pathlib, os
p = pathlib.Path("artifacts/tests/artifacts/junit.xml")
...
PY
```

- junit.xml을 직접 파싱하여 tests, failures, errors, skipped를 누적 계산
- passed = tests - failures - errors - skipped 로 도출
- 이 값을 `GITHUB_OUTPUT` 에 기록해 다음 step에서 `steps.junit.outputs.*` 로 사용

### 5.3 Slack 메시지 구성

```bash
STATUS_COLOR="good"
[ "${DRIFT_STATUS}" != "0" ] && STATUS_COLOR="#E01E5A"
PAGES_URL="https://${OWNER}.github.io/${REPO}/docs/report.md"
```

- Drift 발생 여부에 따라 알림 색상을 변경
- GitHub Pages의 최신 리포트 링크를 포함시켜 Slack에서 바로 상세 리포트로 이동 가능하게 함

Payload 예시:

```json
{
  "text": "Netauto CI Result",
  "attachments": [
    {
      "color": "#E01E5A",
      "fields": [
        { "title": "Branch", "value": "main", "short": true },
        { "title": "Commit", "value": "abc1234", "short": true },
        { "title": "Drift", "value": "1", "short": true },
        { "title": "Pytest", "value": "Passed: 5, Failed: 1, Skipped: 0", "short": true },
        { "title": "Report", "value": "<https://OWNER.github.io/REPO/docs/report.md|Open Latest Report>", "short": false }
      ]
    }
  ]
}
```
![light_slack](https://github.com/ghogho232/netauto/blob/main/images/cicd9_light_slack.png)

이 설계로 운영자는 **Slack만 보고도 현재 CI 상태를 빠르게 인지**할 수 있음

---

## 6. `lint` Job - Prometheus Rules 정적 검사

### 6.1 역할

`lint` Job은 Netauto 프로젝트의 **관측 설정의 안전성**을 미리 검증  

주요 포인트:
- Prometheus alert rule이 문법적으로 올바른지
- 오류가 있을 경우 실제 프로덕션 환경의 Prometheus가 기동 실패하는 사태를 미리 방지

### 6.2 수행 내용

```yaml
- name: Install promtool
  run: |
    curl -L -o promtool.tgz https://github.com/prometheus/prometheus/...
    tar xf promtool.tgz
    sudo mv prometheus-*/promtool /usr/local/bin/promtool

- name: Validate alert rules
  run: promtool check rules prom/alert_rules.yml
```

- promtool을 직접 다운로드해 설치
- `prom/alert_rules.yml`에 정의된 Netauto용 알람 룰을 체크

이 Job은 관측 스택과 밀접하게 관련되어 있지만 실제 alertmanager나 Slack 연동과는 독립적인 **정적 안전망** 역할을 함

---

## 7. `full` Job - Containerlab 기반 E2E CI

### 7.1 역할

`full` Job은 Netauto 프로젝트의 **가장 무거운 Job**으로 **실제 랩 환경을 띄워서** 수행하는 E2E 테스트

조건

```yaml
needs: light
if: |
  github.event_name == 'workflow_dispatch' && github.event.inputs.mode == 'FULL' ||
  (github.event_name == 'push' && github.ref == 'refs/heads/main')
```

- Light Job이 성공적이든 실패했든 논리적으로는 항상 그 이후에 위치
- **main 브랜치 push 또는 수동 실행 + FULL** 선택 시에만 수행

### 7.2 수행 내용

1. 코드 체크아웃  
2. Python 환경 구성 및 의존성 설치  
3. **Containerlab 설치** 및 netauto 토폴로지 배포  
4. Ansible site.yml 실행 (라우터 설정·검증)  
5. validate.py 실행 (실제 환경에서 드리프트 감지)  
6. pytest E2E 테스트 (OSPF, ping, drift 등)  
7. 라우팅 snapshot 수집 (collect_routes.py)  
8. report.py 실행으로 E2E 기준 report 생성  
9. 아티팩트 업로드  
10. containerlab destroy (성공/실패와 무관하게 항상 실행)

### 7.3 Ansible 결합

```yaml
cd ansible
ansible-playbook -i inventory.ini site.yml
```

- FRR 및 네트워크 인터페이스 설정을 선언으로 적용
- OSPF 프로세스, 인터페이스, IP 주소, neighbor 설정이 재현가능하게 관리됨

### 7.4 E2E 테스트와 드리프트

- Drift check는 여기서도 CI를 바로 깨지 않고 DRIFT_STATUS 파일에 코드만 남김
- pytest는 실제 네트워크 상의 OSPF Neighbor, 라우팅, ping 결과 기반으로 성공/실패를 판정
- FULL junit 결과는 `junit-full.xml`로 별도 보관해 Light와 구분되는 E2E 메트릭을 제공

### 7.5 전체 실행 과정
![full_log](https://github.com/ghogho232/netauto/blob/main/images/cicd10_full_log.png)


### 7.6 결과물
### artifacts/junit.xml
![test_junit](https://github.com/ghogho232/netauto/blob/main/images/cicd13_full_test_junit.png)

### report.md
![report](https://github.com/ghogho232/netauto/blob/main/images/cicd11_full_report1.png)
![report](https://github.com/ghogho232/netauto/blob/main/images/cicd11_full_report2.png)

### python/out/route.json
![route](https://github.com/ghogho232/netauto/blob/main/images/cicd12_full_route_json.png)

---

## 8. `notify_full` Job - FULL 결과 Slack 알림

### 8.1 역할

`notify_full` Job은 `full` Job의 결과를 Slack으로 통보
- `needs: full` 속성으로 FULL 이후에 실행
- `if: always() && needs.full.result != 'skipped'`  
  -> FULL Job이 실패하더라도 알림은 반드시 보냄

### 8.2 주요 정보

Slack 메시지에는 다음 정보가 포함됨

- FULL Job 전체 상태(success / failure)
- E2E pytest 결과 (tests, passed, failed, skipped)
- Drift 상태(status)
- report 링크 (GitHub Pages)


이로써 운영자는 **정상적인 CI Light 결과와 실제 랩 환경에서의 FULL 결과를 각각 구분**하여 모니터링할 수 있음

![full_slack](https://github.com/ghogho232/netauto/blob/main/images/cicd14_full_slack.png)

---

## 9. `validate-observability.yml` - 관측 스택 전용 검증 워크플로

### 9.1 트리거 조건

```yaml
on:
  push:
    paths:
      - "prom/**"
      - "grafana/**"
      - "python/api/**"
      - "docs/**"
  pull_request:
```

관측 관련 디렉터리(prom, grafana, api, docs)에 변경이 있을 때만 동작함

이는 다음과 같은 의미를 가짐
- Prometheus 설정, 대시보드, metrics API, 문서 등 **관측과 관련된 변경**이 실제 환경을 깨뜨리지 않도록 별도 검증을 수행

### 9.2 수행 내용

### 9.2.1 Prometheus config check

```bash
promtool check config prom/prometheus.yml
```

- Prometheus 메인 설정 파일 문법 검사

### 9.2.2 Prometheus rules check

```bash
promtool check rules prom/alert_rules.yml
```

- 경고, 알람 룰, 문법 검사

### 9.2.3 Grafana dashboard JSON lint

```bash
jq . grafana/dashboards/netauto-health.json > /dev/null
```

- JSON 형식이 깨지지 않았는지 검사

### 9.2.4 Metrics contract check

```bash
python3 python/api/metrics.py --snapshot
grep -q '^netauto_status ' docs/metrics.txt
grep -q '^netauto_drift_config ' docs/metrics.txt
grep -q 'netauto_neighbors{state="full"}' docs/metrics.txt
grep -q '^netauto_routes_total ' docs/metrics.txt
grep -q 'netauto_tests_count{type="failed"}' docs/metrics.txt
```

- metrics.py에 `--snapshot` 옵션을 주어 `docs/metrics.txt`로 메트릭 텍스트 출력
- 그 안에 **필수 메트릭**들이 모두 존재하는지 grep으로 확인
  - netauto_status
  - netauto_drift_config
  - netauto_neighbors{state="full"}
  - netauto_routes_total
  - netauto_tests_count{type="failed"}

이렇게 함으로 누군가 실수로 메트릭 이름을 바꾸거나 제거했을 때 관측 스택이 깨지는 것을 미리 잡아낼 수 있음 
이는 일종의 **Observability Contract Test**라고 할 수 있음

---

## 10. 전체 아키텍처 요약

Netauto CI/CD 및 관측 전체를 하나의 그림으로 표현하면 아래와 같다

```text
                       +--------------------------+
                       |          GitHub          |
                       |  (Repo / Actions / Pages)|
                       +--------------------------+
                                    |
                +-------------------+-------------------+
                |                                       |
                v                                       v
        +----------------+                     +-------------------------+
        |  netauto.yml   |                     | validate-observability  |
        |   (Main CI)    |                     |    (Observability CI)   |
        +----------------+                     +-------------------------+
                 |                                         |
      +----------+-----------+                             |
      |          |           |                             |
      v          v           v                             v
+-----------+ +--------+  +---------+         +---------------------------+
|  light    | | publish|  | notify  |         |  checks (observability)   |
| (no lab)  | +--------+  +---+-----+         +---------------------------+
+-----------+     |           |                             |
      |           |           |                             |
      |           |           |          +--------------------------------------+
      |           |           |          |                                      |
      v           |           v          v                                      v
+--------------+  |     +-----------+  +----------------+   +-----------------------+
|  artifacts   |  |     |  Slack    |  | Prometheus     |   |  Prometheus Rules     |
| (junit.xml,  |  |     | (Light)   |  | config lint    |   | check (alert_rules)   |
|  report.md,  |  |     +-----------+  | (promtool cfg) |   +-----------------------+
|  routes.json)|  |                    +----------------+
+--------------+  |                          |
      |           |                          v
      |           v                    +------------------------+
      |    +--------------------+      | Grafana dashboard JSON |
      |    | GitHub Pages       |      | lint (jq netauto-health|
      |    |  - index.html      |      | .json)                 |
      |    |  - docs/report.md  |      +------------------------+
      |    +--------------------+                 |
      |                                           v
      |                                   +--------------------------+
      |                                   | Metrics API contract     |
      |                                   | check (metrics.py        |
      |                                   |  --snapshot, grep check) |
      |                                   +--------------------------+
      |
      v
+--------------+
|    full      |
| (E2E lab:    |
|  containerlab|
|  + Ansible   |
|  + pytest)   |
+------+-------+
       |
       v
+----------------+
|  notify_full   |
|    (Slack)     |
+----------------+

```

이 다이어그램에서 볼 수 있듯이
- Light / Full CI는 GitHub Actions 상에서 수행되고
- 결과물은 GitHub Pages / Slack / 관측 스택(Prometheus / Grafana / Alertmanager)과 연결됨
- validate-observability는 별도의 보호 레이어로 관측 스택 변경 시 최소한의 안전망 역할

---

## 11. 결론

지금까지 Netauto 프로젝트의 GitHub Actions CI/CD 구조를 중심으로
- Light/Full 파이프라인의 상호 관계
- GitHub Pages를 통한 리포트 자동 배포
- Slack을 통한 즉각적인 피드백
- Prometheus/Grafana/Alertmanager를 고려한 관측 스택 검증
- metrics contract를 통한 API, 메트릭 호환성 보호

등에 대해 설명했다

이 설계의 핵심은 다음과 같다

1. **재현성** - 코드 변경부터 네트워크 구성, 테스트, 리포트, 알람까지 모두 코드로 정의를 통해 어떤 환경에서도 코드를 이용하면 실행 가능
2. **가시성** - health API, metrics, report, 대시보드, Slack 알림으로 여러 서비스에서 상태를 시각적으로 파악 가능
3. **확장성** - Containerlab, Ansible, FastAPI, Prometheus, GitHub Actions라는 오픈소스 기술 조합으로 향후 확장이 쉬움

Netauto CI/CD는 네트워크 장비도 소프트웨어처럼 다루는 NetDevOps 철학을  
실제 구현해보았으며 이후에 보다 복잡한 토폴로지, 프로토콜, 보안 정책도 이 구조 위에서 확장할 수 있을 것으로 생각한다
