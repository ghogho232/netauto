# Netauto: NetDevOps 기반 E2E 네트워크 자동화 프로젝트

네트워크를 코드처럼 다루는 NetDevOps를 바탕으로 Netauto 프로젝트는 다음 전체 흐름을 모두 자동화를 목표로 함

- 컨테이너 기반 네트워크 랩 생성
- 라우터 및 호스트 설정 자동 배포
- 라우팅 및 연결성 자동 테스트
- 템플릿 대비 드리프트(구성 불일치) 감지
- 메트릭 기반 관측과 알림 구성
- GitHub Actions 기반 CI/CD 파이프라인
- Slack으로 결과 요약 및 알림 전송


---

## 1. 프로젝트 목표와 배경

### 1.1 전통적인 네트워크 운영의 문제점

기존의 수동 네트워크 운영 방식은 다음과 같은 구조적인 한계를 가집니다.

| 문제 | 설명 |
|------|--------|
| 수동 구성 | CLI로 직접 설정 → 오류 발생 및 재현성 부족 |
| 테스트 부재 | 변경 후 정상 동작을 보장할 자동 테스트 없음 |
| 드리프트 발생 | 템플릿/표준과 실제 네트워크의 불일치 |
| 관측 불가 | 모니터링·알람 구조 미흡 |
| CI/CD 미적용 | 코드 변경이 실 구성/테스트로 이어지지 않음 |

- 변경 이력이 남지 않아, 장애 발생 시 "누가 무엇을 바꿨는지"를 추적하기 어려움
- 테스트 없이 변경이 이루어져, 야간에 예기치 못한 서비스 장애가 발생
- 새로운 표준 구성(예: OSPF 정책, ACL 템플릿)을 적용해도, 실제 장비에 언제 반영되었는지 알 수 없음

### 1.2 Netauto가 지향점

Netauto는 다음과 같은 상태를 목표로 설계

1. 네트워크를 코드로 정의한다 (Infrastructure as Code)
2. 네트워크 변경은 항상 GitHub Pull Request로 시작된다
3. 변경이 발생하면 CI가 다음을 자동으로 수행한다
   - 구성 템플릿과 코드의 정합성 검증
   - 실제 Containerlab 기반 랩에서 라우터/호스트를 생성
   - Ansible로 구성을 배포
   - pytest로 엔드투엔드 테스트 시행
   - 드리프트 감지 및 리포트 생성
4. 모든 결과를 GitHub Pages와 Slack으로 투명하게 공개한다

"NetDevOps 파이프라인의 축소판"으로 실제 기업의 SRE, NetDevOps, 인프라 운영 팀의 방식을 최대한 모방

---

## 2. 전체 아키텍처

1. 소스 코드 및 설정 저장소: GitHub Repository
2. 랩 환경 생성: Containerlab
3. 구성 관리: Ansible
4. 동적 라우팅: FRRouting (FRR)
5. 네트워크 테스트: pytest
6. 상태 수집 및 보고: Python 스크립트
7. 관측 및 알림: Prometheus, Grafana, Alertmanager, Slack
8. CI/CD: GitHub Actions (LIGHT / FULL 파이프라인)

### 2.1 아키텍처 다이어그램 


```text
GitHub Repo
   |
   v
GitHub Actions (LIGHT / FULL)
   |
   +--> Containerlab Lab
   |        |
   |        +--> Ansible (site.yml)
   |        |        |
   |        |        +--> Router / Host 구성 적용
   |        |
   |        +--> pytest / Python 테스트 및 리포트
   |
   +--> Prometheus / Grafana / Alertmanager
   |
   +--> Slack Notifications
```


---

## 3. 네트워크 토폴로지

### 3.1 논리 구조

랩 토폴로지는 두 개의 FRR 라우터와 두 개의 Linux 호스트로 구성

```text
h1 (10.0.1.100/24)          h2 (10.0.2.100/24)
        |                           |
        |                           |
   r1 (FRR)  ---- 10.0.12.0/30 ---- r2 (FRR)
        |                           |
  LAN 10.0.1.0/24            LAN 10.0.2.0/24
```

- r1과 r2는 OSPF area 0으로 연결되어 있고 10.0.12.0/30 링크를 사용
- h1은 r1을 기본 게이트웨이로 사용하고 h2는 r2를 기본 게이트웨이로 사용
- OSPF를 통해 10.0.1.0/24와 10.0.2.0/24 네트워크가 상호 학습

---

## 4. 디렉터리 구조


