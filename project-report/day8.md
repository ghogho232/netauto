# Day 8 — Prometheus·Alertmanager·Grafana 연동 + Health 대시보드 완성

## 1) 오늘의 목표
- Prometheus 스크레이프/알람 구성 및 Alertmanager Slack 통합 마무리  
- Grafana 데이터소스 자동 프로비저닝 + 대시보드 자동 배포  
- Netauto용 종합 헬스 대시보드(Neighbors/Routes/Tests/Alerts) 구축  

## 2) 오늘의 활동 요약
###  Alertmanager
- Slack webhook → docker-compose secrets로 정의 → Alertmanager에서 참조하도록 정리  

###  Prometheus
- `prom/prometheus.yml`에 scrape 대상 추가 (Prometheus, Node Exporter, Netauto API 등)  
- `prom/alert_rules.yml`에 Netauto 관련 Alerts 정의 (예: OSPF 다운, HighNetworkErrors 등)  

###  Grafana
- `grafana/provisioning/datasource/datasource.yml` → `uid: "prometheus"`로 고정  
- `grafana/provisioning/dashboards/dashboard.yml` → 폴더 자동 프로비저닝  
- `grafana/dashboards/netauto.json` (기본) + `netauto-health.json` (확장판) 구성  
- 모든 패널에서 **${DS_PROMETHEUS} 제거 → uid="prometheus”**로 통일  

###  산출물 정리
| 파일 | 설명 |
|------|------|
| `docs/grafana-netauto-health-spec.jsonc` | 대시보드 JSON + 주석 명세 |
| `docs/health.json` | Day 7 Health API 결과 샘플 |
| `docs/report.md` | 자동 리포트 (pytest + routes 결과) |

---

## 3) 코드와 자세한 설명

### 3-1. Alertmanager: v2 API & Slack Secret 연결

####  경고 원인
`POST /api/v1/alerts` 사용 시:  
> “v1 API removed, use /api/v2/alerts”

####  해결 방법: v2 API 사용
```bash
curl -H "Content-Type: application/json"   -d '[{"labels":{"alertname":"TestAlert1","severity":"warning"}}]'   http://localhost:9093/api/v2/alerts
```

####  docker-compose + secrets
```yaml
services:
  alertmanager:
    image: prom/alertmanager
    volumes:
      - ./prom/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    secrets:
      - slack_webhook_url

secrets:
  slack_webhook_url:
    file: .secrets/slack_webhook_url
```

---

### 3-2. Prometheus: 스크레이프 & Alert Rules

####  `prom/prometheus.yml`
```yaml
scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['prometheus:9090']

  - job_name: 'netauto-api'
    static_configs:
      - targets: ['netauto-api:8080']   # /metrics 지원 시

rule_files:
  - 'alert_rules.yml'
```

####  `prom/alert_rules.yml` 예시
```yaml
groups:
  - name: netauto-rules
    rules:
      - alert: NetautoStatusDegraded
        expr: netauto_status == 0
        labels:
          severity: warning
        annotations:
          description: "Netauto Health API returned degraded"
          runbook_url: "https://your.wiki/runbooks/netauto"
```

---

### 3-3. Grafana: Datasource + Dashboard 자동화

####  datasource.yml
```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    uid: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
```

####  dashboard.yml
```yaml
apiVersion: 1
providers:
  - name: 'netauto'
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

---

### 3-4. Netauto Health Dashboard 주요 쿼리

| 항목 | PromQL |
|------|--------|
| 전체 상태 | `netauto_status` (0=degraded, 1=ok) |
| Drift 감지 | `netauto_drift_config` |
| Full 이웃 비율 | `sum(netauto_neighbors{state="full"}) / sum(netauto_neighbors{state="total"})` |
| 라우팅 수 | `netauto_routes_total` |
| Pytest 결과 | `netauto_tests_count{type="passed|failed"}` |
| Firing Alerts 개수 | `sum(ALERTS{alertstate="firing"})` |

---

## 4) 어려웠던 점 → 해결 방법

| 문제 | 원인 | 해결 |
|------|------|------|
| Grafana “Datasource not found” | ${DS_PROMETHEUS} 남아있음 | uid를 `"prometheus"`로 전체 수정 |
| Alertmanager v1 API 제거 | 최신 버전에서 `/api/v1` 삭제 | `/api/v2/alerts` 사용 |
| Slack webhook undefined | compose secrets 누락 | `.secrets/slack_webhook_url` 추가 |
| Grafana DB locked | sqlite 초기화 중 잠김 | 재기동으로 자동 복구됨 |

---

## 5) 실행 런북 (Runbook)

```bash
# 0) 컨테이너 재기동
docker compose down
docker compose up -d --force-recreate

# 1) Prometheus 확인
open http://<host>:9090/targets

# 2) Alertmanager 테스트 (v2 API)
curl -H "Content-Type: application/json"   -d '[{"labels":{"alertname":"TestAlert","severity":"warning"}}]'   http://<host>:9093/api/v2/alerts

# 3) Grafana 접속
open http://<host>:3000

# Dashboards:
#    Netauto (기본)
#    Netauto — Health & Observability (uid: prometheus)
```

---

## 6) 오늘 공부한 것
- Grafana 프로비저닝 구조(datasource + dashboards)  
- Prometheus Alert → Alertmanager Slack 연동 파이프라인  
- Health API + Prometheus + Grafana 연동 패턴  
- Observability = “코드 + 메트릭 + 알람 + 시각화”의 통합  

---

## 7) 다음에 할 것
| 개선 | 설명 |
|------|------|
| `/metrics` 제공 | Health API → Prometheus 직접 스크레이프 |
| 대시보드 확장 | BGP, 인터페이스 에러율 등 추가 |
| Slack Routing 고도화 | severity/oncall팀 기반 분리 |
| Public Dashboard | Grafana 공유(읽기 전용 URL 생성) |

---

 **정리**  
**Day 8에서 Prometheus → Alertmanager → Grafana까지 관측 스택이 완성되었다.**  
대시보드와 알람, Health API가 하나의 흐름으로 연결되며  
실제 운영 환경에 가까운 Netauto Observability 구조가 구축되었다.

