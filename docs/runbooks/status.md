# Runbook: Overall Status Degraded (`NetautoStatusDegraded`)

## Alert 정보
| 항목           | 값 |
|----------------|-----------------------------|
| **Alert Name** | NetautoStatusDegraded |
| **Trigger 조건** | `netauto_status == 0` (API `/health` 결과가 degraded) |
| **Severity**   | critical |
| **Source**     | netauto-api → Prometheus |

---

## 1. 문제 개요
Netauto 시스템의 `/health` 엔드포인트가 `{"status": "degraded"}` 상태를 반환할 때 발생
이는 일반적으로 테스트 실패, 드리프트 발생, 라우터 OSPF 문제 등의 종합 결과

---

## 2. 즉시 확인할 체크리스트

| 체크 항목 | 명령어 또는 위치 |
|-----------|--------------------|
| API 상태 확인 | `curl -s http://<IP>:8000/health` |
| OSPF Neighbor 상태 | `docker compose exec r1 vtysh -c "show ip ospf neighbor"` |
| Prometheus Alert 현황 | Grafana → Alerts → Firing Alerts |
| Config 드리프트 여부 | `docs/runbooks/drift.md` 참고 |
| 테스트 실패 여부 | `/docs/runbooks/tests.md` 참고 |

---

## 3. 해결 절차

1. **API `/health` 상태 상세 확인**
   ```bash
   curl -s http://localhost:8000/health | jq

