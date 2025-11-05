# Runbook: Config Drift (`NetautoDriftDetected`)

## Alert 정보
| 항목           | 값 |
|----------------|-----------------------------|
| Alert Name     | NetautoDriftDetected |
| Trigger 조건   | `netauto_drift_config > 0` |
| Severity       | warning |
| 원인           | 장비의 실제 설정과 Ansible 템플릿이 불일치 |

---

## 1. 드리프트 확인 방법

| 항목 | 명령어 |
|------|--------|
| 드리프트 메트릭 | `curl -s http://localhost:8000/metrics | grep netauto_drift` |
| 라우터 실제 설정 백업 확인 | `cat backups/r1/frr.conf` |
| Ansible 템플릿과 비교 | `ansible/roles/frr/templates/frr.conf.j2` |

---

## 2. 해결 절차

1. **실제 설정 백업 최신화**
   ```bash
   ansible-playbook playbooks/backup_frr.yml
