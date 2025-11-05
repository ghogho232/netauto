# Runbook: Pytest Failures (`NetautoTestsFailing`)

## Alert 정보
| 항목           | 값 |
|----------------|-----------------------------|
| Alert Name     | NetautoTestsFailing |
| Trigger 조건   | `netauto_tests_count{type="failed"} > 0` |
| Severity       | critical |
| 원인           | pytest 기반 테스트 실패 발생 |

---

## 1. 테스트 상태 확인

| 항목 | 명령어 |
|------|--------|
| 실패 테스트 확인 | `pytest -q` 또는 `pytest tests/ -vv` |
| Grafana 메트릭 | `netauto_tests_count{type="failed"}` |
| Slack 알림 | #netauto-ci 채널 확인 |

---

## 2. 해결 절차

1. **실패 테스트 상세 확인**
   ```bash
   pytest -vv --maxfail=1

