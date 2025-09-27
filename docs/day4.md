# Day 4 — pytest로 네트워크 검증 자동화

## 1) 오늘의 목표

- 배포 후 네트워크가 정상 동작하는지 **pytest 기반 테스트**로 자동 검증한다.  
- 사람이 CLI로 확인하던 vtysh, ping, OSPF, 라우팅 등을 **테스트 코드화**한다.  
- 실패 시 자동으로 증거(JSON, Markdown 리포트)를 남겨 **관측 가능성(Observability)** 과 **재현성**을 강화한다.  

---

## 2) 오늘의 활동 요약

- `pytest.ini` 작성: 마커(smoke, routing), 로깅 옵션 추가  
- `conftest.py` 작성: Docker exec 헬퍼, retry 기능, 컨테이너 목록 픽스처, 실패 시 상태 수집 훅  
- `test_connectivity.py` 작성:  
  - `vtysh` 실행 확인  
  - h1 → h2 ping 확인  
  - OSPF 이웃 Full 상태 확인  
  - R1/R2 라우팅 테이블에서 기대 경로 및 넥스트홉 확인  
  - Day 3 드리프트 검증 스크립트 실행  
- `Makefile` 업데이트: `make smoke`, `make routing`, `make drift`, `make test` 실행 타겟 추가  
- pytest 실행 결과: 모든 테스트 통과  

---

## 3) 코드와 자세한 설명

### 3-1. pytest 설정: `pytest.ini`

```ini
[pytest]
addopts = -q
log_cli = true
log_cli_level = INFO
markers =
  smoke: 빠르게 돌아가는 핵심 검증
  routing: 라우팅/OSPF 검증
testpaths = tests
```

**설명**  
- `-q` 옵션으로 간단한 출력  
- CLI 로깅 활성화 → 실패 원인 즉시 확인 가능  
- `smoke`, `routing` 마커를 정의해 테스트 그룹화  

---

### 3-2. 공용 픽스처/헬퍼: `tests/conftest.py`

- `run`: shell 명령 실행 헬퍼  
- `docker_exec`: 컨테이너 내부에서 명령 실행  
- `retry`: 수렴 지연 고려한 재시도 헬퍼  
- `containers` 픽스처: r1, r2, h1, h2 컨테이너 이름 제공  
- `pytest_runtest_makereport`: 테스트 실패 시 자동으로 `collect_routes.py`, `report.py` 실행  

---

### 3-3. 실제 테스트: `tests/test_connectivity.py`

- `test_vtysh_available`: 각 라우터에서 `vtysh` 실행 가능 여부 확인  
- `test_ping_h1_to_h2`: h1 → h2 ping 성공 확인  
- `test_ospf_neighbors_full`: 라우터 OSPF 이웃 Full 상태 확인  
- `test_r1_has_ospf_route_to_h2`: R1 라우팅 테이블에 10.0.2.0/24 경로, 넥스트홉 10.0.12.2 확인  
- `test_r2_has_ospf_route_to_h1`: R2 라우팅 테이블에 10.0.1.0/24 경로, 넥스트홉 10.0.12.1 확인  
- `test_no_drift_against_template`: Day 3 `validate.py`를 실행해 드리프트 감지 결과 검증  

---

### 3-4. Makefile 실행 타겟

```make
test:
	. .venv/bin/activate && pytest -q
smoke:
	. .venv/bin/activate && pytest -q -m smoke
routing:
	. .venv/bin/activate && pytest -q -m routing
drift: backup
	python python/validate.py
```

**설명**  
- `make smoke`: 핵심 연결성만 빠르게 확인  
- `make routing`: 라우팅/OSPF 검증만 실행  
- `make test`: 전체 테스트 실행  
- `make drift`: 드리프트 검증 실행  

---

## 4) 실행 런북 (Runbook)

전제: Containerlab 토폴로지 구동, Ansible 배포 완료  

```bash
# smoke 테스트 (핵심만)
make smoke

# 라우팅/OSPF 검증
make routing

# 전체 테스트 실행
make test

# 드리프트 검증
make drift
```

**결과 해석**  
- PASS → 네트워크 정상  
- FAIL → `docs/report.md`, `python/out/routes.json` 확인하여 원인 분석  

---

## 5) 오늘 공부한 것

- pytest 마커(smoke, routing)로 테스트 그룹 분리하는 방법  
- conftest.py에서 픽스처와 헬퍼를 정의해 코드 중복 줄이는 방법  
- 실패 시 자동으로 상태 수집을 실행해 디버깅 시간을 줄이는 패턴  
- IaC → 상태 수집 → 테스트 자동화의 파이프라인 완성  

---

## 6) 보충하면 좋을 것 

- pytest JUnit XML 출력으로 CI 시스템(GitHub Actions) 연동  
- 보고서 상단에 요약 메트릭(예: OSPF 이웃 수, 라우팅 경로 수) 추가  
- 실패 시 Slack/Webhook 알림으로 운영 대응 속도 향상  
- BGP, 정책 기반 검증으로 테스트 커버리지 확장  