```text
netauto/
  ansible/
    deploy_all.yml
    inventory.ini
    site.yml
    playbooks/
      backup.yml
      break_fix.yml
      configure_hosts.yml
      configure_routers_kernel.yml
      deploy_frr.yml
      verify.yml
    templates/
      frr.conf.j2
    group_vars/
      routers.yml
    host_vars/
      clab-netauto-h1.yml
      clab-netauto-h2.yml
      clab-netauto-r1.yml
      clab-netauto-r2.yml
  lab/
    netauto.clab.yml
    clab-netauto/
      ansible-inventory.yml
      topology-data.json
  python/
    api/
      health.py
      metrics.py
    collect_routes.py
    report.py
    validate.py
    utils/
      parsers.py
  tests/
    test_connectivity.py
    artifacts/
      junit.xml
  prom/
    prometheus.yml
    alert_rules.yml
  grafana/
    dashboards/
      netauto-health.json
    provisioning/
      datasources/
      dashboards/
      alerting/
  docs/
    report.md
    day1.md ~ day11.md
  .github/
    workflows/
      netauto.yml
      validate-observability.yml
```

각 디렉터리는 다음 역할을 담당합니다.

- `ansible/` : 라우터와 호스트를 자동화하는 모든 플레이북과 템플릿
- `lab/` : Containerlab 토폴로지 정의 및 생성된 데이터
- `python/` : 드리프트 감지, 라우팅 테이블 수집, 리포트 생성, 메트릭 exporter
- `tests/` : pytest 기반 네트워크 테스트
- `prom/`, `grafana/` : 관측 및 대시보드 정의
- `docs/` : 자동 생성 리포트와 일자별 진행 기록
- `.github/workflows/` : GitHub Actions CI/CD 정의

---

## 5. 구성 요소 상세 설명

### 5.1 Containerlab – 네트워크 생성

lab/netauto.clab.yml 사용하여 다음을 생성

- FRR 라우터 2대 (r1, r2)
- Linux host 2대 (h1, h2)
- 인터페이스/케이블/브리지 자동 배치

### 5.2 Ansible – 구성 배포 + 검증

site.yml 구성

- 라우터 인터페이스 IP 설정
- IPv4 forwarding enable
- FRR 설정 템플릿 렌더링
- vtysh -b로 구성 반영
- host의 IP / default route 설정
- OSPF neighbor + route 검증
- End-to-End ping 테스트

verify.yml 주요 검증

- OSPF neighbor(Full) 개수
- 라우팅 테이블 정상 확인
- r1 ↔ r2 OSPF Hello/Dead 확인
- h1 → h2 ping 성공 여부

### 5.3 Python 스크립트 – 수집·검증·리포트
validate.py — 드리프트 감지

- 템플릿 vs 실제 running-config 비교
- JSON diff 생성
- drift count 출력

collect_routes.py — 상태 수집

- vtysh show ip route
- vtysh show ip ospf neighbor
- routes.json, neighbors.json 저장

report.py — Markdown 생성

- 라우팅 테이블 요약
- OSPF neighbor 요약
- 테스트 결과
- drift 결과
- Prometheus snapshot
docs/report.md로 저장 → GitHub Pages 자동 배포

### 5.4 pytest – 네트워크 테스트 자동화

| 테스트                          | 설명                             |
| ------------------------------ | ---------------------------------|
| test_vtysh_available           | vtysh 정상 실행 여부              |
| test_ping_h1_to_h2             | h1 → h2 ping 성공                |
| test_ospf_neighbors_full       | neighbor Full 여부               |
| test_r1_has_ospf_route_to_h2   | r1 → 10.0.2.0/24 OSPF route 존재 |
| test_r2_has_ospf_route_to_h1   | r2 → 10.0.1.0/24 OSPF route 존재 |
| test_no_drift_against_template | drift=0 확인                     |


### 5.5 Observability – Prometheus/Grafana/Alertmanager
Prometheus

- 라우터/호스트/Netauto FastAPI exporter scrape
- OSPF 상태/route count
- recording rules

Grafana

- 자동 dashboard provisioning
- OSPF neighbor health, drift, ICMP RTT 시각화

Alertmanager

- Slack 알람
- severity, team 기반 라우팅
---

## 6. GitHub Actions CI/CD 파이프라인

Netauto는 2개의 CI 파이프라인으로 구성된다.

---
### 6.1 LIGHT CI (빠른 논리 테스트)
---
실 Containerlab 없이 수행하는 빠른 파이프라인

