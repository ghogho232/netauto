# Day 9 — OSPF Per-Node Monitoring & Recording Rules 완성

## 1) 오늘의 목표
- Prometheus Recording Rules 로 비율 계산을 캐싱하여 대시보드 응답 속도 향상  
- Per-node OSPF 상태 (`netauto_node_neighbors`, `netauto_node_routes`) 패널 완성  
- 노드 별 Neighbor 비율, Route 수, Full/Total 그래프 추가  
- Slack 알림 정상 동작 및 DNS 불안정 이슈 해결  
- 전체 Observability 스택 안정화

---

## 2) 오늘의 활동 요약

###  Prometheus Recording Rules 설정
- `prom/alert_rules.yml`에 **Recording Rule 그룹 `netauto-recording`**을 신설했다.  
  Prometheus는 원래 쿼리 시마다 계산을 수행하지만 Recording Rule을 등록하면 **자주 사용하는 계산식의 결과를 미리 저장**해둬서 대시보드 로딩 속도를 개선할 수 있다.  

- 다음 3개의 지표를 캐싱하도록 설계했다.
  1. **전체 OSPF 이웃 비율 (`netauto_neighbors_ratio`)**  
     - 모든 노드의 `state="full"` 이웃 수를 `total`로 나눈 값.  
     - `clamp_min`, `clamp_max`를 사용해 0~1 사이 값으로 제한함으로써 division by zero나 이상치 방지
  2. **노드별 이웃 비율 (`netauto_node_neighbors_ratio`)**  
     - 각 노드(`node` label 기준)별 `full/total` 비율
     - `ignoring(state)`로 동일 노드 내 상태 비교가 가능하도록 조정
  3. **테스트 통과율 (`netauto_tests_pass_ratio`)**  
     - `passed/total`을 실시간 계산하는 대신 미리 기록
     - Alert Rule과 Gauge 패널에서 바로 활용 가능

  ```yaml
  groups:
    - name: netauto-recording
      rules:
        - record: netauto_neighbors_ratio
          expr: clamp_max(clamp_min(sum(netauto_neighbors{state="full"}) /
            clamp_min(sum(netauto_neighbors{state="total"}),1),0),1)
        - record: netauto_node_neighbors_ratio
          expr: clamp_max(clamp_min(
            netauto_node_neighbors{state="full"} /
            ignoring(state) clamp_min(netauto_node_neighbors{state="total"},1),0),1)
        - record: netauto_tests_pass_ratio
          expr: clamp_max(clamp_min(
            netauto_tests_count{type="passed"} /
            ignoring(type) clamp_min(netauto_tests_count{type="total"},1),0),1)
  ```

>  **의의:**  
> Recording Rules는 쿼리 부하를 줄이고 Grafana의 `Stat`,`Gauge` 패널에서 즉시 응답이 가능하도록 하는 핵심 최적화

---

###  Grafana 대시보드(`netauto-health.json`) 개선
- **새로운 Per-node OSPF 섹션**을 추가했다.  
  각 노드별로 Neighbor 수, Routes 수를 시각화하여 네트워크 단위 관찰에서 장비 단위 관찰로 확장

  - **Stat 패널** : `netauto_node_neighbors{state="full"}`  
  - **Time Series 패널** : `netauto_node_neighbors_ratio{node=~".+"}`  
  - **Routes per Node** : `netauto_node_routes{node="$node"}`  
  - **템플릿 변수 `node`** 를 추가하여 사용자가 특정 노드만 필터링 가능하게 구현

> 예: `"templating": { "list": [{ "name": "node", "query": "label_values(netauto_node_neighbors, node)" }] }`


###  전체 컨테이너 정상 동작 검증
아래 3단계 검증으로 Prometheus → API → Grafana 연계가 정상임을 확인

1. **지표 노출 확인**
   ```bash
   curl -s 'http://localhost:9090/api/v1/query?query=netauto_info'
   ```
   → `env=dev`, `job=netauto-api`, `value=1` 출력 확인

2. **Scrape 타깃 상태**
   ```bash
   curl -s 'http://localhost:9090/api/v1/query?query=up{job="netauto-api"}'
   ```
   → `"value": "1"` 반환 → scrape 성공 상태

3. **Grafana 대시보드 로딩 상태**
   ```bash
   docker compose logs grafana | grep provision
   ```
   → `"Provisioned dashboard from file /var/lib/grafana/dashboards/netauto-health.json"` 로그 확인으로 정상 반영 검증 완료

## 3) 파일 구조 & 변경점
```
prom/
  alert_rules.yml           # Recording Rules 추가
  prometheus.yml            # scrape _configs 확인
grafana/
  dashboards/netauto-health.json  # Per-node 패널 추가
python/api/metrics.py        # netauto_node_* 지표 노출 확인
```

---

## 4) 대시보드 개선 내용
| 구분 | 패널명 | 쿼리 | 비고 |
|:--|:--|:--|:--|
| 새 추가 | Node Neighbor Full/Total | `netauto_node_neighbors{node="$node",state="full"}` / `total` | 노드 별 이웃 상태 |
| 새 추가 | Node Route Count | `netauto_node_routes{node="$node"}` | 라우팅 수 확인 |
| 비율 | Neighbors Full Ratio (5m avg) | `avg_over_time(netauto_neighbors_ratio[5m:])` | 전체 비율 |
| 비율 | Node 별 Neighbors Ratio | `netauto_node_neighbors_ratio{node=~".+"}` | 노드 단위 SLO |

---

## 5) 어려웠던 점 → 어떻게 극복했나
| 증상 | 원인 | 조치 |
|:--|:--|:--|
| 대시보드 로드 오류 (`invalid character "\"`) | JSONC 주석 남아 있음 | 주석 삭제 후 순수 JSON 유지 |
| Per-node 데이터 비표시 | `health.json` 에 `nodes` 항목 없음 | 테스트 후 `collect_routes.py` 실행으로 갱신 |

---

## 6) 오늘 배운 것
- **Recording Rules** 로 지속 쿼리 부하 감소  
- **Label templating** 으로 노드별 관측 단위 확립  
- **DNS Failover** 및 Slack 알림 재시도 로직 이해  
- Grafana 대시보드 변경을 버전 관리로 추적하는 방법

---

## 7) 결론
> Day 9에서는 **OSPF per-node metrics 시각화 및 recording rules 기반의 고성능 모니터링** 완성
> 지금의 netauto 스택은 **CI/CD → Metrics → Grafana → Alertmanager** 까지 연동된 상태

