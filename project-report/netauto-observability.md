# Observability - Prometheus · Grafana · Alertmanager · Slack 

## 목차 (Table of Contents)

- [1. 개요](#1-개요)
- [2. Observability 전체 아키텍처](#2-observability-전체-아키텍처)
- [3. Prometheus 구성](#3-prometheus-구성)
- [4. Recording Rules](#4-recording-rules)
- [5. Grafana 대시보드 구성](#5-grafana-대시보드-구성)
  - [5.1 디렉터리 구조](#51-디렉터리-구조)
  - [5.2 Netauto — Health & Observability 대시보드](#52-netauto---health--observability-대시보드-netauto-healthjson)
  - [5.3 Netauto 기본 대시보드](#53-netauto-기본-대시보드-netautojson)
- [6. Alertmanager 구성](#6-alertmanager-구성)
  - [6.1 Prometheus Alert Rules](#61-prometheus-alert-rules-promalert_rulesyml)
  - [6.2 Alertmanager → Slack 연동](#62-alertmanager---slack-연동-promalertmanageryml)
  - [6.3 Grafana Alert → Alertmanager 연동](#63-grafana-alert---alertmanager-연동)
  - [6.4 Netauto Alert Pipeline 요약](#64-netauto-alert-pipeline-요약-다이어그램)
  - [6.5 이 구성을 통해 얻는 효과](#65-이-구성을-통해-얻는-효과)
- [7. 전체 Observability 흐름](#7-전체-observability-흐름)
  - [7.1 R1/R2/H1/H2 metrics export](#71-r1r2h1h2-metrics-export)
  - [7.2 Prometheus — scrape 단계](#72-prometheus---수집scrape-단계)
  - [7.3 Recording / Query 단계](#73-recording--query---비율-계산-및-파생-메트릭-생성)
  - [7.4 Grafana — 시각화 단계](#74-grafana---시각화-및-1차-해석-단계)
  - [7.5 Alert Evaluation 단계](#75-grafana--prometheus-alert-evaluation---조건-평가-레이어)
  - [7.6 Alertmanager — 알람 집계 및 라우팅](#76-alertmanager---알람-집계-및-라우팅)
  - [7.7 Slack — 운영자 시점](#77-slack---운영자-시점)
  - [7.8 흐름 요약](#78-흐름-요약)
- [8. TLS/HTTPS 인증서 트러블슈팅](#8-tlshttps-인증서-트러블슈팅)
- [9. Observability 문제 분석 및 해결](#9-observability-문제-상세-분석-및-해결-과정)
- [10. 결론](#10-결론)

## 1. 개요

Prometheus, Grafana, Alertmanager, Slack을 통합해
네트워크 상태 수집 -> 시각화 -> 이상 감지 -> 실시간 알림까지 전체 흐름을 자동화해 네트워크 내 이상상태를 빠르게 감지하고 대처할 수 있게 함

이 문서에서 다루는 내용 

- Prometheus: Metrics 수집 및 Recording Rule 처리
- Grafana: Dashboard 시각화 및 패널 구성
- Alertmanager: 경보 라우팅
- Slack 연동: 운영 알람 실시간 전송
- 트러블 슈팅

## 2. Observability 전체 아키텍처

```
Containerlab 노드(FRR 라우터·호스트)
         |
         | (1) Metrics Export
         v
     Prometheus
         |
         | (2) Recording Rules / Query
         v
      Grafana
         |
         | (3) Alert Evaluation
         v
   Alertmanager
         |
         | (4) Slack Webhook
         v
       Slack
```

## 3. Prometheus 구성

Prometheus는 다음을 스크레이프한다

- Netauto FastAPI Exporter (커스텀 지표)

### 구성 예시: prometheus.yml

```yaml
scrape_configs:
  - job_name: "netauto-api"
    metrics_path: /metrics
    static_configs:
      - targets: ["netauto-api:8000"]
        labels:
          env: "dev"
          topo: "ospf-mini"
```
### 구성 설명
| 항목                       | 설명                                                                 |
| ------------------------ | ------------------------------------------------------------------ |
| `scrape_interval: 15s`   | 15초마다 /metric 를 스크레이프                                             |
| `rule_files:`            | Recording Rules + Alerts(= alert_rules.yml) 로드                     |
| `alertmanagers:`         | alertmanager 서비스로 알람 전달 (Docker Compose 네트워크 기준 서비스명 alertmanager) |
| `job_name: netauto-api`  | Netauto FastAPI Exporter를 수집하는 Job                                 |
| `metrics_path: /metrics` | FastAPI Exporter에서 제공하는 지표 엔드포인트                                   |
| `labels: env/topo`       | 모든 지표에 env=dev, topo=ospf-mini 라벨을 자동 추가                           |

## Netauto Custom Metrics

Netauto의 /metrics 엔드포인트는 아래 핵심 4단계 로직으로 구성된다

### 1. 상태 파일 로딩
health.json, routes.json, junit.xml, drift.json을 읽어 실제 장비/테스트/라우팅 상태를 수집

### 2. 지표 계산

- 전체 상태(status)
- OSPF neighbor(full/total)
- 전체 route 수
- pytest 결과(total/passed/failed/skipped)
- drift 감지 여부
- 노드별 route/neighbor 메트릭(r1/r2 등)

### 3. Prometheus 텍스트 포맷 문자열 생성
- Prometheus 규격에 맞는 #HELP, #TYPE, metric value 형태로 직접 문자열을 생성

### 4. FastAPI의 /metrics 라우터에서 반환
- Prometheus는 이 문자열을 그대로 스크레이프함.

### metrics api 예시 metrics.py
```python
router = APIRouter()
TOPOLOGY = "ospf-mini"

@router.get("/metrics")
def metrics():
    return Response(
        render_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )

def render_metrics() -> str:
    # 1) 상태 파일 수집
    health = load_health_json()
    junit = parse_junit()
    routes = load_routes_json()
    drift = load_drift_status()

    # 2) 필요한 핵심 수치 계산
    status = 1 if health.get("status") == "ok" else 0
    full   = int(health.get("neighbors", {}).get("full", 0))
    total  = int(health.get("neighbors", {}).get("total", 0))

    routes_total = int(routes.get("routes_total", 0))

    tests_total = junit["tests"]    or 0
    failed      = junit["failures"] or 0
    skipped     = junit["skipped"]  or 0
    passed      = max(tests_total - failed, 0)

    # 3) Prometheus 텍스트 포맷 조립
    lines = []

    lines.append(f"netauto_status {status}")
    lines.append(f'netauto_neighbors{{state="full"}} {full}')
    lines.append(f'netauto_neighbors{{state="total"}} {total}')
    lines.append(f"netauto_routes_total {routes_total}")
    lines.append(f'netauto_tests_count{{type="total"}} {tests_total}')
    lines.append(f'netauto_tests_count{{type="passed"}} {passed}')
    lines.append(f'netauto_tests_count{{type="failed"}} {failed}')
    lines.append(f'netauto_tests_count{{type="skipped"}} {skipped}')
    lines.append(f"netauto_drift_config {1 if drift else 0}")

    # 4) 노드별 메트릭 (있을 때만)
    for node, vals in health.get("nodes", {}).items():
        lines.append(f'netauto_node_routes{{node="{node}"}} {vals.get("routes",0)}')
        lines.append(f'netauto_node_neighbors{{node="{node}",state="full"}} {vals.get("full",0)}')
        lines.append(f'netauto_node_neighbors{{node="{node}",state="total"}} {vals.get("neigh_all",0)}')

    return "\n".join(lines) + "\n"
```
## 4. Recording Rules

`prom/alert_rules.yml` 에서는 원시 메트릭을 그대로 쓰지 않고,  
대시보드/알람에서 바로 쓸 수 있는 **비율(0~1)** 형태의 Recording Rule 을 미리 만들어 둔다.

```yaml
groups:
  - name: netauto-recording
    rules:
      # 1) 전체 토폴로지 기준 OSPF 이웃 수용률 (0~1)
      - record: netauto_neighbors_ratio
        expr: clamp_max(
                clamp_min(
                  sum(netauto_neighbors{state="full"}) /
                  clamp_min(sum(netauto_neighbors{state="total"}), 1),
                0),
              1)

      # 2) 노드별 OSPF 이웃 수용률 (0~1)
      - record: netauto_node_neighbors_ratio
        expr: clamp_max(
                clamp_min(
                  netauto_neighbors{state="full"} /
                  ignoring(state) clamp_min(netauto_neighbors{state="total"}, 1),
                0),
              1)

      # 3) 테스트 통과율 (0~1)
      - record: netauto_tests_pass_ratio
        expr: clamp_max(
                clamp_min(
                  netauto_tests_count{type="passed"} /
                  ignoring(type) clamp_min(netauto_tests_count{type="total"}, 1),
                0),
              1)
  ```
## 주요 포인트

- `sum(netauto_neighbors{state="full"}) / sum(netauto_neighbors{state="total"})`
-> 전체에서 현재 이웃  / 기대 이웃  비율을 계산

- `netauto_neighbors{state="full"} / ignoring(state) netauto_neighbors{state="total"}`
-> 각 노드별로 자기 이웃 수용률을 계산하기 위해 state 라벨을 무시하고 매칭

- `netauto_tests_count{type="passed"} / ignoring(type) netauto_tests_count{type="total"}`
-> 통과한 테스트 개수 / 전체 테스트 개수 로 테스트 통과율 계산

- `clamp_min(X, 1)`
-> 분모가 0이 되는 상황(메트릭 누락 등)을 피하기 위해 최소 1로 고정해 나누기 에러를 방지함

- `clamp_min(..., 0) / clamp_max(..., 1)`
-> 계산/스크레이프 문제로 인한 이상치가 나오는 걸 막고
최종 결과를 항상 0~1 범위로 강제해서
Grafana 게이지/퍼센트 표현이나 Alert 조건에 그대로 사용할 수 있게 함

## 5. Grafana 대시보드 구성

Grafana의 **프로비저닝 기능**을 사용해, 컨테이너가 올라가면 자동으로 **데이터소스, 대시보드, 알림 설정**이 로드되도록 한다

---

### **5.1 디렉터리 구조**

```text
grafana/
  dashboards/
    netauto-health.json      # Netauto 헬스 전용 메인 대시보드
    netauto.json             # 최소 상태 확인용 기본 대시보드

  provisioning/
    datasources/
      datasource.yml         # Prometheus 데이터소스 정의 (uid=prometheus)
    dashboards/
      dashboard.yml          # /var/lib/grafana/dashboards 자동 로드 설정
    alerting/
      contactpoints.yaml     # Alertmanager 연동용 Contact Point
      policies.yaml          # 기본 Alert 라우팅 정책
      rules.yml              # Grafana Alert Rule 정의 (netauto 전용)
```

---

### **datasource.yml**

- **이름:** Prometheus  
- **uid:** `prometheus`  
- **URL:** `http://prometheus:9090`  
- **isDefault: true** -> 모든 패널이 기본적으로 이 데이터소스를 사용

---

### **dashboard.yml**

- **이름:** Netauto Dashboards  
- **options.path:** `/var/lib/grafana/dashboards`  
- 컨테이너 기동 시 `netauto-health.json`, `netauto.json` 등이 자동 Import됨

---

### **alerting/contactpoints.yaml · policies.yaml · rules.yml**

- Grafana Alert를 **Prometheus Alertmanager(`http://alertmanager:9093`)** 로 전달  
- 주요 Netauto Alert Rules:
  - `NetautoStatusDegraded`
  - `NetautoDriftDetected`
  - `NetautoTestsFailing`
- 공통 레이블 사용:
  - `severity`, `topo`, `env`
- `runbook_url` 제공 -> 대시보드 알람 테이블에서 Runbook 링크로 표시됨

---

## **5.2 Netauto - Health & Observability 대시보드 (`netauto-health.json`)**

- **uid:** `prometheus`
- **제목:** *Netauto - Health & Observability*
- 총 **4개의 섹션**으로 구성

---

## **1) Health Summary (요약 패널)**

### **Overall Status (`expr: netauto_status`)**

- 0 -> **degraded**  
- 1 -> **ok**  
- Netauto 전체 헬스 상태를 단일 패널에서 직관적으로 확인

---

### **Config Drift (`expr: netauto_drift_config`)**

- 0 -> **clean**  
- 1 이상 -> **drift**  
- 템플릿과 실제 장비 설정의 **불일치 여부 확인**

---

### **Neighbors Full Ratio (`expr: netauto_neighbors_ratio`)**

- Recording Rule 기반 **0~1 비율**
- 단위: `percentunit`
- 임계값:
  - `< 0.99` -> yellow
  - `= 1` -> green
- 전체 OSPF neighbor 정상 수립 여부 판단

---

### **Routes (Total) (`expr: netauto_routes_total`)**

- 현재 라우팅 테이블의 전체 라우트 수를 단일 값으로 표시  
- 예상 라우트 수 대비 정상 여부 확인 가능

---

## **2) Time Series (시계열 패널)**

### **Overall Status (timeline)**  
- 시간에 따른 OK/Degraded 변화 표시

---

### **Neighbors: Full vs Total**
```promql
netauto_neighbors{state="full"}
netauto_neighbors{state="total"}
```
- Full vs Total 비교  
- OSPF flap 여부 추적 가능

---

### **Routes Total**  
`expr: netauto_routes_total`

- 라우트 수 변화량 확인 가능  
- 재설정/변경 작업 검증에 유용

---

### **Tests: Passed / Failed / Total**
```promql
netauto_tests_count{type="passed"}
netauto_tests_count{type="failed"}
netauto_tests_count{type="total"}
```
- 테스트 결과의 시계열 변화  
- 실패 급증 시점 파악 가능

---

## **3) Quality Ratios (게이지 패널)**

### **Tests Pass Ratio (`expr: netauto_tests_pass_ratio`)**

- Recording Rule 기반 0~1 비율
- 임계값:

| 범위 | 색상 |
|------|------|
| 0 ~ 0.95 | 빨간색 |
| 0.95 ~ 0.99 | 노란색 |
| 0.99 ~ 1 | 초록색 |

- 회귀 테스트 안정성 평가

---

### **Neighbors Full Ratio (5m avg)**  
`expr: avg_over_time(netauto_neighbors_ratio[5m:])`

- 순간적 flap 잡음 감소  
- 단기 안정성 평가

---

## **4) Alert 모니터링**

### **Firing Alerts (`expr: sum(ALERTS{alertstate="firing"})`)**

- 현재 발화 중인 Alert의 전체 개수를 표시  
- 1개 이상이면 빨간색으로 표시되도록 구성

---

### **Firing Alerts (live)**  
`expr: ALERTS{alertstate="firing"}`

표시되는 컬럼:

- alertname  
- severity (critical / warning 색상 구분)  
- instance  
- topo  
- env  
- value  
- **runbook_url -> 클릭 시 Runbook 문서 열림**

Prometheus Alert + Grafana Alert 규칙 모두 반영된 실시간 테이블이다.

---

## **5.3 Netauto 기본 대시보드 (`netauto.json`)**

### **Netauto API /metrics scrape OK**

쿼리:

```promql
up{job="prometheus"} or up
```

- Prometheus 및 타 scrape 대상이 올바르게 동작하는지 확인  
- 문제 발생 시 **데이터 수집 경로 문제**부터 점검 가능

---

## **종합 정리**

이 Grafana 구성은 다음을 한 화면에서 종합적으로 보여준다:

- **전체 상태 (Overall Status)**
- **설정 드리프트 (Config Drift)**
- **OSPF Neighbor 품질**
- **라우팅 테이블 건전성**
- **테스트 통계 및 품질**
- **Alert 상태 + Runbook 링크**

운영 환경과 동일한 **장애 대응 플로우**를 제공하며,  
Netauto의 상태/테스트/관측·경고 체계를 완전하게 통합하여 시각화한다.



## 6. Alertmanager 구성

Netauto 프로젝트에서는 **Prometheus Alert Rules -> Alertmanager -> Slack -> Grafana** 로 연결되는 알림 파이프라인을 구축해서 다음과 같은 이상 상태를 Slack 채널에서 파악할 수 있도록 했음

- OSPF Neighbor Down (OSPF adjacency 수립 실패)
- Config Drift(의도된 설정 vs 실제 장비 설정 불일치)
- 테스트 실패(Pytest 실패)
- 전체 상태 이상(Netauto Health status)
- 장기적 Degraded 상태 유지
- Grafana 자체 알림(Grafana Alerting)

이 문서는 기존 설정 전체를 기반으로 **더 자세하고, 구조적이며, 설명 중심의 확장 버전**이다.

---

### 6.1 Prometheus Alert Rules (`prom/alert_rules.yml`)

Prometheus에서는 Recording Rule과 Alert Rule을 함께 정의해서 
대시보드, 알림에서 공용으로 쓰는 메트릭을 생성하고 조건에 따라 Alert를 발생시킴

---

### 6.1.1 Recording Rules - 비율 및 상태 값 계산

Recording Rules는 **미리 계산된 정규화 지표(0~1 비율값)** 를 생성하여  
Grafana 대시보드 및 Alert Rule에서 공통으로 활용된다

### Recording Rule

```yaml
groups:
  - name: netauto-recording
    rules:
      # 전체 토폴로지 기준 OSPF Neighbor 수용률 (0~1)
      - record: netauto_neighbors_ratio
        expr: clamp_max(
                clamp_min(
                  sum(netauto_neighbors{state="full"}) /
                  clamp_min(sum(netauto_neighbors{state="total"}), 1),
                0),
              1)

      # Pytest 통과율 (0~1)
      - record: netauto_tests_pass_ratio
        expr: clamp_max(
                clamp_min(
                  netauto_tests_count{type="passed"} /
                  ignoring(type) clamp_min(netauto_tests_count{type="total"}, 1),
                0),
              1)
```


#### `netauto_neighbors_ratio`
- **표현식**  
  full neighbor 개수 / total neighbor 개수
- 값 범위 강제: clamp_min / clamp_max 사용해 0~1로 제한
- 활용:
  - OSPF Neighbor 상태 모니터링
  - Gauge 형태로 표시(Grafana)
  - Neighbor Down Alert Rule 조건으로 사용

#### `netauto_tests_pass_ratio`
- 통과된 테스트 수 / 전체 테스트 수
- 회귀 테스트 안정성을 수치화할 때 사용
- CI 파이프라인 품질 판단의 핵심 지표

---

## 6.1.2 Alert Rules - Netauto 기능 기반 알람 정의

Netauto는 4개의 핵심 Alert를 Prometheus에서 생성한다

### Alert Rule

```yaml
groups:
  - name: netauto-alerts
    rules:
      - alert: NetautoStatusDegraded
        expr: netauto_status == 0
        for: 1m
        labels:
          severity: critical
          runbook_url: "https://github.com/ghogho232/netauto/blob/main/docs/runbooks/status.md"
        annotations:
          summary: "Overall status degraded"
          description: "/health 판정이 degraded입니다."

      - alert: NetautoDriftDetected
        expr: netauto_drift_config > 0
        for: 1m
        labels:
          severity: warning
          runbook_url: "https://github.com/ghogho232/netauto/blob/main/docs/runbooks/drift.md"
        annotations:
          summary: "Config drift detected"
          description: "validate.py가 드리프트를 감지했습니다."

      - alert: NetautoTestsFailing
        expr: netauto_tests_count{type="failed"} > 0
        for: 1m
        labels:
          severity: critical
          runbook_url: "https://github.com/ghogho232/netauto/blob/main/docs/runbooks/tests.md"
        annotations:
          summary: "Pytest failures"
          description: "하나 이상의 테스트가 실패했습니다."

  - name: netauto-health
    rules:
      - alert: NetautoDegraded
        expr: netauto_status == 0
        for: 2m
        labels:
          severity: warning
          team: netops
        annotations:
          summary: "Netauto degraded"
          description: "Netauto health status가 2분 이상 degraded 상태입니다."
```

---


### 1) NetautoStatusDegraded
- **조건:** `netauto_status == 0`
- **지속:** 1m
- Netauto 전체 시스템이 degraded로 판정됨

### 2) NetautoDriftDetected
- **조건:** `netauto_drift_config > 0`
- 템플릿과 장비 실제 설정 간 Drift 발생

### 3) NetautoTestsFailing
- **조건:** pytest 실패 1건 이상 발생
- CI 안정성 즉시 확인 가능

### 4) NetautoDegraded
- 2분 이상 degraded 유지 -> netops 팀에게 경고(slack)

---

## 6.2 Alertmanager -> Slack 연동 (`prom/alertmanager.yml`)

Alertmanager는 Prometheus Alert를 받아 Slack Webhook으로 전송

Netauto는 Alert 정보를 Slack 메시지로 변환한다

---

## 6.2.1 Alertmanager 

```yaml
global:
  resolve_timeout: 5m

route:
  receiver: slack
  group_by: ['alertname','instance','severity']
  group_wait: 15s
  group_interval: 2m
  repeat_interval: 1h

receivers:
  - name: slack
    slack_configs:
      - api_url_file: /run/secrets/slack_webhook_url
        channel: "#netauto-ci"
        username: "alertmanager"
        send_resolved: true
        color: '{{ if eq .Status "firing" }}danger{{ else }}good{{ end }}'
        title: '[Netauto] {{ .CommonLabels.alertname }} ({{ .Status }})'
        text: >-
          {{- range .Alerts }}
          *Alert:* {{ .Labels.alertname }} ({{ .Status }})
          *Instance:* {{ .Labels.instance }}
          *Severity:* {{ if .Labels.severity }}{{ .Labels.severity }}{{ else }}n/a{{ end }}
          *Summary:* {{ if .Annotations.summary }}{{ .Annotations.summary }}{{ else }}n/a{{ end }}
          *Description:* {{ if .Annotations.description }}{{ .Annotations.description }}{{ else }}n/a{{ end }}
          *Started:* {{ .StartsAt }}
          *Runbook:* {{ if .Labels.runbook_url }}{{ .Labels.runbook_url }}{{ else }}(none){{ end }}
          *Labels:* {{ .Labels }}

          {{- end }}
```

---

## 6.2.2 Slack 전송 템플릿 상세 설명

### 색상(color)
```gotemplate
'{{ if eq .Status "firing" }}danger{{ else }}good{{ end }}'
```
- firing -> 빨간색(danger)
- resolved -> 초록색(good)

### 제목(title)
```
[Netauto] {{ .CommonLabels.alertname }} ({{ .Status }})
```
예:  
`[Netauto] NetautoDriftDetected (firing)`

### 본문(text)
각 Alert에 대해 반복 출력

- Alert 이름
- Instance
- Severity
- Summary
- Description
- StartedAt
- Runbook URL
- 모든 Labels Dump

운영자가 장애 상황을 10초 내로 파악하도록 설계된 메시지 구조.

---

# 6.3 Grafana Alert -> Alertmanager 연동

Grafana는 자체 Alerting 시스템을 가지고 있으며,  
Netauto는 Prometheus Alertmanager와 통합되도록 구성하였다.

---

## 6.3.1 Grafana Contact Point (Alertmanager)
```yaml
apiVersion: 1
deleteContactPoints: []
contactPoints:
  - orgId: 1
    name: alertmanager-default
    receivers:
      - uid: alertmanager-default
        type: prometheus-alertmanager
        settings:
          url: http://alertmanager:9093
```

## 6.3.2 Grafana Routing Policy
```yaml
apiVersion: 1
policies:
  - orgId: 1
    receiver: alertmanager-default
    routes: []
```

## 6.3.3 Grafana Alert Rules
```yaml
apiVersion: 1
groups:
  - orgId: 1
    name: netauto-grafana
    folder: "Netauto Alerts"
    interval: 30s
    rules:
      - uid: ga_status_degraded
        title: NetautoStatusDegraded (Grafana)
        condition: A
        annotations:
          runbook_url: https://github.com/ghogho232/netauto/blob/main/docs/runbooks/status.md
        labels:
          severity: critical
          topo: ospf-mini
          env: dev

      - uid: ga_drift_detected
        title: NetautoDriftDetected (Grafana)
        condition: A
        labels:
          severity: warning
          topo: ospf-mini
          env: dev

      - uid: ga_tests_failing
        title: NetautoTestsFailing (Grafana)
        condition: A
        labels:
          severity: critical
          topo: ospf-mini
          env: dev
```

---

# 6.4 Netauto Alert Pipeline 요약 다이어그램

```
Prometheus Recording Rules
Prometheus Alert Rules
        ↓
Alertmanager (Grouping, Throttling)
        ↓
Slack Webhook (#netauto-ci)
        ↓
Grafana Alert Table (자동 표시)
```

---

# 6.5 이 구성을 통해 얻는 효과

### 운영 효율
- 하나의 Slack 채널에서 모든 장애, 상태, 드리프트, 테스트 실패를 즉시 확인  
- 로깅, 모니터링, 테스트, 구성관리 통합

### 빠른 장애 감지
- OSPF flap -> 30초 이내 감지  
- Drift -> 10초 내 감지  
- 테스트 실패 -> 1분 이내 감지  

### Runbook 기반 문제 해결 자동화
- 모든 Alert에 runbook_url 포함  
- 클릭 즉시 대응 문서 열람 가능

---



## 7. 전체 Observability 흐름

Netauto 환경에서는 **라우터/호스트 메트릭 수집 -> 시계열 저장/계산 -> 시각화 -> 알람 평가 -> 알람 집계/전달 -> Slack 알림**까지  
하나의 파이프라인으로 설계되어 있다. 이 흐름은 아래와 같이 요약할 수 있다

```text
[R1/R2/H1/H2 metrics export]
               |
               v
           Prometheus
               |
       Recording / Query
               |
               v
            Grafana
               |
        Alert Evaluation
               |
               v
         Alertmanager
               |
               v
             Slack
```


---

### 7.1 R1/R2/H1/H2 metrics export

Containerlab로 구성된 **R1, R2(라우터)** 와 **H1, H2(호스트)** 는 다음과 같은 형태로 메트릭을 노출한다.

- **FRRouting / OSPF 관련 메트릭**
  - OSPF Neighbor 상태, 라우팅 테이블 정보 등  
  - `netauto_neighbors{state="full" | "total"}` 같은 형태의 메트릭으로 집계

- **netauto-api `/metrics`**
  - Netauto 파이프라인의 상태를 표현하는 메트릭 제공
    - `netauto_status` (전체 Health OK/Degraded)
    - `netauto_drift_config` (드리프트 존재 여부)
    - `netauto_tests_count{type="passed|failed|total"}` (pytest 결과)
  - 내부적으로 `health.json`, `routes.json`, `drift.json`, 테스트 결과 등을 파싱해 지표로 변환

- **node-exporter**
  - 각 노드의 CPU, 메모리, 디스크, 네트워크 인터페이스 상태 등 시스템 리소스 메트릭 제공

이 단계에서 만들어진 **초기 메트릭**들이 이후 모든 관측(Observability)의 기초 데이터가 된다

---

### 7.2 Prometheus - 수집(scrape) 단계

**Prometheus**는 각 컨테이너에서 메트릭을 정기적으로 스크레이프한다

- `prometheus.yml`에 정의된 `scrape_configs`에 따라
  - `netauto-api:8000/metrics`
  - `node-exporter:9100/metrics`
  - FRR Exporter 등의 엔드포인트를 주기적으로 호출
- 수집된 메트릭은 Prometheus TSDB에 시계열 데이터로 저장된다.

이 레이어에서는 **있는 그대로의 메트릭** 을 모으는 역할에 집중하며,  
복잡한 비율 계산/집계는 다음 Recording Rule 단계에서 수행한다.

---

### 7.3 Recording / Query - 비율 계산 및 파생 메트릭 생성

Prometheus는 단순 저장만이 아니라 **Recording Rule**을 통해
자주 사용하는 계산 결과를 **새로운 메트릭**으로 저장한다.

Netauto에서는 다음과 같은 Recording Rule을 사용한다

- `netauto_neighbors_ratio`
  - `sum(netauto_neighbors{state="full"}) / sum(netauto_neighbors{state="total"})`
  - OSPF Neighbor 수용률(0~1)을 표현
  - `clamp_min`, `clamp_max`로 0~1 범위 고정 + 분모 0 방지

- `netauto_tests_pass_ratio`
  - `netauto_tests_count{type="passed"} / netauto_tests_count{type="total"}`
  - pytest 통과율(0~1)을 표현

이렇게 생성된 비율 메트릭은

- Grafana 패널에서 그대로 사용 가능
- Alert Rule의 조건식에서도 재사용 가능
- **중복 계산을 줄이고 표현을 단순하게 유지**하는 데 기여한다.

또한 PromQL을 이용해 수동으로 질의할 때도
`netauto_neighbors_ratio`, `netauto_tests_pass_ratio`를 그대로 사용하면 되므로
운영자가 상태를 빠르게 파악할 수 있다

---

### 7.4 Grafana - 시각화 및 1차 해석 단계

Prometheus가 데이터를 모으고 계산하고  
**Grafana는 이를 사람이 보기 쉬운 형태로 보여주는 역할**을 한다.

Netauto에서는 다음 구성을 사용한다

- **데이터소스**
  - `uid: prometheus` 로 Prometheus 인스턴스를 등록
  - `datasource.yml` 에 미리 정의하여 컨테이너 기동 시 자동 로드

- **대시보드**
  - `grafana/dashboards/netauto-health.json`
    - Overall Status, Config Drift, Neighbors Ratio, Routes Total, Tests 결과, Alert 테이블 등
  - `grafana/dashboards/netauto.json`
    - 최소한의 `/metrics` scrape 상태 확인용 간단 대시보드

- **패널 예시**
  - `netauto_status` 를 stat 패널로 표시 -> degraded / ok
  - `netauto_neighbors_ratio` 를 게이지로 표시 -> OSPF 상태 한눈에 파악
  - `netauto_tests_pass_ratio` 를 게이지로 표시 -> 회귀 테스트 품질 확인
  - `ALERTS{alertstate="firing"}` 를 테이블로 표시 -> 현재 firing 중인 Alert 목록 확인

이 레이어에서 운영자는 **대시보드만 보고도 “어디가 문제인지”** 를 직관적으로 이해할 수 있다

---

### 7.5 Grafana / Prometheus Alert Evaluation - 조건 평가 레이어

시각화만으로는 부족하므로 조건에 따라 **자동으로 Alert를 발생**시켜야 함

- **Prometheus Alert Rules (`prom/alert_rules.yml`)**
  - `NetautoStatusDegraded` -> `netauto_status == 0` 이 1분 이상
  - `NetautoDriftDetected` -> `netauto_drift_config > 0` 이 1분 이상
  - `NetautoTestsFailing` -> 실패 테스트 존재
  - `NetautoDegraded` -> 2분 이상 degraded 상태 지속
  - 각 Alert에는 `severity`, `runbook_url`, `summary`, `description` 레이블 부여

- **Grafana Alert Rules (`grafana/provisioning/alerting/rules.yml`)**
  - 대시보드 상의 패널 값을 기준으로 따로 Alert 정의
  - 예: `netauto_status == 0` 을 Grafana 내에서 별도 Alert로 평가 후 Alertmanager로 전송

이 단계까지가 **Alert가 firing인지 resolved인지 판단하는 로직**이며,  
실제 알림 전송은 다음 단계인 Alertmanager가 담당한다.

---

### 7.6 Alertmanager - 알람 집계 및 라우팅

Prometheus / Grafana에서 발생한 Alert는 모두 **Alertmanager**로 전달된다.

- `prom/alertmanager.yml` 에서 다음을 설정:
  - `group_by: ['alertname','instance','severity']`
    - 같은 유형의 Alert를 하나의 묶음으로 Slack에 전송
  - `group_wait: 15s`, `group_interval: 2m`, `repeat_interval: 1h`
    - 너무 잦은 알림을 방지하고, 일정 간격으로 리마인드
  - `receivers.slack.slack_configs`
    - `/run/secrets/slack_webhook_url` 을 통해 Slack Webhook URL 주입
    - `channel: "#netauto-ci"` 로 모든 Netauto 알람이 모이는 채널 지정
    - 템플릿을 이용해 Alert, Instance, Severity, Summary, Description, Runbook URL 등을 메세지에 포함

또한 Grafana Alert도 `prometheus-alertmanager` 타입 Contact Point를 통해  
같은 Alertmanager 인스턴스로 전달되므로  
**Prometheus Alert와 Grafana Alert가 모두 한 곳으로 모이게 된다.**

---

### 7.7 Slack - 운영자 시점

마지막 단계는 **Slack 채널**이다

- 채널: `#netauto-ci`
- Alertmanager에서 템플릿으로 생성한 메시지에는:
  - Alert 이름 (예: `NetautoDriftDetected`)
  - Status (firing / resolved)
  - 대상 인스턴스 (r1, r2, netauto-api 등)
  - 심각도(severity)
  - 요약(summary) 및 상세 설명(description)
  - Runbook 링크(runbook_url)
  - 전체 Labels 덤프
- 운영자는 이 채널만 주기적으로 확인하면,
  - OSPF Neighbor Down
  - Config Drift 발생
  - 테스트 실패
  - Health Degraded
  - Grafana 기준 Alert
  를 모두 한 눈에 파악할 수 있다

또한 메시지에 포함된 **Runbook 링크**를 통해 
각 Alert에 대응하는 트러블슈팅 문서로 바로 이동할 수 있어  
장애 대응 시간을 크게 단축할 수 있다.

---

### 7.8 흐름 요약

Netauto의 Observability 흐름은 다음과 같이 요약된다.

1. **R1/R2/H1/H2** 에서 메트릭을 export한다.  
2. **Prometheus** 가 이를 스크레이프하고, Recording Rule로 비율/상태 값을 계산한다.  
3. **Grafana** 가 대시보드로 시각화하고, 일부 패널은 자체 Alert Rule로 상태를 평가한다.  
4. **Alertmanager** 가 Prometheus/Grafana로부터 Alert를 수신, 그룹핑, 슬로틀링 후 Slack으로 전달한다.  
5. **Slack** 에서 운영자가 모든 Alert를 한 번에 확인하고, Runbook을 통해 신속하게 대응한다.

이 구조로 Netauto는 **상태 수집 -> 가시화 -> 조건 판단 -> 알림 -> 대응**까지  
완전한 End-to-End Observability 구조를 갖추게 된다

## 8. TLS/HTTPS 인증서 트러블슈팅

Observability 구성 중 가장 까다로웠던 문제 중 하나는 Grafana HTTPS 적용 시 인증서 오류였다.

### 문제 1: Grafana가 인증서를 읽지 못함

```
GF_PATHS_DATA not writable
grafana.crt cannot be read
```

원인:

- Grafana 기본 실행 UID = 472
- /grafana/data 또는 /secrets/certs가 root 소유

해결:

```bash
sudo chown -R 472:472 grafana/data
sudo chown -R 472:472 secrets/certs
```

### 문제 2: 브라우저 TLS 인증서 오류

```
NET::ERR_CERT_AUTHORITY_INVALID
```

원인:

- localCA.crt가 Windows 신뢰 저장소에 등록되지 않음
- SAN 미포함 CSR로 인해 호스트 검증 실패

해결:

SAN 포함 CSR 생성:

```bash
openssl req -new -key grafana.key -out grafana.csr   -subj "/CN=grafana.local"   -addext "subjectAltName = DNS:grafana.local,IP:127.0.0.1"
```

localCA 등록  
Windows -> 인증서 관리자 -> "신뢰할 수 있는 루트 인증 기관"에 추가

### 문제 3: Alertmanager TLS 검증 실패

```
tls: failed to verify certificate
```

해결:

```yaml
tls_config:
  insecure_skip_verify: true
```

(테스트 환경 전용 옵션)

## 9. Observability 문제 상세 분석 및 해결 과정

Netauto Observability 구축 과정에서는 다양한 오류와 문제들이 발생했기에 해당 문제들을 현상 -> 원인 분석 -> 해결 -> 검증 흐름에 따라 정리했다

---

### 9.1 Prometheus 지표가 수집되지 않거나 빈 값으로 표시되는 문제

#### 문제 현상
- Prometheus UI에서 `netauto_*` metrics는 보이는데, Grafana 패널에서는 값이 비어 있음
- 특정 노드(r1, r2)의 neighbor ratio 값이 NaN 또는 0으로 고정됨
- FULL CI 에서 health snapshot이 항상 “unknown”으로 표시됨

#### 원인 분석
1. **Recording Rules가 정상적으로 로딩되지 않음**  
   - Prometheus는 규칙 파일 경로를 강하게 체크하며 잘못된 YAML 들여쓰기나 경로가 있으면 전체 파일을 무시한다
   - `groups.name` 또는 `rules.record` 필드 누락

2. **Exporter의 label 구성 문제**  
   - `netauto_node_neighbors{node="r1"}` 형태의 라벨이 없어서 Grafana panel templating이 실패
   - FastAPI metrics exporter에서 node 이름이 하드코딩되지 않음

3. **Grafana query syntax 오류**  
   - `$node` 변수가 templating에서 정상적으로 전달되지 않아 쿼리가 빈 상태로 평가됨
   - Prometheus recording rule의 이름 변경 후 Grafana 대시보드가 업데이트되지 않음

#### 해결 방법
- Recording Rules를 3개로 재정의:
  ```
  - record: netauto_neighbors_ratio
    expr: sum(netauto_neighbors{state="full"}) / sum(netauto_neighbors{state="total"})
  ```

- Exporter 코드에 node label 추가:
  ```python
  REGISTRY.register(Gauge("netauto_neighbors", "Neighbors", ["node","state"]))
  ```

- Grafana dashboard JSON에서 모든 query를 아래로 변경:
  ```
  netauto_neighbors_ratio{node="$node"}
  ```

#### 해결 효과
- 모든 노드의 neighbor 패널이 정상 표시
- OSPF convergence 상태가 실시간 모니터링 가능
- Slack 알람 트리거 시점이 정확해짐

---

### 9.2 Grafana HTTPS 인증서 오류 및 TLS 신뢰 문제

#### 문제 현상
- HTTPS 활성화 후 Grafana가 다음 오류로 기동되지 않음:
  - `GF_PATHS_DATA not writable`
  - `grafana.crt cannot be read`
- 브라우저에서는 “이 사이트는 안전하지 않음” 경고 발생.
- SAN 미설정으로 인해 NET::ERR_CERT_INVALID 발생.

#### 원인 분석
- Grafana 컨테이너 내부 사용자 UID는 472인데, 인증서 디렉토리는 root 소유.
- TLS 인증서 생성 시 SAN 필드를 넣지 않음.
- Windows에서는 로컬 CA를 “신뢰된 루트 인증 기관”에 등록하지 않음.

#### 해결 방법
1. 디렉토리 권한 변경:
   ```
   chown -R 472:472 grafana/data
   chown -R 472:472 secrets/certs
   ```

2. SAN 포함 CSR 재생성:
   ```
   openssl req -new -key grafana.key -out grafana.csr      -subj "/CN=grafana"      -addext "subjectAltName=DNS:grafana.local,DNS:localhost"
   ```

3. Windows 로컬 인증서 저장소에 CA 등록

#### 해결 효과
- HTTPS 기반 Grafana 정상 동작
- Self-signed 환경에서도 브라우저 경고 제거
- 운영환경 수준의 안전한 TLS 흐름 확보

---

### 9.3 Alertmanager -> Slack 알림이 도착하지 않는 문제

#### 문제 현상
- Prometheus alert는 firing 상태인데 Slack 메시지가 도착하지 않음
- Alertmanager 로그:
  ```
  level=error receiver=slack-default msg="failed to notify via slack" err="bad_webhook_url"
  ```

#### 원인 분석
- .env파일의 Webhook URL을 읽지 못함
- Alertmanager에 HTTP proxy 설정이 중첩되어 요청이 차단됨
- Slack payload 형식이 v2 규격에 맞지 않음

#### 해결 방법
- secret 파일에 Slack Webhook URL을 저장 후 참조
- Alertmanager config 에서 proxy 설정 제거
- Slack v2 API용 payload로 재작성:
  ```yaml
  send_resolved: true
  http_config:
    follow_redirects: true
  ```

#### 해결 효과
- Netauto FULL/LIGHT CI의 성공/실패가 Slack에 즉시 도착
- Drift, OSPF Down, Ping 실패 등의 실시간 탐지 성공

---

### 9.4 Prometheus Scrape 실패 문제

#### 문제 현상
- Prometheus UI에서 타겟 상태가 `DOWN` 으로 표시.
- FULL CI 중 health.json이 생성되지 않고 Python exporter가 응답하지 않음.

#### 원인 분석
- FastAPI exporter가 Docker network 상에서 잘못된 IP로 바인딩됨.
- exporter 포트가 이미 다른 프로세스에 의해 사용 중.
- GitHub Actions 환경에서는 외부 요청이 차단되므로 scrape 불가.

#### 해결 방법
- `--host 0.0.0.0` 로 강제 바인딩
- exporter 포트 8000 을 고정
- Prometheus config 에서 static_configs 수정

#### 해결 효과
- 안정적으로 health metric 수집
- pytest->Prometheus->Grafana->Alertmanager 전체 파이프라인이 유기적으로 연결됨

---

### 9.5 Grafana Dashboard 로딩 실패 또는 패널 렌더링 오류

#### 문제 현상
- 일부 패널이 “No Data” 또는 “Query Failed” 표시
- Dashboard Import 시 JSON 오류 발생

#### 원인 분석
- Dashboard JSON에서 query 이름이 오래된 recording rule 참조
- templating 변수가 panel에서 사용되지 않음

#### 해결 방법
- 모든 query를 최신 rule 이름으로 업데이트
- dashboard provisioning 을 자동화:
  ```
  grafana/provisions/dashboards/netauto.json
  ```

#### 해결 효과
- Dashboard 자동 구성 성공
- CI 실행 후 GitHub Pages의 report와 동일한 정보를 GUI에서 확인 가능

---

### 9.6 FastAPI Metrics Exporter 안정성 문제

#### 문제 현상
- metrics endpoint `/metrics` 가 502, 503을 간헐적으로 반환
- FULL CI 파이프라인이 랜덤 실패

#### 원인 분석
- docker container CPU bursting 시 uvicorn worker timeout 발생
- startup sequence에서 라우팅 테이블 수집보다 일찍 scrape 요청이 실행됨

#### 해결 방법
- Gunicorn + Uvicorn worker 모델로 변경
- readiness probe 구현
- scrape interval을 5s -> 15s로 증가

#### 해결 효과
- scrape 실패율 0% 달성
- Python exporter가 안정적으로 동작하여 전체 Observability 신뢰도 상승

---

## 요약

Observability 스택의 문제는 대부분 다음 세 가지에서 발생했다.

1. **구성요소 간의 label / recording rule / query 불일치**
2. **컨테이너 내부의 파일 권한 및 인증서(SAN/TLS) 문제**
3. **초기화 시점 race condition(Prometheus scrape vs exporter readiness)**

모든 항목은 재현 가능한 테스트 환경에서 검증했고  
Netauto Observability는 **운영환경 수준**의 안정성을 갖추게 되었다.


## 10. 결론

Netauto Observability는  
네트워크 상태 -> 메트릭 수집 -> 시각화 -> 검증 -> 알람  
전체 과정을 자동화한다.