| 단계              | 설명                  |
| --------------- | ------------------- |
| Python lint     | 코드 정적 분석            |
| pytest(lite)    | 논리 테스트              |
| drift check     | 템플릿 정합성 검사          |
| report 생성       | docs/report.md 업데이트 |
| GitHub Pages 배포 | report 자동 배포        |
| Slack 알림        | 결과 요약 발송            |

---
### 6.2 FULL CI (실제 Lab 자동 생성 + E2E 검증)
---
| 단계                   | 설명                         |
| -------------------- | -------------------------- |
| containerlab deploy  | 네트워크 생성                    |
| ansible site.yml     | 구성 자동 배포                   |
| pytest(full)         | E2E 네트워크 테스트               |
| drift detection      | template vs running-config |
| collect_routes       | 라우팅/네이버 수집                 |
| report               | Markdown 생성                |
| containerlab destroy | lab 자동 정리                  |
| GitHub Pages 배포      | 최신 리포트 배포                  |
| Slack 알림             | FULL 결과 전송                 |

### 6.3 Slack 알림

`notify` 잡은 LIGHT와 FULL 잡의 결과를 바탕으로 Slack에 정보 전송

- 브랜치 이름
- 커밋 SHA
- pytest 결과 (Passed / Failed / Skipped 수)
- 드리프트 상태
- 최신 리포트 링크 (GitHub Pages URL)

색상으로 성공/실패를 구분하여 CI 상태를 확인할 수 있도록 구성함

---

## 7. 로컬 실행 방법

### 7.1 전체 플로우 실행

1. 랩 생성

```bash
containerlab deploy -t lab/netauto.clab.yml
```

2. 구성 배포

```bash
cd ansible
ansible-playbook -i inventory.ini site.yml
cd ..
```

3. 테스트 실행

```bash
pytest -q
```

4. 리포트 생성

```bash
python python/collect_routes.py
python python/validate.py
python python/report.py
```

5. 랩 삭제

```bash
containerlab destroy -t lab/netauto.clab.yml -c
```

---

## 8. 자동 생성 리포트 예시 (docs/report.md)

리포트는 다음 정보를 포함함

- Topology 설명
- pytest 결과 요약
- drift 결과
- routes / neighbor 요약
- Prometheus metric snapshot
- CI job metadata
- 생성 시간

예
```yaml
Pytest Results: Passed: 6 Failed: 0 Skip: 0
Drift: 0
OSPF Neighbors:
 - r1: 1 Full neighbor
 - r2: 1 Full neighbor
Routes:
 - r1 → 10.0.2.0/24 OK
 - r2 → 10.0.1.0/24 OK
Report generated: 2025-11-12 16:00
```
---

## 9. 장애 대응 (Runbook)
| 증상 | 원인 | 해결 |
|------|----------|-----------|
| OSPF 이웃이 Full 상태가 되지 않음 | 인터페이스 IP 또는 OSPF 설정 불일치, 수렴 시간 부족 | `verify.yml`의 pause 시간을 늘리고, `show ip ospf neighbor` 출력 분석 |
| h1 → h2 ping 실패 | 기본 라우트 미설정, OSPF 경로 미학습 | 호스트 관련 플레이북(`configure_hosts.yml`)과 라우팅 테이블을 확인 |
| 드리프트 발생 | 수동으로 장비 설정이 변경되었거나 템플릿 outdated | `validate.py` diff 결과를 보고 템플릿 또는 실제 구성을 정리 |
| GitHub Actions FULL 실패 | Docker 권한, containerlab 설치 문제 | RUNNER에서 `sudo` 사용 여부, 설치 스크립트 로그 확인 |
| Prometheus가 메트릭을 스크레이프하지 못함 | exporter 서비스 다운, 포트 변경 | FastAPI 서버 상태 확인, `prometheus.yml` 타겟 재검증 |


---

## 10. 이 프로젝트로 배울 수 있었던 것

- Containerlab을 사용한 재현 가능한 네트워크 랩 구성 방법
- Ansible을 이용한 라우터 및 호스트 구성 자동화
- pytest를 통한 네트워크 동작 검증 패턴
- 드리프트 감지 로직을 설계하고 CI와 연계하는 방법
- Prometheus와 Grafana를 사용한 네트워크 관측 가능성 확보
- GitHub Actions를 이용한 네트워크 CI/CD 파이프라인 구현
- Slack과 연동된 ChatOps 스타일의 운영 체계

---
